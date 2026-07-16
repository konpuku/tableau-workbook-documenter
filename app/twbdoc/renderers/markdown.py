"""Workbook モデルから設計書 Markdown 全体を生成する。

章番号はここで一元管理し、各レンダラーへ引数として渡す。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .. import __version__
from ..model import Workbook
from ..sampler import SampleResult
from .actions import render_actions
from .anchors import gfm_slug
from .datasources import (
    field_list_datasources,
    render_datasources_prep,
    render_field_list_chapter,
)
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
from .table_calcs import render_table_calcs

CH_OVERVIEW = 1
CH_DATASOURCES = 2
CH_DASHBOARDS = 3
CH_ACTIONS = 4
CH_WORKSHEETS = 5
CH_FILTERS = 6
CH_PARAMETERS = 7
CH_CALCULATIONS = 8
CH_TABLE_CALCS = 9
CH_ALIASES = 10
CH_STYLES = 11
CH_FIELD_LIST = 12


def render(
    workbook: Workbook,
    generated_at: datetime | None = None,
    samples: SampleResult | None = None,
) -> str:
    """設計書 Markdown 文字列を生成する。"""
    timestamp = (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M")
    title = Path(workbook.meta.source_file).stem or workbook.meta.source_file
    caption_map = _build_caption_map(workbook)
    field_list_anchors = _build_field_list_anchors(workbook)

    body: list[str] = []
    body.extend(render_overview(workbook, CH_OVERVIEW))
    body.extend(
        render_datasources_prep(
            workbook, caption_map, CH_DATASOURCES, field_list_anchors
        )
    )
    body.extend(
        render_dashboards(workbook.dashboards, caption_map, CH_DASHBOARDS)
    )
    body.extend(render_actions(workbook.actions, caption_map, CH_ACTIONS))
    body.extend(render_worksheets(workbook, CH_WORKSHEETS))
    body.extend(render_filters(workbook, caption_map, CH_FILTERS))
    body.extend(render_parameters(workbook.parameters, CH_PARAMETERS))
    body.extend(
        render_calculated_fields(workbook, caption_map, CH_CALCULATIONS)
    )
    body.extend(render_table_calcs(workbook, caption_map, CH_TABLE_CALCS))
    body.extend(render_aliases(workbook.datasources, CH_ALIASES))
    body.extend(render_styles(workbook.style_rules, CH_STYLES))
    body.extend(render_field_list_chapter(workbook, samples, CH_FIELD_LIST))

    lines: list[str] = [
        f"# {title} 設計書",
        "",
        f"- 生成日時: {timestamp}",
        f"- 元ファイル: {workbook.meta.source_file}",
        f"- 生成ツール: tableau-workbook-documenter v{__version__}",
        "",
    ]
    lines.extend(_render_toc(body))
    lines.extend(body)
    return "\n".join(lines).rstrip() + "\n"


def _render_toc(body: list[str]) -> list[str]:
    """本文の見出し (## / ###) からリンク付き目次を生成する。"""
    lines = ["## 目次", ""]
    seen: dict[str, int] = {}
    in_code_block = False
    for line in body:
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if line.startswith("### "):
            heading, indent = line[4:], "  -"
        elif line.startswith("## "):
            heading, indent = line[3:], "-"
        else:
            continue
        anchor = _unique_anchor(heading, seen)
        lines.append(f"{indent} [{heading}](#{anchor})")
    lines.append("")
    return lines


def _unique_anchor(heading: str, seen: dict[str, int]) -> str:
    """GitHub 方式の重複アンカー解決 (2 回目以降は -1, -2 を付与)。"""
    slug = gfm_slug(heading)
    count = seen.get(slug, 0)
    seen[slug] = count + 1
    return slug if count == 0 else f"{slug}-{count}"


def _build_field_list_anchors(workbook: Workbook) -> dict[str, str]:
    """データソース内部名 -> 巻末フィールド一覧節のアンカー。"""
    return {
        datasource.name: gfm_slug(
            f"{CH_FIELD_LIST}.{index} {datasource.display_name}"
        )
        for index, datasource in enumerate(
            field_list_datasources(workbook), start=1
        )
    }


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
