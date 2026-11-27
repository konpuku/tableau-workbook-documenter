"""サブコマンド `check` (CI チェック) と `watch` (ライブ監視)。

    python -m twbdoc check book.twbx [--format text|json|md] [--fail-on warning]
    python -m twbdoc check --studio --format json      # 編集中のワークブックを検査
    python -m twbdoc watch                              # Tableau Studio を監視
    python -m twbdoc watch book.twbx                    # 保存済みファイルを監視

既存の `python -m twbdoc <files>` (設計書生成) はそのまま動く。
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from .ci.config import FAIL_ON_CHOICES, find_config, load_config, should_fail
from .ci.report import to_json, to_markdown, to_report_dict, to_text
from .ci.rules import run_checks, studio_invalid_fields
from .errors import InvalidFileError, TwbDocError
from .i18n import LANGUAGE_CHOICES, Translator, get_translator
from .loader import load_workbook_xml, parse_workbook_xml_bytes
from .parsers import parse_workbook

EXIT_OK = 0
EXIT_PARSE_ERROR = 1
EXIT_INPUT_ERROR = 2
EXIT_CHECK_FAILED = 5
EXIT_STUDIO_UNAVAILABLE = 6

SUBCOMMANDS = ("check", "watch")


def run_subcommand(argv: list[str]) -> int:
    command, rest = argv[0], argv[1:]
    if command == "check":
        return check_main(rest)
    return watch_main(rest)


# --- check -----------------------------------------------------------------


def _check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="twbdoc check",
        description="Run CI checks on Tableau workbooks (or the workbook "
        "open in Tableau Studio).",
    )
    parser.add_argument("files", nargs="*", help="input files (.twbx / .twb)")
    parser.add_argument(
        "--studio",
        action="store_true",
        help="check the workbook open in Tableau Studio (unsaved edits included)",
    )
    parser.add_argument("--workbook", help="with --studio: pick the Tableau instance by workbook title/path")
    parser.add_argument("--format", choices=("text", "json", "md"), default="text")
    parser.add_argument(
        "--fail-on",
        choices=FAIL_ON_CHOICES,
        default=None,
        help="exit with 5 when a finding at this severity or above exists "
        "(default: the config's fail_on, else error)",
    )
    parser.add_argument("--config", type=Path, default=None, help="path to .twbdoc.json")
    parser.add_argument("--output", "-o", type=Path, default=None, help="also write the report to this file")
    parser.add_argument("--lang", choices=LANGUAGE_CHOICES, default="auto")
    return parser


def check_main(argv: list[str]) -> int:
    args = _check_parser().parse_args(argv)
    t = get_translator(args.lang)
    if not args.files and not args.studio:
        print(t("[エラー] ファイルか --studio を指定してください。",
                "[Error] Give input files or --studio."), file=sys.stderr)
        return EXIT_INPUT_ERROR
    reports: list[dict] = []
    all_findings: list = []
    exit_code = EXIT_OK
    try:
        config_path = args.config or find_config(Path(args.files[0]) if args.files else Path.cwd())
        config = load_config(config_path, t)
    except InvalidFileError as error:
        print(f"{t('[エラー]', '[Error]')} {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    fail_on = args.fail_on or config.fail_on

    for name in args.files:
        path = Path(name)
        try:
            root = load_workbook_xml(path, t)
            workbook = parse_workbook(root, source_file=path.name)
        except InvalidFileError as error:
            print(f"{t('[エラー]', '[Error]')} {error}", file=sys.stderr)
            exit_code = max(exit_code, EXIT_INPUT_ERROR)
            continue
        except (TwbDocError, Exception) as error:  # noqa: BLE001
            print(f"{t('[エラー]', '[Error]')} {path.name}: {error}", file=sys.stderr)
            exit_code = max(exit_code, EXIT_PARSE_ERROR)
            continue
        findings = run_checks(workbook, t, config=config)
        all_findings.extend(findings)
        reports.append(to_report_dict(path.name, findings))

    if args.studio:
        code, report, findings = _check_studio(args.workbook, config, t)
        exit_code = max(exit_code, code)
        if report is not None:
            reports.append(report)
            all_findings.extend(findings)

    output = _format_reports(reports, args.format, t)
    if output:
        print(output)
    if args.output is not None:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output + "\n", encoding="utf-8")
        except OSError as error:
            print(f"{t('[エラー]', '[Error]')} {error}", file=sys.stderr)
            exit_code = max(exit_code, EXIT_INPUT_ERROR)
    if exit_code == EXIT_OK and should_fail(all_findings, fail_on):
        return EXIT_CHECK_FAILED
    return exit_code


def _check_studio(workbook_name: str | None, config, t: Translator):
    from .live.studio import StudioError, StudioUnavailable, connect

    try:
        client = connect(workbook=workbook_name)
        info = client.workbook()
        xml = client.document()
        try:
            diagnostics = client.diagnostics()
        except StudioError:
            diagnostics = None
    except StudioUnavailable as error:
        print(f"{t('[エラー]', '[Error]')} {error}", file=sys.stderr)
        return EXIT_STUDIO_UNAVAILABLE, None, ()
    except StudioError as error:
        print(f"{t('[エラー]', '[Error]')} {error}", file=sys.stderr)
        return EXIT_STUDIO_UNAVAILABLE, None, ()
    title = str(info.get("title") or "workbook")
    try:
        root = parse_workbook_xml_bytes(xml, f"{title}.twb", t)
        workbook = parse_workbook(root, source_file=f"{title}.twb")
    except TwbDocError as error:
        print(f"{t('[エラー]', '[Error]')} {error}", file=sys.stderr)
        return EXIT_PARSE_ERROR, None, ()
    sheet_names = {s.get("id", ""): s.get("name", "") for s in info.get("worksheets", []) or []}
    extra = studio_invalid_fields(diagnostics, sheet_names, t)
    findings = run_checks(workbook, t, extra, config)
    report = to_report_dict(title, findings, source="studio")
    report["unsaved"] = bool(info.get("unsavedChanges"))
    report["location"] = info.get("location")
    return EXIT_OK, report, findings


def _format_reports(reports: list[dict], fmt: str, t: Translator) -> str:
    if not reports:
        return ""
    if fmt == "json":
        if len(reports) == 1:
            return to_json(reports[0])
        return to_json({"reports": reports})
    if fmt == "md":
        return "\n".join(to_markdown(r, t) for r in reports)
    return "\n".join(to_text(r, t) for r in reports)


# --- watch -----------------------------------------------------------------


def _watch_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="twbdoc watch",
        description="Watch the workbook being edited in Tableau Studio (or a "
        "saved file) and keep the documentation and CI findings up to date "
        "on a local dashboard.",
    )
    parser.add_argument("file", nargs="?", help="watch this saved .twb/.twbx instead of Tableau Studio")
    parser.add_argument("--workbook", help="pick the Tableau instance by workbook title/path")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--out", type=Path, default=None,
                        help="output folder for spec.md / findings.json / history.jsonl "
                        "(default: <workbook>.twbdoc next to the workbook)")
    parser.add_argument("--no-output", action="store_true", help="do not write files; dashboard only")
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between polls")
    parser.add_argument("--doc-interval", type=float, default=5.0,
                        help="max seconds between full workbook XML reads")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--open", action="store_true", help="open the dashboard in the browser")
    parser.add_argument("--lang", choices=LANGUAGE_CHOICES, default="auto")
    return parser


def watch_main(argv: list[str]) -> int:
    from .live.runner import LiveRunner, default_out_dir
    from .live.server import LiveServer
    from .live.source import FileSource, StudioSource

    args = _watch_parser().parse_args(argv)
    t = get_translator(args.lang)
    try:
        config = load_config(args.config or find_config(Path(args.file) if args.file else Path.cwd()), t)
    except InvalidFileError as error:
        print(f"{t('[エラー]', '[Error]')} {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    if args.file:
        source = FileSource(Path(args.file), t)
    else:
        source = StudioSource(workbook=args.workbook, doc_interval=args.doc_interval)
    out_dir = None if args.no_output else (args.out or default_out_dir)
    runner = LiveRunner(source, out_dir, config, t, interval=args.interval)
    try:
        server = LiveServer(runner, port=args.port)
    except OSError as error:
        print(f"{t('[エラー]', '[Error]')} port {args.port}: {error}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    server.start()
    print(t(f"[監視中] ダッシュボード: {server.url}  (Ctrl+C で終了)",
            f"[Watching] Dashboard: {server.url}  (Ctrl+C to stop)"))
    if args.open:
        webbrowser.open(server.url)
    try:
        last_error = None
        while not runner.stopped:
            runner.tick()
            state = runner.snapshot_state()
            error = state["error"] or state["status"].get("error")
            if error and error != last_error:
                print(f"{t('[待機]', '[Waiting]')} {error}", file=sys.stderr)
            last_error = error
            runner.wait(runner.interval)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return EXIT_OK
