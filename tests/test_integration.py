"""実サンプル twbx による E2E テスト (サンプルが無い環境ではスキップ)。"""

from __future__ import annotations

from pathlib import Path

import pytest

from twbdoc.cli import main


class TestEndToEnd:
    def test_サンプル_twbx_から設計書を生成できる(
        self, sample_twbx_paths: list[Path], tmp_path: Path
    ) -> None:
        if not sample_twbx_paths:
            pytest.skip("サンプル twbx が見つかりません")
        args = [str(p) for p in sample_twbx_paths] + [
            "--output",
            str(tmp_path),
            "--lang",
            "ja",
        ]
        assert main(args) == 0
        outputs = sorted(tmp_path.glob("*_Documentation_*/*_Documentation.md"))
        assert len(outputs) == len(sample_twbx_paths)
        for output in outputs:
            content = output.read_text(encoding="utf-8-sig")
            assert content.startswith("# ")
            assert "## 2. データソースと前処理" in content
            assert "## 3. ダッシュボード構成" in content
            assert "```mermaid" in content

    def test_存在しないファイルは_exit_code_2(self, tmp_path: Path) -> None:
        assert main([str(tmp_path / "nothing.twbx")]) == 2

    def test_複数ファイルで一部失敗しても残りは処理する(
        self, sample_twbx_paths: list[Path], tmp_path: Path
    ) -> None:
        if not sample_twbx_paths:
            pytest.skip("サンプル twbx が見つかりません")
        args = [
            str(tmp_path / "nothing.twbx"),
            str(sample_twbx_paths[0]),
            "--output",
            str(tmp_path),
        ]
        assert main(args) == 2
        assert list(tmp_path.glob("*_Documentation_*/*_Documentation.md"))

    def test_英語指定で英語の設計書が生成される(
        self, sample_twbx_paths: list[Path], tmp_path: Path
    ) -> None:
        if not sample_twbx_paths:
            pytest.skip("サンプル twbx が見つかりません")
        args = [
            str(sample_twbx_paths[0]),
            "--output",
            str(tmp_path),
            "--no-sample",
            "--lang",
            "en",
        ]
        assert main(args) == 0
        output = next(tmp_path.glob("*_Documentation_*/*_Documentation.md"))
        content = output.read_text(encoding="utf-8-sig")
        assert "## Contents" in content
        assert "## 1. Workbook Overview" in content
        assert "## 2. Data Sources and Preparation" in content
        assert "## 12. Health Check" in content
        assert "設計書" not in content

    def test_BOM_付き_UTF8_で出力される(
        self, sample_twbx_paths: list[Path], tmp_path: Path
    ) -> None:
        if not sample_twbx_paths:
            pytest.skip("サンプル twbx が見つかりません")
        main([str(sample_twbx_paths[0]), "--output", str(tmp_path)])
        output = next(tmp_path.glob("*_Documentation_*/*_Documentation.md"))
        assert output.read_bytes().startswith(b"\xef\xbb\xbf")

