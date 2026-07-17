"""HTML 変換 (renderers/html.py) のテスト。"""

from __future__ import annotations

from twbdoc.renderers.html import render_html


class TestRenderHtml:
    def test_見出しにアンカーidが付く(self) -> None:
        html = render_html("## 1. ワークブック概要\n", "t")
        assert '<h2 id="1-ワークブック概要">1. ワークブック概要</h2>' in html

    def test_重複見出しは連番アンカーになる(self) -> None:
        html = render_html("## 同名\n\n### 同名\n", "t")
        assert '<h2 id="同名">' in html
        assert '<h3 id="同名-1">' in html

    def test_h4はアンカーなし(self) -> None:
        html = render_html("#### 接続\n", "t")
        assert "<h4>接続</h4>" in html

    def test_テーブルが変換される(self) -> None:
        markdown = "| 項目 | 値 |\n|---|---|\n| 名前 | A\\|B |\n"
        html = render_html(markdown, "t")
        assert "<th>項目</th>" in html
        assert "<td>A|B</td>" in html

    def test_入れ子リストが変換される(self) -> None:
        markdown = "- 親\n  - 子\n- 親2\n"
        html = render_html(markdown, "t")
        assert html.index("<li>親</li>") < html.index("<ul>\n<li>子</li>")
        assert "<li>親2</li>" in html

    def test_mermaidフェンスはpre_mermaidになる(self) -> None:
        markdown = "```mermaid\ngraph LR\n    a --> b\n```\n"
        html = render_html(markdown, "t")
        assert '<pre class="mermaid">graph LR\n    a --&gt; b</pre>' in html
        assert "mermaid.initialize" in html

    def test_数式フェンスはコードブロックになる(self) -> None:
        markdown = "```\nSUM([利益]) > 0\n```\n"
        html = render_html(markdown, "t")
        assert "<pre><code>SUM([利益]) &gt; 0</code></pre>" in html

    def test_リンクが変換される(self) -> None:
        html = render_html("- [8. 計算フィールド](#8-計算フィールド)\n", "t")
        assert '<a href="#8-計算フィールド">8. 計算フィールド</a>' in html

    def test_画像はローダーでdata_URIになる(self) -> None:
        html = render_html(
            "![goal](images/goal.png)\n",
            "t",
            load_image=lambda src: f"data:image/png;base64,AAAA:{src}",
        )
        assert 'src="data:image/png;base64,AAAA:images/goal.png"' in html

    def test_ローダーがNoneを返すと元パスのまま(self) -> None:
        html = render_html("![goal](images/goal.png)\n", "t", load_image=lambda _: None)
        assert 'src="images/goal.png"' in html

    def test_テキストはエスケープされる(self) -> None:
        html = render_html("A<B>&C\n", "t")
        assert "<p>A&lt;B&gt;&amp;C</p>" in html

    def test_タイトルとmermaid同梱(self) -> None:
        html = render_html("# x\n", "設計書タイトル")
        assert "<title>設計書タイトル</title>" in html
        assert "securityLevel: 'loose'" in html
        assert len(html) > 1_000_000  # mermaid.min.js がインラインされている
