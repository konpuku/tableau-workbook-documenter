"""CI チェック結果の出力 (JSON / Markdown / テキスト)。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable

from ..i18n import JA, Translator
from .rules import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    Finding,
    count_by_severity,
)

REPORT_SCHEMA_VERSION = 1

_ICONS = {SEVERITY_ERROR: "✖", SEVERITY_WARNING: "⚠", SEVERITY_INFO: "ℹ"}


def severity_label(severity: str, t: Translator) -> str:
    return {
        SEVERITY_ERROR: t("エラー", "Error"),
        SEVERITY_WARNING: t("警告", "Warning"),
        SEVERITY_INFO: t("情報", "Info"),
    }.get(severity, severity)


def to_report_dict(
    workbook_name: str,
    findings: Iterable[Finding],
    generated_at: datetime | None = None,
    source: str = "file",
) -> dict:
    findings = tuple(findings)
    return {
        "schema": REPORT_SCHEMA_VERSION,
        "workbook": workbook_name,
        "source": source,
        "generated_at": (generated_at or datetime.now()).isoformat(timespec="seconds"),
        "summary": count_by_severity(findings),
        "findings": [f.to_dict() for f in findings],
    }


def to_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)


def to_markdown(report: dict, t: Translator = JA) -> str:
    summary = report["summary"]
    lines = [
        f"## {t('CI チェック', 'CI check')}: {report['workbook']}",
        "",
        t(
            f"エラー {summary[SEVERITY_ERROR]} / 警告 {summary[SEVERITY_WARNING]} "
            f"/ 情報 {summary[SEVERITY_INFO]}",
            f"{summary[SEVERITY_ERROR]} errors / {summary[SEVERITY_WARNING]} "
            f"warnings / {summary[SEVERITY_INFO]} info",
        ),
        "",
    ]
    if not report["findings"]:
        lines.append(t("検出はありません。", "No findings."))
        return "\n".join(lines) + "\n"
    header = t(
        "| 重要度 | ルール | 対象 | 内容 | 対処 |",
        "| Severity | Rule | Target | Message | Fix |",
    )
    lines += [header, "|---|---|---|---|---|"]
    for f in report["findings"]:
        cells = [
            f"{_ICONS.get(f['severity'], '')} {severity_label(f['severity'], t)}",
            f"`{f['rule']}`",
            f["target"],
            f["message"],
            f["fix_hint"],
        ]
        lines.append("| " + " | ".join(_escape(c) for c in cells) + " |")
    return "\n".join(lines) + "\n"


def to_text(report: dict, t: Translator = JA) -> str:
    lines = [f"{report['workbook']}:"]
    for f in report["findings"]:
        lines.append(
            f"  {_ICONS.get(f['severity'], '')} [{f['rule']}] {f['target']}: {f['message']}"
        )
    summary = report["summary"]
    lines.append(
        "  "
        + t(
            f"→ エラー {summary[SEVERITY_ERROR]} / 警告 {summary[SEVERITY_WARNING]} "
            f"/ 情報 {summary[SEVERITY_INFO]}",
            f"→ {summary[SEVERITY_ERROR]} errors / {summary[SEVERITY_WARNING]} "
            f"warnings / {summary[SEVERITY_INFO]} info",
        )
    )
    return "\n".join(lines)


def _escape(cell: str) -> str:
    return str(cell).replace("|", "\\|").replace("\n", " ")
