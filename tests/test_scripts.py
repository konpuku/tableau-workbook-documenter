"""起動スクリプト (bat/ps1) のエンコーディング検査。

Windows PowerShell 5.1 は BOM なしの .ps1 を ANSI (cp932) として読むため、
日本語文字列が壊れて構文エラーになる。ps1 は必ず UTF-8 BOM 付きで保存する。
逆に .bat は BOM があると cmd.exe が 1 行目を誤認識するため BOM なしとする。
"""

from __future__ import annotations

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
UTF8_BOM = b"\xef\xbb\xbf"


class TestScriptEncodings:
    def test_ps1_は_UTF8_BOM_付き(self) -> None:
        raw = (SCRIPT_DIR / "generate_doc.ps1").read_bytes()
        assert raw.startswith(UTF8_BOM), (
            "generate_doc.ps1 は UTF-8 BOM 付きで保存してください "
            "(Windows PowerShell 5.1 の文字化け対策)"
        )
        raw.decode("utf-8-sig")

    def test_bat_は_BOM_なし(self) -> None:
        raw = (SCRIPT_DIR / "generate_doc.bat").read_bytes()
        assert not raw.startswith(UTF8_BOM), (
            "generate_doc.bat に BOM を付けないでください "
            "(cmd.exe が 1 行目を誤認識するため)"
        )
        raw.decode("utf-8")
