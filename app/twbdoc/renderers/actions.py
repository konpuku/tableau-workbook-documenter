"""ダッシュボードアクション章のレンダリング。

アクション種別・実行方法の表記は Tableau のアクション設定画面に合わせる。
"""

from __future__ import annotations

from ..fieldref import humanize_field_ref
from ..i18n import JA, Translator
from ..model import DashboardAction
from .tables import table as _table

NOT_APPLICABLE = ("(該当なし)", "(none)")

# アクションの種類 (Tableau: フィルター / ハイライト / URL に移動 など)
ACTION_KIND_LABELS = {
    "filter": ("フィルター", "Filter"),
    "highlight": ("ハイライト", "Highlight"),
    "url": ("URL に移動", "Go to URL"),
    "sheet": ("シートに移動", "Go to Sheet"),
    "parameter": ("パラメーターの変更", "Change Parameter"),
    "set": ("セット値の変更", "Change Set Values"),
}

# アクションの実行方法
ACTIVATION_LABELS = {
    "on-select": ("選択", "Select"),
    "on-hover": ("ポイント", "Hover"),
    "on-menu": ("メニュー", "Menu"),
}


def render_actions(
    actions: tuple[DashboardAction, ...],
    caption_map: dict[str, str],
    number: int,
    t: Translator = JA,
) -> list[str]:
    """ダッシュボードアクション章。"""
    lines = [f"## {number}. " + t("ダッシュボードアクション", "Dashboard Actions"), ""]
    if not actions:
        lines.extend([t(*NOT_APPLICABLE), ""])
        return lines
    rows = [
        (
            action.caption or action.name.strip("[]") or "-",
            _kind_label(action.kind, t),
            _activation_label(action.activation, t),
            _describe_source(action, t),
            _describe_target(action, caption_map, t),
            action.fields or "-",
            _describe_details(action),
        )
        for action in actions
    ]
    lines.extend(
        _table(
            (
                t("名前", "Name"),
                t("種類", "Type"),
                t("実行方法", "Run action on"),
                t("ソースシート", "Source"),
                t("ターゲット", "Target"),
                t("対象フィールド", "Fields"),
                t("詳細", "Details"),
            ),
            rows,
        )
    )
    return lines


def _kind_label(kind: str, t: Translator) -> str:
    pair = ACTION_KIND_LABELS.get(kind)
    return t(*pair) if pair is not None else (kind or "-")


def _activation_label(activation: str, t: Translator) -> str:
    pair = ACTIVATION_LABELS.get(activation)
    return t(*pair) if pair is not None else (activation or "-")


def _describe_source(action: DashboardAction, t: Translator) -> str:
    parts = [
        part
        for part in (action.source_dashboard, action.source_worksheet)
        if part
    ]
    text = " / ".join(parts) or "-"
    if action.excluded_sheets:
        excluded = ", ".join(action.excluded_sheets)
        text += f" ({t('除外', 'excluded')}: {excluded})"
    return text


def _describe_target(
    action: DashboardAction, caption_map: dict[str, str], t: Translator
) -> str:
    if not action.target:
        return "-"
    if action.target.startswith("["):
        return humanize_field_ref(action.target, caption_map, t)
    return action.target


def _describe_details(action: DashboardAction) -> str:
    return (
        ", ".join(f"{name}={value}" for name, value in action.params) or "-"
    )
