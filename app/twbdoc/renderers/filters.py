"""フィルター章のレンダリング。

フィルターの適用内容を「Category の Furniture, Office Supplies のみ保持」の
ような説明文に変換する。用語は Tableau の「のみ保持」「除外」に合わせる。
"""

from __future__ import annotations

import re

from ..fieldref import humanize_field_ref, split_derivation
from ..i18n import JA, Translator
from ..model import WorksheetFilter

FILTER_CLASS_LABELS = {
    "categorical": ("カテゴリ", "Categorical"),
    "quantitative": ("範囲", "Range"),
    "relative-date": ("相対日付", "Relative date"),
}

_YEAR_MONTH_PATTERN = re.compile(r"^(\d{4})(\d{2})$")


def filter_target(filter_: WorksheetFilter, caption_map: dict[str, str]) -> str:
    """フィルター対象フィールドの表示名。"""
    return humanize_field_ref(filter_.column_ref, caption_map)


def filter_kind(filter_: WorksheetFilter, t: Translator = JA) -> str:
    """フィルター種別の表示名。"""
    pair = FILTER_CLASS_LABELS.get(filter_.filter_class)
    label = t(*pair) if pair is not None else (filter_.filter_class or "-")
    if filter_.is_context:
        return f"{label} ({t('コンテキスト', 'Context')})"
    return label


def describe_filter(
    filter_: WorksheetFilter,
    caption_map: dict[str, str],
    t: Translator = JA,
) -> str:
    """フィルターの適用内容を説明する。"""
    if filter_.all_members:
        if filter_.action:
            return t(
                f"全メンバー (アクションフィルター「{filter_.action}」で絞込み)",
                f'All members (narrowed by filter action "{filter_.action}")',
            )
        return t("全メンバー", "All members")
    if filter_.members:
        members = t("、", ", ").join(
            _format_member(member, filter_.level, caption_map, t)
            for member in filter_.members
        )
        if filter_.excluded:
            return t(f"{members} を除外", f"Exclude: {members}")
        return t(f"{members} のみ保持", f"Keep only: {members}")
    if filter_.min_value or filter_.max_value:
        return _describe_range(filter_, t)
    if filter_.expression:
        return t(f"条件式: {filter_.expression}", f"Condition: {filter_.expression}")
    return "-"


def _describe_range(filter_: WorksheetFilter, t: Translator) -> str:
    if filter_.min_value and filter_.max_value:
        return t(
            f"{filter_.min_value} 〜 {filter_.max_value} の範囲のみ保持",
            f"Keep only {filter_.min_value} to {filter_.max_value}",
        )
    if filter_.min_value:
        return t(
            f"{filter_.min_value} 以上のみ保持",
            f"Keep only {filter_.min_value} and above",
        )
    return t(
        f"{filter_.max_value} 以下のみ保持",
        f"Keep only {filter_.max_value} and below",
    )


def _format_member(
    member: str, level: str, caption_map: dict[str, str], t: Translator = JA
) -> str:
    """メンバー値を可読化する。

    - フィールド参照 (メジャーネームの選択値など) は表示名に変換
    - 年月レベル (my:) の '202610' は '2026/10' に変換
    """
    if member.startswith("["):
        return humanize_field_ref(member, caption_map, t)
    derivation, _ = split_derivation(level.strip("[]"))
    if derivation == "my":
        match = _YEAR_MONTH_PATTERN.match(member)
        if match is not None:
            return f"{match.group(1)}/{match.group(2)}"
    return member
