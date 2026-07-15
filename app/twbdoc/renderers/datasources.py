"""データソースと前処理章のレンダリング。

リレーションシップは Mermaid の erDiagram、結合・ユニオンはテーブルで表現する。
"""

from __future__ import annotations

import re

from ..model import Datasource, Relation, Workbook
from ..sampler import SampleResult, find_values
from .filters import describe_filter, filter_kind, filter_target
from .tables import table as _table

CONNECTION_CLASS_LABELS = {
    "excel-direct": "Excel",
    "textscan": "テキストファイル (CSV 等)",
    "federated": "複数接続 (federated)",
    "hyper": "抽出 (Hyper)",
    "sqlserver": "SQL Server",
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "oracle": "Oracle",
    "snowflake": "Snowflake",
    "bigquery": "Google BigQuery",
    "redshift": "Amazon Redshift",
}

JOIN_TYPE_LABELS = {
    "left": "左外部結合",
    "right": "右外部結合",
    "inner": "内部結合",
    "full": "完全外部結合",
}

SEMANTIC_ROLE_LABELS = {
    "Country": "国/地域",
    "State": "都道府県/州",
    "City": "市区町村",
    "ZipCode": "郵便番号",
    "County": "郡",
    "Airport": "空港",
}

DATA_MODEL_LEGEND = (
    "凡例: 枠 = 論理テーブル / 枠同士の点線 = リレーションシップ (ラベルは条件。"
    "Tableau のリレーションシップは結合方法を固定せず、分析内容に応じて自動決定されます) / "
    "枠内の実線 = 結合 (ラベルは結合種別と条件) / 内側の枠 = ユニオン / "
    "「キー:」 = リレーションシップで使用するキー項目"
)


def render_datasources_prep(
    workbook: Workbook,
    caption_map: dict[str, str],
    number: int = 2,
    field_list_anchors: dict[str, str] | None = None,
) -> list[str]:
    """データソースと前処理章。

    field_list_anchors: データソース内部名 -> 巻末フィールド一覧節のアンカー。
    渡された場合はデータモデル図の直下にリンクを併記する。
    """
    lines = [f"## {number}. データソースと前処理", ""]
    if not workbook.datasources:
        lines.extend(["(該当なし)", ""])
        return lines
    anchors = field_list_anchors or {}
    for index, datasource in enumerate(workbook.datasources, start=1):
        lines.extend(
            _render_datasource(
                datasource,
                caption_map,
                f"{number}.{index}",
                anchors.get(datasource.name, ""),
            )
        )
    return lines


def _render_datasource(
    datasource: Datasource,
    caption_map: dict[str, str],
    number: str,
    field_list_anchor: str,
) -> list[str]:
    lines = [f"### {number} {datasource.display_name}", ""]
    lines.extend(_render_basic_info(datasource))
    lines.extend(_render_connections(datasource))
    lines.extend(_render_data_model(datasource, field_list_anchor))
    lines.extend(_render_relationship_table(datasource))
    lines.extend(_render_joins(datasource))
    lines.extend(_render_unions(datasource))
    lines.extend(_render_field_changes(datasource))
    lines.extend(
        _render_filter_table(
            "データソースフィルタ", datasource.ds_filters, caption_map
        )
    )
    if datasource.extract is not None:
        lines.extend(
            _render_filter_table(
                "抽出フィルタ", datasource.extract.filters, caption_map
            )
        )
    return lines


def _render_basic_info(datasource: Datasource) -> list[str]:
    rows = [
        ("名前", datasource.display_name),
        (
            "接続種別",
            CONNECTION_CLASS_LABELS.get(
                datasource.connection_class,
                datasource.connection_class or "-",
            ),
        ),
        ("接続方式", _describe_extract(datasource)),
    ]
    return _table(("項目", "値"), rows)


def _describe_extract(datasource: Datasource) -> str:
    extract = datasource.extract
    if extract is None or not extract.enabled:
        return "ライブ接続"
    if extract.row_limit:
        return f"抽出 (行数制限: {extract.row_limit} 行)"
    return "抽出 (全件)"


def _render_connections(datasource: Datasource) -> list[str]:
    if not datasource.connections:
        return []
    rows = [
        (
            connection.caption or connection.name or "-",
            CONNECTION_CLASS_LABELS.get(
                connection.conn_class, connection.conn_class or "-"
            ),
            connection.source or "-",
        )
        for connection in datasource.connections
    ]
    return ["#### 接続", ""] + _table(("接続名", "種別", "接続先"), rows)


def _render_relationship_table(datasource: Datasource) -> list[str]:
    """リレーションシップの条件テーブル。"""
    if not datasource.relationships:
        return []
    rows = [
        (
            relationship.first_table,
            relationship.expression,
            relationship.second_table,
        )
        for relationship in datasource.relationships
    ]
    return ["#### リレーションシップ", ""] + _table(
        ("テーブル 1", "条件", "テーブル 2"), rows
    )


def _render_data_model(
    datasource: Datasource, field_list_anchor: str = ""
) -> list[str]:
    """データモデル図 (リレーションシップ・結合・ユニオンを 1 枚の flowchart で表現)。

    - 論理テーブル = subgraph の枠 (リレーションシップのキー項目を枠内に表示)
    - リレーションシップ = 枠同士を結ぶ点線 (カーディナリティは XML に記録されないため表記しない)
    - 結合 = 枠内の実線 / ユニオン = 内側の枠
    """
    union_map = _union_map(datasource)
    keys = _entity_keys(datasource)
    tables = {table.caption: table for table in datasource.logical_tables}
    counter = {"node": 0, "sub": 0}
    body: list[str] = []
    sub_ids: dict[str, str] = {}

    for logical_table in datasource.logical_tables:
        sub_id = f"lt{counter['sub']}"
        counter["sub"] += 1
        sub_ids[logical_table.caption] = sub_id
        body.append(f'    subgraph {sub_id} ["{_escape_label(logical_table.caption)}"]')
        if logical_table.relation is not None:
            _emit_relation(logical_table.relation, body, counter, indent="        ")
        key_label = _key_node_label(
            keys.get(logical_table.caption, []), tables.get(logical_table.caption)
        )
        if key_label:
            key_id = f"k{counter['node']}"
            counter["node"] += 1
            body.append(f'        {key_id}[/"{key_label}"/]')
        body.append("    end")

    for relationship in datasource.relationships:
        first = sub_ids.get(relationship.first_table)
        second = sub_ids.get(relationship.second_table)
        if first is None or second is None:
            continue
        label = _escape_label(relationship.expression) or "関連"
        body.append(f'    {first} -. "{label}" .- {second}')

    if datasource.relation is not None:
        if not datasource.logical_tables:
            if not _has_join_or_union(datasource.relation):
                return []
            _emit_relation(datasource.relation, body, counter, indent="    ")
        else:
            # 論理テーブルに属さないユニオン (物理層のみに現れるもの) も描画する
            covered = {
                union.name
                for logical_table in datasource.logical_tables
                if logical_table.relation is not None
                for union in _collect_unions(logical_table.relation)
            }
            for union in _collect_unions(datasource.relation):
                if union.name not in covered:
                    _emit_relation(union, body, counter, indent="    ")

    if not body:
        return []
    lines = ["#### データモデル図", "", "```mermaid", "flowchart LR"]
    lines.extend(body)
    lines.extend(["```", "", DATA_MODEL_LEGEND, ""])
    for caption, unions in union_map.items():
        for union in unions:
            members = ", ".join(_collect_table_names(union))
            lines.append(
                f"- 「{caption}」はユニオン「{union.name}」({members}) で構成されています"
            )
    if field_list_anchor:
        lines.append(
            f"- 各テーブルの全フィールドは"
            f" [テーブル別フィールド一覧](#{field_list_anchor}) を参照"
        )
    if union_map or field_list_anchor:
        lines.append("")
    return lines


def _key_node_label(keys: list[str], table) -> str:
    """枠内に表示するキー項目ノードのラベル (型付き)。"""
    if not keys:
        return ""
    parts = [f"{key} ({_key_datatype(table, key)})" for key in keys]
    return _escape_label("キー: " + "<br>".join(parts))


def _entity_keys(datasource: Datasource) -> dict[str, list[str]]:
    """論理テーブルごとのリレーションシップキー式 (出現順・重複なし)。"""
    keys: dict[str, list[str]] = {}
    for relationship in datasource.relationships:
        for caption, key in (
            (relationship.first_table, relationship.first_key),
            (relationship.second_table, relationship.second_key),
        ):
            if not caption or not key:
                continue
            entry = keys.setdefault(caption, [])
            if key not in entry:
                entry.append(key)
    return keys


def _key_datatype(table, key: str) -> str:
    """キー式に対応するフィールドの型を論理テーブルの列定義から引く。"""
    if table is None:
        return "field"
    base = re.sub(r"\s*\([^)]*\)$", "", key)
    for column in table.columns:
        if column.name in (key, base):
            return column.datatype or "field"
    return "field"


def field_list_datasources(workbook: Workbook) -> tuple[Datasource, ...]:
    """巻末フィールド一覧に節が生成されるデータソース (出現順)。

    render_field_list_chapter の節構成と一致させることで、
    データモデル図からのアンカーリンクの計算に使える。
    """
    return tuple(
        datasource
        for datasource in workbook.datasources
        if any(table.columns for table in datasource.logical_tables)
        or datasource.metadata_columns
    )


def render_field_list_chapter(
    workbook: Workbook,
    samples: SampleResult | None = None,
    number: int = 12,
) -> list[str]:
    """テーブル別フィールド一覧章 (参考)。設計書の巻末に全フィールドを別掲する。

    samples が渡された場合は「サンプル値 (代表値)」列を追加する。
    """
    lines = [f"## {number}. テーブル別フィールド一覧 (参考)", ""]
    headers: tuple[str, ...] = ("論理テーブル", "物理テーブル", "フィールド", "型")
    if samples is not None:
        headers = headers + ("サンプル値 (代表値)",)
    sections: list[list[str]] = []
    for datasource in field_list_datasources(workbook):
        rows = [
            _field_list_row(logical_table, column, samples)
            for logical_table in datasource.logical_tables
            for column in logical_table.columns
        ]
        if not rows:
            # object-graph からフィールドが取れない形式では metadata-record を使う
            rows = [
                _metadata_field_row(column, samples)
                for column in datasource.metadata_columns
            ]
        sections.append(
            [
                f"### {number}.{len(sections) + 1} {datasource.display_name}",
                "",
            ]
            + _table(headers, rows)
        )
    if not sections:
        lines.extend(["(該当なし)", ""])
        return lines
    for section in sections:
        lines.extend(section)
    if samples is not None and samples.notes:
        lines.extend(f"※ {note}" for note in samples.notes)
        lines.append("")
    return lines


def _metadata_field_row(
    column, samples: SampleResult | None
) -> tuple[str, ...]:
    row = (
        column.table or "-",
        column.table or "-",
        column.name,
        column.datatype or "-",
    )
    if samples is None:
        return row
    values = find_values(samples, "", column.name)
    return row + (", ".join(values) if values else "(取得不可)",)


def _field_list_row(
    logical_table, column, samples: SampleResult | None
) -> tuple[str, ...]:
    row = (
        logical_table.caption,
        column.table or "-",
        column.name,
        column.datatype or "-",
    )
    if samples is None:
        return row
    values = find_values(samples, logical_table.object_id, column.name)
    return row + (", ".join(values) if values else "(取得不可)",)


def _union_map(datasource: Datasource) -> dict[str, list[Relation]]:
    """論理テーブル名 -> そのテーブルを構成するユニオンのマップ。"""
    result: dict[str, list[Relation]] = {}
    for logical_table in datasource.logical_tables:
        if logical_table.relation is None:
            continue
        unions = _collect_unions(logical_table.relation)
        if unions:
            result[logical_table.caption] = unions
    return result


def _has_join_or_union(relation: Relation) -> bool:
    if relation.rel_type in ("join", "union"):
        return True
    return any(_has_join_or_union(child) for child in relation.children)


def _emit_relation(
    relation: Relation,
    lines: list[str],
    counter: dict[str, int],
    indent: str,
) -> str | None:
    """relation ツリーを flowchart の行として出力し、代表ノード ID を返す。"""
    if relation.rel_type == "table":
        node_id = f"n{counter['node']}"
        counter["node"] += 1
        lines.append(f'{indent}{node_id}["{_escape_label(relation.name)}"]')
        return node_id
    if relation.rel_type == "union":
        sub_id = f"u{counter.setdefault('union', 0)}"
        counter["union"] += 1
        lines.append(
            f'{indent}subgraph {sub_id} ["{_escape_label(relation.name)} (ユニオン)"]'
        )
        lines.append(f"{indent}    direction TB")
        for child in relation.children:
            _emit_relation(child, lines, counter, indent + "    ")
        lines.append(f"{indent}end")
        return sub_id
    if relation.rel_type == "join" and len(relation.children) == 2:
        left = _emit_relation(relation.children[0], lines, counter, indent)
        right = _emit_relation(relation.children[1], lines, counter, indent)
        label = JOIN_TYPE_LABELS.get(relation.join_type, relation.join_type)
        conditions = " AND ".join(relation.join_conditions)
        text = f"{label}: {conditions}" if conditions else label
        if left and right:
            lines.append(f'{indent}{left} -- "{_escape_label(text)}" --- {right}')
        return left or right
    last: str | None = None
    for child in relation.children:
        last = _emit_relation(child, lines, counter, indent) or last
    return last


def _render_joins(datasource: Datasource) -> list[str]:
    joins: list[tuple[str, str, str, str]] = []
    for logical_table in datasource.logical_tables:
        if logical_table.relation is not None:
            joins.extend(
                _collect_joins(logical_table.relation, logical_table.caption)
            )
    if not joins and datasource.relation is not None:
        joins.extend(_collect_joins(datasource.relation, ""))
    if not joins:
        return []
    return ["#### 結合 (物理テーブル)", ""] + _table(
        ("論理テーブル", "結合種別", "対象", "条件"), list(joins)
    )


def _collect_joins(
    relation: Relation, context: str
) -> list[tuple[str, str, str, str]]:
    joins: list[tuple[str, str, str, str]] = []
    for child in relation.children:
        joins.extend(_collect_joins(child, context))
    if relation.rel_type == "join" and len(relation.children) == 2:
        left, right = relation.children
        joins.append(
            (
                context or "-",
                JOIN_TYPE_LABELS.get(relation.join_type, relation.join_type),
                f"{_relation_label(left)} × {_relation_label(right)}",
                " AND ".join(relation.join_conditions) or "-",
            )
        )
    return joins


def _relation_label(relation: Relation) -> str:
    if relation.rel_type == "table":
        return relation.name
    if relation.rel_type == "union":
        return f"{relation.name} (ユニオン)"
    if relation.rel_type == "join":
        leaves = _collect_table_names(relation)
        return "(" + " + ".join(leaves) + ")"
    return relation.name or relation.rel_type


def _collect_table_names(relation: Relation) -> list[str]:
    if relation.rel_type == "table":
        return [relation.name]
    names: list[str] = []
    for child in relation.children:
        names.extend(_collect_table_names(child))
    return names


def _render_unions(datasource: Datasource) -> list[str]:
    entries: list[tuple[str, Relation]] = []
    for logical_table in datasource.logical_tables:
        if logical_table.relation is not None:
            entries.extend(
                (logical_table.caption, union)
                for union in _collect_unions(logical_table.relation)
            )
    covered = {union.name for _, union in entries}
    if datasource.relation is not None:
        entries.extend(
            ("-", union)
            for union in _collect_unions(datasource.relation)
            if union.name not in covered
        )
    if not entries:
        return []
    rows = [
        (
            caption,
            union.name,
            ", ".join(_collect_table_names(union)) or "-",
        )
        for caption, union in entries
    ]
    return ["#### ユニオン", ""] + _table(
        ("論理テーブル", "ユニオン名", "対象テーブル"), rows
    )


def _collect_unions(relation: Relation) -> list[Relation]:
    found = [relation] if relation.rel_type == "union" else []
    for child in relation.children:
        found.extend(_collect_unions(child))
    return found


def _render_field_changes(datasource: Datasource) -> list[str]:
    if not datasource.field_changes:
        return []
    rows = [
        (
            change.name.strip("[]"),
            change.new_name or "-",
            _describe_type_change(change),
            "非表示" if change.hidden else "-",
            _semantic_role_label(change.semantic_role),
        )
        for change in datasource.field_changes
    ]
    return ["#### フィールド設定の変更", ""] + _table(
        ("フィールド", "変更後の名前", "データ型", "表示", "地理的役割"), rows
    )


def _describe_type_change(change) -> str:
    if change.original_datatype:
        return f"{change.original_datatype} → {change.datatype} (変更)"
    return change.datatype or "-"


def _semantic_role_label(semantic_role: str) -> str:
    if not semantic_role:
        return "-"
    match = re.match(r"\[([^\]]+)\]", semantic_role)
    key = match.group(1) if match else semantic_role
    return SEMANTIC_ROLE_LABELS.get(key, key)


def _render_filter_table(
    title: str, filters, caption_map: dict[str, str]
) -> list[str]:
    if not filters:
        return []
    rows = [
        (
            filter_target(filter_, caption_map),
            filter_kind(filter_),
            describe_filter(filter_, caption_map),
        )
        for filter_ in filters
    ]
    return [f"#### {title}", ""] + _table(("対象フィールド", "種別", "適用内容"), rows)


def _escape_label(label: str) -> str:
    """Mermaid の引用符付きラベル内で安全な文字列にする。"""
    return label.replace('"', "'")
