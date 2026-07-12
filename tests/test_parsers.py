"""パーサー群のテスト (最小 XML フィクスチャベース)。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from twbdoc.parsers import parse_workbook
from twbdoc.parsers.calculations import parse_calculated_fields, resolve_formula
from twbdoc.parsers.dashboards import parse_dashboards
from twbdoc.parsers.datasources import parse_datasources
from twbdoc.parsers.filters import parse_shared_filters, parse_view_filters
from twbdoc.parsers.metadata import parse_metadata
from twbdoc.parsers.parameters import parse_parameters
from twbdoc.parsers.styles import parse_style_rules
from twbdoc.parsers.worksheets import parse_worksheets


class TestMetadata:
    def test_ワークブック属性を抽出する(self, minimal_root: ET.Element) -> None:
        meta = parse_metadata(minimal_root, "test.twbx")
        assert meta.source_file == "test.twbx"
        assert meta.version == "18.1"
        assert meta.source_build.startswith("2026.1.1")
        assert meta.source_platform == "win"


class TestParameters:
    def test_範囲型パラメーターを抽出する(self, minimal_root: ET.Element) -> None:
        parameters = parse_parameters(minimal_root)
        range_param = parameters[0]
        assert range_param.display_name == "上位顧客数"
        assert range_param.domain_type == "range"
        assert (range_param.range_min, range_param.range_max) == ("5", "20")
        assert range_param.granularity == "5"
        assert range_param.current_value == "5"

    def test_リスト型パラメーターの選択肢を抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        parameters = parse_parameters(minimal_root)
        list_param = parameters[1]
        assert list_param.domain_type == "list"
        assert [m.alias for m in list_param.members] == ["東", "西"]

    def test_パラメーターなしなら空タプル(self) -> None:
        root = ET.fromstring("<workbook><datasources/></workbook>")
        assert parse_parameters(root) == ()


class TestDatasources:
    def test_Parameters_擬似データソースを除外する(
        self, minimal_root: ET.Element
    ) -> None:
        datasources = parse_datasources(minimal_root)
        assert [ds.display_name for ds in datasources] == ["スーパーストア"]
        assert datasources[0].connection_class == "federated"

    def test_フィールドと別名を抽出する(self, minimal_root: ET.Element) -> None:
        fields = parse_datasources(minimal_root)[0].fields
        region = next(f for f in fields if f.caption == "地域")
        assert not region.is_calculated
        assert [(a.key, a.value) for a in region.aliases] == [
            ('"east"', "東地区"),
            ('"west"', "西地区"),
        ]


class TestCalculations:
    def test_計算フィールドを抽出する(self, minimal_root: ET.Element) -> None:
        fields = parse_calculated_fields(minimal_root)
        assert [f.display_name for f in fields] == ["利益率", "利益率判定"]
        assert fields[0].formula == "SUM([利益])/SUM([売上])"
        assert fields[0].datasource == "スーパーストア"

    def test_数式内の内部IDを表示名に置換する(
        self, minimal_root: ET.Element
    ) -> None:
        fields = parse_calculated_fields(minimal_root)
        resolved = fields[1].formula
        assert "[利益率]" in resolved
        assert "[Calculation_100]" not in resolved
        assert "[Parameters].[上位顧客数]" in resolved
        assert "[Calculation_100]" in fields[1].raw_formula

    def test_GUIコメントを抽出する(self, minimal_root: ET.Element) -> None:
        fields = parse_calculated_fields(minimal_root)
        assert fields[1].comment == "利益率のしきい値判定。設計意図のメモ。"
        assert fields[0].comment == ""

    def test_式内コメントを抽出する(self, minimal_root: ET.Element) -> None:
        fields = parse_calculated_fields(minimal_root)
        assert "しきい値は要件 #123 参照" in fields[1].inline_comments
        assert "暫定条件" in fields[1].inline_comments
        assert fields[0].inline_comments == ()

    def test_依存フィールドを抽出する(self, minimal_root: ET.Element) -> None:
        fields = parse_calculated_fields(minimal_root)
        assert fields[1].depends_on == ("[Calculation_100]", "[Parameter 1]")

    def test_長い内部IDから優先して置換する(self) -> None:
        caption_map = {"[Calc_1]": "[短い]", "[Calc_10]": "[長い]"}
        assert resolve_formula("[Calc_10]+[Calc_1]", caption_map) == "[長い]+[短い]"


class TestWorksheets:
    def test_ワークシートの基本情報を抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        worksheets = parse_worksheets(minimal_root)
        sheet = worksheets[0]
        assert sheet.name == "売上推移"
        assert sheet.title == "月別売上の推移"
        assert sheet.datasources == ("スーパーストア",)

    def test_使用データソースから_Parameters_を除外する(
        self, minimal_root: ET.Element
    ) -> None:
        worksheets = parse_worksheets(minimal_root)
        for sheet in worksheets:
            assert "Parameters" not in sheet.datasources

    def test_使用フィールドの内部名を抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        sheet = parse_worksheets(minimal_root)[0]
        assert "[Calculation_100]" in sheet.used_columns
        assert "[Parameter 1]" in sheet.used_columns
        assert "[Region]" in sheet.used_columns


class TestFilters:
    def test_カテゴリフィルターの保持メンバーを抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        worksheet = minimal_root.find("worksheets/worksheet")
        filters = parse_view_filters(worksheet)
        categorical = filters[0]
        assert categorical.filter_class == "categorical"
        assert categorical.members == ("East", "West")
        assert not categorical.excluded

    def test_数値範囲フィルターを抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        worksheet = minimal_root.find("worksheets/worksheet")
        filters = parse_view_filters(worksheet)
        quantitative = filters[1]
        assert quantitative.filter_class == "quantitative"
        assert (quantitative.min_value, quantitative.max_value) == ("0.0", "0.25")
        assert quantitative.included_values == "in-range"

    def test_除外フィルター_except_を抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        worksheet = minimal_root.findall("worksheets/worksheet")[1]
        filters = parse_view_filters(worksheet)
        assert filters[0].excluded
        assert filters[0].members == ("Central",)

    def test_共通フィルターとコンテキストを抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        shared = parse_shared_filters(minimal_root)
        assert len(shared) == 1
        assert shared[0].is_context
        assert shared[0].members == ("202607", "202608")

    def test_フィルターなしのワークシートは空タプル(self) -> None:
        worksheet = ET.fromstring(
            "<worksheet name='x'><table><view/></table></worksheet>"
        )
        assert parse_view_filters(worksheet) == ()


class TestDashboards:
    def test_サイズとゾーンツリーを抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        dashboard = parse_dashboards(minimal_root)[0]
        assert dashboard.name == "売上ダッシュボード"
        assert dashboard.size.sizing_mode == "fixed"
        assert (dashboard.size.minwidth, dashboard.size.minheight) == ("1200", "800")
        root_zone = dashboard.zones[0]
        assert root_zone.zone_type == "layout-basic"
        container = root_zone.children[0]
        assert container.zone_type == "layout-flow"
        assert container.param == "vert"
        types = [child.zone_type for child in container.children]
        assert types == ["title", "worksheet", "filter", "text"]

    def test_devicelayouts_のゾーンは含めない(
        self, minimal_root: ET.Element
    ) -> None:
        dashboard = parse_dashboards(minimal_root)[0]
        all_names = _collect_names(dashboard.zones)
        assert all_names.count("売上推移") == 1

    def test_テキストゾーンの本文を抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        dashboard = parse_dashboards(minimal_root)[0]
        container = dashboard.zones[0].children[0]
        text_zone = container.children[3]
        assert text_zone.text == "注釈テキスト"

    def test_座標を整数で保持する(self, minimal_root: ET.Element) -> None:
        dashboard = parse_dashboards(minimal_root)[0]
        worksheet_zone = dashboard.zones[0].children[0].children[1]
        assert (worksheet_zone.w, worksheet_zone.h) == (70000, 92000)


class TestStyles:
    def test_ワークブックとワークシートの書式を収集する(
        self, minimal_root: ET.Element
    ) -> None:
        rules = parse_style_rules(minimal_root)
        scopes = {f.scope for rule in rules for f in rule.formats}
        assert "ワークブック全体" in scopes
        assert "ワークシート: 売上推移" in scopes
        workbook_rule = next(r for r in rules if r.element == "all")
        assert ("font-family", "Meiryo UI") in [
            (f.attr, f.value) for f in workbook_rule.formats
        ]


class TestParseWorkbook:
    def test_全体を集約しダッシュボード配置を付与する(
        self, minimal_root: ET.Element
    ) -> None:
        workbook = parse_workbook(minimal_root, "test.twbx")
        placed = next(w for w in workbook.worksheets if w.name == "売上推移")
        alone = next(w for w in workbook.worksheets if w.name == "単独シート")
        assert placed.dashboards == ("売上ダッシュボード",)
        assert alone.dashboards == ()

    def test_空のワークブックでも解析できる(self) -> None:
        root = ET.fromstring("<workbook version='18.1'/>")
        workbook = parse_workbook(root, "empty.twb")
        assert workbook.datasources == ()
        assert workbook.dashboards == ()
        assert workbook.parameters == ()


def _collect_names(zones: tuple) -> list[str]:
    names: list[str] = []
    for zone in zones:
        if zone.name:
            names.append(zone.name)
        names.extend(_collect_names(zone.children))
    return names
