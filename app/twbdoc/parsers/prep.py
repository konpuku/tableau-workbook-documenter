"""データソースの前処理 (結合・リレーションシップ・ユニオン・抽出など) の解析。

対象の XML 構造:
- 接続:             datasource/connection/named-connections/named-connection
- 物理テーブル構造: connection/relation (join / union / table の再帰ツリー)
- 論理テーブル:     datasource/object-graph/objects/object
- リレーションシップ: datasource/object-graph/relationships/relationship
- データソースフィルタ: datasource/filter
- 抽出:             datasource/extract (+ extract/filter)
- フィールド設定変更: datasource/column (caption=名前変更, hidden, semantic-role) と
                     metadata-record の local-type 比較 (型変更)
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import replace

from ..model import (
    Connection,
    ExtractInfo,
    FieldChange,
    LogicalTable,
    Relation,
    Relationship,
    TableColumn,
)
from .filters import parse_filter_element

_INTERNAL_OBJECT_PREFIX = "[__tableau_internal_object_id__]"
# '[A]' または '[A].[B]' のような修飾フィールド参照
_FIELD_REF_PATTERN = re.compile(r"^\[[^\[\]]+\](?:\.\[[^\[\]]+\])*$")


def parse_connections(datasource: ET.Element) -> tuple[Connection, ...]:
    """接続一覧を抽出する (federated は named-connection、単独接続はそのまま)。"""
    connection = datasource.find("connection")
    if connection is None:
        return ()
    named = connection.findall("named-connections/named-connection")
    if named:
        return tuple(_parse_named_connection(element) for element in named)
    return (
        Connection(
            conn_class=connection.get("class", ""),
            source=_connection_source(connection),
        ),
    )


def parse_relation_tree(datasource: ET.Element) -> Relation | None:
    """connection 直下の物理テーブル構造ツリーを抽出する。"""
    relation = datasource.find("connection/relation")
    if relation is None:
        return None
    return _parse_relation(relation)


def parse_logical_tables(datasource: ET.Element) -> tuple[LogicalTable, ...]:
    """論理テーブル (object-graph の object) を抽出する。

    抽出専用ワークブック (元接続の properties context='' を持たない形式) では
    フィールド定義が relation に含まれないため、metadata-record から補完する。
    """
    tables = tuple(
        _parse_logical_table(element)
        for element in datasource.findall("object-graph/objects/object")
    )
    if not tables or all(table.columns for table in tables):
        return tables
    metadata_columns = _metadata_columns_by_object(datasource)
    return tuple(
        table
        if table.columns
        else replace(table, columns=metadata_columns.get(table.object_id, ()))
        for table in tables
    )


def parse_metadata_columns(datasource: ET.Element) -> tuple[TableColumn, ...]:
    """metadata-record から全フィールド定義を抽出する (object-graph が無い場合の代替)。"""
    columns: dict[tuple[str, str], TableColumn] = {}
    for record in datasource.iter("metadata-record"):
        column = _metadata_record_to_column(record)
        if column is not None:
            columns.setdefault((column.table, column.name), column)
    return tuple(columns.values())


def parse_relationships(
    datasource: ET.Element, logical_tables: tuple[LogicalTable, ...]
) -> tuple[Relationship, ...]:
    """リレーションシップを抽出する (object-id は論理テーブル名に解決)。"""
    captions = {table.object_id: table.caption for table in logical_tables}
    relationships: list[Relationship] = []
    for element in datasource.findall(
        "object-graph/relationships/relationship"
    ):
        first = element.find("first-end-point")
        second = element.find("second-end-point")
        expression = element.find("expression")
        first_id = "" if first is None else first.get("object-id", "")
        second_id = "" if second is None else second.get("object-id", "")
        first_key, second_key = _relationship_keys(expression)
        relationships.append(
            Relationship(
                first_table=captions.get(first_id, first_id),
                second_table=captions.get(second_id, second_id),
                expression=(
                    "" if expression is None else render_expression(expression)
                ),
                first_key=first_key,
                second_key=second_key,
            )
        )
    return tuple(relationships)


def _relationship_keys(expression: ET.Element | None) -> tuple[str, str]:
    """式の両辺 (テーブル 1 側 / テーブル 2 側) のキー式を返す。"""
    if expression is None:
        return "", ""
    children = expression.findall("expression")
    if len(children) != 2:
        return "", ""
    return render_expression(children[0]), render_expression(children[1])


def parse_ds_filters(datasource: ET.Element):
    """データソースフィルタ (datasource 直下の filter) を抽出する。"""
    return tuple(
        parse_filter_element(element)
        for element in datasource.findall("filter")
    )


def parse_extract(datasource: ET.Element) -> ExtractInfo | None:
    """抽出設定と抽出フィルタを抽出する。"""
    extract = datasource.find("extract")
    if extract is None:
        return None
    count = extract.get("count", "-1")
    return ExtractInfo(
        enabled=extract.get("enabled") == "true",
        row_limit="" if count == "-1" else count,
        filters=tuple(
            parse_filter_element(element)
            for element in extract.findall("filter")
        ),
    )


def parse_field_changes(datasource: ET.Element) -> tuple[FieldChange, ...]:
    """GUI で変更されたフィールド設定を抽出する。

    名前変更 (caption)・非表示 (hidden)・地理的役割 (semantic-role)・
    型変更 (metadata-record の local-type と column の datatype の不一致) を対象とする。
    """
    original_types = _collect_metadata_types(datasource)
    changes: list[FieldChange] = []
    for column in datasource.findall("column"):
        if column.find("calculation") is not None:
            continue
        name = column.get("name", "")
        if column.get("datatype") == "table" or name.startswith(
            _INTERNAL_OBJECT_PREFIX
        ):
            continue
        datatype = column.get("datatype", "")
        original = original_types.get(name, "")
        type_changed = bool(original) and original != datatype
        change = FieldChange(
            name=name,
            new_name=column.get("caption", ""),
            datatype=datatype,
            original_datatype=original if type_changed else "",
            role=column.get("role", ""),
            hidden=column.get("hidden") == "true",
            semantic_role=column.get("semantic-role", ""),
        )
        if (
            change.new_name
            or change.hidden
            or change.semantic_role
            or type_changed
        ):
            changes.append(change)
    return tuple(changes)


def render_expression(expression: ET.Element) -> str:
    """リレーションシップ/結合条件の式ツリーを文字列化する。

    例: <expression op='='> [A] [B] </expression> -> 'A = B'
    """
    children = expression.findall("expression")
    op = expression.get("op", "")
    if not children:
        if _FIELD_REF_PATTERN.match(op):
            return ".".join(
                part for part in re.findall(r"\[([^\[\]]+)\]", op)
            )
        return op
    rendered = [render_expression(child) for child in children]
    return f" {op} ".join(rendered)


def _parse_named_connection(element: ET.Element) -> Connection:
    inner = element.find("connection")
    return Connection(
        name=element.get("name", ""),
        caption=element.get("caption", ""),
        conn_class="" if inner is None else inner.get("class", ""),
        source="" if inner is None else _connection_source(inner),
    )


def _connection_source(connection: ET.Element) -> str:
    for attr in ("filename", "server", "dbname"):
        value = connection.get(attr, "")
        if value:
            return value
    return ""


def _parse_relation(element: ET.Element) -> Relation:
    return Relation(
        rel_type=element.get("type", ""),
        name=element.get("name", ""),
        table=element.get("table", ""),
        connection=element.get("connection", ""),
        join_type=element.get("join", ""),
        join_conditions=_parse_join_conditions(element),
        children=tuple(
            _parse_relation(child) for child in element.findall("relation")
        ),
    )


def _parse_join_conditions(element: ET.Element) -> tuple[str, ...]:
    return tuple(
        render_expression(expression)
        for clause in element.findall("clause[@type='join']")
        for expression in clause.findall("expression")
    )


def _parse_logical_table(element: ET.Element) -> LogicalTable:
    caption = element.get("caption", "")
    relation_element = element.find("properties[@context='']/relation")
    used_fallback = relation_element is None
    if relation_element is None:
        # 抽出専用形式では元接続の properties が無いため extract 側を使う
        relation_element = element.find("properties/relation")
    relation = (
        None if relation_element is None else _parse_relation(relation_element)
    )
    if (
        used_fallback
        and relation is not None
        and relation.rel_type == "table"
        and caption
    ):
        # extract 側のテーブル名は内部 ID のため表示名に置き換える
        relation = replace(relation, name=caption)
    return LogicalTable(
        object_id=element.get("id", ""),
        caption=caption,
        relation=relation,
        columns=(
            ()
            if relation_element is None
            else _collect_relation_columns(relation_element)
        ),
    )


def _metadata_columns_by_object(
    datasource: ET.Element,
) -> dict[str, tuple[TableColumn, ...]]:
    """metadata-record を object-id (論理テーブル) ごとにまとめる。"""
    grouped: dict[str, dict[tuple[str, str], TableColumn]] = {}
    for record in datasource.iter("metadata-record"):
        column = _metadata_record_to_column(record)
        if column is None:
            continue
        object_id = (record.findtext("object-id") or "").strip().strip("[]")
        if not object_id:
            continue
        grouped.setdefault(object_id, {}).setdefault(
            (column.table, column.name), column
        )
    return {
        object_id: tuple(columns.values())
        for object_id, columns in grouped.items()
    }


def _metadata_record_to_column(record: ET.Element) -> TableColumn | None:
    if record.get("class") != "column":
        return None
    local_name = (record.findtext("local-name") or "").strip().strip("[]")
    remote_name = (record.findtext("remote-name") or "").strip()
    name = local_name or remote_name
    if not name:
        return None
    return TableColumn(
        name=name,
        datatype=(record.findtext("local-type") or "").strip(),
        table=(record.findtext("parent-name") or "").strip().strip("[]"),
    )


def _collect_relation_columns(element: ET.Element) -> tuple[TableColumn, ...]:
    """relation ツリーからフィールド定義 (columns/column) を収集する。

    ユニオンは統合後のスキーマ (ユニオン自身の columns) を優先し、
    メンバーテーブルの重複列挙は避ける。
    """
    rel_type = element.get("type", "")
    table_name = element.get("name", "")
    own_columns = tuple(
        TableColumn(
            name=column.get("name", ""),
            datatype=column.get("datatype", ""),
            table=table_name,
        )
        for column in element.findall("columns/column")
    )
    if rel_type == "union" or (rel_type == "table" and own_columns):
        return own_columns
    collected: list[TableColumn] = list(own_columns)
    for child in element.findall("relation"):
        collected.extend(_collect_relation_columns(child))
    return tuple(collected)


def _collect_metadata_types(datasource: ET.Element) -> dict[str, str]:
    """metadata-record から local-name -> local-type のマップを構築する。

    同名フィールドが複数テーブルに存在し型が食い違う場合は
    型変更の誤検知を避けるため対象から除外する。
    """
    types: dict[str, str] = {}
    conflicted: set[str] = set()
    for record in datasource.iter("metadata-record"):
        if record.get("class") != "column":
            continue
        local_name = (record.findtext("local-name") or "").strip()
        local_type = (record.findtext("local-type") or "").strip()
        if not local_name or not local_type:
            continue
        if local_name in types and types[local_name] != local_type:
            conflicted.add(local_name)
        types[local_name] = local_type
    return {
        name: local_type
        for name, local_type in types.items()
        if name not in conflicted
    }
