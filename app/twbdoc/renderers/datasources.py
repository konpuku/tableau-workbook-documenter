"""データソースと前処理章のレンダリング。

データモデル (リレーションシップ・結合・ユニオン) を Mermaid の flowchart
1 枚で表現する。用語は Tableau のデータモデルの表記に合わせる。
"""

from __future__ import annotations

import re

from ..i18n import JA, Translator
from ..model import Datasource, Relation, TableColumn, Workbook
from ..sampler import SampleResult, find_values
from .filters import describe_filter, filter_kind, filter_target
from .tables import table as _table

NOT_APPLICABLE = ("(該当なし)", "(none)")

CONNECTION_CLASS_LABELS = {
    "excel-direct": ("Excel", "Excel"),
    "textscan": ("テキストファイル (CSV 等)", "Text file (CSV etc.)"),
    "federated": ("複数接続 (federated)", "Multiple connections (federated)"),
    "hyper": ("抽出 (Hyper)", "Extract (Hyper)"),
    "sqlserver": ("SQL Server", "SQL Server"),
    "postgres": ("PostgreSQL", "PostgreSQL"),
    "mysql": ("MySQL", "MySQL"),
    "oracle": ("Oracle", "Oracle"),
    "snowflake": ("Snowflake", "Snowflake"),
    "bigquery": ("Google BigQuery", "Google BigQuery"),
    "redshift": ("Amazon Redshift", "Amazon Redshift"),
}

JOIN_TYPE_LABELS = {
    "left": ("左結合", "Left join"),
    "right": ("右結合", "Right join"),
    "inner": ("内部結合", "Inner join"),
    "full": ("完全外部結合", "Full outer join"),
}

SEMANTIC_ROLE_LABELS = {
    "Country": ("国/地域", "Country/Region"),
    "State": ("都道府県/州", "State/Province"),
    "City": ("市区町村", "City"),
    "ZipCode": ("郵便番号", "ZIP Code/Postcode"),
    "County": ("郡", "County"),
    "Airport": ("空港", "Airport"),
}

DATA_MODEL_LEGEND = (
    "凡例: 枠 = 論理テーブル / 枠同士の点線 = リレーションシップ (ラベルは条件。"
    "Tableau のリレーションシップは結合方法を固定せず、分析内容に応じて自動決定されます) / "
    "枠内の実線 = 結合 (ラベルは結合種別と条件) / 内側の枠 = ユニオン / "
    "「キー:」 = リレーションシップで使用するキー項目",
    "Legend: box = logical table / dotted line between boxes = relationship "
    "(the label is the condition; Tableau relationships do not fix the join "
    "type, it is chosen automatically for each analysis) / solid line inside "
    "a box = join (the label is the join type and condition) / inner box = "
    "union / \"Key:\" = fields used by the relationship",
)

NO_EDGES_NOTE = (
    "- リレーションシップ・結合の定義がワークブックに残っていないため、"
    "テーブルと列の構成のみを表示しています",
    "- The workbook does not contain relationship or join definitions, "
    "so only the tables and their fields are shown",
)

_MAX_DIAGRAM_COLUMNS = 10


def render_datasources_prep(
    workbook: Workbook,
    caption_map: dict[str, str],
    number: int = 2,
    field_list_anchors: dict[str, str] | None = None,
    t: Translator = JA,
) -> list[str]:
    """データソースと前処理章。

    field_list_anchors: データソース内部名 -> 巻末フィールド一覧節のアンカー。
    渡された場合はデータモデル図の直下にリンクを併記する。
    """
    lines = [
        f"## {number}. " + t("データソースと前処理", "Data Sources and Preparation"),
        "",
    ]
    if not workbook.datasources:
        lines.extend([t(*NOT_APPLICABLE), ""])
        return lines
    anchors = field_list_anchors or {}
    for index, datasource in enumerate(workbook.datasources, start=1):
        lines.extend(
            _render_datasource(
                datasource,
                caption_map,
                f"{number}.{index}",
                anchors.get(datasource.name, ""),
                t,
            )
        )
    return lines


def _render_datasource(
    datasource: Datasource,
    caption_map: dict[str, str],
    number: str,
    field_list_anchor: str,
    t: Translator,
) -> list[str]:
    lines = [f"### {number} {datasource.display_name}", ""]
    lines.extend(_render_basic_info(datasource, t))
    lines.extend(_render_connections(datasource, t))
    lines.extend(_render_data_model(datasource, field_list_anchor, t))
    lines.extend(_render_relationship_table(datasource, t))
    lines.extend(_render_joins(datasource, t))
    lines.extend(_render_unions(datasource, t))
    lines.extend(_render_field_changes(datasource, t))
    lines.extend(
        _render_filter_table(
            t("データソースフィルター", "Data Source Filters"),
            datasource.ds_filters,
            caption_map,
            t,
        )
    )
    if datasource.extract is not None:
        lines.extend(
            _render_filter_table(
                t("抽出フィルター", "Extract Filters"),
                datasource.extract.filters,
                caption_map,
                t,
            )
        )
    return lines


def _render_basic_info(datasource: Datasource, t: Translator) -> list[str]:
    rows = [
        (t("名前", "Name"), datasource.display_name),
        (
            t("接続種別", "Connection type"),
            _connection_class_label(datasource.connection_class, t),
        ),
        (t("接続方式", "Live or extract"), _describe_extract(datasource, t)),
    ]
    return _table((t("項目", "Item"), t("値", "Value")), rows)


def _connection_class_label(connection_class: str, t: Translator) -> str:
    pair = CONNECTION_CLASS_LABELS.get(connection_class)
    return t(*pair) if pair is not None else (connection_class or "-")


def _describe_extract(datasource: Datasource, t: Translator) -> str:
    extract = datasource.extract
    if extract is None or not extract.enabled:
        return t("ライブ", "Live")
    if extract.row_limit:
        return t(
            f"抽出 (行数制限: {extract.row_limit} 行)",
            f"Extract (limited to {extract.row_limit} rows)",
        )
    return t("抽出 (全件)", "Extract (all rows)")


def _render_connections(datasource: Datasource, t: Translator) -> list[str]:
    if not datasource.connections:
        return []
    rows = [
        (
            connection.caption or connection.name or "-",
            _connection_class_label(connection.conn_class, t),
            connection.source or "-",
        )
        for connection in datasource.connections
    ]
    return ["#### " + t("接続", "Connections"), ""] + _table(
        (
            t("接続名", "Connection"),
            t("種別", "Type"),
            t("接続先", "Source"),
        ),
        rows,
    )


def _render_relationship_table(
    datasource: Datasource, t: Translator
) -> list[str]:
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
    return ["#### " + t("リレーションシップ", "Relationships"), ""] + _table(
        (
            t("テーブル 1", "Table 1"),
            t("条件", "Condition"),
            t("テーブル 2", "Table 2"),
        ),
        rows,
    )


def _render_data_model(
    datasource: Datasource,
    field_list_anchor: str = "",
    t: Translator = JA,
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
    has_edges = _has_data_model_edges(datasource)

    for logical_table in datasource.logical_tables:
        sub_id = f"lt{counter['sub']}"
        counter["sub"] += 1
        sub_ids[logical_table.caption] = sub_id
        body.append(f'    subgraph {sub_id} ["{_escape_label(logical_table.caption)}"]')
        if logical_table.relation is not None:
            _emit_relation(
                logical_table.relation, body, counter, "        ", t
            )
        key_label = _key_node_label(
            keys.get(logical_table.caption, []),
            tables.get(logical_table.caption),
            t,
        )
        if key_label:
            key_id = f"k{counter['node']}"
            counter["node"] += 1
            body.append(f'        {key_id}[/"{key_label}"/]')
        if not has_edges and logical_table.columns:
            # 線の情報が無いワークブックでは列一覧を枠内に表示して情報量を補う
            column_id = f"c{counter['node']}"
            counter["node"] += 1
            body.append(
                f'        {column_id}'
                f'["{_column_list_label(logical_table.columns, t)}"]'
            )
        body.append("    end")

    for relationship in datasource.relationships:
        first = sub_ids.get(relationship.first_table)
        second = sub_ids.get(relationship.second_table)
        if first is None or second is None:
            continue
        label = _escape_label(relationship.expression) or t("関連", "related")
        body.append(f'    {first} -. "{label}" .- {second}')

    if datasource.relation is not None:
        if not datasource.logical_tables:
            if _has_join_or_union(datasource.relation):
                _emit_relation(datasource.relation, body, counter, "    ", t)
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
                    _emit_relation(union, body, counter, "    ", t)

    if not body:
        # object-graph を持たない形式では metadata-record からテーブル枠+列を描く
        body.extend(
            _metadata_table_boxes(datasource.metadata_columns, counter, t)
        )
    if not body:
        return []
    lines = [
        "#### " + t("データモデル図", "Data model diagram"),
        "",
        "```mermaid",
        "flowchart LR",
    ]
    lines.extend(body)
    lines.extend(["```", "", t(*DATA_MODEL_LEGEND), ""])
    if not has_edges and counter["sub"] > 1:
        lines.append(t(*NO_EDGES_NOTE))
    for caption, unions in union_map.items():
        for union in unions:
            members = ", ".join(_collect_table_names(union))
            lines.append(
                t(
                    f"- 「{caption}」はユニオン「{union.name}」"
                    f"({members}) で構成されています",
                    f'- "{caption}" is made up of the union '
                    f'"{union.name}" ({members})',
                )
            )
    if field_list_anchor:
        link_label = t("テーブル別フィールド一覧", "Field List by Table")
        lines.append(
            t(
                f"- 各テーブルの全フィールドは"
                f" [{link_label}](#{field_list_anchor}) を参照",
                f"- See [{link_label}](#{field_list_anchor}) "
                "for all fields in each table",
            )
        )
    if lines[-1] != "":
        lines.append("")
    return lines


def _key_node_label(keys: list[str], table, t: Translator = JA) -> str:
    """枠内に表示するキー項目ノードのラベル (型付き)。"""
    if not keys:
        return ""
    parts = [f"{key} ({_key_datatype(table, key)})" for key in keys]
    return _escape_label(t("キー: ", "Key: ") + "<br>".join(parts))


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
    number: int = 13,
    t: Translator = JA,
) -> list[str]:
    """テーブル別フィールド一覧章 (参考)。設計書の巻末に全フィールドを別掲する。

    samples が渡された場合は「サンプル値 (代表値)」列を追加する。
    """
    lines = [
        f"## {number}. "
        + t("テーブル別フィールド一覧 (参考)", "Field List by Table (Reference)"),
        "",
    ]
    headers: tuple[str, ...] = (
        t("論理テーブル", "Logical table"),
        t("物理テーブル", "Physical table"),
        t("フィールド", "Field"),
        t("型", "Data type"),
    )
    if samples is not None:
        headers = headers + (t("サンプル値 (代表値)", "Sample values"),)
    sections: list[list[str]] = []
    for datasource in field_list_datasources(workbook):
        rows = [
            _field_list_row(logical_table, column, samples, t)
            for logical_table in datasource.logical_tables
            for column in logical_table.columns
        ]
        if not rows:
            # object-graph からフィールドが取れない形式では metadata-record を使う
            rows = [
                _metadata_field_row(column, samples, t)
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
        lines.extend([t(*NOT_APPLICABLE), ""])
        return lines
    for section in sections:
        lines.extend(section)
    if samples is not None and samples.notes:
        marker = t("※ ", "* ")
        lines.extend(f"{marker}{note}" for note in samples.notes)
        lines.append("")
    return lines


def _metadata_field_row(
    column, samples: SampleResult | None, t: Translator = JA
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
    return row + (", ".join(values) if values else _unavailable(t),)


def _field_list_row(
    logical_table, column, samples: SampleResult | None, t: Translator = JA
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
    return row + (", ".join(values) if values else _unavailable(t),)


def _unavailable(t: Translator) -> str:
    return t("(取得不可)", "(not available)")


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


def _has_data_model_edges(datasource: Datasource) -> bool:
    """データモデル図に線 (リレーションシップ・結合・ユニオン) が描かれるか。"""
    if datasource.relationships:
        return True
    if datasource.relation is not None and _has_join_or_union(
        datasource.relation
    ):
        return True
    return any(
        logical_table.relation is not None
        and _has_join_or_union(logical_table.relation)
        for logical_table in datasource.logical_tables
    )


def _column_list_label(
    columns: tuple[TableColumn, ...], t: Translator = JA
) -> str:
    """枠内に表示する列一覧のラベル (多すぎる場合は省略)。"""
    names = [column.name for column in columns]
    shown = names[:_MAX_DIAGRAM_COLUMNS]
    remaining = len(names) - _MAX_DIAGRAM_COLUMNS
    if remaining > 0:
        shown.append(t(f"…他 {remaining} 列", f"…and {remaining} more"))
    return _escape_label("<br>".join(shown))


def _metadata_table_boxes(
    columns: tuple[TableColumn, ...],
    counter: dict[str, int],
    t: Translator = JA,
) -> list[str]:
    """metadata-record の列をテーブルごとの枠+列一覧として描く。"""
    unknown = t("(テーブル名不明)", "(unknown table)")
    groups: dict[str, list[TableColumn]] = {}
    for column in columns:
        groups.setdefault(column.table or unknown, []).append(column)
    lines: list[str] = []
    for table_name, table_columns in groups.items():
        sub_id = f"lt{counter['sub']}"
        counter["sub"] += 1
        lines.append(f'    subgraph {sub_id} ["{_escape_label(table_name)}"]')
        column_id = f"c{counter['node']}"
        counter["node"] += 1
        lines.append(
            f'        {column_id}'
            f'["{_column_list_label(tuple(table_columns), t)}"]'
        )
        lines.append("    end")
    return lines


def _emit_relation(
    relation: Relation,
    lines: list[str],
    counter: dict[str, int],
    indent: str,
    t: Translator = JA,
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
        union_label = t("ユニオン", "union")
        lines.append(
            f'{indent}subgraph {sub_id} '
            f'["{_escape_label(relation.name)} ({union_label})"]'
        )
        lines.append(f"{indent}    direction TB")
        for child in relation.children:
            _emit_relation(child, lines, counter, indent + "    ", t)
        lines.append(f"{indent}end")
        return sub_id
    if relation.rel_type == "join" and len(relation.children) == 2:
        left = _emit_relation(relation.children[0], lines, counter, indent, t)
        right = _emit_relation(relation.children[1], lines, counter, indent, t)
        label = _join_type_label(relation.join_type, t)
        conditions = " AND ".join(relation.join_conditions)
        text = f"{label}: {conditions}" if conditions else label
        if left and right:
            lines.append(f'{indent}{left} -- "{_escape_label(text)}" --- {right}')
        return left or right
    last: str | None = None
    for child in relation.children:
        last = _emit_relation(child, lines, counter, indent, t) or last
    return last


def _join_type_label(join_type: str, t: Translator) -> str:
    pair = JOIN_TYPE_LABELS.get(join_type)
    return t(*pair) if pair is not None else join_type


def _render_joins(datasource: Datasource, t: Translator = JA) -> list[str]:
    joins: list[tuple[str, str, str, str]] = []
    for logical_table in datasource.logical_tables:
        if logical_table.relation is not None:
            joins.extend(
                _collect_joins(logical_table.relation, logical_table.caption, t)
            )
    if not joins and datasource.relation is not None:
        joins.extend(_collect_joins(datasource.relation, "", t))
    if not joins:
        return []
    return ["#### " + t("結合 (物理テーブル)", "Joins (physical tables)"), ""] + _table(
        (
            t("論理テーブル", "Logical table"),
            t("結合種別", "Join type"),
            t("対象", "Tables"),
            t("条件", "Condition"),
        ),
        list(joins),
    )


def _collect_joins(
    relation: Relation, context: str, t: Translator = JA
) -> list[tuple[str, str, str, str]]:
    joins: list[tuple[str, str, str, str]] = []
    for child in relation.children:
        joins.extend(_collect_joins(child, context, t))
    if relation.rel_type == "join" and len(relation.children) == 2:
        left, right = relation.children
        joins.append(
            (
                context or "-",
                _join_type_label(relation.join_type, t),
                f"{_relation_label(left, t)} × {_relation_label(right, t)}",
                " AND ".join(relation.join_conditions) or "-",
            )
        )
    return joins


def _relation_label(relation: Relation, t: Translator = JA) -> str:
    if relation.rel_type == "table":
        return relation.name
    if relation.rel_type == "union":
        return f"{relation.name} ({t('ユニオン', 'union')})"
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


def _render_unions(datasource: Datasource, t: Translator = JA) -> list[str]:
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
    return ["#### " + t("ユニオン", "Unions"), ""] + _table(
        (
            t("論理テーブル", "Logical table"),
            t("ユニオン名", "Union name"),
            t("対象テーブル", "Tables"),
        ),
        rows,
    )


def _collect_unions(relation: Relation) -> list[Relation]:
    found = [relation] if relation.rel_type == "union" else []
    for child in relation.children:
        found.extend(_collect_unions(child))
    return found


def _render_field_changes(
    datasource: Datasource, t: Translator = JA
) -> list[str]:
    if not datasource.field_changes:
        return []
    rows = [
        (
            change.name.strip("[]"),
            change.new_name or "-",
            _describe_type_change(change, t),
            t("非表示", "Hidden") if change.hidden else "-",
            _semantic_role_label(change.semantic_role, t),
        )
        for change in datasource.field_changes
    ]
    return [
        "#### " + t("フィールド設定の変更", "Field changes"),
        "",
    ] + _table(
        (
            t("フィールド", "Field"),
            t("変更後の名前", "Renamed to"),
            t("データ型", "Data type"),
            t("表示", "Visibility"),
            t("地理的役割", "Geographic role"),
        ),
        rows,
    )


def _describe_type_change(change, t: Translator = JA) -> str:
    if change.original_datatype:
        changed = t("変更", "changed")
        return f"{change.original_datatype} → {change.datatype} ({changed})"
    return change.datatype or "-"


def _semantic_role_label(semantic_role: str, t: Translator = JA) -> str:
    if not semantic_role:
        return "-"
    match = re.match(r"\[([^\]]+)\]", semantic_role)
    key = match.group(1) if match else semantic_role
    pair = SEMANTIC_ROLE_LABELS.get(key)
    return t(*pair) if pair is not None else key


def _render_filter_table(
    title: str, filters, caption_map: dict[str, str], t: Translator = JA
) -> list[str]:
    if not filters:
        return []
    rows = [
        (
            filter_target(filter_, caption_map),
            filter_kind(filter_, t),
            describe_filter(filter_, caption_map, t),
        )
        for filter_ in filters
    ]
    return [f"#### {title}", ""] + _table(
        (
            t("対象フィールド", "Field"),
            t("種別", "Type"),
            t("適用内容", "Setting"),
        ),
        rows,
    )


def _escape_label(label: str) -> str:
    """Mermaid の引用符付きラベル内で安全な文字列にする。"""
    return label.replace('"', "'")
