"""起動スクリプト (bat/ps1) のエンコーディング・構成検査。

Windows PowerShell 5.1 は BOM なしの .ps1 を ANSI (cp932) として読むため、
日本語文字列が壊れて構文エラーになる。ps1 は必ず UTF-8 BOM 付きで保存する。
逆に .bat は BOM があると cmd.exe が 1 行目を誤認識するため BOM なしとする。
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT_DIR / "app" / "python"
UTF8_BOM = b"\xef\xbb\xbf"


class TestScriptEncodings:
    def test_全ての_ps1_は_UTF8_BOM_付き(self) -> None:
        ps1_files = list(ROOT_DIR.rglob("*.ps1"))
        assert ps1_files, "ps1 ファイルが見つかりません"
        for ps1 in ps1_files:
            if "python" in ps1.parts:  # 同梱 Python 内は対象外
                continue
            raw = ps1.read_bytes()
            assert raw.startswith(UTF8_BOM), (
                f"{ps1.name} は UTF-8 BOM 付きで保存してください "
                "(Windows PowerShell 5.1 の文字化け対策)"
            )
            raw.decode("utf-8-sig")

    def test_bat_は_BOM_なし(self) -> None:
        raw = (ROOT_DIR / "generate_doc.bat").read_bytes()
        assert not raw.startswith(UTF8_BOM), (
            "generate_doc.bat に BOM を付けないでください "
            "(cmd.exe が 1 行目を誤認識するため)"
        )
        raw.decode("utf-8")


class TestLayout:
    def test_bat_のフォルダに_ps1_を置かない(self) -> None:
        """ビジネスユーザー向けに、bat のあるフォルダは bat + フォルダ構成を保つ。"""
        assert not list(ROOT_DIR.glob("*.ps1")), (
            "ps1 は app/ フォルダに置いてください (bat のあるフォルダには置かない)"
        )
        assert (ROOT_DIR / "app" / "generate_doc.ps1").exists()
        assert (ROOT_DIR / "app" / "twbdoc" / "__main__.py").exists()

    def test_bat_は_app_内の_ps1_を呼ぶ(self) -> None:
        content = (ROOT_DIR / "generate_doc.bat").read_text(encoding="utf-8")
        assert "app\\generate_doc.ps1" in content


class TestBundledPythonEncryptionSafety:
    """同梱 Python に、社内のファイル暗号化ソフトの対象になりやすい
    拡張子 (.zip / .txt) を残さない。暗号化されると Python が起動できなくなる。
    """

    def _require_bundled_python(self) -> None:
        if not PYTHON_DIR.is_dir():
            pytest.skip("同梱 Python は未配置です (setup_python.ps1 で作成)")

    def test_標準ライブラリの_zip_を含めない(self) -> None:
        self._require_bundled_python()
        assert not list(PYTHON_DIR.glob("python*.zip")), (
            "標準ライブラリは Lib フォルダへ展開してください "
            "(.zip のままだと暗号化ソフトで起動不能になる)"
        )
        assert (PYTHON_DIR / "Lib" / "encodings").is_dir()

    def test_txt_を含めない(self) -> None:
        self._require_bundled_python()
        assert not list(PYTHON_DIR.rglob("*.txt")), (
            ".txt は .dat にリネームしてください (暗号化ソフト対策)"
        )

    def test_pth_の先頭が_Lib(self) -> None:
        self._require_bundled_python()
        pth = next(PYTHON_DIR.glob("python*._pth"))
        lines = pth.read_text(encoding="ascii").split()
        assert lines[0] == "Lib"


class TestEncryptionGuidance:
    def test_起動スクリプトに標準ライブラリの事前確認がある(self) -> None:
        content = (ROOT_DIR / "app" / "generate_doc.ps1").read_text(
            encoding="utf-8-sig"
        )
        assert "import encodings" in content
        assert "exit 4" in content
