"""計算フィールドのリネージュ (依存関係) を Mermaid で描画する。

ノード形状: 長方形 = 計算フィールド / 六角形 = パラメーター / 丸角 = データソース列
エッジ: 参照元 --> 参照先 (データの流れる方向)
"""

from __future__ import annotations

from ..model import Workbook

LEGEND = "凡例: 長方形 = 計算フィールド / 六角形 = パラメーター / 丸角 = データソース列"


def render_lineage_mermaid(workbook: Workbook) -> list[str]:
    """ワークブック全体の計算フィールド依存関係図の行リストを返す。"""
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
    return (
        ["```mermaid", "graph LR"]
        + node_lines
        + edge_lines
        + ["```", "", LEGEND]
    )


def _escape(label: str) -> str:
    return label.replace('"', "#quot;")
