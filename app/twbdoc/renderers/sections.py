"""設計書の各章を Markdown 行リストとして描画する関数群。"""

from __future__ import annotations

from ..model import (
    Dashboard,
    DashboardSize,
    Datasource,
    Parameter,
    StyleRule,
    Workbook,
)
from .anchors import gfm_slug
from .filters import describe_filter, filter_kind, filter_target
from .lineage import render_lineage_mermaid
from .tables import table as _table
from .zones import render_zone_list, render_zone_mermaid

NOT_APPLICABLE = "(該当なし)"

DATATYPE_LABELS = {
    "integer": "整数",
    "real": "数値 (小数)",
    "string": "文字列",
    "boolean": "真偽値",
    "date": "日付",
    "datetime": "日付時刻",
}

DOMAIN_TYPE_LABELS = {
    "range": "範囲",
    "list": "リスト",
    "any": "すべて (自由入力)",
}

ROLE_LABELS = {
    "dimension": "ディメンション",
    "measure": "メジャー",
}


def render_overview(workbook: Workbook, number: int = 1) -> list[str]:
    """ワークブック概要章。"""
    meta = workbook.meta
    rows = [
        ("元ファイル", meta.source_file),
        ("ドキュメントバージョン", meta.version),
        ("作成 Tableau ビルド", meta.source_build),
        ("作成プラットフォーム", meta.source_platform),
        ("データソース数", str(len(workbook.datasources))),
        ("ワークシート数", str(len(workbook.worksheets))),
        ("ダッシュボード数", str(len(workbook.dashboards))),
        ("パラメーター数", str(len(workbook.parameters))),
        ("計算フィールド数", str(len(workbook.calculated_fields))),
        ("ダッシュボードアクション数", str(len(workbook.actions))),
    ]
    lines = [f"## {number}. ワークブック概要", ""]
    lines.extend(_table(("項目", "値"), rows))
    return lines


def render_dashboards(
    dashboards: tuple[Dashboard, ...],
    caption_map: dict[str, str],
    number: int = 3,
) -> list[str]:
    """ダッシュボード構成章。"""
    lines = [f"## {number}. ダッシュボード構成", ""]
    if not dashboards:
        lines.extend([NOT_APPLICABLE, ""])
        return lines
    for index, dashboard in enumerate(dashboards, start=1):
        lines.append(f"### {number}.{index} {dashboard.name}")
        lines.append("")
        lines.append(f"- サイズ: {_describe_size(dashboard.size)}")
        if dashboard.image_path:
            lines.append("")
            lines.append(f"![{dashboard.name}]({dashboard.image_path})")
        lines.append("")
        lines.append("#### レイアウト構成")
        lines.append("")
        lines.extend(render_zone_list(dashboard.zones, caption_map))
        lines.append("")
        lines.extend(render_zone_mermaid(dashboard.zones, caption_map))
        lines.append("")
    return lines


def render_worksheets(workbook: Workbook, number: int = 5) -> list[str]:
    """ワークシート一覧章 (使用している計算フィールド・パラメーター付き)。"""
    lines = [f"## {number}. ワークシート一覧", ""]
    if not workbook.worksheets:
        lines.extend([NOT_APPLICABLE, ""])
        return lines
    calc_displays = {
        calc.name: calc.display_name for calc in workbook.calculated_fields
    }
    param_displays = {
        parameter.name: parameter.display_name
        for parameter in workbook.parameters
    }
    rows = [
        (
            sheet.name,
            sheet.title or "-",
            ", ".join(sheet.datasources) or "-",
            _used_names(sheet.used_columns, calc_displays),
            _used_names(sheet.used_columns, param_displays),
            ", ".join(sheet.dashboards) or "(単独シート)",
        )
        for sheet in workbook.worksheets
    ]
    lines.extend(
        _table(
            (
                "ワークシート名",
                "タイトル",
                "使用データソース",
                "使用計算フィールド",
                "使用パラメーター",
                "配置先ダッシュボード",
            ),
            rows,
        )
    )
    return lines


def render_filters(
    workbook: Workbook, caption_map: dict[str, str], number: int = 6
) -> list[str]:
    """フィルター章 (共通フィルター + ワークシートごとのフィルター)。"""
    lines = [f"## {number}. フィルター", ""]
    shared_rows = [
        (
            filter_target(filter_, caption_map),
            filter_kind(filter_),
            describe_filter(filter_, caption_map),
        )
        for filter_ in workbook.shared_filters
    ]
    sheet_rows = [
        (
            sheet.name,
            filter_target(filter_, caption_map),
            filter_kind(filter_),
            describe_filter(filter_, caption_map),
        )
        for sheet in workbook.worksheets
        for filter_ in sheet.filters
    ]
    if not shared_rows and not sheet_rows:
        lines.extend([NOT_APPLICABLE, ""])
        return lines
    if shared_rows:
        lines.extend([f"### {number}.1 共通フィルター (複数シートに適用)", ""])
        lines.extend(_table(("対象フィールド", "種別", "適用内容"), shared_rows))
    if sheet_rows:
        section_number = f"{number}.2" if shared_rows else f"{number}.1"
        lines.extend([f"### {section_number} ワークシートのフィルター", ""])
        lines.extend(
            _table(("ワークシート", "対象フィールド", "種別", "適用内容"), sheet_rows)
        )
    return lines


def render_parameters(
    parameters: tuple[Parameter, ...], number: int = 7
) -> list[str]:
    """パラメーター章。"""
    lines = [f"## {number}. パラメーター", ""]
    if not parameters:
        lines.extend([NOT_APPLICABLE, ""])
        return lines
    rows = [
        (
            parameter.display_name,
            _datatype_label(parameter.datatype),
            parameter.current_value or "-",
            DOMAIN_TYPE_LABELS.get(parameter.domain_type, parameter.domain_type),
            _describe_domain(parameter),
        )
        for parameter in parameters
    ]
    lines.extend(_table(("名前", "データ型", "現在値", "許容値の種別", "許容値"), rows))
    return lines


def render_calculated_fields(
    workbook: Workbook, caption_map: dict[str, str], number: int = 8
) -> list[str]:
    """計算フィールド章 (リネージュ図 + フィールドごとの詳細)。"""
    fields = workbook.calculated_fields
    lines = [f"## {number}. 計算フィールド", ""]
    if not fields:
        lines.extend([NOT_APPLICABLE, ""])
        return lines

    anchors = {
        calculated.name: gfm_slug(
            f"{number}.{index} {calculated.display_name}"
        )
        for index, calculated in enumerate(fields, start=2)
    }
    lines.extend([f"### {number}.1 リネージュ (依存関係図)", ""])
    lines.extend(render_lineage_mermaid(workbook, anchors))
    lines.append("")

    for index, calculated in enumerate(fields, start=2):
        lines.append(f"### {number}.{index} {calculated.display_name}")
        lines.append("")
        used_in = _worksheets_using(workbook, calculated.name)
        referenced_by = [
            other.display_name
            for other in fields
            if calculated.name in other.depends_on
        ]
        rows = [
            ("データ型", _datatype_label(calculated.datatype)),
            ("ロール", ROLE_LABELS.get(calculated.role, calculated.role or "-")),
            ("所属データソース", calculated.datasource or "-"),
        ]
        if calculated.comment:
            rows.append(("コメント (GUI)", calculated.comment))
        if calculated.inline_comments:
            rows.append(("式内コメント", "\n".join(calculated.inline_comments)))
        rows.extend(
            [
                (
                    "参照しているフィールド",
                    _display_names(calculated.depends_on, caption_map) or "-",
                ),
                ("利用先ワークシート", ", ".join(used_in) or "なし"),
                ("参照元計算フィールド", ", ".join(referenced_by) or "なし"),
            ]
        )
        if not used_in and not referenced_by:
            rows.append(("状態", "⚠ 未使用の可能性 (どのワークシート・計算フィールドからも参照されていません)"))
        lines.extend(_table(("項目", "値"), rows))
        lines.append("式:")
        lines.append("")
        lines.append("```")
        lines.extend(calculated.formula.splitlines() or [""])
        lines.append("```")
        lines.append("")
    return lines


def render_aliases(
    datasources: tuple[Datasource, ...], number: int = 10
) -> list[str]:
    """別名一覧章。"""
    lines = [f"## {number}. 別名一覧", ""]
    fields_with_aliases = [
        (datasource, field)
        for datasource in datasources
        for field in datasource.fields
        if field.aliases
    ]
    if not fields_with_aliases:
        lines.extend([NOT_APPLICABLE, ""])
        return lines
    for datasource, field in fields_with_aliases:
        lines.append(f"### {field.display_name} ({datasource.display_name})")
        lines.append("")
        rows = [(alias.key, alias.value) for alias in field.aliases]
        lines.extend(_table(("元の値", "別名"), rows))
    return lines


def render_styles(
    style_rules: tuple[StyleRule, ...], number: int = 11
) -> list[str]:
    """書式設定章。"""
    lines = [f"## {number}. 書式設定", ""]
    rows = [
        (setting.scope or "-", rule.element or "-", setting.attr, setting.value)
        for rule in style_rules
        for setting in rule.formats
    ]
    if not rows:
        lines.extend([NOT_APPLICABLE, ""])
        return lines
    lines.extend(_table(("適用範囲", "対象要素", "属性", "値"), rows))
    return lines


def _describe_size(size: DashboardSize) -> str:
    if size.sizing_mode == "fixed":
        return f"固定 ({size.minwidth} x {size.minheight})"
    if size.sizing_mode == "automatic" or not size.sizing_mode:
        return "自動"
    ranges = []
    if size.minwidth or size.minheight:
        ranges.append(f"最小 {size.minwidth or '-'} x {size.minheight or '-'}")
    if size.maxwidth or size.maxheight:
        ranges.append(f"最大 {size.maxwidth or '-'} x {size.maxheight or '-'}")
    detail = f" ({', '.join(ranges)})" if ranges else ""
    return f"{size.sizing_mode}{detail}"


def _describe_domain(parameter: Parameter) -> str:
    if parameter.domain_type == "range":
        step = f" (刻み: {parameter.granularity})" if parameter.granularity else ""
        return f"{parameter.range_min} 〜 {parameter.range_max}{step}"
    if parameter.domain_type == "list":
        values = [
            f"{member.value} ({member.alias})" if member.alias else member.value
            for member in parameter.members
        ]
        return ", ".join(values) or "-"
    return "制限なし"


def _datatype_label(datatype: str) -> str:
    return DATATYPE_LABELS.get(datatype, datatype or "-")


def _used_names(
    used_columns: tuple[str, ...], displays: dict[str, str]
) -> str:
    names = [displays[name] for name in used_columns if name in displays]
    return ", ".join(names) or "-"


def _worksheets_using(workbook: Workbook, internal_name: str) -> list[str]:
    return [
        sheet.name
        for sheet in workbook.worksheets
        if internal_name in sheet.used_columns
    ]


def _display_names(
    internal_names: tuple[str, ...], caption_map: dict[str, str]
) -> str:
    return ", ".join(
        caption_map.get(name, name).strip("[]") for name in internal_names
    )


