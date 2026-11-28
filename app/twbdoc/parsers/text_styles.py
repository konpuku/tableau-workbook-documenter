"""フォントの設定 (TextStyle) の解析。書式の一貫性チェック用。

フォントの指定は 2 か所にある。
- テキストの装飾: <formatted-text>/<run fontsize= fontname=>
  (シートタイトル・ツールヒント・ダッシュボードのテキスト等。件数はこちらが大半)
- 書式ルール: <style>/<style-rule element=>/<format attr='font-size'|'font-family'>

テキストの装飾は 1 ブロック (1 つのタイトル・1 つのツールヒント等) を 1 件にまとめ、
「基本サイズ」を 1 つ決める。タイトルは 1 行目 (見出し) のサイズ、それ以外は
文字数が最も多いサイズとする。見出しと副題のように意図してサイズを変えた部分を
ばらつきとして数えないため。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter

from ..model import TextStyle

# テキストの装飾の役割
TEXT_ROLE_WORKSHEET_TITLE = "worksheet-title"
TEXT_ROLE_DASHBOARD_TITLE = "dashboard-title"
TEXT_ROLE_DASHBOARD_TEXT = "dashboard-text"
TEXT_ROLE_TOOLTIP = "tooltip"
TEXT_ROLE_CAPTION = "caption"
TEXT_ROLE_MARK_LABEL = "mark-label"
TEXT_ROLE_ANNOTATION = "annotation"

OWNER_WORKBOOK = "workbook"
OWNER_WORKSHEET = "worksheet"
OWNER_DASHBOARD = "dashboard"

SOURCE_TEXT = "text"
SOURCE_FORMAT = "format"

# Tableau は段落の区切りに "Æ" + 改行を使う
_PARAGRAPH_MARK = "Æ"


def parse_text_styles(root: ET.Element) -> tuple[TextStyle, ...]:
    styles: list[TextStyle] = []
    styles.extend(_format_styles(root.find("style"), OWNER_WORKBOOK, ""))
    for worksheet in root.findall("worksheets/worksheet"):
        name = worksheet.get("name", "")
        styles.extend(_worksheet_styles(worksheet, name))
    for dashboard in root.findall("dashboards/dashboard"):
        name = dashboard.get("name", "")
        styles.extend(_dashboard_styles(dashboard, name))
    return tuple(styles)


def _worksheet_styles(worksheet: ET.Element, name: str) -> list[TextStyle]:
    styles: list[TextStyle] = []
    title = worksheet.find("layout-options/title/formatted-text")
    if title is not None:
        styles.append(_text_style(title, TEXT_ROLE_WORKSHEET_TITLE, OWNER_WORKSHEET, name, first_line=True))
    caption = worksheet.find("layout-options/caption/formatted-text")
    if caption is not None:
        styles.append(_text_style(caption, TEXT_ROLE_CAPTION, OWNER_WORKSHEET, name))
    for container, role in (
        ("customized-tooltip", TEXT_ROLE_TOOLTIP),
        ("customized-label", TEXT_ROLE_MARK_LABEL),
        ("annotation", TEXT_ROLE_ANNOTATION),
    ):
        for element in worksheet.iter(container):
            text = element.find("formatted-text")
            if text is not None:
                styles.append(_text_style(text, role, OWNER_WORKSHEET, name))
    for style in worksheet.iter("style"):
        styles.extend(_format_styles(style, OWNER_WORKSHEET, name))
    return [s for s in styles if s.font_size is not None or s.font_names]


def _dashboard_styles(dashboard: ET.Element, name: str) -> list[TextStyle]:
    styles: list[TextStyle] = []
    title = dashboard.find("layout-options/title/formatted-text")
    if title is not None:
        styles.append(_text_style(title, TEXT_ROLE_DASHBOARD_TITLE, OWNER_DASHBOARD, name, first_line=True))
    # デバイスレイアウト (<devicelayouts>) は既定レイアウトの複製なので数えない
    zones = dashboard.find("zones")
    if zones is not None:
        for zone in zones.iter("zone"):
            text = zone.find("formatted-text")
            if text is not None:
                styles.append(_text_style(text, TEXT_ROLE_DASHBOARD_TEXT, OWNER_DASHBOARD, name))
    styles.extend(_format_styles(dashboard.find("style"), OWNER_DASHBOARD, name))
    return [s for s in styles if s.font_size is not None or s.font_names]


def _text_style(
    formatted_text: ET.Element,
    role: str,
    owner_kind: str,
    owner: str,
    first_line: bool = False,
) -> TextStyle:
    runs = [
        (run, _visible_text(run.text or ""))
        for run in formatted_text.findall("run")
    ]
    names: list[str] = []
    for run, text in runs:
        font_name = (run.get("fontname") or "").strip()
        if text and font_name and font_name not in names:
            names.append(font_name)
    size = _first_line_size(runs) if first_line else _dominant_size(runs)
    return TextStyle(
        role=role,
        owner_kind=owner_kind,
        owner=owner,
        source=SOURCE_TEXT,
        font_size=size,
        font_names=tuple(names),
    )


def _visible_text(text: str) -> str:
    return text.replace(_PARAGRAPH_MARK, "").strip()


def _first_line_size(runs: list[tuple[ET.Element, str]]) -> float | None:
    """見出し (文字のある最初の run) のサイズ。副題など 2 行目以降は見ない。"""
    for run, text in runs:
        if text:
            return _to_size(run.get("fontsize"))
    return None


def _dominant_size(runs: list[tuple[ET.Element, str]]) -> float | None:
    """文字数が最も多いサイズ (同数なら先に出たもの)。"""
    weights: Counter[float] = Counter()
    order: list[float] = []
    for run, text in runs:
        size = _to_size(run.get("fontsize"))
        if size is None or not text:
            continue
        if size not in weights:
            order.append(size)
        weights[size] += len(text)
    if not weights:
        return None
    best = max(weights.values())
    return next(size for size in order if weights[size] == best)


def _format_styles(
    style: ET.Element | None, owner_kind: str, owner: str
) -> list[TextStyle]:
    if style is None:
        return []
    styles: list[TextStyle] = []
    for rule in style.findall("style-rule"):
        size: float | None = None
        names: list[str] = []
        for format_element in rule.findall("format"):
            attr = format_element.get("attr", "")
            value = (format_element.get("value") or "").strip()
            if attr == "font-size" and size is None:
                size = _to_size(value)
            elif attr == "font-family" and value and value not in names:
                names.append(value)
        if size is None and not names:
            continue
        styles.append(
            TextStyle(
                role=rule.get("element", ""),
                owner_kind=owner_kind,
                owner=owner,
                source=SOURCE_FORMAT,
                font_size=size,
                font_names=tuple(names),
            )
        )
    return styles


def _to_size(value: str | None) -> float | None:
    if not value:
        return None
    try:
        size = float(value)
    except ValueError:
        return None
    return size if size > 0 else None
