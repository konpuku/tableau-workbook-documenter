"""フィルター章のレンダリング。

フィルターの適用内容を「Category の Furniture, Office Supplies のみ保持」の
ような日本語の説明文に変換する。
"""

from __future__ import annotations

import re

from ..fieldref import humanize_field_ref, split_derivation
from ..model import WorksheetFilter

FILTER_CLASS_LABELS = {
    "categorical": "カテゴリ",
    "quantitative": "範囲",
    "relative-date": "相対日付",
}

_YEAR_MONTH_PATTERN = re.compile(r"^(\d{4})(\d{2})$")


def filter_target(filter_: WorksheetFilter, caption_map: dict[str, str]) -> str:
    """フィルター対象フィールドの表示名。"""
    return humanize_field_ref(filter_.column_ref, caption_map)


def filter_kind(filter_: WorksheetFilter) -> str:
    """フィルター種別の表示名。"""
    label = FILTER_CLASS_LABELS.get(
        filter_.filter_class, filter_.filter_class or "-"
    )
    if filter_.is_context:
        return f"{label} (コンテキスト)"
    return label


def describe_filter(
    filter_: WorksheetFilter, caption_map: dict[str, str]
) -> str:
    """フィルターの適用内容を日本語で説明する。"""
    if filter_.all_members:
        if filter_.action:
            return f"全メンバー (アクションフィルター「{filter_.action}」で絞込み)"
        return "全メンバー"
    if filter_.members:
        members = "、".join(
            _format_member(member, filter_.level, caption_map)
            for member in filter_.members
        )
        if filter_.excluded:
            return f"{members} を除外"
        return f"{members} のみ保持"
    if filter_.min_value or filter_.max_value:
        return _describe_range(filter_)
    if filter_.expression:
        return f"条件式: {filter_.expression}"
    return "-"


def _describe_range(filter_: WorksheetFilter) -> str:
    if filter_.min_value and filter_.max_value:
        return f"{filter_.min_value} 〜 {filter_.max_value} の範囲のみ保持"
    if filter_.min_value:
        return f"{filter_.min_value} 以上のみ保持"
    return f"{filter_.max_value} 以下のみ保持"


def _format_member(
    member: str, level: str, caption_map: dict[str, str]
) -> str:
    """メンバー値を可読化する。

    - フィールド参照 (メジャーネームの選択値など) は表示名に変換
    - 年月レベル (my:) の '202610' は '2026/10' に変換
    """
    if member.startswith("["):
        return humanize_field_ref(member, caption_map)
    derivation, _ = split_derivation(level.strip("[]"))
    if derivation == "my":
        match = _YEAR_MONTH_PATTERN.match(member)
        if match is not None:
            return f"{match.group(1)}/{match.group(2)}"
    return member
