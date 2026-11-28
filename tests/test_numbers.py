"""直書きの数値のルール (ci/number_rules.py) と設定のテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from twbdoc.ci.config import CheckConfig, load_config
from twbdoc.ci.number_rules import compared_numbers
from twbdoc.ci.rules import SEVERITY_INFO, SEVERITY_WARNING, run_checks
from twbdoc.errors import InvalidFileError
from twbdoc.i18n import EN
from twbdoc.model import CalculatedField, Workbook, WorkbookMeta


def _calc(caption: str, formula: str) -> CalculatedField:
    return CalculatedField(
        name=f"[{caption}]", caption=caption, formula=formula, raw_formula=formula
    )


def _wb(*calcs: CalculatedField) -> Workbook:
    return Workbook(meta=WorkbookMeta(source_file="x.twb"), calculated_fields=calcs)


def _findings(workbook: Workbook, config: CheckConfig | None = None) -> list:
    return [f for f in run_checks(workbook, EN, config=config) if f.rule == "magic-number"]


def _numbers(formula: str) -> list[str]:
    return [text for text, _ in compared_numbers(formula)]


class TestComparedNumbers:
    @pytest.mark.parametrize(
        ("formula", "expected"),
        [
            ("IF [利益率] > 0.1 THEN 'OK' END", ["0.1"]),
            ("0.1 < [利益率]", ["0.1"]),
            ("[x] <= -0.25", ["-0.25"]),
            ("IF SUM([Sales]) >= 1000 AND SUM([Sales]) < 5000 THEN 1 END", ["1000", "5000"]),
            ("IIF(DATEPART('year', [Order Date]) = 2022, [Sales], 0)", ["2022"]),
            ("{FIXED [Region] : SUM([Sales])} > 300", ["300"]),
            ("[a] <> 3 OR [b] != 4", ["3", "4"]),
            ("[x] > .5", [".5"]),
            # しきい値のパラメーターはフィールドと比べるので、別の数値は拾う
            ("[Sales] > [Parameters].[Target] AND [Margin] > 0.2", ["0.2"]),
        ],
    )
    def test_比較の数値を拾う(self, formula: str, expected: list[str]) -> None:
        assert _numbers(formula) == expected

    @pytest.mark.parametrize(
        "formula",
        [
            # 関数の引数・掛け算・割り算は対象外
            "SPLIT([x], '|', 2) = [y]",
            "LEFT([Code], 4)",
            "ROUND([x] * 50, -1)",
            "DATEADD('month', -3, [Order Date])",
            "MAKEPOINT(35.6, 139.7)",
            "CEILING([x] / 10) * 10",
            "WINDOW_AVG(SUM([Sales]), -2, 0)",
            # 表計算の位置との比較は対象外
            "INDEX() = 5",
            "IF FIRST() > -3 THEN 1 END",
            "3 < SIZE()",
            # パラメーターとの比較はリストの選択肢の番号
            "IF [Parameters].[Measure Select] = 2 THEN [Sales] END",
            "3 = [Parameters].[Measure Select]",
            # 算術の途中の数値は比較の相手ではない
            "[a] * 2 > [b]",
            # 文字列・コメント・フィールド名の中の数字は数えない
            "[x] = '2022' // [y] > 10",
            "[Sales 2022] > [Target]",
            "[x] > #2022-01-01#",
        ],
    )
    def test_対象外(self, formula: str) -> None:
        assert _numbers(formula) == []


class TestMagicNumberRule:
    def test_計算フィールドごとに1件(self) -> None:
        workbook = _wb(_calc("判定", "IF [利益率] > 0.1 THEN 'A' ELSEIF [利益率] > 0.05 THEN 'B' END"))
        (finding,) = _findings(workbook)
        assert finding.severity == SEVERITY_INFO
        assert finding.target == "判定"
        assert "0.1, 0.05" in finding.message
        assert "author-parameter" in finding.fix_tools

    def test_既定の対象外の値(self) -> None:
        workbook = _wb(_calc("f", "IF [x] > 0 AND [y] = 1 AND [z] <= 100 AND [w] = -1 THEN 1 END"))
        assert _findings(workbook) == []

    def test_同じ数値が複数の計算式にあれば警告(self) -> None:
        workbook = _wb(
            _calc("高利益", "[利益率] > 0.1"),
            _calc("色分け", "IF [利益率] > 0.10 THEN 'red' END"),
            _calc("別の値", "[利益率] > 0.2"),
        )
        by_target = {f.target: f for f in _findings(workbook)}
        assert by_target["高利益"].severity == SEVERITY_WARNING
        assert "色分け" in by_target["高利益"].message
        assert by_target["色分け"].severity == SEVERITY_WARNING
        assert by_target["別の値"].severity == SEVERITY_INFO

    def test_年には相対日付を提案する(self) -> None:
        workbook = _wb(_calc("今年", "IIF(DATEPART('year', [Order Date]) = 2024, [Sales], NULL)"))
        (finding,) = _findings(workbook)
        assert "DATEDIFF" in finding.fix_hint and "2024" in finding.fix_hint

    def test_年でない数値には相対日付を出さない(self) -> None:
        (finding,) = _findings(_wb(_calc("f", "[x] > 5000")))
        assert "DATEDIFF" not in finding.fix_hint

    def test_数値を直しても_ID_は変わらない(self) -> None:
        (before,) = _findings(_wb(_calc("判定", "[x] > 0.1")))
        (after,) = _findings(_wb(_calc("判定", "[x] > 0.2 AND [y] < 3")))
        assert before.id == after.id


class TestMagicNumberConfig:
    def _config(self, tmp_path: Path, data: dict) -> CheckConfig:
        path = tmp_path / ".twbdoc.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return load_config(path, EN)

    def test_allow_で対象外を足せる(self, tmp_path: Path) -> None:
        config = self._config(tmp_path, {"magic_numbers": {"allow": [0.5, 12]}})
        workbook = _wb(_calc("f", "[x] > 0.5 AND [m] = 12"), _calc("g", "[x] > 0.7"))
        assert [f.target for f in _findings(workbook, config)] == ["g"]

    def test_ルールを無効にできる(self, tmp_path: Path) -> None:
        config = self._config(tmp_path, {"rules": {"magic-number": "off"}})
        assert _findings(_wb(_calc("f", "[x] > 0.7")), config) == []

    @pytest.mark.parametrize(
        "magic",
        [[0.5], {"allow": "0.5"}, {"allow": ["0.5"]}, {"allow": [True]}, {"allowed": [1]}],
    )
    def test_不正な設定はエラー(self, tmp_path: Path, magic) -> None:
        with pytest.raises(InvalidFileError):
            self._config(tmp_path, {"magic_numbers": magic})
