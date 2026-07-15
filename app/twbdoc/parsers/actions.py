"""ダッシュボードアクション (<actions>) の解析。

<actions> 直下にはコマンド形式の <action> のほか、
セットアクション (<edit-group-action>)・
パラメーターアクション (<edit-parameter-action>) が現れる。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import replace

from ..model import DashboardAction

COMMAND_KINDS = {
    "tsc:brush": "ハイライト",
    "tsc:filter": "フィルター",
    "tsc:tsl-filter": "フィルター",
    "tsc:url": "URL を開く",
    "tsc:navigate": "シートに移動",
}

_SPECIAL_ACTION_KINDS = {
    "edit-group-action": "セットの値を変更",
    "edit-parameter-action": "パラメーターの値を変更",
}

# 表示済みの列と重複するため詳細から除外するパラメーター
_CONSUMED_PARAMS = frozenset(
    {"target", "target-group", "field-captions", "exclude"}
)


def parse_actions(root: ET.Element) -> tuple[DashboardAction, ...]:
    """ワークブック直下のアクション一覧を抽出する。"""
    container = root.find("actions")
    if container is None:
        return ()
    parsed = []
    for element in container:
        if element.tag == "action":
            parsed.append(_parse_command_action(element))
        elif element.tag in _SPECIAL_ACTION_KINDS:
            parsed.append(
                _parse_common(element, _SPECIAL_ACTION_KINDS[element.tag])
            )
    return tuple(parsed)


def _parse_command_action(element: ET.Element) -> DashboardAction:
    command = element.find("command")
    command_name = "" if command is None else command.get("command", "")
    params = _collect_params(element)
    base = _parse_common(
        element, COMMAND_KINDS.get(command_name, command_name or "-")
    )
    return replace(base, fields=params.get("field-captions", ""))


def _parse_common(element: ET.Element, kind: str) -> DashboardAction:
    activation = element.find("activation")
    source = element.find("source")
    params = _collect_params(element)
    return DashboardAction(
        caption=element.get("caption", ""),
        name=element.get("name", ""),
        kind=kind,
        activation="" if activation is None else activation.get("type", ""),
        source_dashboard="" if source is None else source.get("dashboard", ""),
        source_worksheet="" if source is None else source.get("worksheet", ""),
        excluded_sheets=_excluded_sheets(source),
        target=params.get("target-group") or params.get("target", ""),
        params=tuple(
            (name, value)
            for name, value in params.items()
            if name not in _CONSUMED_PARAMS
        ),
    )


def _collect_params(element: ET.Element) -> dict[str, str]:
    return {
        param.get("name", ""): param.get("value", "")
        for param in element.iter("param")
    }


def _excluded_sheets(source: ET.Element | None) -> tuple[str, ...]:
    if source is None:
        return ()
    return tuple(
        excluded.get("name", "")
        for excluded in source.findall("exclude-sheet")
    )
