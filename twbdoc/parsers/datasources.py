"""データソース・フィールド・別名の解析。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..model import Alias, Datasource, Field
from .calculations import parse_field_comment
from .parameters import PARAMETERS_DATASOURCE_NAME
from .prep import (
    parse_connections,
    parse_ds_filters,
    parse_extract,
    parse_field_changes,
    parse_logical_tables,
    parse_relation_tree,
    parse_relationships,
)


def parse_datasources(root: ET.Element) -> tuple[Datasource, ...]:
    """Parameters 擬似データソースを除く全データソースを抽出する。"""
    return tuple(
        _parse_datasource(element)
        for element in root.findall("datasources/datasource")
        if element.get("name") != PARAMETERS_DATASOURCE_NAME
    )


def _parse_datasource(element: ET.Element) -> Datasource:
    connection = element.find("connection")
    logical_tables = parse_logical_tables(element)
    return Datasource(
        name=element.get("name", ""),
        caption=element.get("caption", ""),
        connection_class="" if connection is None else connection.get("class", ""),
        fields=tuple(
            _parse_field(column) for column in element.findall("column")
        ),
        connections=parse_connections(element),
        relation=parse_relation_tree(element),
        logical_tables=logical_tables,
        relationships=parse_relationships(element, logical_tables),
        ds_filters=parse_ds_filters(element),
        extract=parse_extract(element),
        field_changes=parse_field_changes(element),
    )


def _parse_field(column: ET.Element) -> Field:
    calculation = column.find("calculation")
    return Field(
        name=column.get("name", ""),
        caption=column.get("caption", ""),
        datatype=column.get("datatype", ""),
        role=column.get("role", ""),
        is_calculated=calculation is not None
        and bool(calculation.get("formula")),
        aliases=_parse_aliases(column),
        comment=parse_field_comment(column),
    )


def _parse_aliases(column: ET.Element) -> tuple[Alias, ...]:
    aliases_element = column.find("aliases")
    if aliases_element is None:
        return ()
    return tuple(
        Alias(key=alias.get("key", ""), value=alias.get("value", ""))
        for alias in aliases_element.findall("alias")
    )
