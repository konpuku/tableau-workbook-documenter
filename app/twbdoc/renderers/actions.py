"""ダッシュボードアクション章のレンダリング。"""

from __future__ import annotations

from ..fieldref import humanize_field_ref
from ..model import DashboardAction
from .tables import table as _table

NOT_APPLICABLE = "(該当なし)"

ACTIVATION_LABELS = {
    "on-select": "選択時",
    "on-hover": "ポイント時 (ホバー)",
    "on-menu": "メニュー選択時",
}


def render_actions(
    actions: tuple[DashboardAction, ...],
    caption_map: dict[str, str],
    number: int,
) -> list[str]:
    """ダッシュボードアクション章。"""
    lines = [f"## {number}. ダッシュボードアクション", ""]
    if not actions:
        lines.extend([NOT_APPLICABLE, ""])
        return lines
    rows = [
        (
            action.caption or action.name.strip("[]") or "-",
            action.kind or "-",
            ACTIVATION_LABELS.get(action.activation, action.activation or "-"),
            _describe_source(action),
            _describe_target(action, caption_map),
            action.fields or "-",
            _describe_details(action),
        )
        for action in actions
    ]
    lines.extend(
        _table(
            (
                "名前",
                "種類",
                "実行タイミング",
                "ソース",
                "ターゲット",
                "対象フィールド",
                "詳細",
            ),
            rows,
        )
    )
    return lines


def _describe_source(action: DashboardAction) -> str:
    parts = [
        part
        for part in (action.source_dashboard, action.source_worksheet)
        if part
    ]
    text = " / ".join(parts) or "-"
    if action.excluded_sheets:
        text += f" (除外: {', '.join(action.excluded_sheets)})"
    return text


def _describe_target(
    action: DashboardAction, caption_map: dict[str, str]
) -> str:
    if not action.target:
        return "-"
    if action.target.startswith("["):
        return humanize_field_ref(action.target, caption_map)
    return action.target


def _describe_details(action: DashboardAction) -> str:
    return (
        ", ".join(f"{name}={value}" for name, value in action.params) or "-"
    )
