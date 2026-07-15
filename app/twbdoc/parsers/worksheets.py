"""ワークシートの解析。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..model import Worksheet
from .filters import parse_view_filters
from .parameters import PARAMETERS_DATASOURCE_NAME
from .table_calcs import parse_pill_table_calcs


def parse_worksheets(root: ET.Element) -> tuple[Worksheet, ...]:
    """ワークシート一覧を抽出する (配置先ダッシュボードは集約時に付与)。"""
    return tuple(
        _parse_worksheet(element)
        for element in root.findall("worksheets/worksheet")
    )


def _parse_worksheet(element: ET.Element) -> Worksheet:
    return Worksheet(
        name=element.get("name", ""),
        title=_parse_title(element),
        datasources=_parse_used_datasources(element),
        filters=parse_view_filters(element),
        used_columns=_parse_used_columns(element),
        table_calcs=parse_pill_table_calcs(element),
    )


def _parse_title(element: ET.Element) -> str:
    runs = element.findall("layout-options/title/formatted-text/run")
    return "".join(run.text or "" for run in runs).strip()


def _parse_used_datasources(element: ET.Element) -> tuple[str, ...]:
    """使用データソースを抽出する (Parameters 擬似データソースは除く)。"""
    return tuple(
        datasource.get("caption") or datasource.get("name", "")
        for datasource in element.findall("table/view/datasources/datasource")
        if datasource.get("name") != PARAMETERS_DATASOURCE_NAME
    )


def _parse_used_columns(element: ET.Element) -> tuple[str, ...]:
    """ワークシートが参照するフィールドの内部名一覧 (datasource-dependencies)。"""
    names: list[str] = []
    for dependencies in element.iter("datasource-dependencies"):
        for column in dependencies.findall("column"):
            name = column.get("name", "")
            if name and name not in names:
                names.append(name)
    return tuple(names)
