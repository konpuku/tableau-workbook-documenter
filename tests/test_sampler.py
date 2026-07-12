"""sampler.py のテスト (CSV/XLSX は自作 twbx、hyper は実サンプルで検証)。"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from twbdoc.sampler import SampleResult, TableSamples, collect_samples, find_values

from conftest import MINIMAL_TWB, SAMPLES_DIR


def _make_twbx_with_csv(tmp_path: Path) -> Path:
    path = tmp_path / "with_csv.twbx"
    csv_body = "地域,売上\n東,100\n西,200\n東,100\n南,300\n"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("book.twb", MINIMAL_TWB)
        archive.writestr("Data/sales.csv", csv_body.encode("utf-8-sig"))
    return path


def _make_xlsx_bytes() -> bytes:
    shared = (
        "<?xml version='1.0'?>"
        "<sst xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
        "<si><t>Category</t></si><si><t>Furniture</t></si><si><t>Office</t></si>"
        "</sst>"
    )
    sheet = (
        "<?xml version='1.0'?>"
        "<worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'>"
        "<sheetData>"
        "<row><c t='s'><v>0</v></c></row>"
        "<row><c t='s'><v>1</v></c></row>"
        "<row><c t='s'><v>2</v></c></row>"
        "<row><c t='s'><v>1</v></c></row>"
        "</sheetData></worksheet>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as workbook:
        workbook.writestr("xl/sharedStrings.xml", shared)
        workbook.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


class TestCollectSamples:
    def test_CSV_から重複除外した代表値を取得する(self, tmp_path: Path) -> None:
        result = collect_samples(_make_twbx_with_csv(tmp_path))
        table = result.tables[0]
        assert table.columns["地域"] == ("東", "西", "南")
        assert table.columns["売上"] == ("100", "200", "300")

    def test_XLSX_から値を取得する(self, tmp_path: Path) -> None:
        path = tmp_path / "with_xlsx.twbx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("book.twb", MINIMAL_TWB)
            archive.writestr("Data/data.xlsx", _make_xlsx_bytes())
        result = collect_samples(path)
        table = result.tables[0]
        assert table.columns["Category"] == ("Furniture", "Office")

    def test_旧Excel形式は注記を出す(self, tmp_path: Path) -> None:
        path = tmp_path / "with_xls.twbx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("book.twb", MINIMAL_TWB)
            archive.writestr("Data/old.xls", b"\xd0\xcf\x11\xe0dummy")
        result = collect_samples(path)
        assert any(".xls" in note for note in result.notes)
        assert result.tables == ()

    def test_twb_単体は注記のみ(self, tmp_path: Path) -> None:
        path = tmp_path / "plain.twb"
        path.write_text(MINIMAL_TWB, encoding="utf-8")
        result = collect_samples(path)
        assert result.tables == ()
        assert any("同梱" in note for note in result.notes)

    def test_hyper_からの取得_実サンプル(self) -> None:
        pytest.importorskip("tableauhyperapi")
        twbx = SAMPLES_DIR / "#WOW2026 W14_Can you calculate the correct metric.twbx"
        if not twbx.exists():
            pytest.skip("サンプル twbx が見つかりません")
        result = collect_samples(twbx)
        assert result.tables
        columns = result.tables[0].columns
        assert "Ship Mode" in columns
        assert len(columns["Ship Mode"]) <= 5
        assert columns["Ship Mode"]


class TestFindValues:
    def _samples(self) -> SampleResult:
        return SampleResult(
            tables=(
                TableSamples(
                    name='"Extract"."Author_OBJID1"',
                    columns={"AuthID": ("a1", "a2")},
                ),
                TableSamples(
                    name='"Extract"."Book_OBJID2"',
                    columns={"AuthID": ("b1",), "Title": ("t1",)},
                ),
            )
        )

    def test_object_id_が一致するテーブルを優先する(self) -> None:
        assert find_values(self._samples(), "Book_OBJID2", "AuthID") == ("b1",)

    def test_object_id_不一致なら全テーブルから探す(self) -> None:
        assert find_values(self._samples(), "Unknown", "Title") == ("t1",)

    def test_大文字小文字を無視して照合する(self) -> None:
        assert find_values(self._samples(), "", "authid") == ("a1", "a2")

    def test_見つからなければ空タプル(self) -> None:
        assert find_values(self._samples(), "", "None") == ()
