"""計算フィールドの解析。

数式内の内部 ID (例: [Calculation_0861198210101248]) を
表示名 (caption) に置換して可読性を高める。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ..fieldref import find_referenced_names
from ..model import CalculatedField
from .parameters import PARAMETERS_DATASOURCE_NAME

_LINE_COMMENT_PATTERN = re.compile(r"//([^\r\n]*)")
_BLOCK_COMMENT_PATTERN = re.compile(r"/\*(.*?)\*/", re.DOTALL)


def parse_calculated_fields(root: ET.Element) -> tuple[CalculatedField, ...]:
    """全データソースの計算フィールドを抽出する (パラメーターの既定式は除く)。"""
    caption_map = build_caption_map(root)
    known_names = _collect_known_names(root)
    fields: list[CalculatedField] = []
    for datasource in root.findall("datasources/datasource"):
        if datasource.get("name") == PARAMETERS_DATASOURCE_NAME:
            continue
        datasource_name = datasource.get("caption") or datasource.get("name", "")
        for column in datasource.findall("column"):
            calculated = _parse_calculated_field(
                column, datasource_name, caption_map, known_names
            )
            if calculated is not None:
                fields.append(calculated)
    return tuple(fields)


def parse_field_comment(column: ET.Element) -> str:
    """GUI で設定されたフィールドコメント (<desc>) を抽出する。"""
    runs = column.findall("desc/formatted-text/run")
    return "\n".join(run.text or "" for run in runs).strip()


def _collect_known_names(root: ET.Element) -> frozenset[str]:
    """全データソースのフィールド内部名の集合 (数式内参照の解決用)。

    カスタマイズされていない生フィールドは <column> を持たず
    <metadata-record> にのみ現れるため、両方から収集する。
    """
    names: set[str] = set()
    for datasource in root.findall("datasources/datasource"):
        for column in datasource.findall("column"):
            if column.get("name"):
                names.add(column.get("name", ""))
        for record in datasource.iter("metadata-record"):
            local_name = record.find("local-name")
            if local_name is not None and local_name.text:
                names.add(local_name.text.strip())
    return frozenset(names)


def _extract_inline_comments(raw_formula: str) -> tuple[str, ...]:
    """数式内の // 行コメントと /* */ ブロックコメントを抽出する。"""
    comments = [
        match.strip() for match in _BLOCK_COMMENT_PATTERN.findall(raw_formula)
    ]
    without_blocks = _BLOCK_COMMENT_PATTERN.sub("", raw_formula)
    comments.extend(
        match.strip() for match in _LINE_COMMENT_PATTERN.findall(without_blocks)
    )
    return tuple(comment for comment in comments if comment)


def build_caption_map(root: ET.Element) -> dict[str, str]:
    """内部 ID ([Calculation_xxx] 等) -> [表示名] の置換マップを構築する。

    パラメーター ([Parameters].[Parameter 1] 形式で参照される) も含む。
    """
    caption_map: dict[str, str] = {}
    for datasource in root.findall("datasources/datasource"):
        for column in datasource.findall("column"):
            name = column.get("name", "")
            caption = column.get("caption", "")
            if name and caption and name != f"[{caption}]":
                caption_map[name] = f"[{caption}]"
    return caption_map


def resolve_formula(raw_formula: str, caption_map: dict[str, str]) -> str:
    """数式内の内部 ID を表示名に置換する。"""
    resolved = raw_formula
    for internal_name in sorted(caption_map, key=len, reverse=True):
        resolved = resolved.replace(internal_name, caption_map[internal_name])
    return resolved


def _parse_calculated_field(
    column: ET.Element,
    datasource_name: str,
    caption_map: dict[str, str],
    known_names: frozenset[str],
) -> CalculatedField | None:
    calculation = column.find("calculation")
    if calculation is None:
        return None
    raw_formula = calculation.get("formula", "")
    if not raw_formula:
        return None
    return CalculatedField(
        name=column.get("name", ""),
        caption=column.get("caption", ""),
        formula=resolve_formula(raw_formula, caption_map),
        raw_formula=raw_formula,
        datatype=column.get("datatype", ""),
        role=column.get("role", ""),
        calc_class=calculation.get("class", "tableau"),
        datasource=datasource_name,
        comment=parse_field_comment(column),
        inline_comments=_extract_inline_comments(raw_formula),
        depends_on=find_referenced_names(raw_formula, known_names),
    )
