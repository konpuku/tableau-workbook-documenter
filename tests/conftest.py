"""テスト共通フィクスチャ。"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SAMPLES_DIR = Path(__file__).resolve().parents[2]

MINIMAL_TWB = """<?xml version='1.0' encoding='utf-8' ?>
<workbook version='18.1' source-build='2026.1.1 (20261.26.0410.0924)' source-platform='win'
          xmlns:user='http://www.tableausoftware.com/xml/user'>
  <datasources>
    <datasource name='Parameters' inline='true'>
      <column caption='上位顧客数' datatype='integer' name='[Parameter 1]'
              param-domain-type='range' role='measure' type='quantitative' value='5'>
        <calculation class='tableau' formula='5' />
        <range granularity='5' max='20' min='5' />
      </column>
      <column caption='地域選択' datatype='string' name='[Parameter 2]'
              param-domain-type='list' role='measure' type='nominal' value='&quot;east&quot;'>
        <calculation class='tableau' formula='&quot;east&quot;' />
        <members>
          <member alias='東' value='&quot;east&quot;' />
          <member alias='西' value='&quot;west&quot;' />
        </members>
      </column>
    </datasource>
    <datasource caption='スーパーストア' name='superstore-federated' inline='true'>
      <connection class='federated'>
        <named-connections>
          <named-connection caption='スーパーストア Excel' name='excel-direct.abc'>
            <connection class='excel-direct' filename='C:/data/superstore.xls' />
          </named-connection>
        </named-connections>
        <relation type='collection'>
          <relation join='left' type='join'>
            <clause type='join'>
              <expression op='='>
                <expression op='[オーダー].[地域]' />
                <expression op='[関係者].[地域]' />
              </expression>
            </clause>
            <relation connection='excel-direct.abc' name='オーダー' table='[オーダー$]' type='table' />
            <relation connection='excel-direct.abc' name='関係者' table='[関係者$]' type='table' />
          </relation>
          <relation all='true' name='売上ユニオン' type='union'>
            <relation connection='excel-direct.abc' name='売上Q1' table='[Q1$]' type='table' />
            <relation connection='excel-direct.abc' name='売上Q2' table='[Q2$]' type='table' />
          </relation>
        </relation>
        <metadata-records>
          <metadata-record class='column'>
            <remote-name>Sales</remote-name>
            <local-name>[Sales]</local-name>
            <local-type>string</local-type>
          </metadata-record>
        </metadata-records>
      </connection>
      <object-graph>
        <objects>
          <object caption='オーダー+関係者' id='OBJ_A'>
            <properties context=''>
              <relation join='left' type='join'>
                <clause type='join'>
                  <expression op='='>
                    <expression op='[オーダー].[地域]' />
                    <expression op='[関係者].[地域]' />
                  </expression>
                </clause>
                <relation connection='excel-direct.abc' name='オーダー' table='[オーダー$]' type='table'>
                  <columns header='yes'>
                    <column datatype='string' name='オーダー ID' ordinal='0' />
                    <column datatype='string' name='地域' ordinal='1' />
                    <column datatype='real' name='売上' ordinal='2' />
                  </columns>
                </relation>
                <relation connection='excel-direct.abc' name='関係者' table='[関係者$]' type='table'>
                  <columns header='yes'>
                    <column datatype='string' name='地域' ordinal='0' />
                    <column datatype='string' name='担当者' ordinal='1' />
                  </columns>
                </relation>
              </relation>
            </properties>
          </object>
          <object caption='返品' id='OBJ_B'>
            <properties context=''>
              <relation connection='excel-direct.abc' name='返品' table='[返品$]' type='table'>
                <columns header='yes'>
                  <column datatype='string' name='オーダー ID (返品)' ordinal='0' />
                  <column datatype='boolean' name='返品済み' ordinal='1' />
                </columns>
              </relation>
            </properties>
          </object>
        </objects>
        <relationships>
          <relationship>
            <expression op='='>
              <expression op='[オーダー ID]' />
              <expression op='[オーダー ID (返品)]' />
            </expression>
            <first-end-point object-id='OBJ_A' />
            <second-end-point object-id='OBJ_B' />
          </relationship>
        </relationships>
      </object-graph>
      <filter class='categorical' column='[superstore-federated].[none:Segment:nk]'>
        <groupfilter function='union' user:ui-enumeration='inclusive'>
          <groupfilter function='member' level='[none:Segment:nk]' member='&quot;Consumer&quot;' />
        </groupfilter>
      </filter>
      <extract count='-1' enabled='true'>
        <filter class='quantitative' column='[superstore-federated].[Sales]' included-values='in-range'>
          <min>0</min>
          <max>100000</max>
        </filter>
      </extract>
      <column caption='売上高' datatype='real' name='[Sales]' role='measure' type='quantitative' />
      <column datatype='string' hidden='true' name='[RowID]' role='dimension' semantic-role='[ZipCode].[Name]' type='nominal' />
      <column caption='利益率' datatype='real' name='[Calculation_100]' role='measure' type='quantitative'>
        <calculation class='tableau' formula='SUM([利益])/SUM([売上])' />
      </column>
      <column caption='利益率判定' datatype='boolean' name='[Calculation_200]' role='dimension' type='nominal'>
        <desc>
          <formatted-text>
            <run>利益率のしきい値判定。設計意図のメモ。</run>
          </formatted-text>
        </desc>
        <calculation class='tableau' formula='// しきい値は要件 #123 参照&#10;[Calculation_100]&gt;0.1 AND [Parameters].[Parameter 1]&gt;3 /* 暫定条件 */' />
      </column>
      <column caption='地域' datatype='string' name='[Region]' role='dimension' type='nominal'>
        <aliases enabled='yes'>
          <alias key='&quot;east&quot;' value='東地区' />
          <alias key='&quot;west&quot;' value='西地区' />
        </aliases>
      </column>
    </datasource>
  </datasources>
  <shared-views>
    <shared-view name='スーパーストア'>
      <filter class='categorical' column='[superstore-federated].[my:OrderDate:ok]' context='true'>
        <groupfilter function='union' user:ui-enumeration='inclusive' user:ui-marker='enumerate'>
          <groupfilter function='member' level='[my:OrderDate:ok]' member='202607' />
          <groupfilter function='member' level='[my:OrderDate:ok]' member='202608' />
        </groupfilter>
      </filter>
    </shared-view>
  </shared-views>
  <worksheets>
    <worksheet name='売上推移'>
      <layout-options>
        <title>
          <formatted-text>
            <run bold='true' fontsize='14'>月別売上の推移</run>
          </formatted-text>
        </title>
      </layout-options>
      <table>
        <view>
          <datasources>
            <datasource name='Parameters' />
            <datasource caption='スーパーストア' name='superstore-federated' />
          </datasources>
          <datasource-dependencies datasource='Parameters'>
            <column caption='上位顧客数' datatype='integer' name='[Parameter 1]' />
          </datasource-dependencies>
          <datasource-dependencies datasource='superstore-federated'>
            <column caption='利益率' datatype='real' name='[Calculation_100]' />
            <column datatype='string' name='[Region]' />
          </datasource-dependencies>
          <filter class='categorical' column='[superstore-federated].[none:Region:nk]'>
            <groupfilter function='union' user:ui-enumeration='inclusive' user:ui-marker='enumerate'>
              <groupfilter function='member' level='[none:Region:nk]' member='&quot;East&quot;' />
              <groupfilter function='member' level='[none:Region:nk]' member='&quot;West&quot;' />
            </groupfilter>
          </filter>
          <filter class='quantitative' column='[superstore-federated].[usr:Calculation_100:qk]' included-values='in-range'>
            <min>0.0</min>
            <max>0.25</max>
          </filter>
        </view>
        <style>
          <style-rule element='axis'>
            <format attr='font-size' value='9' />
          </style-rule>
        </style>
      </table>
    </worksheet>
    <worksheet name='単独シート'>
      <table>
        <view>
          <datasources>
            <datasource caption='スーパーストア' name='superstore-federated' />
          </datasources>
          <filter class='categorical' column='[superstore-federated].[none:Region:nk]'>
            <groupfilter function='except'>
              <groupfilter function='level-members' level='[none:Region:nk]' />
              <groupfilter function='member' level='[none:Region:nk]' member='&quot;Central&quot;' />
            </groupfilter>
          </filter>
        </view>
      </table>
    </worksheet>
  </worksheets>
  <dashboards>
    <dashboard name='売上ダッシュボード'>
      <size maxheight='800' maxwidth='1200' minheight='800' minwidth='1200' sizing-mode='fixed' />
      <zones>
        <zone id='1' type-v2='layout-basic' x='0' y='0' w='100000' h='100000'>
          <zone id='2' type-v2='layout-flow' param='vert' x='0' y='0' w='100000' h='100000'>
            <zone id='3' type-v2='title' x='0' y='0' w='100000' h='8000' />
            <zone id='4' name='売上推移' x='0' y='8000' w='70000' h='92000' />
            <zone id='5' type-v2='filter' param='[superstore-federated].[usr:Calculation_100:qk]'
                  x='70000' y='8000' w='30000' h='46000' />
            <zone id='6' type-v2='text' x='70000' y='54000' w='30000' h='46000'>
              <formatted-text>
                <run>注釈テキスト</run>
              </formatted-text>
            </zone>
          </zone>
        </zone>
      </zones>
      <devicelayouts>
        <devicelayout auto-generated='true' name='電話'>
          <zones>
            <zone id='7' name='売上推移' />
          </zones>
        </devicelayout>
      </devicelayouts>
    </dashboard>
  </dashboards>
  <style>
    <style-rule element='all'>
      <format attr='font-family' value='Meiryo UI' />
      <format attr='color' value='#000000' />
    </style-rule>
  </style>
</workbook>
"""


@pytest.fixture
def minimal_root() -> ET.Element:
    """最小構成の twb XML ルート要素。"""
    return ET.fromstring(MINIMAL_TWB)


@pytest.fixture
def sample_twbx_paths() -> list[Path]:
    """親フォルダの実サンプル twbx (存在するもののみ)。"""
    return sorted(SAMPLES_DIR.glob("*.twbx"))
