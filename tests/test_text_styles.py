"""フォントの設定の解析 (parsers/text_styles.py) と書式の一貫性ルールのテスト。"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from twbdoc.ci.config import load_config
from twbdoc.ci.rules import SEVERITY_INFO, SEVERITY_WARNING, run_checks
from twbdoc.ci.style_rules import StyleConfig, font_family
from twbdoc.errors import InvalidFileError
from twbdoc.i18n import EN
from twbdoc.model import TextStyle, Workbook, WorkbookMeta
from twbdoc.parsers import parse_workbook
from twbdoc.parsers.text_styles import parse_text_styles


def _title(size: str, subtitle_size: str | None = None, font: str = "Tableau Book") -> str:
    runs = f"<run fontsize='{size}' fontname='{font}'>Sales&#10;</run>"
    if subtitle_size:
        runs += f"<run fontsize='{subtitle_size}'>Æ&#10;</run><run fontsize='{subtitle_size}'>by region</run>"
    return f"<layout-options><title><formatted-text>{runs}</formatted-text></title></layout-options>"


def _workbook_xml(sheets: str, dashboards: str = "", style: str = "") -> ET.Element:
    return ET.fromstring(
        f"<workbook>{style}<worksheets>{sheets}</worksheets>"
        f"<dashboards>{dashboards}</dashboards></workbook>"
    )


class TestParse:
    def test_タイトルは見出しのサイズ_副題は見ない(self) -> None:
        root = _workbook_xml(f"<worksheet name='A'>{_title('16', subtitle_size='10')}</worksheet>")
        (style,) = parse_text_styles(root)
        assert (style.role, style.owner_kind, style.owner) == ("worksheet-title", "worksheet", "A")
        assert style.font_size == 16
        assert style.font_names == ("Tableau Book",)

    def test_ツールヒントは文字数が最も多いサイズ(self) -> None:
        root = _workbook_xml(
            "<worksheet name='A'><table><panes><pane><customized-tooltip><formatted-text>"
            "<run fontsize='9'>Sales:</run><run fontsize='12'>&lt;SUM(Sales)&gt; and more text</run>"
            "<run fontsize='9'>Æ&#10;</run>"
            "</formatted-text></customized-tooltip></pane></panes></table></worksheet>"
        )
        (style,) = parse_text_styles(root)
        assert style.role == "tooltip"
        assert style.font_size == 12

    def test_ダッシュボードのテキストとタイトル_デバイスレイアウトは除く(self) -> None:
        root = _workbook_xml(
            "",
            "<dashboard name='D'>"
            "<layout-options><title><formatted-text><run fontsize='20'>Overview</run></formatted-text></title></layout-options>"
            "<zones><zone><zone type-v2='text'><formatted-text><run fontsize='11'>Note</run></formatted-text></zone></zone></zones>"
            "<devicelayouts><devicelayout><zones><zone><formatted-text><run fontsize='8'>x</run></formatted-text></zone></zones></devicelayout></devicelayouts>"
            "</dashboard>",
        )
        roles = {(s.role, s.font_size) for s in parse_text_styles(root)}
        assert roles == {("dashboard-title", 20), ("dashboard-text", 11)}

    def test_書式ルールのサイズとフォント名(self) -> None:
        root = _workbook_xml(
            "<worksheet name='A'><table><style><style-rule element='axis-title'>"
            "<format attr='font-size' value='9' /><format attr='font-family' value='Meiryo UI' />"
            "</style-rule><style-rule element='cell'><format attr='color' value='#000' /></style-rule>"
            "</style></table></worksheet>",
            style="<style><style-rule element='all'><format attr='font-family' value='Tableau Book' /></style-rule></style>",
        )
        styles = parse_text_styles(root)
        assert TextStyle("all", "workbook", "", "format", None, ("Tableau Book",)) in styles
        assert TextStyle("axis-title", "worksheet", "A", "format", 9, ("Meiryo UI",)) in styles
        assert len(styles) == 2  # フォントの指定が無い書式ルールは含めない

    def test_サイズ指定の無いテキストは含めない(self) -> None:
        root = _workbook_xml(
            "<worksheet name='A'><layout-options><title><formatted-text><run>Sales</run>"
            "</formatted-text></title></layout-options></worksheet>"
        )
        assert parse_text_styles(root) == ()

    def test_parse_workbook_に含まれる(self, minimal_root) -> None:
        assert isinstance(parse_workbook(minimal_root, "x.twb").text_styles, tuple)


def _wb(*styles: TextStyle) -> Workbook:
    return Workbook(meta=WorkbookMeta(source_file="x.twb"), text_styles=styles)


def _title_style(owner: str, size: float, font: str = "Tableau Book") -> TextStyle:
    return TextStyle("worksheet-title", "worksheet", owner, "text", size, (font,))


def _findings(workbook: Workbook, rule: str, config=None):
    return [f for f in run_checks(workbook, EN, config=config) if f.rule == rule]


class TestFontSize:
    def test_多数派と違うシートを指摘する(self) -> None:
        workbook = _wb(_title_style("A", 14), _title_style("B", 14), _title_style("C", 18))
        (finding,) = _findings(workbook, "inconsistent-font-size")
        assert finding.severity == SEVERITY_INFO
        assert finding.target == "C / worksheet title"
        assert "18pt" in finding.message and "14pt" in finding.message

    def test_そろっていれば指摘しない(self) -> None:
        workbook = _wb(_title_style("A", 14), _title_style("B", 14))
        assert _findings(workbook, "inconsistent-font-size") == []

    def test_多数派が決まらなければ役割単位で1件(self) -> None:
        workbook = _wb(_title_style("A", 14), _title_style("B", 18))
        (finding,) = _findings(workbook, "inconsistent-font-size")
        assert finding.target == "worksheet title"
        assert "14pt (A)" in finding.message and "18pt (B)" in finding.message

    def test_チームの基準と違えば警告(self) -> None:
        config = load_config(None)
        config = type(config)(style=StyleConfig(font_sizes={"worksheet-title": 16}))
        workbook = _wb(_title_style("A", 14), _title_style("B", 16))
        (finding,) = _findings(workbook, "inconsistent-font-size", config)
        assert finding.severity == SEVERITY_WARNING
        assert finding.target == "A / worksheet title"

    def test_意図して変えることが多い役割は既定では見ない(self) -> None:
        workbook = _wb(
            TextStyle("dashboard-text", "dashboard", "D", "text", 30),
            TextStyle("dashboard-text", "dashboard", "E", "text", 10),
            TextStyle("mark-label", "worksheet", "A", "text", 8),
            TextStyle("mark-label", "worksheet", "B", "text", 20),
        )
        assert _findings(workbook, "inconsistent-font-size") == []

    def test_同じシートの複数のツールヒントは1件として数える(self) -> None:
        tooltip = lambda owner, size: TextStyle("tooltip", "worksheet", owner, "text", size)  # noqa: E731
        workbook = _wb(tooltip("A", 10), tooltip("A", 12), tooltip("B", 10), tooltip("C", 10))
        assert _findings(workbook, "inconsistent-font-size") == []


class TestFontFamily:
    def test_大文字小文字の表記ゆれ(self) -> None:
        workbook = _wb(_title_style("A", 14, "Tableau Medium"), _title_style("B", 14, "Tableau medium"))
        (finding,) = _findings(workbook, "inconsistent-font-family")
        assert finding.target == "Tableau Medium / Tableau medium"

    def test_太さ違いは同じファミリーとみなす(self) -> None:
        assert font_family("Tableau Semibold") == font_family("Tableau Book") == "tableau"
        assert font_family("Meiryo UI Bold") == "meiryo ui"
        workbook = _wb(*[
            _title_style(name, 14, f"Tableau {weight}")
            for name, weight in zip("ABCDE", ["Book", "Light", "Medium", "Semibold", "Bold"])
        ])
        assert _findings(workbook, "inconsistent-font-family") == []

    def test_ファミリーが多すぎれば指摘(self) -> None:
        fonts = ["Tableau Book", "Meiryo UI", "Arial", "Georgia"]
        workbook = _wb(*[_title_style(n, 14, f) for n, f in zip("ABCD", fonts)])
        (finding,) = _findings(workbook, "inconsistent-font-family")
        assert "4 font families" in finding.message

    def test_許可リストにないフォントは警告(self) -> None:
        config = type(load_config(None))(style=StyleConfig(font_families=("Meiryo UI",)))
        workbook = _wb(_title_style("A", 14, "Meiryo UI"), _title_style("B", 14, "Arial"))
        (finding,) = _findings(workbook, "inconsistent-font-family", config)
        assert finding.severity == SEVERITY_WARNING
        assert finding.target == "Arial"
        assert "B" in finding.message


class TestStyleConfig:
    def _load(self, tmp_path: Path, style: dict):
        path = tmp_path / ".twbdoc.json"
        path.write_text(json.dumps({"style": style}), encoding="utf-8")
        return load_config(path)

    def test_読み込み(self, tmp_path: Path) -> None:
        config = self._load(tmp_path, {
            "font_families": ["Meiryo UI"],
            "font_sizes": {"worksheet-title": 14, "format:axis-title": "9"},
            "max_font_families": 2,
        })
        assert config.style.font_families == ("Meiryo UI",)
        assert config.style.font_sizes == {"worksheet-title": 14.0, "format:axis-title": 9.0}
        assert config.style.max_font_families == 2

    @pytest.mark.parametrize("style", [
        {"font_sizes": {"unknown-role": 12}},
        {"font_sizes": {"tooltip": "big"}},
        {"font_sizes": {"tooltip": 0}},
        {"font_families": "Meiryo UI"},
        {"max_font_families": 0},
        "not an object",
    ])
    def test_不正な設定はエラー(self, tmp_path: Path, style) -> None:
        with pytest.raises(InvalidFileError):
            self._load(tmp_path, style)
