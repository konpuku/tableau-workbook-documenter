"""書式設定 (<style>/<style-rule>/<format>) の解析。

ワークブック直下・ワークシート内・ダッシュボード内のスタイルルールを収集する。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..model import FormatSetting, StyleRule

WORKBOOK_SCOPE = "ワークブック全体"


def parse_style_rules(root: ET.Element) -> tuple[StyleRule, ...]:
    """全レベルのスタイルルールを scope 付きで抽出する。"""
    rules: list[StyleRule] = []
    rules.extend(_parse_scope(root.find("style"), WORKBOOK_SCOPE))
    for worksheet in root.findall("worksheets/worksheet"):
        scope = f"ワークシート: {worksheet.get('name', '')}"
        for style in worksheet.iter("style"):
            rules.extend(_parse_scope(style, scope))
    for dashboard in root.findall("dashboards/dashboard"):
        scope = f"ダッシュボード: {dashboard.get('name', '')}"
        for style in dashboard.iter("style"):
            rules.extend(_parse_scope(style, scope))
    return tuple(rules)


def _parse_scope(
    style: ET.Element | None, scope: str
) -> tuple[StyleRule, ...]:
    if style is None:
        return ()
    rules: list[StyleRule] = []
    for rule in style.findall("style-rule"):
        formats = tuple(
            FormatSetting(
                attr=format_element.get("attr", ""),
                value=format_element.get("value", ""),
                scope=scope,
            )
            for format_element in rule.findall("format")
        )
        if formats:
            rules.append(
                StyleRule(element=rule.get("element", ""), formats=formats)
            )
    return tuple(rules)
