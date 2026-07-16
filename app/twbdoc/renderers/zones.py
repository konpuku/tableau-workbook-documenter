"""ダッシュボードのゾーンツリーを Markdown (インデント付きリスト + Mermaid) で描画する。"""

from __future__ import annotations

from ..fieldref import humanize_field_ref
from ..model import DashboardSize, Zone

ZONE_TYPE_LABELS = {
    "layout-flow": "コンテナ",
    "layout-basic": "基本レイアウト",
    "title": "タイトル",
    "text": "テキスト",
    "filter": "フィルター",
    "paramctrl": "パラメーターコントロール",
    "color": "凡例 (色)",
    "size": "凡例 (サイズ)",
    "shape": "凡例 (形状)",
    "map": "凡例 (マップ)",
    "highlight": "ハイライター",
    "web": "Web ページ",
    "bitmap": "イメージ",
    "empty": "空白",
    "worksheet": "ワークシート",
    "unknown": "その他",
}

# twb の相対座標 (0〜100000) を % に換算する除数
_COORDINATE_SCALE = 1000
# インデントリスト内でのテキスト表示の最大文字数
_TEXT_PREVIEW_LIMIT = 40


def render_zone_list(
    zones: tuple[Zone, ...],
    caption_map: dict[str, str],
    size: DashboardSize | None = None,
) -> list[str]:
    """ゾーンツリーをインデント付きリストの行リストとして返す。

    固定サイズのダッシュボードでは Tableau の「位置/サイズ」パネルと同じ
    ピクセル表記、それ以外 (自動・範囲) は % 表記になる。
    """
    pixel_size = fixed_pixel_size(size)
    lines: list[str] = []
    for zone in zones:
        _append_zone_lines(zone, caption_map, pixel_size, depth=0, lines=lines)
    return lines


def fixed_pixel_size(size: DashboardSize | None) -> tuple[int, int] | None:
    """固定サイズダッシュボードのピクセルサイズ (幅, 高さ)。それ以外は None。"""
    if size is None or size.sizing_mode != "fixed":
        return None
    try:
        width, height = int(size.minwidth), int(size.minheight)
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def render_zone_mermaid(
    zones: tuple[Zone, ...], caption_map: dict[str, str]
) -> list[str]:
    """ゾーンツリーを Mermaid (graph TD) の行リストとして返す。"""
    lines = ["```mermaid", "graph TD"]
    counter = [0]
    for zone in zones:
        _append_mermaid_lines(zone, caption_map, None, counter, lines)
    lines.append("```")
    return lines


def zone_label(zone: Zone, caption_map: dict[str, str]) -> str:
    """ゾーン 1 件の表示ラベル (種別 + 内容)。"""
    type_label = _zone_type_label(zone)
    detail = _zone_detail(zone, caption_map)
    if detail:
        return f"[{type_label}] {detail}"
    return f"[{type_label}]"


def _zone_type_label(zone: Zone) -> str:
    if zone.zone_type == "layout-flow":
        direction = {"vert": "垂直", "horz": "水平"}.get(zone.param, "")
        return f"{direction}コンテナ" if direction else "コンテナ"
    label = ZONE_TYPE_LABELS.get(zone.zone_type)
    if label is not None:
        return label
    return f"不明: {zone.zone_type}"


def _zone_detail(zone: Zone, caption_map: dict[str, str]) -> str:
    if zone.zone_type == "worksheet":
        return zone.name
    if zone.text:
        return _shorten(zone.text)
    if zone.zone_type in ("filter", "paramctrl", "color", "size", "shape", "highlight"):
        if not zone.param:
            return ""
        return humanize_field_ref(zone.param, caption_map)
    if zone.name:
        return zone.name
    return ""


def _coordinates_note(
    zone: Zone, pixel_size: tuple[int, int] | None
) -> str:
    if pixel_size is not None:
        width, height = pixel_size
        parts = [
            f"{label}:{_to_pixel(value, base)}px"
            for label, value, base in (
                ("x", zone.x, width),
                ("y", zone.y, height),
                ("幅", zone.w, width),
                ("高さ", zone.h, height),
            )
            if value is not None
        ]
    else:
        parts = [
            f"{label}:{_to_percent(value)}"
            for label, value in (
                ("x", zone.x),
                ("y", zone.y),
                ("w", zone.w),
                ("h", zone.h),
            )
            if value is not None
        ]
    return f" ({', '.join(parts)})" if parts else ""


def _to_pixel(value: int, base: int) -> int:
    """twb の相対座標 (0〜100000) を実ピクセルに換算する。"""
    return round(value * base / 100000)


def _to_percent(value: int) -> str:
    percent = value / _COORDINATE_SCALE
    if percent == int(percent):
        return f"{int(percent)}%"
    return f"{percent:.1f}%"


def _shorten(text: str, limit: int = _TEXT_PREVIEW_LIMIT) -> str:
    flattened = " ".join(text.split())
    if len(flattened) <= limit:
        return flattened
    return flattened[: limit - 1] + "…"


def _append_zone_lines(
    zone: Zone,
    caption_map: dict[str, str],
    pixel_size: tuple[int, int] | None,
    depth: int,
    lines: list[str],
) -> None:
    indent = "  " * depth
    lines.append(
        f"{indent}- {zone_label(zone, caption_map)}"
        f"{_coordinates_note(zone, pixel_size)}"
    )
    for child in zone.children:
        _append_zone_lines(child, caption_map, pixel_size, depth + 1, lines)


def _append_mermaid_lines(
    zone: Zone,
    caption_map: dict[str, str],
    parent_id: str | None,
    counter: list[int],
    lines: list[str],
) -> None:
    node_id = f"z{counter[0]}"
    counter[0] += 1
    label = zone_label(zone, caption_map).replace('"', "#quot;")
    lines.append(f'    {node_id}["{label}"]')
    if parent_id is not None:
        lines.append(f"    {parent_id} --> {node_id}")
    for child in zone.children:
        _append_mermaid_lines(child, caption_map, node_id, counter, lines)
