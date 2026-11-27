"""起動スクリプト (bat/ps1) のエンコーディング・構成検査。

Windows PowerShell 5.1 は BOM なしの .ps1 を ANSI (cp932) として読むため、
日本語文字列が壊れて構文エラーになる。ps1 は必ず UTF-8 BOM 付きで保存する。
逆に .bat は BOM があると cmd.exe が 1 行目を誤認識するため BOM なしとする。
"""

from __future__ import annotations

import sys
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


class TestLiveCiLauncher:
    """live_ci.ps1: Studio が使えなければ保存済みファイルの監視に切り替える。"""

    def _script(self) -> str:
        return (ROOT_DIR / "app" / "live_ci.ps1").read_text(encoding="utf-8-sig")

    def test_引数なしは_Studio_の状態を確かめる(self) -> None:
        script = self._script()
        assert "studio-status" in script
        assert "$probe.Available" in script

    def test_Studio_が無ければファイル選択に切り替える(self) -> None:
        script = self._script()
        assert "System.Windows.Forms.OpenFileDialog" in script
        assert "*.twbx;*.twb" in script
        # キャンセル時は使い方を出して終了する
        assert "exit 2" in script

    def test_オプションだけでも_Studio_の状態を確かめる(self) -> None:
        # ワークブックの有無で判定する (引数の有無ではない)
        assert "$hasWorkbook" in self._script()

    def test_引数を高度なスクリプトとして受けない(self) -> None:
        """[Parameter()] があると --out が -OutVariable と解釈されてエラーになる。"""
        script = self._script()
        assert "[Parameter(" not in script
        assert "$WatchArgs = @($args)" in script

    def test_ファイル選択ダイアログを最前面に出す(self) -> None:
        script = self._script()
        assert "$owner.TopMost = $true" in script
        assert "$owner.Show()" in script

    def test_Python_の出力を_UTF8_で受け取る(self) -> None:
        assert "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8" in self._script()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell が必要")
    def test_構文エラーがない(self) -> None:
        import subprocess

        command = (
            "$e=$null; $null=[System.Management.Automation.Language.Parser]::ParseFile("
            f"'{ROOT_DIR / 'app' / 'live_ci.ps1'}',[ref]$null,[ref]$e); $e.Count"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True, text=True, timeout=60,
        )
        assert result.stdout.strip() == "0", result.stdout + result.stderr
