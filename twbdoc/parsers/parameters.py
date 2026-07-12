"""パラメーター (datasource name='Parameters') の解析。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..model import Parameter, ParameterMember

PARAMETERS_DATASOURCE_NAME = "Parameters"


def parse_parameters(root: ET.Element) -> tuple[Parameter, ...]:
    """Parameters 擬似データソース内の column をパラメーターとして抽出する。"""
    datasource = root.find(
        f"datasources/datasource[@name='{PARAMETERS_DATASOURCE_NAME}']"
    )
    if datasource is None:
        return ()
    return tuple(
        _parse_parameter(column) for column in datasource.findall("column")
    )


def _parse_parameter(column: ET.Element) -> Parameter:
    range_element = column.find("range")
    return Parameter(
        name=column.get("name", ""),
        caption=column.get("caption", ""),
        datatype=column.get("datatype", ""),
        current_value=column.get("value", ""),
        domain_type=column.get("param-domain-type", "any"),
        range_min=_get_or_empty(range_element, "min"),
        range_max=_get_or_empty(range_element, "max"),
        granularity=_get_or_empty(range_element, "granularity"),
        members=_parse_members(column),
    )


def _parse_members(column: ET.Element) -> tuple[ParameterMember, ...]:
    members_element = column.find("members")
    if members_element is None:
        return ()
    return tuple(
        ParameterMember(
            value=member.get("value", ""),
            alias=member.get("alias", ""),
        )
        for member in members_element.findall("member")
    )


def _get_or_empty(element: ET.Element | None, attr: str) -> str:
    if element is None:
        return ""
    return element.get(attr, "")
