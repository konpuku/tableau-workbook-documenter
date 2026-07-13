"""起動スクリプト (bat/ps1) のエンコーディング・構成検査。

Windows PowerShell 5.1 は BOM なしの .ps1 を ANSI (cp932) として読むため、
日本語文字列が壊れて構文エラーになる。ps1 は必ず UTF-8 BOM 付きで保存する。
逆に .bat は BOM があると cmd.exe が 1 行目を誤認識するため BOM なしとする。
"""

from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
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
