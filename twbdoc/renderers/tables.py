"""Markdown テーブル生成の共通ヘルパー。"""

from __future__ import annotations


def table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    """Markdown テーブルの行リストを生成する (セル内のパイプ・改行はエスケープ)。"""
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "---|" * len(headers),
    ]
    for row in rows:
        cells = (_escape_cell(cell) for cell in row)
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")
