"""健康診断 (health.py + レンダラー) のテスト。"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from twbdoc.health import (
    SEVERITY_INFO,
    SEVERITY_WARNING,
    diagnose,
    warning_count,
)
from twbdoc.model import (
    CalculatedField,
    Dashboard,
    Datasource,
    ExtractInfo,
    Parameter,
    Workbook,
    WorkbookMeta,
    Worksheet,
)
from twbdoc.parsers import parse_workbook
from twbdoc.renderers.health import render_health


def _calc(name: str, formula: str, **kwargs) -> CalculatedField:
    return CalculatedField(
        name=name, caption=name.strip("[]"), formula=formula,
        raw_formula=formula, **kwargs,
    )


class TestDiagnose:
    def test_未使用計算フィールドを検出する(self) -> None:
        workbook = Workbook(
            meta=WorkbookMeta(source_file="x.twbx"),
            calculated_fields=(_calc("[C1]", "1+1"),),
        )
        findings = diagnose(workbook)
        assert any(
            f.category == "未使用の計算フィールド" and f.target == "C1"
            for f in findings
        )

    def test_未使用パラメーターを検出する(self) -> None:
        workbook = Workbook(
            meta=WorkbookMeta(source_file="x.twbx"),
            parameters=(
                Parameter(name="[P1]", caption="使わないパラメーター"),
                Parameter(name="[P2]", caption="式で使うパラメーター"),
            ),
            calculated_fields=(
                _calc("[C1]", "[Parameters].[P2] * 2"),
            ),
            worksheets=(
                Worksheet(name="s", used_columns=("[C1]",), dashboards=("d",)),
            ),
        )
        findings = diagnose(workbook)
        targets = [
            f.target for f in findings if f.category == "未使用パラメーター"
        ]
        assert targets == ["使わないパラメーター"]

    def test_重複した計算式を検出する(self) -> None:
        workbook = Workbook(
            meta=WorkbookMeta(source_file="x.twbx"),
            calculated_fields=(
                _calc("[C1]", "SUM([Sales]) // 売上合計"),
                _calc("[C2]", "sum([Sales])"),
                _calc("[C3]", "AVG([Sales])"),
            ),
        )
        findings = diagnose(workbook)
        duplicated = [
            f for f in findings if f.category == "重複した計算式"
        ]
        assert len(duplicated) == 1
        assert "C1" in duplicated[0].target and "C2" in duplicated[0].target

    def test_抽出の行数制限を警告する(self) -> None:
        workbook = Workbook(
            meta=WorkbookMeta(source_file="x.twbx"),
            datasources=(
                Datasource(
                    name="ds",
                    extract=ExtractInfo(enabled=True, row_limit="1000"),
                ),
            ),
        )
        findings = diagnose(workbook)
        assert any(f.category == "抽出の行数制限" for f in findings)

    def test_ダッシュボード未配置シートは情報レベル(self) -> None:
        workbook = Workbook(
            meta=WorkbookMeta(source_file="x.twbx"),
            worksheets=(Worksheet(name="作業用"),),
            dashboards=(Dashboard(name="d"),),
        )
        findings = diagnose(workbook)
        finding = next(
            f for f in findings if f.category == "ダッシュボード未配置のシート"
        )
        assert finding.severity == SEVERITY_INFO
        assert finding.target == "作業用"

    def test_深い依存チェーンを検出する(self) -> None:
        workbook = Workbook(
            meta=WorkbookMeta(source_file="x.twbx"),
            calculated_fields=(
                _calc("[C1]", "[Sales]"),
                _calc("[C2]", "[C1]", depends_on=("[C1]",)),
                _calc("[C3]", "[C2]", depends_on=("[C2]",)),
                _calc("[C4]", "[C3]", depends_on=("[C3]",)),
            ),
            worksheets=(
                Worksheet(
                    name="s",
                    used_columns=("[C1]", "[C2]", "[C3]", "[C4]"),
                    dashboards=("d",),
                ),
            ),
        )
        findings = diagnose(workbook)
        deep = [f for f in findings if f.category == "深い依存チェーン"]
        assert [f.target for f in deep] == ["C4"]

    def test_循環参照でも無限ループしない(self) -> None:
        workbook = Workbook(
            meta=WorkbookMeta(source_file="x.twbx"),
            calculated_fields=(
                _calc("[C1]", "[C2]", depends_on=("[C2]",)),
                _calc("[C2]", "[C1]", depends_on=("[C1]",)),
            ),
        )
        diagnose(workbook)  # 完了すれば OK

    def test_警告が情報より先に並ぶ(self, minimal_root: ET.Element) -> None:
        workbook = parse_workbook(minimal_root, "test.twbx")
        findings = diagnose(workbook)
        severities = [f.severity for f in findings]
        first_info = severities.index(SEVERITY_INFO)
        assert SEVERITY_WARNING not in severities[first_info:]

    def test_warning_count(self) -> None:
        workbook = Workbook(
            meta=WorkbookMeta(source_file="x.twbx"),
            calculated_fields=(_calc("[C1]", "1+1"),),
        )
        findings = diagnose(workbook)
        assert warning_count(findings) >= 1


class TestRenderHealth:
    def test_章とテーブルが出る(self, minimal_root: ET.Element) -> None:
        workbook = parse_workbook(minimal_root, "test.twbx")
        text = "\n".join(render_health(diagnose(workbook), 12))
        assert "## 12. 健康診断" in text
        assert "| 重要度 | 項目 | 対象 | 内容 |" in text
        assert "⚠ 警告" in text or "ℹ 情報" in text

    def test_検出なしはメッセージのみ(self) -> None:
        text = "\n".join(render_health((), 12))
        assert "問題は検出されませんでした。" in text
