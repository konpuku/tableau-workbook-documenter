"""表計算設定章のレンダリング。

Tableau の表計算はフィールド既定の設定に加えて、
配置したピル (シート上のフィールド) ごとに上書きできるため、
「ピルごとの設定」と「フィールド既定の設定」を分けて記載する。
"""

from __future__ import annotations

import re

from ..fieldref import humanize_field_ref
from ..model import TableCalc, Workbook
from .tables import table as _table

NOT_APPLICABLE = "(該当なし)"

# ordering-type (次を使用して計算) の日本語ラベル。
# 確認できていない値は生の値のまま表示する (fail-soft)。
ORDERING_TYPE_LABELS = {
    "Rows": "表 (横)",
    "Columns": "表 (下)",
    "RowsAcrossThenDown": "表 (横から下)",
    "ColumnsDownThenAcross": "表 (下から横)",
    "Cell": "セル",
    "Field": "特定のディメンション",
}

# type 属性 (簡易表計算の種類) の日本語ラベル。
CALC_TYPE_LABELS = {
    "PctTotal": "合計に対する割合",
    "RunningTotal": "累計",
    "Difference": "差",
    "PercentDifference": "差の割合",
    "Percentile": "パーセンタイル",
    "Rank": "ランク",
    "MovingCalc": "移動計算",
    "CompoundGrowthRate": "複合成長率",
    "YTDTotal": "YTD 合計",
    "YTDGrowth": "YTD 成長率",
}

DERIVATION_LABELS = {
    "Sum": "合計",
    "Avg": "平均",
    "Min": "最小",
    "Max": "最大",
    "Count": "カウント",
    "CountD": "個別カウント",
    "Median": "中央値",
    "User": "(式の定義どおり)",
    "None": "-",
}

_INTERNAL_ID_PATTERN = re.compile(r"_[0-9A-Fa-f]{16,}\b")

NOTE = (
    "※ 「次を使用して計算」の [ ] 内は twb 内部の設定値です。"
    "ピルごとの設定はワークシート上の配置に対する上書きを表します。"
)


def render_table_calcs(
    workbook: Workbook, caption_map: dict[str, str], number: int
) -> list[str]:
    """表計算設定章 (ピルごとの設定 + フィールド既定の設定)。"""
    pill_rows = [
        (
            sheet.name,
            _pill_label(pill.column_ref, caption_map),
            DERIVATION_LABELS.get(pill.derivation, pill.derivation or "-"),
            _calc_type_label(pill.table_calc),
            _ordering_label(pill.table_calc, caption_map),
            _details(pill.table_calc),
        )
        for sheet in workbook.worksheets
        for pill in sheet.table_calcs
    ]
    default_rows = [
        (
            calc.display_name,
            _calc_type_label(calc.table_calc),
            _ordering_label(calc.table_calc, caption_map),
            _details(calc.table_calc),
        )
        for calc in workbook.calculated_fields
        if calc.table_calc is not None
    ]
    lines = [f"## {number}. 表計算設定", ""]
    if not pill_rows and not default_rows:
        lines.extend([NOT_APPLICABLE, ""])
        return lines
    section = 1
    if pill_rows:
        lines.extend([f"### {number}.{section} ピルごとの設定 (シート別)", ""])
        section += 1
        lines.extend(
            _table(
                (
                    "ワークシート",
                    "対象ピル",
                    "集計",
                    "表計算の種類",
                    "次を使用して計算",
                    "詳細",
                ),
                pill_rows,
            )
        )
    if default_rows:
        lines.extend([f"### {number}.{section} フィールド既定の設定", ""])
        lines.extend(
            _table(
                ("計算フィールド", "表計算の種類", "次を使用して計算", "詳細"),
                default_rows,
            )
        )
    lines.extend([NOTE, ""])
    return lines


def _pill_label(column_ref: str, caption_map: dict[str, str]) -> str:
    label = humanize_field_ref(column_ref, caption_map)
    return _INTERNAL_ID_PATTERN.sub("", label)


def _ordering_label(table_calc: TableCalc, caption_map: dict[str, str]) -> str:
    if table_calc.ordering_type == "Field":
        fields = " → ".join(
            humanize_field_ref(field, caption_map)
            for field in table_calc.order_fields
            if field
        )
        base = ORDERING_TYPE_LABELS["Field"]
        return f"{base}: {fields}" if fields else base
    label = ORDERING_TYPE_LABELS.get(table_calc.ordering_type)
    if label is None:
        return table_calc.ordering_type or "-"
    return f"{label} [{table_calc.ordering_type}]"


def _calc_type_label(table_calc: TableCalc) -> str:
    if not table_calc.calc_type:
        return "式による表計算"
    label = CALC_TYPE_LABELS.get(table_calc.calc_type)
    if label is None:
        return table_calc.calc_type
    return f"{label} [{table_calc.calc_type}]"


def _details(table_calc: TableCalc) -> str:
    return (
        ", ".join(f"{name}={value}" for name, value in table_calc.extra)
        or "-"
    )
