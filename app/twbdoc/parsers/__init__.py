"""パーサー群の集約。XML ルート要素から Workbook モデルを構築する。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import replace

from ..model import Dashboard, Workbook, Worksheet, Zone
from .actions import parse_actions
from .calculations import parse_calculated_fields
from .dashboards import ZONE_TYPE_WORKSHEET, parse_dashboards
from .datasources import parse_datasources
from .filters import parse_shared_filters
from .metadata import parse_metadata
from .parameters import parse_parameters
from .styles import parse_style_rules
from .worksheets import parse_worksheets


def parse_workbook(root: ET.Element, source_file: str) -> Workbook:
    """twb XML 全体を解析して Workbook モデルを返す。"""
    dashboards = parse_dashboards(root)
    worksheets = _attach_dashboards(parse_worksheets(root), dashboards)
    return Workbook(
        meta=parse_metadata(root, source_file),
        datasources=parse_datasources(root),
        parameters=parse_parameters(root),
        calculated_fields=parse_calculated_fields(root),
        worksheets=worksheets,
        dashboards=dashboards,
        style_rules=parse_style_rules(root),
        shared_filters=parse_shared_filters(root),
        actions=parse_actions(root),
    )


def _attach_dashboards(
    worksheets: tuple[Worksheet, ...],
    dashboards: tuple[Dashboard, ...],
) -> tuple[Worksheet, ...]:
    """各ワークシートに配置先ダッシュボード名を付与する (イミュータブルに再構築)。"""
    placement: dict[str, tuple[str, ...]] = {}
    for dashboard in dashboards:
        for sheet_name in _collect_worksheet_names(dashboard.zones):
            current = placement.get(sheet_name, ())
            if dashboard.name not in current:
                placement[sheet_name] = current + (dashboard.name,)
    return tuple(
        replace(worksheet, dashboards=placement.get(worksheet.name, ()))
        for worksheet in worksheets
    )


def _collect_worksheet_names(zones: tuple[Zone, ...]) -> tuple[str, ...]:
    names: list[str] = []
    for zone in zones:
        if zone.zone_type == ZONE_TYPE_WORKSHEET and zone.name:
            names.append(zone.name)
        names.extend(_collect_worksheet_names(zone.children))
    return tuple(names)
