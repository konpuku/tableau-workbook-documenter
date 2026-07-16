"""コマンドラインインターフェース。

使い方:
    python -m twbdoc <file.twbx> [<file2.twb> ...] [--output <dir>]

各入力ファイルと同じフォルダ (または --output 指定先) に
「<ファイル名>_設計書_yyyymmdd」フォルダを作成し、その中に
「<ファイル名>_設計書.md」(UTF-8 BOM 付き) と、ダッシュボードの
プレビュー画像 (images サブフォルダ) を出力する。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from . import __version__
from .errors import InvalidFileError, ParseError, TwbDocError
from .loader import load_workbook_xml
from .model import Workbook
from .parsers import parse_workbook
from .renderers import render
from .sampler import collect_samples
from .thumbnails import extract_thumbnails, safe_filename

EXIT_OK = 0
EXIT_PARSE_ERROR = 1
EXIT_INPUT_ERROR = 2

OUTPUT_SUFFIX = "_設計書"
IMAGES_DIR_NAME = "images"


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
        help="設計書フォルダの作成先 (省略時は入力ファイルと同じフォルダ)",
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
        generated_at = datetime.now()
        root = load_workbook_xml(input_path)
        workbook = parse_workbook(root, source_file=input_path.name)
        samples = None if no_sample else collect_samples(input_path)
        doc_dir = _resolve_output_dir(input_path, output_dir, generated_at)
        workbook = _attach_dashboard_images(
            workbook, extract_thumbnails(root), doc_dir
        )
        markdown = render(workbook, generated_at=generated_at, samples=samples)
        output_path = doc_dir / f"{input_path.stem}{OUTPUT_SUFFIX}.md"
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


def _resolve_output_dir(
    input_path: Path, output_dir: Path | None, generated_at: datetime
) -> Path:
    """設計書一式を格納する日付付きフォルダのパスを返す。"""
    base = output_dir if output_dir is not None else input_path.parent
    date_label = generated_at.strftime("%Y%m%d")
    return base / f"{input_path.stem}{OUTPUT_SUFFIX}_{date_label}"


def _attach_dashboard_images(
    workbook: Workbook, thumbnails: dict[str, bytes], doc_dir: Path
) -> Workbook:
    """ダッシュボードのサムネイル PNG を書き出し、image_path を設定する。

    サムネイルが無いダッシュボードはそのまま (画像なしで) 出力する。
    """
    if not workbook.dashboards or not thumbnails:
        return workbook
    used_names: set[str] = set()
    dashboards = []
    for dashboard in workbook.dashboards:
        data = thumbnails.get(dashboard.name)
        if data is None:
            dashboards.append(dashboard)
            continue
        filename = _unique_filename(safe_filename(dashboard.name), used_names)
        _write_image(doc_dir / IMAGES_DIR_NAME / filename, data)
        dashboards.append(
            replace(dashboard, image_path=f"{IMAGES_DIR_NAME}/{filename}")
        )
    return replace(workbook, dashboards=tuple(dashboards))


def _unique_filename(base: str, used_names: set[str]) -> str:
    """サニタイズ後の名前衝突を連番で回避する。"""
    candidate = f"{base}.png"
    counter = 2
    while candidate in used_names:
        candidate = f"{base}_{counter}.png"
        counter += 1
    used_names.add(candidate)
    return candidate


def _write_image(path: Path, data: bytes) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except OSError as error:
        raise InvalidFileError(
            f"画像ファイルを書き込めません: {path} ({error})"
        ) from error


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
