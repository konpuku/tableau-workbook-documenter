"""ダッシュボード・ゾーンツリーの解析。

ゾーンは dashboard 直下の <zones> のみを対象とする
(<devicelayouts> 配下の複製ゾーンは含めない)。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..model import Dashboard, DashboardSize, Zone

ZONE_TYPE_WORKSHEET = "worksheet"
ZONE_TYPE_UNKNOWN = "unknown"


def parse_dashboards(root: ET.Element) -> tuple[Dashboard, ...]:
    """ダッシュボード一覧をゾーンツリー付きで抽出する。"""
    return tuple(
        _parse_dashboard(element)
        for element in root.findall("dashboards/dashboard")
    )


def _parse_dashboard(element: ET.Element) -> Dashboard:
    zones_element = element.find("zones")
    zones: tuple[Zone, ...] = ()
    if zones_element is not None:
        zones = tuple(
            _parse_zone(zone) for zone in zones_element.findall("zone")
        )
    return Dashboard(
        name=element.get("name", ""),
        size=_parse_size(element),
        zones=zones,
    )


def _parse_size(element: ET.Element) -> DashboardSize:
    size = element.find("size")
    if size is None:
        return DashboardSize(sizing_mode="automatic")
    return DashboardSize(
        sizing_mode=size.get("sizing-mode", ""),
        minwidth=size.get("minwidth", ""),
        minheight=size.get("minheight", ""),
        maxwidth=size.get("maxwidth", ""),
        maxheight=size.get("maxheight", ""),
    )


def _parse_zone(element: ET.Element) -> Zone:
    return Zone(
        zone_type=_zone_type(element),
        name=element.get("name", ""),
        param=element.get("param", ""),
        text=_parse_zone_text(element),
        x=_parse_coordinate(element, "x"),
        y=_parse_coordinate(element, "y"),
        w=_parse_coordinate(element, "w"),
        h=_parse_coordinate(element, "h"),
        children=tuple(
            _parse_zone(child) for child in element.findall("zone")
        ),
    )


def _zone_type(element: ET.Element) -> str:
    type_v2 = element.get("type-v2") or element.get("type")
    if type_v2:
        return type_v2
    if element.get("name"):
        return ZONE_TYPE_WORKSHEET
    return ZONE_TYPE_UNKNOWN


def _parse_zone_text(element: ET.Element) -> str:
    runs = element.findall("formatted-text/run")
    text = "".join(run.text or "" for run in runs)
    # Tableau はテキストオブジェクト内の改行を「Æ + 改行」で表現する
    return text.replace("Æ\n", "\n").strip()


def _parse_coordinate(element: ET.Element, attr: str) -> int | None:
    value = element.get(attr)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None
