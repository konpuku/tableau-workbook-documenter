"""入力ファイル (.twbx / .twb) から XML ルート要素を取得する。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .errors import InvalidFileError, ParseError
from .i18n import JA, Translator

SUPPORTED_EXTENSIONS = (".twbx", ".twb")

# zip bomb 対策: twb (XML) の展開後サイズ上限
MAX_TWB_UNCOMPRESSED_BYTES = 512 * 1024 * 1024


def load_workbook_xml(path: Path, t: Translator = JA) -> ET.Element:
    """twbx / twb ファイルからワークブック XML のルート要素を返す。

    - .twbx: ZIP としてメモリ上に展開し、内部の .twb を読む
    - .twb : そのまま XML として解析する
    """
    validated = _validate_path(path, t)
    if validated.suffix.lower() == ".twbx":
        xml_bytes = _read_twb_from_twbx(validated, t)
    else:
        xml_bytes = _read_file(validated, t)
    return _parse_xml(xml_bytes, validated, t)


def _validate_path(path: Path, t: Translator) -> Path:
    if not path.exists():
        raise InvalidFileError(
            t(f"ファイルが見つかりません: {path}", f"File not found: {path}")
        )
    if not path.is_file():
        raise InvalidFileError(
            t(f"ファイルではありません: {path}", f"Not a file: {path}")
        )
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise InvalidFileError(
            t(
                f"対応していない拡張子です (.twbx / .twb のみ対応): {path.name}",
                f"Unsupported file type (.twbx / .twb only): {path.name}",
            )
        )
    return path


def _read_twb_from_twbx(path: Path, t: Translator) -> bytes:
    """twbx (ZIP) 内の .twb をメモリ上で読み出す。

    ZIP 内エントリ名は日本語が文字化けする場合があるため、
    名前一致ではなく拡張子 .twb で検索する (ルートに近い最短パス優先)。
    """
    try:
        with zipfile.ZipFile(path) as archive:
            twb_entries = [
                name
                for name in archive.namelist()
                if name.lower().endswith(".twb")
            ]
            if not twb_entries:
                raise InvalidFileError(
                    t(
                        f"twbx 内に .twb が見つかりません: {path.name}",
                        f"No .twb file inside the twbx: {path.name}",
                    )
                )
            entry = min(twb_entries, key=lambda name: name.count("/"))
            info = archive.getinfo(entry)
            if info.file_size > MAX_TWB_UNCOMPRESSED_BYTES:
                raise InvalidFileError(
                    t(
                        f"twb の展開後サイズが上限を超えています: "
                        f"{path.name} ({info.file_size:,} bytes)",
                        f"The uncompressed twb exceeds the size limit: "
                        f"{path.name} ({info.file_size:,} bytes)",
                    )
                )
            return archive.read(entry)
    except zipfile.BadZipFile as error:
        raise InvalidFileError(
            t(
                f"twbx ファイルが壊れています (ZIP として読めません): {path.name}",
                f"The twbx file is corrupted (cannot be read as a ZIP): "
                f"{path.name}",
            )
        ) from error
    except (RuntimeError, NotImplementedError, OSError) as error:
        # 暗号化 ZIP は RuntimeError、未対応圧縮方式は NotImplementedError になる
        raise InvalidFileError(
            t(
                f"twbx を展開できません (暗号化・未対応圧縮の可能性): "
                f"{path.name} ({error})",
                f"Cannot extract the twbx (it may be encrypted or use an "
                f"unsupported compression): {path.name} ({error})",
            )
        ) from error


def _read_file(path: Path, t: Translator) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise InvalidFileError(
            t(f"ファイルを読み込めません: {path}", f"Cannot read the file: {path}")
        ) from error


def _parse_xml(xml_bytes: bytes, path: Path, t: Translator) -> ET.Element:
    # billion laughs 対策: 正規の twb は DTD/エンティティを使わないため拒否する
    if b"<!DOCTYPE" in xml_bytes[:8192] or b"<!ENTITY" in xml_bytes[:8192]:
        raise ParseError(
            t(
                f"DTD/エンティティ定義を含む XML は非対応です: {path.name}",
                f"XML with DTD or entity definitions is not supported: "
                f"{path.name}",
            )
        )
    try:
        return ET.fromstring(xml_bytes)
    except ET.ParseError as error:
        raise ParseError(
            t(
                f"XML の解析に失敗しました ({path.name}): {error}",
                f"Failed to parse the XML ({path.name}): {error}",
            )
        ) from error
