"""Tableau Agent スキル用: 開いているワークブックを twbdoc で検査し JSON を出力する。

Tableau Agent は install_skill.ps1 が書き出す run_ci.cmd 経由でこれを実行する。
twbdoc の app フォルダは、同じく install_skill.ps1 が書き出す config.json の
"twbdoc_app" で指定する (環境変数 TWBDOC_APP でも上書きできる)。

終了コード: 0 = 検出なし/警告のみ, 5 = エラーあり, 6 = Studio に接続できない,
            3 = twbdoc が見つからない
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _twbdoc_app() -> Path | None:
    override = os.environ.get("TWBDOC_APP")
    if override:
        return Path(override)
    config = Path(__file__).resolve().parent / "config.json"
    try:
        return Path(json.loads(config.read_text(encoding="utf-8-sig"))["twbdoc_app"])
    except (OSError, ValueError, KeyError):
        return None


def main() -> int:
    app = _twbdoc_app()
    if app is None or not (app / "twbdoc" / "__init__.py").is_file():
        print(
            "twbdoc was not found. Double-click install_skill.bat in the twbdoc "
            "folder again, or set TWBDOC_APP to its app folder.",
            file=sys.stderr,
        )
        return 3
    sys.path.insert(0, str(app))
    from twbdoc.cli import main as twbdoc_main

    args = ["check", "--studio", "--format", "json", "--fail-on", "error", *sys.argv[1:]]
    return twbdoc_main(args)


if __name__ == "__main__":
    sys.exit(main())
