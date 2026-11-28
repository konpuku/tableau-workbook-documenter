"""命名規則のルール (ci/naming_rules.py) と設定のテスト。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from twbdoc.ci.config import CheckConfig, load_config
from twbdoc.ci.naming_rules import (
    KIND_BOOLEAN_CALC,
    KIND_CALC,
    KIND_LOD_CALC,
    KIND_TABLE_CALC,
    calc_kind,
)
from twbdoc.ci.rules import SEVERITY_INFO, SEVERITY_WARNING, run_checks
from twbdoc.errors import InvalidFileError
from twbdoc.i18n import EN
from twbdoc.model import (
    CalculatedField,
    Dashboard,
    Parameter,
    TableCalc,
    Workbook,
    WorkbookMeta,
    Worksheet,
)


def _calc(caption: str, formula: str = "1", **kwargs) -> CalculatedField:
    return CalculatedField(
        name=f"[{caption}]", caption=caption, formula=formula, raw_formula=formula, **kwargs
    )


def _wb(**kwargs) -> Workbook:
    return Workbook(meta=WorkbookMeta(source_file="x.twb"), **kwargs)


def _config(tmp_path: Path, naming: dict) -> CheckConfig:
    path = tmp_path / ".twbdoc.json"
    path.write_text(json.dumps({"naming": naming}), encoding="utf-8")
    return load_config(path, EN)


def _by_rule(workbook: Workbook, config: CheckConfig | None = None) -> dict[str, list]:
    result: dict[str, list] = {}
    for finding in run_checks(workbook, EN, config=config):
        result.setdefault(finding.rule, []).append(finding)
    return result


class TestCalcKind:
    @pytest.mark.parametrize(
        ("formula", "kwargs", "kind"),
        [
            ("{FIXED [Region] : SUM([Sales])}", {}, KIND_LOD_CALC),
            ("{ include [Region]: AVG([Profit])}", {}, KIND_LOD_CALC),
            ("WINDOW_AVG(SUM([Sales]), -2, 0)", {}, KIND_TABLE_CALC),
            ("RANK(SUM([Sales]))", {}, KIND_TABLE_CALC),
            ("SUM([Sales])", {"table_calc": TableCalc(ordering_type="Rows")}, KIND_TABLE_CALC),
            ("[Sales] > 100", {"datatype": "boolean"}, KIND_BOOLEAN_CALC),
            ("SUM([Sales])", {}, KIND_CALC),
            # 文字列・コメント内の語は数えない
            ("'{FIXED}' + \"INDEX()\" // RANK(", {}, KIND_CALC),
        ],
    )
    def test_種類の判定(self, formula: str, kwargs: dict, kind: str) -> None:
        assert calc_kind(_calc("x", formula, **kwargs)) == kind


class TestNamingConvention:
    def test_設定が無ければ規則の検査はしない(self) -> None:
        rules = _by_rule(_wb(calculated_fields=(_calc("売上"),)))
        assert "naming-convention" not in rules

    def test_規則に合わない名前を警告し説明を出す(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"calc": {"pattern": "^c_", "description": "c_ で始める"}})
        workbook = _wb(calculated_fields=(_calc("c_売上"), _calc("利益率")))
        (finding,) = _by_rule(workbook, config)["naming-convention"]
        assert finding.severity == SEVERITY_WARNING
        assert finding.target == "利益率"
        assert "c_ で始める" in finding.message
        assert "references" in finding.fix_hint  # 名前を変えても参照は壊れない旨
        assert finding.fix_tools == ("get-datasource-xml", "apply-datasource")

    def test_細かい種類は規則が無ければ計算フィールドの規則を使う(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"calc": "^c_"})
        workbook = _wb(calculated_fields=(_calc("c_lod", "{FIXED : SUM([Sales])}"), _calc("lod2", "{FIXED : 1}")))
        (finding,) = _by_rule(workbook, config)["naming-convention"]
        assert finding.target == "lod2"

    def test_パラメーターとシート(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"parameter": "^p_", "worksheet": "^(?!Sheet)", "dashboard": "^DB_"})
        workbook = _wb(
            parameters=(Parameter(name="[Parameter 1]", caption="閾値"),),
            worksheets=(Worksheet(name="Sheet 3", dashboards=("d",)),),
            dashboards=(Dashboard(name="DB_概要"),),
        )
        targets = {f.target for f in _by_rule(workbook, config)["naming-convention"]}
        assert targets == {"閾値", "Sheet 3"}


class TestKindMismatch:
    def test_lod_の名前なのに_LOD_でない(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"preset": "prefix"})
        workbook = _wb(calculated_fields=(_calc("lod_売上", "SUM([Sales])"),))
        rules = _by_rule(workbook, config)
        assert "naming-convention" not in rules
        (finding,) = rules["naming-kind-mismatch"]
        assert finding.target == "lod_売上"
        assert "LOD calculation" in finding.message and "calculated field" in finding.message

    def test_LOD_なのに計算フィールドの名前(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"preset": "prefix"})
        workbook = _wb(calculated_fields=(_calc("c_顧客別売上", "{FIXED [Customer] : SUM([Sales])}"),))
        (finding,) = _by_rule(workbook, config)["naming-kind-mismatch"]
        assert finding.target == "c_顧客別売上"

    def test_規則どおりならずれは出ない(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"preset": "prefix"})
        workbook = _wb(
            calculated_fields=(
                _calc("c_売上", "SUM([Sales])"),
                _calc("lod_顧客別", "{FIXED [Customer] : SUM([Sales])}"),
                _calc("tc_移動平均", "WINDOW_AVG(SUM([Sales]), -2, 0)"),
            ),
            parameters=(Parameter(name="[Parameter 1]", caption="p_閾値"),),
        )
        rules = _by_rule(workbook, config)
        assert "naming-convention" not in rules and "naming-kind-mismatch" not in rules

    def test_シートの緩い規則とは比べない(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"calc": "^c_", "worksheet": "^(?!Sheet)"})
        workbook = _wb(calculated_fields=(_calc("売上"),))
        rules = _by_rule(workbook, config)
        assert "naming-kind-mismatch" not in rules
        assert rules["naming-convention"][0].target == "売上"

    def test_個別の規則でひな形を上書きできる(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"preset": "prefix", "parameter": {"pattern": "^prm_", "description": "prm_"}})
        workbook = _wb(parameters=(Parameter(name="[P]", caption="prm_閾値"),))
        assert "naming-convention" not in _by_rule(workbook, config)


class TestWhitespace:
    @pytest.mark.parametrize("name", ["売上 ", " 売上", "売上  合計", "売上　合計"])
    def test_空白を指摘する(self, name: str) -> None:
        (finding,) = _by_rule(_wb(calculated_fields=(_calc(name),)))["naming-whitespace"]
        assert finding.severity == SEVERITY_INFO
        assert finding.target == name

    def test_普通の名前は指摘しない(self) -> None:
        workbook = _wb(
            calculated_fields=(_calc("売上 合計"),),
            worksheets=(Worksheet(name="Sales by Region", dashboards=("d",)),),
        )
        assert "naming-whitespace" not in _by_rule(workbook)

    def test_シート名も対象(self) -> None:
        workbook = _wb(dashboards=(Dashboard(name="概要 "),))
        (finding,) = _by_rule(workbook)["naming-whitespace"]
        assert finding.fix_tools == ("rename-sheet",)


class TestNamingConfig:
    @pytest.mark.parametrize(
        "naming",
        [
            {"preset": "unknown"},
            {"measure": "^m_"},
            {"calc": "^c_("},
            {"calc": {"description": "no pattern"}},
            {"calc": 1},
            "^c_",
        ],
    )
    def test_不正な設定はエラー(self, tmp_path: Path, naming) -> None:
        with pytest.raises(InvalidFileError):
            _config(tmp_path, naming)

    def test_ひな形の説明は出力言語で出る(self, tmp_path: Path) -> None:
        config = _config(tmp_path, {"preset": "prefix"})
        assert config.naming.rules["calc"].description == "Calculated fields start with c_"
