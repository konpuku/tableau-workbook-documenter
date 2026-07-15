"""Markdown 見出しアンカー (GitHub / VS Code 方式) の生成。"""

from __future__ import annotations

import re

_REMOVE_PATTERN = re.compile(r"[^\w\- ]")


def gfm_slug(heading: str) -> str:
    """見出しテキストからアンカー ID を生成する。

    GitHub 方式: 小文字化 → 英数字・ハイフン・スペース以外を除去 →
    スペースをハイフンに置換 (日本語はそのまま保持される)。
    """
    slug = _REMOVE_PATTERN.sub("", heading.strip().lower())
    return slug.replace(" ", "-")
