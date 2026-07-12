"""loader.py のテスト。"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from twbdoc.errors import InvalidFileError, ParseError
from twbdoc.loader import load_workbook_xml

from conftest import MINIMAL_TWB


def _make_twb(tmp_path: Path, name: str = "test.twb") -> Path:
    path = tmp_path / name
    path.write_text(MINIMAL_TWB, encoding="utf-8")
    return path


def _make_twbx(tmp_path: Path, twb_entry: str, name: str = "test.twbx") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(twb_entry, MINIMAL_TWB)
        archive.writestr("Data/dummy.hyper", b"dummy")
    return path


class TestLoadTwb:
    def test_twb_直接指定で読める(self, tmp_path: Path) -> None:
        root = load_workbook_xml(_make_twb(tmp_path))
        assert root.tag == "workbook"
        assert root.get("version") == "18.1"

    def test_日本語ファイル名の_twb_を読める(self, tmp_path: Path) -> None:
        root = load_workbook_xml(_make_twb(tmp_path, "日本語ブック.twb"))
        assert root.tag == "workbook"

    def test_不正な_XML_は_ParseError(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.twb"
        path.write_text("<workbook><unclosed>", encoding="utf-8")
        with pytest.raises(ParseError):
            load_workbook_xml(path)


class TestLoadTwbx:
    def test_twbx_から_twb_を読める(self, tmp_path: Path) -> None:
        root = load_workbook_xml(_make_twbx(tmp_path, "book.twb"))
        assert root.tag == "workbook"

    def test_日本語エントリ名でも拡張子検索で読める(self, tmp_path: Path) -> None:
        root = load_workbook_xml(_make_twbx(tmp_path, "日本語ブック.twb"))
        assert root.tag == "workbook"

    def test_ルートに近い_twb_を優先する(self, tmp_path: Path) -> None:
        path = tmp_path / "nested.twbx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("Data/backup/old.twb", "<workbook version='old'/>")
            archive.writestr("main.twb", MINIMAL_TWB)
        root = load_workbook_xml(path)
        assert root.get("version") == "18.1"

    def test_twb_が無い_twbx_は_InvalidFileError(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.twbx"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("Data/dummy.hyper", b"dummy")
        with pytest.raises(InvalidFileError, match="twb が見つかりません"):
            load_workbook_xml(path)

    def test_ZIP_破損は_InvalidFileError(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.twbx"
        path.write_bytes(b"this is not a zip file")
        with pytest.raises(InvalidFileError, match="壊れています"):
            load_workbook_xml(path)

    def test_展開後サイズ上限を超えると_InvalidFileError(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import twbdoc.loader as loader_module

        monkeypatch.setattr(loader_module, "MAX_TWB_UNCOMPRESSED_BYTES", 10)
        with pytest.raises(InvalidFileError, match="上限を超えています"):
            load_workbook_xml(_make_twbx(tmp_path, "book.twb"))


class TestXmlSafety:
    def test_DOCTYPE_を含む_XML_は拒否する(self, tmp_path: Path) -> None:
        path = tmp_path / "evil.twb"
        path.write_text(
            "<?xml version='1.0'?><!DOCTYPE workbook [<!ENTITY x 'y'>]>"
            "<workbook>&x;</workbook>",
            encoding="utf-8",
        )
        with pytest.raises(ParseError, match="非対応"):
            load_workbook_xml(path)


class TestValidation:
    def test_存在しないファイルは_InvalidFileError(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidFileError, match="見つかりません"):
            load_workbook_xml(tmp_path / "nothing.twbx")

    def test_対応外の拡張子は_InvalidFileError(self, tmp_path: Path) -> None:
        path = tmp_path / "doc.xlsx"
        path.write_text("x", encoding="utf-8")
        with pytest.raises(InvalidFileError, match="対応していない拡張子"):
            load_workbook_xml(path)

    def test_ディレクトリ指定は_InvalidFileError(self, tmp_path: Path) -> None:
        with pytest.raises(InvalidFileError):
            load_workbook_xml(tmp_path)
