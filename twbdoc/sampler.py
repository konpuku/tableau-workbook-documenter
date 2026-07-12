"""twbx 内のデータファイルからフィールドのサンプル値 (重複除外の代表値) を取得する。

対応形式:
- .hyper : tableauhyperapi が導入されている場合のみ (オプション依存)
- .csv / .txt : 標準ライブラリ (csv)
- .xlsx : 標準ライブラリ (zipfile + ElementTree)
- .xls (旧 Excel バイナリ) : 非対応 (注記を出す)

いずれも読めない場合は「(取得不可)」として設計書に表示される。
"""

from __future__ import annotations

import csv
import io
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

SAMPLE_COUNT = 5
MAX_VALUE_LENGTH = 30
MAX_CSV_SCAN_ROWS = 10000
MAX_DATA_FILE_BYTES = 512 * 1024 * 1024

_XLSX_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


@dataclass(frozen=True)
class TableSamples:
    """1 テーブル分のサンプル値 (列名 -> 代表値タプル)。"""

    name: str
    columns: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class SampleResult:
    """サンプリング結果全体。notes は取得できなかった理由の注記。"""

    tables: tuple[TableSamples, ...] = ()
    notes: tuple[str, ...] = ()


def collect_samples(twbx_path: Path) -> SampleResult:
    """twbx 内の全データファイルからサンプル値を収集する。"""
    if twbx_path.suffix.lower() != ".twbx":
        return SampleResult(
            notes=("twb 単体のためデータが同梱されておらず、サンプル値は取得できません",)
        )
    tables: list[TableSamples] = []
    notes: list[str] = []
    try:
        with zipfile.ZipFile(twbx_path) as archive:
            for info in archive.infolist():
                _collect_from_entry(archive, info, tables, notes)
    except (zipfile.BadZipFile, OSError) as error:
        notes.append(f"データファイルを読み込めませんでした: {error}")
    return SampleResult(tables=tuple(tables), notes=tuple(_unique(notes)))


def find_values(
    samples: SampleResult, object_id: str, column_name: str
) -> tuple[str, ...]:
    """テーブル (object_id 優先) と列名からサンプル値を探す。"""
    matched = [
        table
        for table in samples.tables
        if object_id and object_id in table.name
    ] or list(samples.tables)
    for table in matched:
        values = table.columns.get(column_name)
        if values is None:
            values = _case_insensitive_get(table.columns, column_name)
        if values:
            return values
    return ()


def _collect_from_entry(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    tables: list[TableSamples],
    notes: list[str],
) -> None:
    suffix = Path(info.filename).suffix.lower()
    if suffix not in (".hyper", ".csv", ".txt", ".xlsx", ".xls"):
        return
    if info.file_size > MAX_DATA_FILE_BYTES:
        notes.append(f"{Path(info.filename).name}: サイズ超過のためスキップしました")
        return
    if suffix == ".xls":
        notes.append(
            "旧 Excel 形式 (.xls) はサンプル値の取得に対応していません"
        )
        return
    if suffix == ".hyper":
        _collect_from_hyper(archive, info, tables, notes)
        return
    if suffix == ".xlsx":
        _collect_from_xlsx(archive, info, tables, notes)
        return
    _collect_from_csv(archive, info, tables, notes)


def _collect_from_hyper(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    tables: list[TableSamples],
    notes: list[str],
) -> None:
    try:
        from tableauhyperapi import Connection, HyperProcess, Telemetry
    except ImportError:
        notes.append(
            "Tableau 抽出 (.hyper) の読み取りには tableauhyperapi の導入が必要です "
            "(pip install tableauhyperapi)"
        )
        return
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            extracted = archive.extract(info.filename, tmpdir)
            with HyperProcess(
                telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU,
                parameters={"log_config": ""},  # hyperd.log を出力しない
            ) as process:
                with Connection(
                    endpoint=process.endpoint, database=extracted
                ) as connection:
                    tables.extend(_read_hyper_tables(connection))
    except Exception as error:  # hyper 側の例外型は依存導入時のみ存在するため広く捕捉
        notes.append(
            f"{Path(info.filename).name}: 抽出データの読み取りに失敗しました ({error})"
        )


def _read_hyper_tables(connection) -> list[TableSamples]:
    tables: list[TableSamples] = []
    catalog = connection.catalog
    for schema in catalog.get_schema_names():
        for table_name in catalog.get_table_names(schema):
            definition = catalog.get_table_definition(table_name)
            columns: dict[str, tuple[str, ...]] = {}
            for column in definition.columns:
                quoted = str(column.name)
                rows = connection.execute_list_query(
                    f"SELECT DISTINCT {quoted} FROM {table_name} "
                    f"WHERE {quoted} IS NOT NULL ORDER BY 1 LIMIT {SAMPLE_COUNT}"
                )
                columns[column.name.unescaped] = tuple(
                    _format_value(row[0]) for row in rows
                )
            tables.append(TableSamples(name=str(table_name), columns=columns))
    return tables


def _collect_from_csv(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    tables: list[TableSamples],
    notes: list[str],
) -> None:
    try:
        raw = archive.read(info.filename)
        text = _decode(raw)
        reader = csv.reader(io.StringIO(text))
        header = next(reader, None)
        if not header:
            return
        distinct: list[dict[str, None]] = [dict() for _ in header]
        for row_number, row in enumerate(reader):
            if row_number >= MAX_CSV_SCAN_ROWS:
                break
            for index, value in enumerate(row[: len(header)]):
                if value and len(distinct[index]) < SAMPLE_COUNT:
                    distinct[index].setdefault(_format_value(value))
        tables.append(
            TableSamples(
                name=Path(info.filename).name,
                columns={
                    name: tuple(values)
                    for name, values in zip(header, distinct)
                },
            )
        )
    except (csv.Error, UnicodeDecodeError, OSError) as error:
        notes.append(
            f"{Path(info.filename).name}: CSV の読み取りに失敗しました ({error})"
        )


def _collect_from_xlsx(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    tables: list[TableSamples],
    notes: list[str],
) -> None:
    try:
        data = archive.read(info.filename)
        with zipfile.ZipFile(io.BytesIO(data)) as workbook:
            shared = _read_shared_strings(workbook)
            for sheet_entry in workbook.namelist():
                if not sheet_entry.startswith(
                    "xl/worksheets/sheet"
                ) or not sheet_entry.endswith(".xml"):
                    continue
                table = _read_xlsx_sheet(
                    workbook, sheet_entry, shared, Path(info.filename).name
                )
                if table is not None:
                    tables.append(table)
    except (zipfile.BadZipFile, ET.ParseError, OSError) as error:
        notes.append(
            f"{Path(info.filename).name}: Excel の読み取りに失敗しました ({error})"
        )


def _read_shared_strings(workbook: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []
    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    return [
        "".join(node.text or "" for node in item.iter(f"{_XLSX_NS}t"))
        for item in root.findall(f"{_XLSX_NS}si")
    ]


def _read_xlsx_sheet(
    workbook: zipfile.ZipFile,
    sheet_entry: str,
    shared: list[str],
    book_name: str,
) -> TableSamples | None:
    root = ET.fromstring(workbook.read(sheet_entry))
    rows = root.findall(f"{_XLSX_NS}sheetData/{_XLSX_NS}row")
    if not rows:
        return None
    header = _read_xlsx_row(rows[0], shared)
    if not header:
        return None
    distinct: list[dict[str, None]] = [dict() for _ in header]
    for row in rows[1 : MAX_CSV_SCAN_ROWS + 1]:
        for index, value in enumerate(_read_xlsx_row(row, shared)[: len(header)]):
            if value and len(distinct[index]) < SAMPLE_COUNT:
                distinct[index].setdefault(_format_value(value))
    sheet_name = Path(sheet_entry).stem
    return TableSamples(
        name=f"{book_name}:{sheet_name}",
        columns={
            name: tuple(values) for name, values in zip(header, distinct)
        },
    )


def _read_xlsx_row(row: ET.Element, shared: list[str]) -> list[str]:
    values: list[str] = []
    for cell in row.findall(f"{_XLSX_NS}c"):
        value_node = cell.find(f"{_XLSX_NS}v")
        raw = "" if value_node is None else (value_node.text or "")
        if cell.get("t") == "s" and raw.isdigit() and int(raw) < len(shared):
            values.append(shared[int(raw)])
        elif cell.get("t") == "inlineStr":
            values.append(
                "".join(node.text or "" for node in cell.iter(f"{_XLSX_NS}t"))
            )
        else:
            values.append(raw)
    return values


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _format_value(value: object) -> str:
    text = str(value)
    if len(text) > MAX_VALUE_LENGTH:
        return text[: MAX_VALUE_LENGTH - 1] + "…"
    return text


def _case_insensitive_get(
    columns: dict[str, tuple[str, ...]], name: str
) -> tuple[str, ...] | None:
    lowered = name.lower()
    for key, values in columns.items():
        if key.lower() == lowered:
            return values
    return None


def _unique(items: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item)
    return list(seen)
