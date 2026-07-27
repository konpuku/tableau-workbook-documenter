"""健康診断章のレンダリング。"""

from __future__ import annotations

from ..health import SEVERITY_WARNING, HealthFinding
from ..i18n import JA, Translator
from .tables import table as _table

SEVERITY_LABELS = {
    SEVERITY_WARNING: ("⚠ 警告", "⚠ Warning"),
    "info": ("ℹ 情報", "ℹ Info"),
}

INTRO = (
    "ワークブックの保守リスクを機械的にチェックした結果です。"
    "⚠ 警告 = 対応を推奨 / ℹ 情報 = 参考情報 (意図的な設計の場合は対応不要)。",
    "Automated check of maintenance risks in this workbook. "
    "⚠ Warning = action recommended / ℹ Info = for reference "
    "(no action needed if intentional).",
)


def render_health(
    findings: tuple[HealthFinding, ...], number: int, t: Translator = JA
) -> list[str]:
    """健康診断章。"""
    lines = [
        f"## {number}. " + t("健康診断", "Health Check"),
        "",
        t(*INTRO),
        "",
    ]
    if not findings:
        lines.extend(
            [t("問題は検出されませんでした。", "No issues were detected."), ""]
        )
        return lines
    rows = [
        (
            t(*SEVERITY_LABELS.get(finding.severity, (finding.severity,) * 2)),
            finding.category,
            finding.target,
            finding.message,
        )
        for finding in findings
    ]
    lines.extend(
        _table(
            (
                t("重要度", "Severity"),
                t("項目", "Check"),
                t("対象", "Target"),
                t("内容", "Detail"),
            ),
            rows,
        )
    )
    return lines
