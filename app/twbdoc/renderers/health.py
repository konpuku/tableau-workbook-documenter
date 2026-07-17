"""健康診断章のレンダリング。"""

from __future__ import annotations

from ..health import SEVERITY_WARNING, HealthFinding
from .tables import table as _table

SEVERITY_LABELS = {
    SEVERITY_WARNING: "⚠ 警告",
    "info": "ℹ 情報",
}

INTRO = (
    "ワークブックの保守リスクを機械的にチェックした結果です。"
    "⚠ 警告 = 対応を推奨 / ℹ 情報 = 参考情報 (意図的な設計の場合は対応不要)。"
)


def render_health(
    findings: tuple[HealthFinding, ...], number: int
) -> list[str]:
    """健康診断章。"""
    lines = [f"## {number}. 健康診断", "", INTRO, ""]
    if not findings:
        lines.extend(["問題は検出されませんでした。", ""])
        return lines
    rows = [
        (
            SEVERITY_LABELS.get(finding.severity, finding.severity),
            finding.category,
            finding.target,
            finding.message,
        )
        for finding in findings
    ]
    lines.extend(_table(("重要度", "項目", "対象", "内容"), rows))
    return lines
