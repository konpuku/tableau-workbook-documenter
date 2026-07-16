"""twb 内蔵サムネイル (base64 PNG) の抽出。

Tableau はワークブック保存時に各シート・ダッシュボードのプレビュー画像
(約 192px の PNG) を <thumbnails>/<thumbnail name='...'> に base64 で埋め込む。
保存設定によってはサムネイルが存在しないワークブックもある。
"""

from __future__ import annotations

import base64
import binascii
import re
import xml.etree.ElementTree as ET

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]')


def extract_thumbnails(root: ET.Element) -> dict[str, bytes]:
    """シート/ダッシュボード名 -> PNG バイト列のマップを返す。

    base64 が壊れているものや PNG でないものは黙って除外する (fail-soft)。
    """
    result: dict[str, bytes] = {}
    for thumbnail in root.findall("thumbnails/thumbnail"):
        name = thumbnail.get("name", "")
        text = (thumbnail.text or "").strip()
        if not name or not text:
            continue
        try:
            data = base64.b64decode(text)
        except (ValueError, binascii.Error):
            continue
        if data.startswith(_PNG_MAGIC):
            result[name] = data
    return result


def safe_filename(name: str) -> str:
    """シート名を Windows で使えるファイル名に変換する。"""
    cleaned = _INVALID_FILENAME_CHARS.sub("_", name).strip().rstrip(".")
    return cleaned or "image"
