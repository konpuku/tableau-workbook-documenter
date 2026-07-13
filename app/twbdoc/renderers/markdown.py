"""Workbook モデルから設計書 Markdown 全体を生成する。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..model import Workbook
from ..sampler import SampleResult
from .datasources import render_datasources_prep, render_field_list_chapter
from .sections import (
    render_aliases,
    render_calculated_fields,
    render_dashboards,
    render_filters,
    render_overview,
    render_parameters,
    render_styles,
    render_worksheets,
)


def render(
    workbook: Workbook,
    generated_at: datetime | None = None,
    samples: SampleResult | None = None,
) -> str:
    """設計書 Markdown 文字列を生成する。"""
    timestamp = (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M")
    title = Path(workbook.meta.source_file).stem or workbook.meta.source_file
    caption_map = _build_caption_map(workbook)

    lines: list[str] = [
        f"# {title} 設計書",
        "",
        f"- 生成日時: {timestamp}",
        f"- 元ファイル: {workbook.meta.source_file}",
        "",
    ]
    lines.extend(render_overview(workbook))
    lines.extend(render_datasources_prep(workbook, caption_map))
    lines.extend(render_dashboards(workbook.dashboards, caption_map))
    lines.extend(render_worksheets(workbook))
    lines.extend(render_filters(workbook, caption_map))
    lines.extend(render_parameters(workbook.parameters))
    lines.extend(render_calculated_fields(workbook, caption_map))
    lines.extend(render_aliases(workbook.datasources))
    lines.extend(render_styles(workbook.style_rules))
    lines.extend(render_field_list_chapter(workbook, samples))
    return "\n".join(lines).rstrip() + "\n"


def _build_caption_map(workbook: Workbook) -> dict[str, str]:
    """内部名 -> 表示名のマップ (ゾーンのフィールド参照可読化に使用)。"""
    caption_map: dict[str, str] = {}
    for datasource in workbook.datasources:
        for field in datasource.fields:
            if field.caption:
                caption_map[field.name] = f"[{field.caption}]"
    for parameter in workbook.parameters:
        if parameter.caption:
            caption_map[parameter.name] = f"[{parameter.caption}]"
    return caption_map
