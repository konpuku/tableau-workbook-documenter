"""コマンドラインインターフェース。

使い方:
    python -m twbdoc <file.twbx> [<file2.twb> ...] [--output <dir>]

各入力ファイルと同じフォルダ (または --output 指定先) に
「<ファイル名>_設計書.md」を UTF-8 (BOM 付き) で出力する。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .errors import InvalidFileError, ParseError, TwbDocError
from .loader import load_workbook_xml
from .parsers import parse_workbook
from .renderers import render
from .sampler import collect_samples

EXIT_OK = 0
EXIT_PARSE_ERROR = 1
EXIT_INPUT_ERROR = 2

OUTPUT_SUFFIX = "_設計書.md"


def main(argv: list[str] | None = None) -> int:
    """エントリポイント。成功 0 / 解析エラー 1 / 入力エラー 2 を返す。"""
    _configure_stdout()
    args = _parse_args(argv)
    exit_code = EXIT_OK
    for input_path in args.files:
        code = _process_file(Path(input_path), args.output, args.no_sample)
        exit_code = max(exit_code, code)
    return exit_code


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="twbdoc",
        description="Tableau ワークブック (.twbx/.twb) から設計書 Markdown を生成します。",
    )
    parser.add_argument("files", nargs="+", help="入力ファイル (.twbx / .twb)")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="出力先フォルダ (省略時は入力ファイルと同じフォルダ)",
    )
    parser.add_argument(
        "--no-sample",
        action="store_true",
        help="フィールドのサンプル値取得をスキップする",
    )
    parser.add_argument(
        "--version", action="version", version=f"twbdoc {__version__}"
    )
    return parser.parse_args(argv)


def _process_file(
    input_path: Path, output_dir: Path | None, no_sample: bool = False
) -> int:
    try:
        root = load_workbook_xml(input_path)
        workbook = parse_workbook(root, source_file=input_path.name)
        samples = None if no_sample else collect_samples(input_path)
        markdown = render(workbook, samples=samples)
        output_path = _resolve_output_path(input_path, output_dir)
        _write_output(output_path, markdown)
    except InvalidFileError as error:
        print(f"[エラー] {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except ParseError as error:
        print(f"[エラー] {error}", file=sys.stderr)
        return EXIT_PARSE_ERROR
    except TwbDocError as error:
        print(f"[エラー] {error}", file=sys.stderr)
        return EXIT_PARSE_ERROR
    except Exception as error:  # 想定外の例外もトレースバックを見せず日本語で報告する
        print(
            f"[エラー] 予期しないエラーが発生しました ({input_path.name}): "
            f"{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return EXIT_PARSE_ERROR
    print(f"[完了] {input_path.name} -> {output_path}")
    return EXIT_OK


def _resolve_output_path(input_path: Path, output_dir: Path | None) -> Path:
    directory = output_dir if output_dir is not None else input_path.parent
    return directory / f"{input_path.stem}{OUTPUT_SUFFIX}"


def _write_output(output_path: Path, markdown: str) -> None:
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8-sig")
    except OSError as error:
        raise InvalidFileError(
            f"出力ファイルを書き込めません: {output_path} ({error})"
        ) from error


def _configure_stdout() -> None:
    """cp932 コンソールでも文字化けしないよう UTF-8 に再設定する。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
