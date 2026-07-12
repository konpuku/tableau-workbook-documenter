"""ワークブックのメタ情報 (<workbook> 属性) の解析。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from ..model import WorkbookMeta


def parse_metadata(root: ET.Element, source_file: str) -> WorkbookMeta:
    """<workbook> のバージョン情報などを抽出する。"""
    return WorkbookMeta(
        source_file=source_file,
        version=root.get("version", ""),
        source_build=root.get("source-build", ""),
        source_platform=root.get("source-platform", ""),
    )
