"""設計書 Markdown を単一 HTML に変換する。

ビジネスユーザが VS Code なしでも閲覧できるよう、mermaid.js を
インラインで同梱し、ブラウザで図・目次ジャンプ・ツールチップが動く
HTML を生成する。変換対象は本ツールが出力する Markdown サブセットのみ:
見出し / 段落 / 入れ子リスト / テーブル / 画像 / リンク / コードフェンス。
"""

from __future__ import annotations

import html as html_module
import re
from collections.abc import Callable
from pathlib import Path

from .anchors import gfm_slug

_ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets"
_MERMAID_FILENAME = "mermaid.min.js"

_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_IMAGE_PATTERN = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)$")
_HEADING_PATTERN = re.compile(r"^(#{1,4}) (.*)$")
_LIST_PATTERN = re.compile(r"^(\s*)- (.*)$")
_TABLE_SEPARATOR_PATTERN = re.compile(r"^\|[\s\-:|]+\|$")
_CELL_SPLIT_PATTERN = re.compile(r"(?<!\\)\|")

MERMAID_MISSING_NOTE = (
    "※ Mermaid ライブラリが見つからないため、図はコードとして表示されます。"
)

_CSS = """
body { font-family: 'Meiryo UI', 'Yu Gothic UI', 'Hiragino Sans', sans-serif;
       color: #24292f; line-height: 1.6; margin: 0; background: #ffffff; }
main { max-width: 1100px; margin: 0 auto; padding: 24px 32px 64px; }
h1 { border-bottom: 2px solid #d0d7de; padding-bottom: 8px; }
h2 { border-bottom: 1px solid #d0d7de; padding-bottom: 6px; margin-top: 40px; }
h3 { margin-top: 28px; }
table { border-collapse: collapse; margin: 12px 0; display: block;
        max-width: 100%; overflow-x: auto; }
th, td { border: 1px solid #d0d7de; padding: 5px 10px; text-align: left;
         vertical-align: top; }
th { background: #f6f8fa; }
pre { background: #f6f8fa; padding: 12px; border-radius: 6px;
      overflow-x: auto; }
pre.mermaid { background: #ffffff; }
img { max-width: 100%; height: auto; }
a { color: #0969da; text-decoration: none; }
a:hover { text-decoration: underline; }
ul { padding-left: 1.6em; }
li { margin: 2px 0; }
.mermaidTooltip { position: absolute; background: #fff8dc;
                  border: 1px solid #b8a86a; border-radius: 4px;
                  padding: 6px 10px; font-size: 12px; max-width: 480px;
                  pointer-events: none; z-index: 100; color: #24292f; }
"""


def render_html(
    markdown: str,
    title: str,
    load_image: Callable[[str], str | None] | None = None,
) -> str:
    """設計書 Markdown を単一 HTML 文字列に変換する。

    load_image: 画像パス -> data URI (取得できない場合 None)。
    """
    mermaid_js = _load_mermaid_js()
    body = _convert_body(markdown, load_image)
    if mermaid_js is None:
        body = f"<p>{_escape(MERMAID_MISSING_NOTE)}</p>\n" + body
        scripts = ""
    else:
        scripts = (
            f"<script>{mermaid_js}</script>\n"
            "<script>mermaid.initialize({ startOnLoad: true, "
            "securityLevel: 'loose' });</script>\n"
        )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{_escape(title)}</title>\n"
        f"<style>{_CSS}</style>\n"
        "</head>\n<body>\n<main>\n"
        + body
        + "</main>\n"
        + scripts
        + "</body>\n</html>\n"
    )


def _load_mermaid_js() -> str | None:
    path = _ASSETS_DIR / _MERMAID_FILENAME
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _convert_body(
    markdown: str, load_image: Callable[[str], str | None] | None
) -> str:
    lines = markdown.splitlines()
    out: list[str] = []
    anchor_seen: dict[str, int] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            index = _convert_fence(lines, index, out)
            continue
        if _LIST_PATTERN.match(line):
            index = _convert_list(lines, index, out, load_image)
            continue
        if line.startswith("|"):
            index = _convert_table(lines, index, out)
            continue
        heading = _HEADING_PATTERN.match(line)
        if heading is not None:
            out.append(_heading_html(heading, anchor_seen))
            index += 1
            continue
        if line.strip():
            out.append(f"<p>{_inline_html(line, load_image)}</p>")
        index += 1
    return "\n".join(out) + "\n"


def _convert_fence(lines: list[str], index: int, out: list[str]) -> int:
    language = lines[index][3:].strip()
    content: list[str] = []
    index += 1
    while index < len(lines) and not lines[index].startswith("```"):
        content.append(lines[index])
        index += 1
    escaped = _escape("\n".join(content))
    if language == "mermaid":
        out.append(f'<pre class="mermaid">{escaped}</pre>')
    else:
        out.append(f"<pre><code>{escaped}</code></pre>")
    return index + 1  # 終了フェンスを読み飛ばす


def _convert_list(
    lines: list[str],
    index: int,
    out: list[str],
    load_image: Callable[[str], str | None] | None,
) -> int:
    out.append("<ul>")
    depth = 0
    while index < len(lines):
        match = _LIST_PATTERN.match(lines[index])
        if match is None:
            break
        item_depth = len(match.group(1)) // 2
        while depth < item_depth:
            out.append("<ul>")
            depth += 1
        while depth > item_depth:
            out.append("</ul>")
            depth -= 1
        out.append(f"<li>{_inline_html(match.group(2), load_image)}</li>")
        index += 1
    while depth > 0:
        out.append("</ul>")
        depth -= 1
    out.append("</ul>")
    return index


def _convert_table(lines: list[str], index: int, out: list[str]) -> int:
    rows: list[list[str]] = []
    while index < len(lines) and lines[index].startswith("|"):
        if not _TABLE_SEPARATOR_PATTERN.match(lines[index]):
            rows.append(_split_cells(lines[index]))
        index += 1
    if not rows:
        return index
    out.append("<table>")
    out.append("<tr>" + "".join(f"<th>{_inline_html(cell, None)}</th>" for cell in rows[0]) + "</tr>")
    for row in rows[1:]:
        out.append("<tr>" + "".join(f"<td>{_inline_html(cell, None)}</td>" for cell in row) + "</tr>")
    out.append("</table>")
    return index


def _split_cells(line: str) -> list[str]:
    cells = _CELL_SPLIT_PATTERN.split(line.strip())[1:-1]
    return [cell.strip().replace("\\|", "|") for cell in cells]


def _heading_html(match: re.Match[str], anchor_seen: dict[str, int]) -> str:
    level = len(match.group(1))
    text = match.group(2)
    if level in (2, 3):
        # 目次生成 (markdown.py) と同じ順序・アルゴリズムでアンカーを付与する
        slug = gfm_slug(text)
        count = anchor_seen.get(slug, 0)
        anchor_seen[slug] = count + 1
        anchor = slug if count == 0 else f"{slug}-{count}"
        return f'<h{level} id="{anchor}">{_escape(text)}</h{level}>'
    return f"<h{level}>{_escape(text)}</h{level}>"


def _inline_html(
    text: str, load_image: Callable[[str], str | None] | None
) -> str:
    image = _IMAGE_PATTERN.match(text.strip())
    if image is not None:
        src = image.group(2)
        if load_image is not None:
            src = load_image(src) or src
        return f'<img alt="{_escape(image.group(1))}" src="{_escape(src)}">'
    escaped = _escape(text)
    return _LINK_PATTERN.sub(
        lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', escaped
    )


def _escape(text: str) -> str:
    return html_module.escape(text, quote=True)
