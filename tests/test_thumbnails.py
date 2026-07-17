"""サムネイル抽出と出力フォルダ構成のテスト。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from conftest import MINIMAL_TWB
from twbdoc.cli import main
from twbdoc.thumbnails import extract_thumbnails, safe_filename

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class TestExtractThumbnails:
    def test_PNGサムネイルを名前付きで抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        thumbnails = extract_thumbnails(minimal_root)
        assert set(thumbnails) == {"売上ダッシュボード", "売上推移"}
        assert thumbnails["売上ダッシュボード"].startswith(PNG_MAGIC)

    def test_壊れたbase64は除外される(self, minimal_root: ET.Element) -> None:
        thumbnails = extract_thumbnails(minimal_root)
        assert "壊れたサムネイル" not in thumbnails

    def test_thumbnailsなしは空(self) -> None:
        root = ET.fromstring("<workbook />")
        assert extract_thumbnails(root) == {}


class TestSafeFilename:
    def test_windows禁止文字を置換する(self) -> None:
        assert safe_filename('売上/利益: "2026"') == "売上_利益_ _2026_"

    def test_空文字はフォールバック(self) -> None:
        assert safe_filename("///") != ""


class TestOutputFolderLayout:
    def _run(self, tmp_path: Path) -> Path:
        twb = tmp_path / "テスト.twb"
        twb.write_text(MINIMAL_TWB, encoding="utf-8")
        assert main([str(twb), "--no-sample"]) == 0
        date_label = datetime.now().strftime("%Y%m%d")
        return tmp_path / f"テスト_設計書_{date_label}"

    def test_日付付きフォルダにmdと画像が出力される(
        self, tmp_path: Path
    ) -> None:
        doc_dir = self._run(tmp_path)
        assert doc_dir.is_dir()
        markdown_path = doc_dir / "テスト_設計書.md"
        assert markdown_path.is_file()
        html_path = doc_dir / "テスト_設計書.html"
        assert html_path.is_file()
        html = html_path.read_text(encoding="utf-8")
        assert "mermaid.initialize" in html
        assert 'src="data:image/png;base64,' in html
        image_path = doc_dir / "images" / "売上ダッシュボード.png"
        assert image_path.is_file()
        assert image_path.read_bytes().startswith(PNG_MAGIC)
        # ワークシートのサムネイルは出力しない (ダッシュボードのみ)
        assert not (doc_dir / "images" / "売上推移.png").exists()

    def test_設計書にダッシュボード画像とバージョンが載る(
        self, tmp_path: Path
    ) -> None:
        from twbdoc import __version__

        doc_dir = self._run(tmp_path)
        content = (doc_dir / "テスト_設計書.md").read_text(encoding="utf-8-sig")
        assert "![売上ダッシュボード](images/売上ダッシュボード.png)" in content
        assert f"- 生成ツール: tableau-workbook-documenter v{__version__}" in content

    def test_サムネイル注釈とレイアウト簡略図が載る(
        self, tmp_path: Path
    ) -> None:
        doc_dir = self._run(tmp_path)
        content = (doc_dir / "テスト_設計書.md").read_text(encoding="utf-8-sig")
        assert "※ 画像はサムネイルであり、実際のダッシュボード全体画像ではありません。" in content
        assert "![売上ダッシュボード レイアウト](images/layout_売上ダッシュボード.svg)" in content
        svg_path = doc_dir / "images" / "layout_売上ダッシュボード.svg"
        assert svg_path.is_file()
        assert svg_path.read_text(encoding="utf-8").startswith("<svg ")
        # レイアウト図がある場合は Mermaid のゾーン図は出さない
        assert "graph TD" not in content

    def test_サムネイルなしではPNGを出力しない(
        self, tmp_path: Path
    ) -> None:
        twb = tmp_path / "画像なし.twb"
        twb.write_text(
            MINIMAL_TWB.replace("<thumbnails>", "<thumbnails-disabled>").replace(
                "</thumbnails>", "</thumbnails-disabled>"
            ),
            encoding="utf-8",
        )
        assert main([str(twb), "--no-sample"]) == 0
        date_label = datetime.now().strftime("%Y%m%d")
        doc_dir = tmp_path / f"画像なし_設計書_{date_label}"
        content = (doc_dir / "画像なし_設計書.md").read_text(encoding="utf-8-sig")
        assert not list((doc_dir / "images").glob("*.png"))
        assert "サムネイルであり" not in content
        # レイアウト簡略図はサムネイルが無くても生成される
        assert list((doc_dir / "images").glob("layout_*.svg"))
