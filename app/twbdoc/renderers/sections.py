"""設計書の各章を Markdown 行リストとして描画する関数群。

用語は Tableau 公式ヘルプの表記に合わせる (日本語/英語とも)。
"""

from __future__ import annotations

from ..i18n import JA, Translator
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

NOT_APPLICABLE = ("(該当なし)", "(none)")

THUMBNAIL_NOTE = (
    "※ 画像はサムネイルであり、実際のダッシュボード全体画像ではありません。",
    "* This image is the thumbnail stored in the workbook, "
    "not a full-size image of the dashboard.",
)
LAYOUT_IMAGE_NOTE = (
    "※ レイアウト簡略図: 各要素の位置・サイズ比率を twb の定義から再現したものです "
    "(実際の描画内容は含みません)。",
    "* Layout diagram: positions and sizes are reproduced from the twb "
    "definition (it does not show the rendered content).",
)

# Tableau のデータ型表記
DATATYPE_LABELS = {
    "integer": ("数値 (整数)", "Number (whole)"),
    "real": ("数値 (小数)", "Number (decimal)"),
    "string": ("文字列", "String"),
    "boolean": ("ブール値", "Boolean"),
    "date": ("日付", "Date"),
    "datetime": ("日付と時刻", "Date & Time"),
}

# パラメーターの「許容値」の種別
DOMAIN_TYPE_LABELS = {
    "range": ("範囲", "Range"),
    "list": ("リスト", "List"),
    "any": ("すべて", "All"),
}

ROLE_LABELS = {
    "dimension": ("ディメンション", "Dimension"),
    "measure": ("メジャー", "Measure"),
}


def render_overview(
    workbook: Workbook,
    number: int = 1,
    health_summary: str = "",
    t: Translator = JA,
) -> list[str]:
    """ワークブック概要章。health_summary は健康診断の警告数セル。"""
    meta = workbook.meta
    rows = [
        (t("元ファイル", "Source file"), meta.source_file),
        (t("ドキュメントバージョン", "Document version"), meta.version),
        (t("作成 Tableau ビルド", "Tableau build"), meta.source_build),
        (t("作成プラットフォーム", "Platform"), meta.source_platform),
        (t("データソース数", "Data sources"), str(len(workbook.datasources))),
        (t("ワークシート数", "Worksheets"), str(len(workbook.worksheets))),
        (t("ダッシュボード数", "Dashboards"), str(len(workbook.dashboards))),
        (t("パラメーター数", "Parameters"), str(len(workbook.parameters))),
        (
            t("計算フィールド数", "Calculated fields"),
            str(len(workbook.calculated_fields)),
        ),
        (
            t("ダッシュボードアクション数", "Dashboard actions"),
            str(len(workbook.actions)),
        ),
    ]
    if health_summary:
        rows.append((t("健康診断の警告", "Health check warnings"), health_summary))
    lines = [f"## {number}. " + t("ワークブック概要", "Workbook Overview"), ""]
    lines.extend(_table((t("項目", "Item"), t("値", "Value")), rows))
    return lines


def render_dashboards(
    dashboards: tuple[Dashboard, ...],
    caption_map: dict[str, str],
    number: int = 3,
    t: Translator = JA,
) -> list[str]:
    """ダッシュボード構成章。"""
    lines = [f"## {number}. " + t("ダッシュボード構成", "Dashboards"), ""]
    if not dashboards:
        lines.extend([t(*NOT_APPLICABLE), ""])
        return lines
    for index, dashboard in enumerate(dashboards, start=1):
        lines.append(f"### {number}.{index} {dashboard.name}")
        lines.append("")
        lines.append(f"- {t('サイズ', 'Size')}: {_describe_size(dashboard.size, t)}")
        if dashboard.image_path:
            lines.append("")
            lines.append(f"![{dashboard.name}]({dashboard.image_path})")
            lines.append("")
            lines.append(t(*THUMBNAIL_NOTE))
        lines.append("")
        lines.append("#### " + t("レイアウト構成", "Layout"))
        lines.append("")
        lines.extend(
            render_zone_list(dashboard.zones, caption_map, dashboard.size, t)
        )
        lines.append("")
        if dashboard.layout_image_path:
            label = t("レイアウト", "layout")
            lines.append(
                f"![{dashboard.name} {label}]({dashboard.layout_image_path})"
            )
            lines.append("")
            lines.append(t(*LAYOUT_IMAGE_NOTE))
        else:
            lines.extend(render_zone_mermaid(dashboard.zones, caption_map, t))
        lines.append("")
    return lines


def render_worksheets(
    workbook: Workbook, number: int = 5, t: Translator = JA
) -> list[str]:
    """ワークシート一覧章 (使用している計算フィールド・パラメーター付き)。"""
    lines = [f"## {number}. " + t("ワークシート一覧", "Worksheets"), ""]
    if not workbook.worksheets:
        lines.extend([t(*NOT_APPLICABLE), ""])
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
            ", ".join(sheet.dashboards) or t("(単独シート)", "(standalone)"),
        )
        for sheet in workbook.worksheets
    ]
    lines.extend(
        _table(
            (
                t("ワークシート名", "Worksheet"),
                t("タイトル", "Title"),
                t("使用データソース", "Data sources"),
                t("使用計算フィールド", "Calculated fields used"),
                t("使用パラメーター", "Parameters used"),
                t("配置先ダッシュボード", "Dashboards"),
            ),
            rows,
        )
    )
    return lines


def render_filters(
    workbook: Workbook,
    caption_map: dict[str, str],
    number: int = 6,
    t: Translator = JA,
) -> list[str]:
    """フィルター章 (共通フィルター + ワークシートごとのフィルター)。"""
    lines = [f"## {number}. " + t("フィルター", "Filters"), ""]
    shared_rows = [
        (
            filter_target(filter_, caption_map),
            filter_kind(filter_, t),
            describe_filter(filter_, caption_map, t),
        )
        for filter_ in workbook.shared_filters
    ]
    sheet_rows = [
        (
            sheet.name,
            filter_target(filter_, caption_map),
            filter_kind(filter_, t),
            describe_filter(filter_, caption_map, t),
        )
        for sheet in workbook.worksheets
        for filter_ in sheet.filters
    ]
    if not shared_rows and not sheet_rows:
        lines.extend([t(*NOT_APPLICABLE), ""])
        return lines
    headers = (
        t("対象フィールド", "Field"),
        t("種別", "Type"),
        t("適用内容", "Setting"),
    )
    if shared_rows:
        lines.extend(
            [
                f"### {number}.1 "
                + t(
                    "共通フィルター (複数シートに適用)",
                    "Shared filters (applied to multiple worksheets)",
                ),
                "",
            ]
        )
        lines.extend(_table(headers, shared_rows))
    if sheet_rows:
        section_number = f"{number}.2" if shared_rows else f"{number}.1"
        lines.extend(
            [
                f"### {section_number} "
                + t("ワークシートのフィルター", "Worksheet filters"),
                "",
            ]
        )
        lines.extend(
            _table((t("ワークシート", "Worksheet"),) + headers, sheet_rows)
        )
    return lines


def render_parameters(
    parameters: tuple[Parameter, ...], number: int = 7, t: Translator = JA
) -> list[str]:
    """パラメーター章。"""
    lines = [f"## {number}. " + t("パラメーター", "Parameters"), ""]
    if not parameters:
        lines.extend([t(*NOT_APPLICABLE), ""])
        return lines
    rows = [
        (
            parameter.display_name,
            datatype_label(parameter.datatype, t),
            parameter.current_value or "-",
            t(
                *DOMAIN_TYPE_LABELS.get(
                    parameter.domain_type,
                    (parameter.domain_type, parameter.domain_type),
                )
            ),
            _describe_domain(parameter, t),
        )
        for parameter in parameters
    ]
    lines.extend(
        _table(
            (
                t("名前", "Name"),
                t("データ型", "Data type"),
                t("現在値", "Current value"),
                t("許容値の種別", "Allowable values"),
                t("許容値", "Values"),
            ),
            rows,
        )
    )
    return lines


def render_calculated_fields(
    workbook: Workbook,
    caption_map: dict[str, str],
    number: int = 8,
    t: Translator = JA,
) -> list[str]:
    """計算フィールド章 (リネージュ図 + フィールドごとの詳細)。"""
    fields = workbook.calculated_fields
    lines = [f"## {number}. " + t("計算フィールド", "Calculated Fields"), ""]
    if not fields:
        lines.extend([t(*NOT_APPLICABLE), ""])
        return lines

    anchors = {
        calculated.name: gfm_slug(
            f"{number}.{index} {calculated.display_name}"
        )
        for index, calculated in enumerate(fields, start=2)
    }
    lines.extend(
        [
            f"### {number}.1 "
            + t("リネージュ (依存関係図)", "Lineage (dependency diagram)"),
            "",
        ]
    )
    lines.extend(render_lineage_mermaid(workbook, anchors, t))
    lines.append("")

    none_label = t("なし", "None")
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
            (t("データ型", "Data type"), datatype_label(calculated.datatype, t)),
            (t("ロール", "Role"), role_label(calculated.role, t)),
            (t("所属データソース", "Data source"), calculated.datasource or "-"),
        ]
        if calculated.comment:
            rows.append(
                (t("コメント (Tableau)", "Comment (Tableau)"), calculated.comment)
            )
        if calculated.inline_comments:
            rows.append(
                (
                    t("式内コメント", "Comments in formula"),
                    "\n".join(calculated.inline_comments),
                )
            )
        rows.extend(
            [
                (
                    t("参照しているフィールド", "Fields referenced"),
                    _display_names(calculated.depends_on, caption_map) or "-",
                ),
                (
                    t("利用先ワークシート", "Used in worksheets"),
                    ", ".join(used_in) or none_label,
                ),
                (
                    t("参照元計算フィールド", "Referenced by"),
                    ", ".join(referenced_by) or none_label,
                ),
            ]
        )
        if not used_in and not referenced_by:
            rows.append(
                (
                    t("状態", "Status"),
                    t(
                        "⚠ 未使用の可能性 (どのワークシート・計算フィールドからも"
                        "参照されていません)",
                        "⚠ Possibly unused (not referenced by any worksheet "
                        "or calculated field)",
                    ),
                )
            )
        lines.extend(_table((t("項目", "Item"), t("値", "Value")), rows))
        lines.append(t("式:", "Formula:"))
        lines.append("")
        lines.append("```")
        lines.extend(calculated.formula.splitlines() or [""])
        lines.append("```")
        lines.append("")
    return lines


def render_aliases(
    datasources: tuple[Datasource, ...], number: int = 10, t: Translator = JA
) -> list[str]:
    """別名章。"""
    lines = [f"## {number}. " + t("別名", "Aliases"), ""]
    fields_with_aliases = [
        (datasource, field)
        for datasource in datasources
        for field in datasource.fields
        if field.aliases
    ]
    if not fields_with_aliases:
        lines.extend([t(*NOT_APPLICABLE), ""])
        return lines
    for datasource, field in fields_with_aliases:
        lines.append(f"### {field.display_name} ({datasource.display_name})")
        lines.append("")
        rows = [(alias.key, alias.value) for alias in field.aliases]
        lines.extend(
            _table((t("元の値", "Member"), t("別名", "Alias")), rows)
        )
    return lines


def render_styles(
    style_rules: tuple[StyleRule, ...], number: int = 11, t: Translator = JA
) -> list[str]:
    """書式設定章。"""
    lines = [f"## {number}. " + t("書式設定", "Formatting"), ""]
    rows = [
        (setting.scope or "-", rule.element or "-", setting.attr, setting.value)
        for rule in style_rules
        for setting in rule.formats
    ]
    if not rows:
        lines.extend([t(*NOT_APPLICABLE), ""])
        return lines
    lines.extend(
        _table(
            (
                t("適用範囲", "Scope"),
                t("対象要素", "Element"),
                t("属性", "Property"),
                t("値", "Value"),
            ),
            rows,
        )
    )
    return lines


def _describe_size(size: DashboardSize, t: Translator) -> str:
    if size.sizing_mode == "fixed":
        return t("固定", "Fixed") + f" ({size.minwidth} x {size.minheight})"
    if size.sizing_mode == "automatic" or not size.sizing_mode:
        return t("自動", "Automatic")
    ranges = []
    if size.minwidth or size.minheight:
        ranges.append(
            t("最小", "Min") + f" {size.minwidth or '-'} x {size.minheight or '-'}"
        )
    if size.maxwidth or size.maxheight:
        ranges.append(
            t("最大", "Max") + f" {size.maxwidth or '-'} x {size.maxheight or '-'}"
        )
    detail = f" ({', '.join(ranges)})" if ranges else ""
    return f"{size.sizing_mode}{detail}"


def _describe_domain(parameter: Parameter, t: Translator) -> str:
    if parameter.domain_type == "range":
        step = (
            f" ({t('刻み', 'Step size')}: {parameter.granularity})"
            if parameter.granularity
            else ""
        )
        return f"{parameter.range_min} 〜 {parameter.range_max}{step}"
    if parameter.domain_type == "list":
        values = [
            f"{member.value} ({member.alias})" if member.alias else member.value
            for member in parameter.members
        ]
        return ", ".join(values) or "-"
    return t("制限なし", "All")


def datatype_label(datatype: str, t: Translator = JA) -> str:
    """Tableau のデータ型表記を返す。"""
    pair = DATATYPE_LABELS.get(datatype)
    if pair is None:
        return datatype or "-"
    return t(*pair)


def role_label(role: str, t: Translator = JA) -> str:
    """ディメンション / メジャーの表記を返す。"""
    pair = ROLE_LABELS.get(role)
    if pair is None:
        return role or "-"
    return t(*pair)


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
