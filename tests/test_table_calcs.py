"""表計算設定 (パーサー + レンダラー) のテスト。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from twbdoc.parsers import parse_workbook
from twbdoc.parsers.calculations import parse_calculated_fields
from twbdoc.parsers.worksheets import parse_worksheets
from twbdoc.renderers.table_calcs import render_table_calcs


class TestParsePillTableCalcs:
    def test_ピルごとの表計算を抽出する(self, minimal_root: ET.Element) -> None:
        sheet = parse_worksheets(minimal_root)[0]
        assert len(sheet.table_calcs) == 2
        by_ref = {pill.column_ref: pill for pill in sheet.table_calcs}
        sales = by_ref["[Sales]"]
        assert sales.derivation == "Sum"
        assert sales.table_calc.calc_type == "PctTotal"
        assert sales.table_calc.ordering_type == "Columns"

    def test_column定義とcolumn_instanceは重複しない(
        self, minimal_root: ET.Element
    ) -> None:
        # [Calculation_300] はシート内に column 定義と column-instance の
        # 両方で table-calc を持つが、1 ピルとしてのみ抽出される
        sheet = parse_worksheets(minimal_root)[0]
        refs = [pill.column_ref for pill in sheet.table_calcs]
        assert refs.count("[Calculation_300]") == 1

    def test_表計算なしのシートは空(self, minimal_root: ET.Element) -> None:
        sheet = parse_worksheets(minimal_root)[1]
        assert sheet.table_calcs == ()


class TestParseFieldDefaultTableCalc:
    def test_フィールド既定の表計算を抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        fields = {
            calc.display_name: calc
            for calc in parse_calculated_fields(minimal_root)
        }
        table_calc = fields["移動平均売上"].table_calc
        assert table_calc is not None
        assert table_calc.ordering_type == "Field"
        assert table_calc.order_fields == (
            "[superstore-federated].[none:Region:nk]",
            "[superstore-federated].[Sales]",
        )

    def test_表計算なしの計算フィールドはNone(
        self, minimal_root: ET.Element
    ) -> None:
        fields = {
            calc.display_name: calc
            for calc in parse_calculated_fields(minimal_root)
        }
        assert fields["利益率"].table_calc is None


class TestRenderTableCalcs:
    def _render(self, minimal_root: ET.Element) -> str:
        workbook = parse_workbook(minimal_root, "test.twbx")
        caption_map = {
            "[Sales]": "[売上高]",
            "[Region]": "[地域]",
            "[Calculation_300]": "[移動平均売上]",
        }
        return "\n".join(render_table_calcs(workbook, caption_map, 9))

    def test_章とピルごとの設定が出る(self, minimal_root: ET.Element) -> None:
        text = self._render(minimal_root)
        assert "## 9. 表計算設定" in text
        assert "### 9.1 ピルごとの設定 (シート別)" in text
        assert "| 売上推移 | 売上高 | 合計 | 合計に対する割合 [PctTotal] | 表 (下) [Columns] |" in text

    def test_フィールド既定の設定が出る(self, minimal_root: ET.Element) -> None:
        text = self._render(minimal_root)
        assert "### 9.2 フィールド既定の設定" in text
        assert "特定のディメンション: 地域 → 売上高" in text
        assert "式による表計算" in text

    def test_表計算なしは該当なし(self) -> None:
        from twbdoc.model import Workbook, WorkbookMeta

        workbook = Workbook(meta=WorkbookMeta(source_file="x.twbx"))
        text = "\n".join(render_table_calcs(workbook, {}, 9))
        assert "(該当なし)" in text
