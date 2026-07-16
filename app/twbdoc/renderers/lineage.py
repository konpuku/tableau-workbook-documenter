"""計算フィールドのリネージュ (依存関係) を Mermaid で描画する。

ノード形状: 長方形 = 計算フィールド / 六角形 = パラメーター / 丸角 = データソース列
エッジ: 参照元 --> 参照先 (データの流れる方向)
"""

from __future__ import annotations

import re

from ..model import Workbook

LEGEND = "凡例: 長方形 = 計算フィールド / 六角形 = パラメーター / 丸角 = データソース列"


def render_lineage_mermaid(
    workbook: Workbook, anchors: dict[str, str] | None = None
) -> list[str]:
    """ワークブック全体の計算フィールド依存関係図の行リストを返す。

    anchors: 計算フィールド内部名 -> 詳細節のアンカー。渡された場合は
    Mermaid の click (対応ビューアのみ動作) と図直下のリンク一覧を併記する。
    """
    calc_names = {calc.name: calc.display_name for calc in workbook.calculated_fields}
    param_names = {
        parameter.name: parameter.display_name
        for parameter in workbook.parameters
    }
    field_names = {
        field.name: field.display_name
        for datasource in workbook.datasources
        for field in datasource.fields
        if not field.is_calculated
    }

    node_ids: dict[str, str] = {}
    node_lines: list[str] = []
    edge_lines: list[str] = []

    def ensure_node(internal_name: str) -> str:
        if internal_name in node_ids:
            return node_ids[internal_name]
        node_id = f"f{len(node_ids)}"
        node_ids[internal_name] = node_id
        node_lines.append(_node_line(node_id, internal_name))
        return node_id

    def _node_line(node_id: str, internal_name: str) -> str:
        if internal_name in calc_names:
            label = _escape(calc_names[internal_name])
            return f'    {node_id}["{label}"]'
        if internal_name in param_names:
            label = _escape(param_names[internal_name])
            return f'    {node_id}{{{{"{label}"}}}}'
        label = _escape(
            field_names.get(internal_name, internal_name.strip("[]"))
        )
        return f'    {node_id}(["{label}"])'

    for calc in workbook.calculated_fields:
        calc_id = ensure_node(calc.name)
        for dependency in calc.depends_on:
            dependency_id = ensure_node(dependency)
            edge_lines.append(f"    {dependency_id} --> {calc_id}")

    if not node_ids:
        return []
    formulas = {calc.name: calc.formula for calc in workbook.calculated_fields}
    click_lines: list[str] = []
    link_items: list[str] = []
    for internal_name, node_id in node_ids.items():
        anchor = (anchors or {}).get(internal_name)
        if not anchor:
            continue
        tooltip = _tooltip_text(
            calc_names.get(internal_name, internal_name),
            formulas.get(internal_name, ""),
        )
        click_lines.append(f'    click {node_id} "#{anchor}" "{tooltip}"')
        link_items.append(f"[{calc_names.get(internal_name, internal_name)}](#{anchor})")
    lines = (
        ["```mermaid", "graph LR"]
        + node_lines
        + edge_lines
        + click_lines
        + ["```", "", LEGEND]
    )
    if link_items:
        lines.extend(
            [
                "",
                "各計算フィールドの詳細: " + " / ".join(link_items),
                "(対応ビューアでは図中のノードをクリックしても移動できます)",
            ]
        )
    return lines


def _escape(label: str) -> str:
    return label.replace('"', "#quot;")


# ツールチップに表示する計算式の最大文字数 (超過分は省略)
_TOOLTIP_FORMULA_LIMIT = 160

_BLOCK_COMMENT_PATTERN = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_PATTERN = re.compile(r"//[^\r\n]*")


def _tooltip_text(display_name: str, formula: str) -> str:
    """マウスオーバー時のツールチップ文字列 (フィールド名: 計算式)。

    ツールチップは改行を表示できないため、コメントを除いて 1 行に平坦化する。
    """
    without_comments = _LINE_COMMENT_PATTERN.sub(
        " ", _BLOCK_COMMENT_PATTERN.sub(" ", formula)
    )
    flattened = " ".join(without_comments.split())
    if len(flattened) > _TOOLTIP_FORMULA_LIMIT:
        flattened = flattened[: _TOOLTIP_FORMULA_LIMIT - 1] + "…"
    if not flattened:
        return _escape(f"{display_name} の詳細へ")
    return _escape(f"{display_name}: {flattened}")
