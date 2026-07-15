"""表計算設定 (<table-calc>) の解析。

表計算設定は 2 か所に現れる:
- データソース側 column/calculation/table-calc = フィールド既定の設定
- ワークシート側 datasource-dependencies 内の column-instance/table-calc
  = ピルごとの設定 (同じフィールドでもシート・ピルによって異なる)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..model import PillTableCalc, TableCalc

_KNOWN_ATTRS = frozenset({"ordering-type", "type"})


def parse_table_calc(calculation: ET.Element | None) -> TableCalc | None:
    """<calculation> 直下の <table-calc> を解析する (無ければ None)。"""
    if calculation is None:
        return None
    element = calculation.find("table-calc")
    if element is None:
        return None
    return _to_table_calc(element)


def parse_pill_table_calcs(worksheet: ET.Element) -> tuple[PillTableCalc, ...]:
    """ワークシート内のピルごとの表計算設定を抽出する。

    column-instance (ピルそのもの) を優先し、同じフィールドの
    シート内 column/calculation 定義は column-instance が無い場合のみ採用する
    (両方に現れると重複するため)。
    """
    pills: list[PillTableCalc] = []
    covered: set[str] = set()
    for dependencies in worksheet.iter("datasource-dependencies"):
        for instance in dependencies.findall("column-instance"):
            element = instance.find("table-calc")
            if element is None:
                continue
            column_ref = instance.get("column", "")
            covered.add(column_ref)
            pills.append(
                PillTableCalc(
                    column_ref=column_ref,
                    table_calc=_to_table_calc(element),
                    derivation=instance.get("derivation", ""),
                )
            )
    for dependencies in worksheet.iter("datasource-dependencies"):
        for column in dependencies.findall("column"):
            table_calc = parse_table_calc(column.find("calculation"))
            column_ref = column.get("name", "")
            if table_calc is None or column_ref in covered:
                continue
            covered.add(column_ref)
            pills.append(
                PillTableCalc(column_ref=column_ref, table_calc=table_calc)
            )
    return tuple(pills)


def _to_table_calc(element: ET.Element) -> TableCalc:
    extra = tuple(
        (name, value)
        for name, value in sorted(element.attrib.items())
        if name not in _KNOWN_ATTRS
    )
    return TableCalc(
        ordering_type=element.get("ordering-type", ""),
        calc_type=element.get("type", ""),
        order_fields=tuple(
            order.get("field", "") for order in element.findall("order")
        ),
        extra=extra,
    )
