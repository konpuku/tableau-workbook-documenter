"""CI 向けチェック (安定 ID 付きの検出結果・構造差分・設定・レポート)。

設計書生成 (renderers) とは独立して、Workbook モデルから
機械可読な検出結果を作る。`python -m twbdoc check` と
`python -m twbdoc watch` (Tableau Studio 連携) の両方から使う。
"""

from .rules import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    Finding,
    run_checks,
)

__all__ = [
    "SEVERITY_ERROR",
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
    "Finding",
    "run_checks",
]
