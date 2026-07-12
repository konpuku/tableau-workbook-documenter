"""フィルター (<filter>) の解析。

対象:
- ワークシート内: worksheet/table/view/filter
- 共通フィルター: shared-views/shared-view/filter (複数シート適用・コンテキスト)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import replace

from ..model import WorksheetFilter

_USER_NS = "{http://www.tableausoftware.com/xml/user}"


def parse_view_filters(worksheet: ET.Element) -> tuple[WorksheetFilter, ...]:
    """ワークシート内のフィルターを抽出する。"""
    view = worksheet.find("table/view")
    if view is None:
        return ()
    return tuple(_parse_filter(element) for element in view.findall("filter"))


def parse_shared_filters(root: ET.Element) -> tuple[WorksheetFilter, ...]:
    """shared-views 内の共通フィルター (複数シートに適用) を抽出する。"""
    return tuple(
        _parse_filter(element)
        for shared_view in root.findall("shared-views/shared-view")
        for element in shared_view.findall("filter")
    )


def parse_filter_element(element: ET.Element) -> WorksheetFilter:
    """単一の <filter> 要素を解析する (データソース/抽出フィルタでも再利用)。"""
    return _parse_filter(element)


def _parse_filter(element: ET.Element) -> WorksheetFilter:
    base = WorksheetFilter(
        column_ref=element.get("column", ""),
        filter_class=element.get("class", ""),
        included_values=element.get("included-values", ""),
        min_value=_child_text(element, "min"),
        max_value=_child_text(element, "max"),
        is_context=element.get("context") == "true",
    )
    group = element.find("groupfilter")
    if group is None:
        return base
    return _apply_groupfilter(base, group)


def _apply_groupfilter(
    base: WorksheetFilter, group: ET.Element
) -> WorksheetFilter:
    """groupfilter ツリーからメンバー選択・除外・全メンバー情報を反映する。"""
    function = group.get("function", "")
    enumeration = group.get(f"{_USER_NS}ui-enumeration", "")
    if function == "except":
        # except(全メンバー, 選択メンバー) = 選択メンバーを除外
        members: list[str] = []
        for child in group.findall("groupfilter"):
            members.extend(_collect_members(child))
        return replace(
            base,
            excluded=True,
            members=tuple(members),
            level=_find_level(group),
        )
    if function == "union" or function == "member":
        return replace(
            base,
            excluded=enumeration == "exclusive",
            members=tuple(_collect_members(group)),
            level=_find_level(group),
        )
    if function == "level-members":
        return replace(
            base,
            all_members=True,
            action=_strip_brackets(group.get(f"{_USER_NS}ui-action-filter", "")),
            level=_find_level(group),
        )
    if function == "filter":
        return replace(base, expression=group.get("expression", ""))
    return replace(base, expression=function)


def _collect_members(group: ET.Element) -> list[str]:
    members: list[str] = []
    if group.get("function") == "member":
        member = group.get("member", "")
        if member:
            members.append(_strip_quotes(member))
    for child in group.findall("groupfilter"):
        members.extend(_collect_members(child))
    return members


def _find_level(group: ET.Element) -> str:
    level = group.get("level", "")
    if level:
        return level
    for child in group.findall("groupfilter"):
        found = _find_level(child)
        if found:
            return found
    return ""


def _child_text(element: ET.Element, tag: str) -> str:
    child = element.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _strip_brackets(value: str) -> str:
    return value.strip("[]")
