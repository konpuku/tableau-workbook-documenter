"""twb XML から抽出した情報を保持する中間モデル。

すべて frozen dataclass (イミュータブル)。
パーサー (XML -> モデル) とレンダラー (モデル -> Markdown) の間の契約となる。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WorkbookMeta:
    """ワークブックのメタ情報。"""

    source_file: str
    version: str = ""
    source_build: str = ""
    source_platform: str = ""


@dataclass(frozen=True)
class FormatSetting:
    """書式設定の 1 項目 (<format attr='...' value='...'/>)。"""

    attr: str
    value: str
    scope: str = ""


@dataclass(frozen=True)
class StyleRule:
    """スタイルルール (<style-rule element='...'>)。"""

    element: str
    formats: tuple[FormatSetting, ...] = ()


@dataclass(frozen=True)
class Alias:
    """メンバー別名 (<alias key='元値' value='表示名'/>)。"""

    key: str
    value: str


@dataclass(frozen=True)
class Field:
    """データソース内のフィールド (<column>)。"""

    name: str
    caption: str = ""
    datatype: str = ""
    role: str = ""
    is_calculated: bool = False
    aliases: tuple[Alias, ...] = ()
    comment: str = ""

    @property
    def display_name(self) -> str:
        """設計書に表示する名前 (caption が無ければ name)。"""
        return self.caption or self.name.strip("[]")


@dataclass(frozen=True)
class CalculatedField:
    """計算フィールド。"""

    name: str
    caption: str
    formula: str
    raw_formula: str
    datatype: str = ""
    role: str = ""
    calc_class: str = "tableau"
    datasource: str = ""
    comment: str = ""
    inline_comments: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    table_calc: TableCalc | None = None

    @property
    def display_name(self) -> str:
        return self.caption or self.name.strip("[]")


@dataclass(frozen=True)
class TableCalc:
    """表計算の設定 (<table-calc>)。

    ordering_type: 次を使用して計算 (Rows / Columns / Field 等)。
    calc_type: 簡易表計算の種類 (PctTotal 等)。空なら式による表計算。
    order_fields: ordering_type='Field' のとき計算に使うディメンション (順序付き)。
    extra: 未知の属性 (名前, 値) — サンプル未確認の設定も欠落させないための受け皿。
    """

    ordering_type: str = ""
    calc_type: str = ""
    order_fields: tuple[str, ...] = ()
    extra: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PillTableCalc:
    """ワークシート上のピルに設定された表計算 (column-instance 単位)。"""

    column_ref: str
    table_calc: TableCalc
    derivation: str = ""


@dataclass(frozen=True)
class DashboardAction:
    """ダッシュボードアクション (<actions> 配下)。

    kind はコマンド種別を日本語化したもの (ハイライト / フィルター / URL 等)。
    params には表示済み以外の生パラメーターを (名前, 値) で保持する。
    """

    caption: str
    name: str = ""
    kind: str = ""
    activation: str = ""
    source_dashboard: str = ""
    source_worksheet: str = ""
    excluded_sheets: tuple[str, ...] = ()
    target: str = ""
    fields: str = ""
    params: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ParameterMember:
    """リスト型パラメーターの選択肢。"""

    value: str
    alias: str = ""


@dataclass(frozen=True)
class Parameter:
    """パラメーター (datasource name='Parameters' 内の column)。"""

    name: str
    caption: str = ""
    datatype: str = ""
    current_value: str = ""
    domain_type: str = "any"
    range_min: str = ""
    range_max: str = ""
    granularity: str = ""
    members: tuple[ParameterMember, ...] = ()

    @property
    def display_name(self) -> str:
        return self.caption or self.name.strip("[]")


@dataclass(frozen=True)
class Connection:
    """接続 (named-connection または直接接続)。"""

    name: str = ""
    caption: str = ""
    conn_class: str = ""
    source: str = ""


@dataclass(frozen=True)
class Relation:
    """物理テーブル構造 (<relation>) の再帰ツリー。

    rel_type: table / join / union / collection / text など。
    """

    rel_type: str
    name: str = ""
    table: str = ""
    connection: str = ""
    join_type: str = ""
    join_conditions: tuple[str, ...] = ()
    children: tuple[Relation, ...] = ()


@dataclass(frozen=True)
class TableColumn:
    """物理テーブルが持つフィールド (object-graph 内の columns 定義)。"""

    name: str
    datatype: str = ""
    table: str = ""


@dataclass(frozen=True)
class LogicalTable:
    """論理テーブル (object-graph の object)。"""

    object_id: str
    caption: str = ""
    relation: Relation | None = None
    columns: tuple[TableColumn, ...] = ()


@dataclass(frozen=True)
class Relationship:
    """論理テーブル間のリレーションシップ。

    first_key / second_key は各テーブル側のキー式 (単純な場合はフィールド名)。
    """

    first_table: str
    second_table: str
    expression: str
    first_key: str = ""
    second_key: str = ""


@dataclass(frozen=True)
class FieldChange:
    """GUI で変更されたフィールド設定 (名前変更・型変更・非表示・地理的役割)。"""

    name: str
    new_name: str = ""
    datatype: str = ""
    original_datatype: str = ""
    role: str = ""
    hidden: bool = False
    semantic_role: str = ""


@dataclass(frozen=True)
class ExtractInfo:
    """抽出 (<extract>) の設定。"""

    enabled: bool = False
    row_limit: str = ""
    filters: tuple[WorksheetFilter, ...] = ()


@dataclass(frozen=True)
class Datasource:
    """データソース (Parameters 擬似データソースを除く)。"""

    name: str
    caption: str = ""
    connection_class: str = ""
    fields: tuple[Field, ...] = ()
    connections: tuple[Connection, ...] = ()
    relation: Relation | None = None
    logical_tables: tuple[LogicalTable, ...] = ()
    metadata_columns: tuple[TableColumn, ...] = ()
    relationships: tuple[Relationship, ...] = ()
    ds_filters: tuple[WorksheetFilter, ...] = ()
    extract: ExtractInfo | None = None
    field_changes: tuple[FieldChange, ...] = ()

    @property
    def display_name(self) -> str:
        return self.caption or self.name


@dataclass(frozen=True)
class WorksheetFilter:
    """フィルター (<filter>)。

    column_ref は '[データソース].[none:Category:nk]' 形式の生参照。
    """

    column_ref: str
    filter_class: str = ""
    excluded: bool = False
    members: tuple[str, ...] = ()
    all_members: bool = False
    action: str = ""
    min_value: str = ""
    max_value: str = ""
    included_values: str = ""
    expression: str = ""
    level: str = ""
    is_context: bool = False


@dataclass(frozen=True)
class Worksheet:
    """ワークシート。"""

    name: str
    title: str = ""
    datasources: tuple[str, ...] = ()
    dashboards: tuple[str, ...] = ()
    filters: tuple[WorksheetFilter, ...] = ()
    used_columns: tuple[str, ...] = ()
    table_calcs: tuple[PillTableCalc, ...] = ()


@dataclass(frozen=True)
class Zone:
    """ダッシュボード内のゾーン (入れ子ツリー)。

    座標 x/y/w/h は twb の相対座標 (0〜100000)。None は未指定。
    """

    zone_type: str
    name: str = ""
    param: str = ""
    text: str = ""
    x: int | None = None
    y: int | None = None
    w: int | None = None
    h: int | None = None
    children: tuple[Zone, ...] = ()


@dataclass(frozen=True)
class DashboardSize:
    """ダッシュボードのサイズ設定 (<size>)。"""

    sizing_mode: str = ""
    minwidth: str = ""
    minheight: str = ""
    maxwidth: str = ""
    maxheight: str = ""


@dataclass(frozen=True)
class Dashboard:
    """ダッシュボード。image_path は将来の画像埋め込み用。"""

    name: str
    size: DashboardSize = field(default_factory=DashboardSize)
    zones: tuple[Zone, ...] = ()
    image_path: str | None = None


@dataclass(frozen=True)
class Workbook:
    """ワークブック全体の集約モデル。"""

    meta: WorkbookMeta
    datasources: tuple[Datasource, ...] = ()
    parameters: tuple[Parameter, ...] = ()
    calculated_fields: tuple[CalculatedField, ...] = ()
    worksheets: tuple[Worksheet, ...] = ()
    dashboards: tuple[Dashboard, ...] = ()
    style_rules: tuple[StyleRule, ...] = ()
    shared_filters: tuple[WorksheetFilter, ...] = ()
    actions: tuple[DashboardAction, ...] = ()
