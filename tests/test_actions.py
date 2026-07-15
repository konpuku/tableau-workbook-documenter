"""ダッシュボードアクション (パーサー + レンダラー) のテスト。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from twbdoc.parsers.actions import parse_actions
from twbdoc.renderers.actions import render_actions


class TestParseActions:
    def test_アクション3種を抽出する(self, minimal_root: ET.Element) -> None:
        actions = parse_actions(minimal_root)
        assert [action.kind for action in actions] == [
            "ハイライト",
            "URL を開く",
            "セットの値を変更",
        ]

    def test_ハイライトアクションの詳細(self, minimal_root: ET.Element) -> None:
        highlight = parse_actions(minimal_root)[0]
        assert highlight.caption == "ハイライト1"
        assert highlight.activation == "on-select"
        assert highlight.source_dashboard == "売上ダッシュボード"
        assert highlight.excluded_sheets == ("単独シート",)
        assert highlight.fields == "地域"
        assert highlight.target == "売上ダッシュボード"
        assert highlight.params == ()  # 表示済みパラメーターは除外される

    def test_URLアクションのパラメーター(self, minimal_root: ET.Element) -> None:
        url_action = parse_actions(minimal_root)[1]
        assert url_action.activation == "on-menu"
        assert url_action.source_worksheet == "売上推移"
        assert ("url", "https://example.com/detail?region=<地域>") in url_action.params

    def test_セットアクションのターゲット(self, minimal_root: ET.Element) -> None:
        set_action = parse_actions(minimal_root)[2]
        assert set_action.target == "[superstore-federated].[Region Set]"

    def test_actionsなしは空(self) -> None:
        root = ET.fromstring("<workbook />")
        assert parse_actions(root) == ()


class TestRenderActions:
    def test_章とテーブルが出る(self, minimal_root: ET.Element) -> None:
        actions = parse_actions(minimal_root)
        text = "\n".join(render_actions(actions, {}, 4))
        assert "## 4. ダッシュボードアクション" in text
        assert "| 名前 | 種類 | 実行タイミング | ソース | ターゲット | 対象フィールド | 詳細 |" in text
        assert "選択時" in text
        assert "メニュー選択時" in text
        assert "売上ダッシュボード (除外: 単独シート)" in text
        # セットアクションのターゲットは可読化される
        assert "Region Set" in text

    def test_アクションなしは該当なし(self) -> None:
        text = "\n".join(render_actions((), {}, 4))
        assert "(該当なし)" in text
