"""表計算設定章のレンダリング。

Tableau の表計算はフィールド既定の設定に加えて、
ワークシートに配置したピル (フィールド) ごとに上書きできるため、
「ピルごとの設定」と「フィールド既定の設定」を分けて記載する。
用語は Tableau の「次を使用して計算」「簡易表計算」の表記に合わせる。
"""

from __future__ import annotations

import re

from ..fieldref import humanize_field_ref
from ..i18n import JA, Translator
from ..model import TableCalc, Workbook
from .tables import table as _table

NOT_APPLICABLE = ("(該当なし)", "(none)")

# 「次を使用して計算」(Compute Using) の選択肢
ORDERING_TYPE_LABELS = {
    "Rows": ("表 (横)", "Table (across)"),
    "Columns": ("表 (下)", "Table (down)"),
    "RowsAcrossThenDown": ("表 (横から下へ)", "Table (across then down)"),
    "ColumnsDownThenAcross": ("表 (下から横へ)", "Table (down then across)"),
    "PaneAcross": ("ペイン (横)", "Pane (across)"),
    "PaneDown": ("ペイン (下)", "Pane (down)"),
    "PaneAcrossThenDown": ("ペイン (横から下へ)", "Pane (across then down)"),
    "PaneDownThenAcross": ("ペイン (下から横へ)", "Pane (down then across)"),
    "Cell": ("セル", "Cell"),
    "Field": ("特定のディメンション", "Specific Dimensions"),
}

# 簡易表計算の種類
CALC_TYPE_LABELS = {
    "PctTotal": ("合計に対する割合", "Percent of Total"),
    "RunningTotal": ("累計", "Running Total"),
    "Difference": ("差", "Difference"),
    "PercentDifference": ("差の割合", "Percent Difference"),
    "Percentile": ("百分位", "Percentile"),
    "Rank": ("ランク", "Rank"),
    "MovingCalc": ("移動平均", "Moving Average"),
    "CompoundGrowthRate": ("複合成長率", "Compound Growth Rate"),
    "YTDTotal": ("現時点年間累計の合計", "Year to Date Total"),
    "YTDGrowth": ("現時点年間累計の成長", "Year to Date Growth"),
    "YearOverYearGrowth": ("前年比成長率", "Year over Year Growth"),
}

DERIVATION_LABELS = {
    "Sum": ("合計", "Sum"),
    "Avg": ("平均", "Average"),
    "Min": ("最小値", "Minimum"),
    "Max": ("最大値", "Maximum"),
    "Count": ("カウント", "Count"),
    "CountD": ("個別カウント", "Count (Distinct)"),
    "Median": ("中央値", "Median"),
    "User": ("(式の定義どおり)", "(as defined in formula)"),
    "None": ("-", "-"),
}

_INTERNAL_ID_PATTERN = re.compile(r"_[0-9A-Fa-f]{16,}\b")

NOTE = (
    "※ 「次を使用して計算」の [ ] 内は twb 内部の設定値です。"
    "ピルごとの設定はワークシート上の配置に対する上書きを表します。",
    "* Values in [ ] are the raw settings stored in the twb file. "
    "Per-field settings are overrides applied to a field placed on a worksheet.",
)


def render_table_calcs(
    workbook: Workbook,
    caption_map: dict[str, str],
    number: int,
    t: Translator = JA,
) -> list[str]:
    """表計算設定章 (ピルごとの設定 + フィールド既定の設定)。"""
    pill_rows = [
        (
            sheet.name,
            _pill_label(pill.column_ref, caption_map, t),
            t(
                *DERIVATION_LABELS.get(
                    pill.derivation, (pill.derivation or "-", pill.derivation or "-")
                )
            ),
            _calc_type_label(pill.table_calc, t),
            _ordering_label(pill.table_calc, caption_map, t),
            _details(pill.table_calc),
        )
        for sheet in workbook.worksheets
        for pill in sheet.table_calcs
    ]
    default_rows = [
        (
            calc.display_name,
            _calc_type_label(calc.table_calc, t),
            _ordering_label(calc.table_calc, caption_map, t),
            _details(calc.table_calc),
        )
        for calc in workbook.calculated_fields
        if calc.table_calc is not None
    ]
    lines = [f"## {number}. " + t("表計算設定", "Table Calculations"), ""]
    if not pill_rows and not default_rows:
        lines.extend([t(*NOT_APPLICABLE), ""])
        return lines
    calc_type_header = t("表計算の種類", "Table calculation")
    compute_using_header = t("次を使用して計算", "Compute Using")
    details_header = t("詳細", "Details")
    section = 1
    if pill_rows:
        lines.extend(
            [
                f"### {number}.{section} "
                + t(
                    "ピルごとの設定 (ワークシート別)",
                    "Per-field settings (by worksheet)",
                ),
                "",
            ]
        )
        section += 1
        lines.extend(
            _table(
                (
                    t("ワークシート", "Worksheet"),
                    t("対象フィールド", "Field"),
                    t("集計", "Aggregation"),
                    calc_type_header,
                    compute_using_header,
                    details_header,
                ),
                pill_rows,
            )
        )
    if default_rows:
        lines.extend(
            [
                f"### {number}.{section} "
                + t("フィールド既定の設定", "Default settings on the field"),
                "",
            ]
        )
        lines.extend(
            _table(
                (
                    t("計算フィールド", "Calculated field"),
                    calc_type_header,
                    compute_using_header,
                    details_header,
                ),
                default_rows,
            )
        )
    lines.extend([t(*NOTE), ""])
    return lines


def _pill_label(
    column_ref: str, caption_map: dict[str, str], t: Translator
) -> str:
    label = humanize_field_ref(column_ref, caption_map, t)
    return _INTERNAL_ID_PATTERN.sub("", label)


def _ordering_label(
    table_calc: TableCalc, caption_map: dict[str, str], t: Translator
) -> str:
    if table_calc.ordering_type == "Field":
        fields = " → ".join(
            humanize_field_ref(field, caption_map, t)
            for field in table_calc.order_fields
            if field
        )
        base = t(*ORDERING_TYPE_LABELS["Field"])
        return f"{base}: {fields}" if fields else base
    pair = ORDERING_TYPE_LABELS.get(table_calc.ordering_type)
    if pair is None:
        return table_calc.ordering_type or "-"
    return f"{t(*pair)} [{table_calc.ordering_type}]"


def _calc_type_label(table_calc: TableCalc, t: Translator) -> str:
    if not table_calc.calc_type:
        return t("式による表計算", "Custom (defined in formula)")
    pair = CALC_TYPE_LABELS.get(table_calc.calc_type)
    if pair is None:
        return table_calc.calc_type
    return f"{t(*pair)} [{table_calc.calc_type}]"


def _details(table_calc: TableCalc) -> str:
    return (
        ", ".join(f"{name}={value}" for name, value in table_calc.extra)
        or "-"
    )
