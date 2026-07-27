"""言語判定と Translator のテスト。"""

from __future__ import annotations

import pytest

from twbdoc.i18n import (
    ENGLISH,
    JAPANESE,
    LANG_ENV_VAR,
    Translator,
    detect_language,
    get_translator,
)


class TestTranslator:
    def test_日本語では第1引数を返す(self) -> None:
        t = Translator(JAPANESE)
        assert t("計算フィールド", "Calculated Field") == "計算フィールド"
        assert not t.is_english

    def test_英語では第2引数を返す(self) -> None:
        t = Translator(ENGLISH)
        assert t("計算フィールド", "Calculated Field") == "Calculated Field"
        assert t.is_english

    def test_未知の言語は日本語扱い(self) -> None:
        assert Translator("fr").language == JAPANESE


class TestDetectLanguage:
    def test_明示指定が最優先(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(LANG_ENV_VAR, "ja")
        assert detect_language("en") == ENGLISH

    def test_ロケール形式も正規化する(self) -> None:
        assert detect_language("ja-JP") == JAPANESE
        assert detect_language("en_US") == ENGLISH

    def test_autoは環境から判定する(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(LANG_ENV_VAR, "en")
        assert detect_language("auto") == ENGLISH
        assert detect_language(None) == ENGLISH

    def test_環境変数で切り替わる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(LANG_ENV_VAR, "ja")
        assert detect_language() == JAPANESE
        monkeypatch.setenv(LANG_ENV_VAR, "en-US")
        assert detect_language() == ENGLISH

    def test_不正な値は無視して環境判定に進む(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(LANG_ENV_VAR, "zzz")
        assert detect_language() in (JAPANESE, ENGLISH)

    def test_get_translatorは判定結果を返す(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(LANG_ENV_VAR, "en")
        assert get_translator().is_english


class TestTerminology:
    """Tableau 公式ヘルプの用語と一致していることを確認する。"""

    def test_次を使用して計算の表記(self) -> None:
        from twbdoc.renderers.table_calcs import ORDERING_TYPE_LABELS

        assert ORDERING_TYPE_LABELS["Rows"] == ("表 (横)", "Table (across)")
        assert ORDERING_TYPE_LABELS["RowsAcrossThenDown"] == (
            "表 (横から下へ)",
            "Table (across then down)",
        )
        assert ORDERING_TYPE_LABELS["Field"] == (
            "特定のディメンション",
            "Specific Dimensions",
        )

    def test_簡易表計算の表記(self) -> None:
        from twbdoc.renderers.table_calcs import CALC_TYPE_LABELS

        assert CALC_TYPE_LABELS["Percentile"][0] == "百分位"
        assert CALC_TYPE_LABELS["MovingCalc"][0] == "移動平均"
        assert CALC_TYPE_LABELS["PctTotal"] == (
            "合計に対する割合",
            "Percent of Total",
        )

    def test_アクション種別の表記(self) -> None:
        from twbdoc.renderers.actions import ACTION_KIND_LABELS

        assert ACTION_KIND_LABELS["url"] == ("URL に移動", "Go to URL")
        assert ACTION_KIND_LABELS["set"] == ("セット値の変更", "Change Set Values")

    def test_データ型の表記(self) -> None:
        from twbdoc.renderers.sections import DATATYPE_LABELS

        assert DATATYPE_LABELS["integer"] == ("数値 (整数)", "Number (whole)")
        assert DATATYPE_LABELS["boolean"][0] == "ブール値"
        assert DATATYPE_LABELS["datetime"] == ("日付と時刻", "Date & Time")
