"""データソース前処理 (parsers/prep.py + renderers/datasources.py) のテスト。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from twbdoc.parsers.datasources import parse_datasources
from twbdoc.parsers.prep import render_expression
from twbdoc.renderers.datasources import render_datasources_prep


class TestPrepParsing:
    def test_接続一覧を抽出する(self, minimal_root: ET.Element) -> None:
        datasource = parse_datasources(minimal_root)[0]
        connection = datasource.connections[0]
        assert connection.caption == "スーパーストア Excel"
        assert connection.conn_class == "excel-direct"
        assert connection.source == "C:/data/superstore.xls"

    def test_論理テーブルとリレーションシップを抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        datasource = parse_datasources(minimal_root)[0]
        assert [t.caption for t in datasource.logical_tables] == [
            "オーダー+関係者",
            "返品",
        ]
        relationship = datasource.relationships[0]
        assert relationship.first_table == "オーダー+関係者"
        assert relationship.second_table == "返品"
        assert relationship.expression == "オーダー ID = オーダー ID (返品)"

    def test_結合を論理テーブル内から抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        datasource = parse_datasources(minimal_root)[0]
        join = datasource.logical_tables[0].relation
        assert join.rel_type == "join"
        assert join.join_type == "left"
        assert join.join_conditions == ("オーダー.地域 = 関係者.地域",)
        assert [child.name for child in join.children] == ["オーダー", "関係者"]

    def test_ユニオンを物理ツリーから抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        datasource = parse_datasources(minimal_root)[0]
        unions = [
            child
            for child in datasource.relation.children
            if child.rel_type == "union"
        ]
        assert unions[0].name == "売上ユニオン"
        assert [m.name for m in unions[0].children] == ["売上Q1", "売上Q2"]

    def test_データソースフィルタと抽出フィルタを抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        datasource = parse_datasources(minimal_root)[0]
        assert datasource.ds_filters[0].members == ("Consumer",)
        assert datasource.extract.enabled
        assert datasource.extract.filters[0].min_value == "0"

    def test_フィールド設定の変更を抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        datasource = parse_datasources(minimal_root)[0]
        changes = {change.name: change for change in datasource.field_changes}
        sales = changes["[Sales]"]
        assert sales.new_name == "売上高"
        assert sales.original_datatype == "string"  # 型変更 (string -> real)
        assert sales.datatype == "real"
        row_id = changes["[RowID]"]
        assert row_id.hidden
        assert row_id.semantic_role == "[ZipCode].[Name]"

    def test_変更のないフィールドは含めない(
        self, minimal_root: ET.Element
    ) -> None:
        datasource = parse_datasources(minimal_root)[0]
        names = [change.name for change in datasource.field_changes]
        # 計算フィールド・論理テーブル (datatype=table) は対象外
        assert "[Calculation_100]" not in names

    def test_前処理なしのデータソースでも解析できる(self) -> None:
        root = ET.fromstring(
            "<workbook><datasources>"
            "<datasource name='simple'><connection class='hyper' /></datasource>"
            "</datasources></workbook>"
        )
        datasource = parse_datasources(root)[0]
        assert datasource.logical_tables == ()
        assert datasource.relationships == ()
        assert datasource.extract is None


class TestRenderExpression:
    def test_単純な等式(self) -> None:
        element = ET.fromstring(
            "<expression op='='>"
            "<expression op='[A]' /><expression op='[B]' />"
            "</expression>"
        )
        assert render_expression(element) == "A = B"

    def test_計算を含む式はそのまま出す(self) -> None:
        element = ET.fromstring(
            "<expression op='='>"
            "<expression op='[A]' /><expression op='[B1]+[B2]' />"
            "</expression>"
        )
        assert render_expression(element) == "A = [B1]+[B2]"


class TestPrepRendering:
    def test_章とセクションが出力される(self, minimal_root: ET.Element) -> None:
        from twbdoc.parsers import parse_workbook

        workbook = parse_workbook(minimal_root, "test.twbx")
        lines = render_datasources_prep(workbook, {})
        text = "\n".join(lines)
        assert "## 2. データソースと前処理" in text
        assert "#### 接続" in text
        assert "#### データモデル図" in text
        assert "#### リレーションシップ" in text
        assert "#### 結合 (物理テーブル)" in text
        assert "左外部結合" in text
        assert "#### ユニオン" in text
        assert "売上Q1, 売上Q2" in text
        # erDiagram は廃止 (flowchart 統合図のみ)
        assert "erDiagram" not in text
        assert "}o--o{" not in text
        assert "#### フィールド設定の変更" in text
        assert "string → real (変更)" in text
        assert "郵便番号" in text  # semantic-role の日本語化
        assert "#### データソースフィルタ" in text
        assert "Consumer のみ保持" in text
        assert "#### 抽出フィルタ" in text
        assert "抽出 (全件)" in text

    def test_リレーションシップが点線で描かれる(
        self, minimal_root: ET.Element
    ) -> None:
        from twbdoc.parsers import parse_workbook

        workbook = parse_workbook(minimal_root, "test.twbx")
        text = "\n".join(render_datasources_prep(workbook, {}))
        assert 'lt0 -. "オーダー ID = オーダー ID (返品)" .- lt1' in text

    def test_リレーションシップの条件なしはラベルが関連になる(self) -> None:
        from twbdoc.model import (
            Datasource,
            LogicalTable,
            Relationship,
            Workbook,
            WorkbookMeta,
        )

        workbook = Workbook(
            meta=WorkbookMeta(source_file="x.twbx"),
            datasources=(
                Datasource(
                    name="ds",
                    logical_tables=(
                        LogicalTable(object_id="A", caption="A"),
                        LogicalTable(object_id="B", caption="B"),
                    ),
                    relationships=(
                        Relationship(
                            first_table="A", second_table="B", expression=""
                        ),
                    ),
                ),
            ),
        )
        text = "\n".join(render_datasources_prep(workbook, {}))
        assert 'lt0 -. "関連" .- lt1' in text

    def test_データソースなしは該当なし(self) -> None:
        from twbdoc.model import Workbook, WorkbookMeta

        workbook = Workbook(meta=WorkbookMeta(source_file="x.twb"))
        text = "\n".join(render_datasources_prep(workbook, {}))
        assert "(該当なし)" in text

    def test_データモデル図に論理テーブル枠と結合の線が出る(
        self, minimal_root: ET.Element
    ) -> None:
        from twbdoc.parsers import parse_workbook

        workbook = parse_workbook(minimal_root, "test.twbx")
        text = "\n".join(render_datasources_prep(workbook, {}))
        assert "flowchart LR" in text
        assert 'subgraph lt0 ["オーダー+関係者"]' in text
        assert '-- "左外部結合: オーダー.地域 = 関係者.地域" ---' in text
        # 論理テーブル外のユニオンも内側の枠として出力される
        assert '["売上ユニオン (ユニオン)"]' in text
        assert "direction TB" in text

    def test_ユニオン表に論理テーブル列が出る(
        self, minimal_root: ET.Element
    ) -> None:
        from twbdoc.parsers import parse_workbook

        workbook = parse_workbook(minimal_root, "test.twbx")
        text = "\n".join(render_datasources_prep(workbook, {}))
        assert "| 論理テーブル | ユニオン名 | 対象テーブル |" in text

    def test_論理テーブルのフィールド定義を抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        datasource = parse_datasources(minimal_root)[0]
        columns = datasource.logical_tables[0].columns
        assert ("オーダー ID", "string", "オーダー") == (
            columns[0].name,
            columns[0].datatype,
            columns[0].table,
        )
        # 結合の両テーブル分が収集される
        assert {column.table for column in columns} == {"オーダー", "関係者"}

    def test_リレーションシップの両端キーを抽出する(
        self, minimal_root: ET.Element
    ) -> None:
        datasource = parse_datasources(minimal_root)[0]
        relationship = datasource.relationships[0]
        assert relationship.first_key == "オーダー ID"
        assert relationship.second_key == "オーダー ID (返品)"

    def test_データモデル図にキー項目が型付きで出る(
        self, minimal_root: ET.Element
    ) -> None:
        from twbdoc.parsers import parse_workbook

        workbook = parse_workbook(minimal_root, "test.twbx")
        text = "\n".join(render_datasources_prep(workbook, {}))
        assert '[/"キー: オーダー ID (string)"/]' in text
        assert '[/"キー: オーダー ID (返品) (string)"/]' in text

    def test_テーブル別フィールド一覧が最終章として出る(
        self, minimal_root: ET.Element
    ) -> None:
        from twbdoc.parsers import parse_workbook
        from twbdoc.renderers.datasources import render_field_list_chapter

        workbook = parse_workbook(minimal_root, "test.twbx")
        text = "\n".join(render_field_list_chapter(workbook))
        assert "## 10. テーブル別フィールド一覧 (参考)" in text
        assert "### 10.1 スーパーストア" in text
        assert "| オーダー+関係者 | 関係者 | 担当者 | string |" in text
        assert "| 返品 | 返品 | 返品済み | boolean |" in text
        # 2章側には含まれない
        prep_text = "\n".join(render_datasources_prep(workbook, {}))
        assert "テーブル別フィールド一覧" not in prep_text

    def test_ユニオン構成の論理テーブルにERマーカーと注釈が出る(self) -> None:
        from twbdoc.model import (
            Datasource,
            LogicalTable,
            Relation,
            Relationship,
            Workbook,
            WorkbookMeta,
        )

        union = Relation(
            rel_type="union",
            name="Sales Q1+",
            children=(
                Relation(rel_type="table", name="Sales Q1"),
                Relation(rel_type="table", name="Sales Q2"),
            ),
        )
        workbook = Workbook(
            meta=WorkbookMeta(source_file="x.twbx"),
            datasources=(
                Datasource(
                    name="ds",
                    logical_tables=(
                        LogicalTable(
                            object_id="S", caption="Sales", relation=union
                        ),
                        LogicalTable(object_id="E", caption="Edition"),
                    ),
                    relationships=(
                        Relationship(
                            first_table="Sales",
                            second_table="Edition",
                            expression="ISBN = ISBN (Edition)",
                        ),
                    ),
                ),
            ),
        )
        text = "\n".join(render_datasources_prep(workbook, {}))
        assert '["Sales Q1+ (ユニオン)"]' in text
        assert 'lt0 -. "ISBN = ISBN (Edition)" .- lt1' in text
        assert "erDiagram" not in text
        assert (
            "「Sales」はユニオン「Sales Q1+」(Sales Q1, Sales Q2) で構成されています"
            in text
        )
