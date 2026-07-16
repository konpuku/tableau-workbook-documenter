"""ダッシュボードレイアウトの簡略図 (SVG) を生成する。

実際の位置・サイズ比率を保った入れ子のボックス図を描く。
コンテナは枠のみ (ラベルは左上)、ワークシート等の末端要素は
塗りつぶし + 中央ラベルで表示する。
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from ..model import Dashboard, Zone
from .zones import fixed_pixel_size, zone_label

# 自動サイズなどピクセルサイズが不明な場合の描画キャンバス
_DEFAULT_CANVAS = (800, 600)
# 表示上の最大幅 (これより大きいダッシュボードは縮小表示)
_MAX_DISPLAY_WIDTH = 820
_FONT_SIZE = 13
# ラベル 1 文字あたりの概算幅 (px)。枠に収まる文字数の見積もりに使う
_CHAR_WIDTH = 13

_CONTAINER_TYPES = frozenset({"layout-flow", "layout-basic"})

_STYLE = (
    "  <style>\n"
    "    text { font-family: 'Meiryo UI', 'Yu Gothic UI', sans-serif; "
    f"font-size: {_FONT_SIZE}px; fill: #1f4e63; }}\n"
    "    .container { fill: none; stroke: #4a7a94; stroke-width: 1.5; }\n"
    "    .leaf { fill: #cfe8f5; fill-opacity: 0.85; stroke: #2c5f7c; "
    "stroke-width: 1; }\n"
    "  </style>\n"
)


def render_layout_svg(
    dashboard: Dashboard, caption_map: dict[str, str] | None = None
) -> str | None:
    """ダッシュボードのレイアウト簡略図を SVG 文字列として返す。

    座標を持つゾーンが無い場合は None。
    """
    width, height = fixed_pixel_size(dashboard.size) or _DEFAULT_CANVAS
    shapes: list[str] = []
    for zone in dashboard.zones:
        _append_zone_shapes(zone, caption_map or {}, width, height, shapes, 0)
    if not shapes:
        return None
    display_width = min(width, _MAX_DISPLAY_WIDTH)
    display_height = round(height * display_width / width)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" '
        f'width="{display_width}" height="{display_height}">\n'
        + _STYLE
        + f'  <rect x="0" y="0" width="{width}" height="{height}" '
        'fill="#ffffff" stroke="#333333" stroke-width="2" />\n'
        + "".join(shapes)
        + "</svg>\n"
    )


def _append_zone_shapes(
    zone: Zone,
    caption_map: dict[str, str],
    width: int,
    height: int,
    shapes: list[str],
    depth: int,
) -> None:
    box = _zone_box(zone, width, height)
    if box is not None:
        x, y, w, h = box
        label = zone_label(zone, caption_map)
        if zone.zone_type in _CONTAINER_TYPES:
            shapes.append(
                f'  <rect class="container" x="{x:.1f}" y="{y:.1f}" '
                f'width="{w:.1f}" height="{h:.1f}" />\n'
            )
            # 入れ子コンテナは左上が一致しがちなのでラベルを深さ分ずらす
            shapes.append(
                _label_text(
                    label, x + 6, y + _FONT_SIZE + 4 + depth * (_FONT_SIZE + 3), w
                )
            )
        else:
            shapes.append(
                f'  <rect class="leaf" x="{x:.1f}" y="{y:.1f}" '
                f'width="{w:.1f}" height="{h:.1f}" />\n'
            )
            shapes.append(
                _label_text(
                    label,
                    x + w / 2,
                    y + h / 2 + _FONT_SIZE / 2,
                    w,
                    centered=True,
                )
            )
    for child in zone.children:
        _append_zone_shapes(child, caption_map, width, height, shapes, depth + 1)


def _zone_box(
    zone: Zone, width: int, height: int
) -> tuple[float, float, float, float] | None:
    if None in (zone.x, zone.y, zone.w, zone.h):
        return None
    return (
        zone.x * width / 100000,
        zone.y * height / 100000,
        zone.w * width / 100000,
        zone.h * height / 100000,
    )


def _label_text(
    label: str, x: float, y: float, box_width: float, centered: bool = False
) -> str:
    max_chars = max(int(box_width / _CHAR_WIDTH), 0)
    if max_chars < 2:
        return ""
    if len(label) > max_chars:
        label = label[: max_chars - 1] + "…"
    anchor = ' text-anchor="middle"' if centered else ""
    return f'  <text x="{x:.0f}" y="{y:.0f}"{anchor}>{escape(label)}</text>\n'
