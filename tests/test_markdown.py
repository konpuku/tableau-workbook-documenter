"""レンダラー (markdown / sections / zones) のテスト。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime

from twbdoc.model import (
    Dashboard,
    DashboardSize,
    Parameter,
    ParameterMember,
    Workbook,
    WorkbookMeta,
    Zone,
)
from twbdoc.parsers import parse_workbook
from twbdoc.renderers import render
from twbdoc.renderers.sections import render_parameters
from twbdoc.renderers.zones import render_zone_list, render_zone_mermaid, zone_label


def _render_minimal(minimal_root: ET.Element) -> str:
    workbook = parse_workbook(minimal_root, "test.twbx")
    return render(workbook, generated_at=datetime(2026, 7, 12, 10, 0))


class TestRender:
    def test_全章が出力される(self, minimal_root: ET.Element) -> None:
        markdown = _render_minimal(minimal_root)
        for heading in [
            "# test 設計書",
            "## 1. ワークブック概要",
            "## 2. データソースと前処理",
            "## 3. ダッシュボード構成",
            "## 4. ワークシート一覧",
            "## 5. フィルター",
            "## 6. パラメーター",
            "## 7. 計算フィールド",
            "## 8. 別名一覧",
            "## 9. 書式設定",
            "## 10. テーブル別フィールド一覧 (参考)",
        ]:
            assert heading in markdown, heading

    def test_生成日時が出力される(self, minimal_root: ET.Element) -> None:
        assert "生成日時: 2026-07-12 10:00" in _render_minimal(minimal_root)

    def test_ダッシュボード章にサイズとMermaidが出る(
        self, minimal_root: ET.Element
    ) -> None:
        markdown = _render_minimal(minimal_root)
        assert "サイズ: 固定 (1200 x 800)" in markdown
        assert "```mermaid" in markdown
        assert "graph TD" in markdown

    def test_計算フィールドの式がコードブロックに出る(
        self, minimal_root: ET.Element
    ) -> None:
        markdown = _render_minimal(minimal_root)
        assert "SUM([利益])/SUM([売上])" in markdown

    def test_別名テーブルが出る(self, minimal_root: ET.Element) -> None:
        markdown = _render_minimal(minimal_root)
        assert "東地区" in markdown

    def test_フィルターゾーンのフィールド名が可読化される(
        self, minimal_root: ET.Element
    ) -> None:
        markdown = _render_minimal(minimal_root)
        assert "[フィルター] 利益率" in markdown
        assert "usr:Calculation_100:qk" not in markdown

    def test_空ワークブックは各章が該当なしになる(self) -> None:
        workbook = Workbook(meta=WorkbookMeta(source_file="empty.twb"))
        markdown = render(workbook, generated_at=datetime(2026, 7, 12))
        assert markdown.count("(該当なし)") >= 6

    def test_フィルター章に適用内容が出る(self, minimal_root: ET.Element) -> None:
        markdown = _render_minimal(minimal_root)
        assert "East、West のみ保持" in markdown
        assert "0.0 〜 0.25 の範囲のみ保持" in markdown
        assert "Central を除外" in markdown

    def test_共通フィルターがコンテキスト付きで出る(
        self, minimal_root: ET.Element
    ) -> None:
        markdown = _render_minimal(minimal_root)
        assert "共通フィルター" in markdown
        assert "カテゴリ (コンテキスト)" in markdown
        assert "2026/07、2026/08 のみ保持" in markdown

    def test_計算フィールドのコメントが出る(
        self, minimal_root: ET.Element
    ) -> None:
        markdown = _render_minimal(minimal_root)
        assert "利益率のしきい値判定。設計意図のメモ。" in markdown
        assert "しきい値は要件 #123 参照" in markdown

    def test_リネージュ図が出る(self, minimal_root: ET.Element) -> None:
        markdown = _render_minimal(minimal_root)
        assert "リネージュ" in markdown
        assert "graph LR" in markdown
        # 利益率 (依存元) --> 利益率判定 (依存先) のエッジがある
        assert '["利益率"]' in markdown
        assert '{{"上位顧客数"}}' in markdown

    def test_計算フィールドの利用先ワークシートが出る(
        self, minimal_root: ET.Element
    ) -> None:
        markdown = _render_minimal(minimal_root)
        assert "| 利用先ワークシート | 売上推移 |" in markdown

    def test_未使用の計算フィールドに警告が出る(self) -> None:
        from twbdoc.model import CalculatedField

        workbook = Workbook(
            meta=WorkbookMeta(source_file="x.twbx"),
            calculated_fields=(
                CalculatedField(
                    name="[Calc_1]",
                    caption="未使用計算",
                    formula="1+1",
                    raw_formula="1+1",
                ),
            ),
        )
        markdown = render(workbook, generated_at=datetime(2026, 7, 12))
        assert "未使用の可能性" in markdown

    def test_ワークシート一覧に使用フィールドが出る(
        self, minimal_root: ET.Element
    ) -> None:
        markdown = _render_minimal(minimal_root)
        row = next(
            line for line in markdown.splitlines()
            if line.startswith("| 売上推移 |")
        )
        assert "利益率" in row
        assert "上位顧客数" in row


class TestZoneRendering:
    def test_インデント付きリストと座標換算(self) -> None:
        tree = Zone(
            zone_type="layout-flow",
            param="horz",
            x=0,
            y=0,
            w=100000,
            h=50000,
            children=(Zone(zone_type="worksheet", name="売上", w=70500),),
        )
        lines = render_zone_list((tree,), {})
        assert lines[0] == "- [水平コンテナ] (x:0%, y:0%, w:100%, h:50%)"
        assert lines[1] == "  - [ワークシート] 売上 (w:70.5%)"

    def test_Mermaid_で親子エッジが張られる(self) -> None:
        tree = Zone(
            zone_type="layout-flow",
            param="vert",
            children=(Zone(zone_type="title"),),
        )
        lines = render_zone_mermaid((tree,), {})
        assert lines[0] == "```mermaid"
        assert '    z0["[垂直コンテナ]"]' in lines
        assert '    z1["[タイトル]"]' in lines
        assert "    z0 --> z1" in lines

    def test_未知のゾーン種別は不明として出す(self) -> None:
        label = zone_label(Zone(zone_type="new-fancy-zone"), {})
        assert label == "[不明: new-fancy-zone]"


class TestSections:
    def test_リスト型パラメーターの許容値表示(self) -> None:
        parameter = Parameter(
            name="[P1]",
            caption="地域",
            datatype="string",
            domain_type="list",
            current_value='"east"',
            members=(
                ParameterMember(value='"east"', alias="東"),
                ParameterMember(value='"west"', alias="西"),
            ),
        )
        lines = render_parameters((parameter,))
        row = next(line for line in lines if "地域" in line)
        assert '"east" (東)' in row
        assert "リスト" in row

    def test_セル内のパイプがエスケープされる(self) -> None:
        parameter = Parameter(name="[P]", caption="A|B", datatype="string")
        lines = render_parameters((parameter,))
        assert any("A\\|B" in line for line in lines)


class TestFutureImagePath:
    def test_image_path_があれば画像リンクを出す(self) -> None:
        workbook = Workbook(
            meta=WorkbookMeta(source_file="x.twbx"),
            dashboards=(
                Dashboard(
                    name="DB1",
                    size=DashboardSize(sizing_mode="automatic"),
                    image_path="images/db1.png",
                ),
            ),
        )
        markdown = render(workbook, generated_at=datetime(2026, 7, 12))
        assert "![DB1](images/db1.png)" in markdown
