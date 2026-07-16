"""レイアウト簡略図 (SVG) と座標のピクセル表記のテスト。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from twbdoc.model import Dashboard, DashboardSize, Zone
from twbdoc.parsers import parse_workbook
from twbdoc.renderers.layout_svg import render_layout_svg
from twbdoc.renderers.zones import fixed_pixel_size, render_zone_list

FIXED_SIZE = DashboardSize(
    sizing_mode="fixed",
    minwidth="1200",
    minheight="800",
    maxwidth="1200",
    maxheight="800",
)


class TestFixedPixelSize:
    def test_固定サイズを返す(self) -> None:
        assert fixed_pixel_size(FIXED_SIZE) == (1200, 800)

    def test_自動サイズはNone(self) -> None:
        assert fixed_pixel_size(DashboardSize(sizing_mode="automatic")) is None

    def test_数値でない場合はNone(self) -> None:
        size = DashboardSize(sizing_mode="fixed", minwidth="", minheight="800")
        assert fixed_pixel_size(size) is None


class TestZoneListPixels:
    def test_固定サイズではピクセル表記になる(self) -> None:
        zone = Zone(
            zone_type="worksheet", name="売上", x=0, y=8000, w=70000, h=92000
        )
        lines = render_zone_list((zone,), {}, FIXED_SIZE)
        assert lines[0] == "- [ワークシート] 売上 (x:0px, y:64px, 幅:840px, 高さ:736px)"

    def test_サイズ不明では従来の百分率表記(self) -> None:
        zone = Zone(zone_type="worksheet", name="売上", x=0, y=8000)
        lines = render_zone_list((zone,), {})
        assert lines[0] == "- [ワークシート] 売上 (x:0%, y:8%)"


class TestRenderLayoutSvg:
    def _dashboard(self, minimal_root: ET.Element) -> Dashboard:
        workbook = parse_workbook(minimal_root, "test.twbx")
        return workbook.dashboards[0]

    def test_固定サイズのviewBoxで描画される(
        self, minimal_root: ET.Element
    ) -> None:
        svg = render_layout_svg(self._dashboard(minimal_root))
        assert svg is not None
        assert 'viewBox="0 0 1200 800"' in svg

    def test_ワークシートは塗りつぶしボックスで出る(
        self, minimal_root: ET.Element
    ) -> None:
        svg = render_layout_svg(self._dashboard(minimal_root))
        assert svg is not None
        # 売上推移: x=0 y=8000 w=70000 h=92000 -> 0, 64, 840, 736
        assert '<rect class="leaf" x="0.0" y="64.0" width="840.0" height="736.0"' in svg
        assert "売上推移" in svg

    def test_コンテナは枠のみで出る(self, minimal_root: ET.Element) -> None:
        svg = render_layout_svg(self._dashboard(minimal_root))
        assert svg is not None
        assert '<rect class="container"' in svg

    def test_ラベルはXMLエスケープされる(self) -> None:
        dashboard = Dashboard(
            name="d",
            size=FIXED_SIZE,
            zones=(
                Zone(
                    zone_type="worksheet",
                    name="A<B>&C",
                    x=0,
                    y=0,
                    w=100000,
                    h=100000,
                ),
            ),
        )
        svg = render_layout_svg(dashboard)
        assert svg is not None
        assert "A&lt;B&gt;&amp;C" in svg

    def test_座標を持つゾーンがなければNone(self) -> None:
        dashboard = Dashboard(name="d", zones=(Zone(zone_type="title"),))
        assert render_layout_svg(dashboard) is None
