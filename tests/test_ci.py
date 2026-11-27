"""CI チェック (ci/rules・ci/diff・ci/config・ci/report) と check サブコマンドのテスト。"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from twbdoc.ci.config import CheckConfig, find_config, load_config, should_fail
from twbdoc.ci.diff import (
    ADDED,
    CHANGED,
    REMOVED,
    diff_findings,
    diff_snapshots,
    labels_for,
    renames_from_ids,
    snapshot,
)
from twbdoc.ci.report import to_markdown, to_report_dict
from twbdoc.ci.rules import (
    SEVERITY_ERROR,
    SEVERITY_INFO,
    SEVERITY_WARNING,
    finding_id,
    run_checks,
    studio_invalid_fields,
)
from twbdoc.cli import main
from twbdoc.commands import EXIT_CHECK_FAILED, EXIT_INPUT_ERROR, EXIT_OK
from twbdoc.errors import InvalidFileError
from twbdoc.i18n import EN
from twbdoc.model import (
    CalculatedField,
    Dashboard,
    Datasource,
    Field,
    Workbook,
    WorkbookMeta,
    Worksheet,
)
from twbdoc.parsers import parse_workbook


def _calc(name: str, formula: str, caption: str = "", **kwargs) -> CalculatedField:
    return CalculatedField(
        name=name, caption=caption or name.strip("[]"), formula=formula,
        raw_formula=formula, datasource="ds", **kwargs,
    )


def _workbook(**kwargs) -> Workbook:
    base = dict(
        meta=WorkbookMeta(source_file="x.twb"),
        datasources=(
            Datasource(
                name="ds",
                fields=(Field(name="[Sales]"), Field(name="[Profit]")),
                group_names=("[Top Set]",),
            ),
        ),
    )
    base.update(kwargs)
    return Workbook(**base)


def _rules(findings) -> list[str]:
    return [f.rule for f in findings]


class TestRules:
    def test_health_の検出にルールIDと安定IDが付く(self, minimal_root) -> None:
        workbook = parse_workbook(minimal_root, source_file="x.twb")
        findings = run_checks(workbook)
        unused = [f for f in findings if f.rule == "unused-calc"]
        assert unused and unused[0].id == finding_id("unused-calc", unused[0].target)
        assert unused[0].fix_hint

    def test_重要度順に並ぶ(self, minimal_root) -> None:
        workbook = parse_workbook(minimal_root, source_file="x.twb")
        order = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}
        severities = [order[f.severity] for f in run_checks(workbook)]
        assert severities == sorted(severities)

    def test_参照切れを検出する(self) -> None:
        workbook = _workbook(
            calculated_fields=(_calc("[C1]", "SUM([Sales]) / SUM([Missing])"),),
            worksheets=(Worksheet(name="s", used_columns=("[C1]",)),),
        )
        broken = [f for f in run_checks(workbook) if f.rule == "broken-reference"]
        assert len(broken) == 1
        assert "[Missing]" in broken[0].message

    def test_文字列リテラル_コメント_セット_パラメーターは参照切れにしない(self) -> None:
        formula = (
            "// [NotAField] in a comment\n"
            "IF [Top Set] AND [Parameters].[Parameter 1] > 0 "
            "THEN '[literal]' ELSE \"[x]\" END /* [y] */ + [ds].[Profit]"
        )
        workbook = _workbook(
            calculated_fields=(_calc("[C1]", formula),),
            worksheets=(Worksheet(name="s", used_columns=("[C1]",)),),
            parameters=(),
        )
        # パラメーターを登録
        from twbdoc.model import Parameter

        workbook = replace(workbook, parameters=(Parameter(name="[Parameter 1]"),))
        assert "broken-reference" not in _rules(run_checks(workbook))

    def test_列定義のないデータソースは参照切れ判定をしない(self) -> None:
        workbook = _workbook(
            datasources=(Datasource(name="ds"),),
            calculated_fields=(_calc("[C1]", "SUM([Unknown])"),),
        )
        assert "broken-reference" not in _rules(run_checks(workbook))

    @pytest.mark.parametrize("name", ["Sheet 1", "シート 3", "Dashboard 2"])
    def test_既定名のシートを検出する(self, name: str) -> None:
        workbook = _workbook(
            worksheets=(Worksheet(name=name, dashboards=("d",)),),
        )
        assert "default-sheet-name" in _rules(run_checks(workbook))

    def test_意味のある名前のシートは対象外(self) -> None:
        workbook = _workbook(worksheets=(Worksheet(name="売上推移", dashboards=("d",)),))
        assert "default-sheet-name" not in _rules(run_checks(workbook))

    @pytest.mark.parametrize("caption", ["利益率 (コピー)", "Profit (copy)", "Calculation1", "計算 2"])
    def test_仮の名前の計算フィールドを検出する(self, caption: str) -> None:
        workbook = _workbook(calculated_fields=(_calc("[C1]", "1", caption=caption),))
        assert "placeholder-calc-name" in _rules(run_checks(workbook))

    def test_コメントのない長い計算式を検出する(self) -> None:
        long_formula = " + ".join(["SUM([Sales])"] * 12)
        workbook = _workbook(calculated_fields=(_calc("[C1]", long_formula),))
        assert "uncommented-complex-calc" in _rules(run_checks(workbook))
        commented = _workbook(
            calculated_fields=(_calc("[C1]", "// why\n" + long_formula, inline_comments=("why",)),)
        )
        assert "uncommented-complex-calc" not in _rules(run_checks(commented))

    def test_Studio_診断の無効フィールドはエラー(self) -> None:
        diagnostics = {
            "worksheets": [
                {
                    "worksheetId": "w1",
                    "status": "complete",
                    "invalidFields": [
                        {"fieldName": "[x]", "fieldCaption": "X", "shelf": "Rows",
                         "marksSpecificationId": "", "encodingType": "", "reason": "missing"}
                    ],
                },
                {"worksheetId": "w2", "status": "unavailable"},
            ]
        }
        findings = studio_invalid_fields(diagnostics, {"w1": "売上"})
        assert len(findings) == 1
        assert findings[0].severity == SEVERITY_ERROR
        assert findings[0].target == "売上 / X"
        assert studio_invalid_fields(None, {}) == []

    def test_英語出力(self, minimal_root) -> None:
        workbook = parse_workbook(minimal_root, source_file="x.twb")
        unused = [f for f in run_checks(workbook, EN) if f.rule == "unused-calc"]
        assert unused[0].category == "Unused calculated field"


class TestStableIds:
    def test_コメント記載率は計算フィールドが増えても同じ_ID(self) -> None:
        one = run_checks(_workbook(calculated_fields=(_calc("[C1]", "1"),)))
        two = run_checks(
            _workbook(calculated_fields=(_calc("[C1]", "1"), _calc("[C2]", "2")))
        )
        ids_one = {f.id for f in one if f.rule == "comment-coverage"}
        ids_two = {f.id for f in two if f.rule == "comment-coverage"}
        assert ids_one and ids_one == ids_two
        coverage = next(f for f in two if f.rule == "comment-coverage")
        assert "0/2" in coverage.message
        new, resolved = diff_findings(one, two)
        assert all(f.rule != "comment-coverage" for f in (*new, *resolved))


class TestConfig:
    def test_ルールの無効化_重要度上書き_除外(self, minimal_root, tmp_path: Path) -> None:
        workbook = parse_workbook(minimal_root, source_file="x.twb")
        baseline = run_checks(workbook)
        unused = next(f for f in baseline if f.rule == "unused-calc")
        path = tmp_path / ".twbdoc.json"
        path.write_text(
            json.dumps(
                {
                    "rules": {"orphan-worksheet": "off", "unused-parameter": "error"},
                    "ignore": [unused.id],
                    "fail_on": "warning",
                }
            ),
            encoding="utf-8",
        )
        config = load_config(path)
        findings = run_checks(workbook, config=config)
        rules = _rules(findings)
        assert "orphan-worksheet" not in rules
        assert unused.id not in {f.id for f in findings}
        assert next(f for f in findings if f.rule == "unused-parameter").severity == SEVERITY_ERROR
        assert config.fail_on == "warning"

    def test_rule_target_の組でも除外できる(self) -> None:
        config = CheckConfig(ignore_pairs=frozenset({("unused-calc", "C1")}))
        workbook = _workbook(calculated_fields=(_calc("[C1]", "1"),))
        assert "unused-calc" not in _rules(run_checks(workbook, config=config))

    def test_不正な重要度はエラー(self, tmp_path: Path) -> None:
        path = tmp_path / ".twbdoc.json"
        path.write_text('{"rules": {"unused-calc": "fatal"}}', encoding="utf-8")
        with pytest.raises(InvalidFileError):
            load_config(path)

    def test_親フォルダの設定を見つける(self, tmp_path: Path) -> None:
        (tmp_path / ".twbdoc.json").write_text("{}", encoding="utf-8")
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        assert find_config(nested) == tmp_path / ".twbdoc.json"

    def test_should_fail(self, minimal_root) -> None:
        findings = run_checks(parse_workbook(minimal_root, source_file="x.twb"))
        assert should_fail(findings, "warning")
        assert not should_fail(findings, "error")
        assert not should_fail(findings, "never")


class TestDiff:
    def test_初回は差分なし(self) -> None:
        assert diff_snapshots(None, snapshot(_workbook())) == ()

    def test_計算フィールドとシートの追加_削除_変更(self) -> None:
        before = _workbook(
            calculated_fields=(_calc("[C1]", "1", caption="旧"), _calc("[C2]", "2")),
            worksheets=(Worksheet(name="s", used_columns=("[Sales]",)),),
        )
        after = _workbook(
            calculated_fields=(_calc("[C1]", "1 + 1", caption="旧"), _calc("[C3]", "3")),
            worksheets=(Worksheet(name="s", used_columns=("[Sales]", "[C1]")),),
            dashboards=(Dashboard(name="d"),),
        )
        changes = diff_snapshots(snapshot(before), snapshot(after), labels_for(after))
        summary = {(c.kind, c.category, c.target) for c in changes}
        assert (ADDED, "calc", "C3") in summary
        assert (REMOVED, "calc", "[C2]") in summary
        assert (CHANGED, "calc", "旧") in summary
        assert (ADDED, "dashboard", "d") in summary
        sheet_change = next(c for c in changes if c.category == "worksheet")
        assert "[C1]" in sheet_change.detail

    def test_ID_から分かるシート名の変更は変更として扱う(self) -> None:
        before = _workbook(worksheets=(Worksheet(name="Sheet 1", used_columns=("[Sales]",)),))
        after = _workbook(worksheets=(Worksheet(name="売上", used_columns=("[Sales]", "[Profit]")),))
        renames = renames_from_ids({"w1": "Sheet 1"}, {"w1": "売上"})
        assert renames == {"Sheet 1": "売上"}
        changes = diff_snapshots(
            snapshot(before), snapshot(after), renames={"worksheet": renames}
        )
        assert [(c.kind, c.target) for c in changes] == [(CHANGED, "売上")]
        assert "Sheet 1 → 売上" in changes[0].detail
        assert "[Profit]" in changes[0].detail

    def test_ID_が無くても属性が同じ1組は名前の変更とみなす(self) -> None:
        before = _workbook(worksheets=(Worksheet(name="Sheet 1"), Worksheet(name="b")))
        after = _workbook(worksheets=(Worksheet(name="売上"), Worksheet(name="b")))
        changes = diff_snapshots(snapshot(before), snapshot(after))
        assert [(c.kind, c.category, c.target) for c in changes] == [
            (CHANGED, "worksheet", "売上")
        ]

    def test_属性が違えば削除と追加のまま(self) -> None:
        before = _workbook(worksheets=(Worksheet(name="a", used_columns=("[Sales]",)),))
        after = _workbook(worksheets=(Worksheet(name="b"),))
        kinds = {c.kind for c in diff_snapshots(snapshot(before), snapshot(after))}
        assert kinds == {ADDED, REMOVED}

    def test_初回は名前の変更なし(self) -> None:
        assert renames_from_ids(None, {"w1": "a"}) == {}

    def test_検出の新規と解消(self) -> None:
        before = run_checks(_workbook(calculated_fields=(_calc("[C1]", "1"),)))
        after = run_checks(_workbook(calculated_fields=(_calc("[C2]", "2"),)))
        new, resolved = diff_findings(before, after)
        assert any(f.target == "C2" for f in new)
        assert any(f.target == "C1" for f in resolved)
        assert diff_findings(None, after) == ((), ())


class TestReport:
    def test_markdown_は表を出しパイプをエスケープする(self) -> None:
        findings = run_checks(_workbook(calculated_fields=(_calc("[C1]", "1", caption="a|b"),)))
        markdown = to_markdown(to_report_dict("x.twb", findings))
        assert "| 重要度 |" in markdown
        assert "a\\|b" in markdown


class TestCheckCommand:
    def _write(self, tmp_path: Path, xml: str) -> Path:
        path = tmp_path / "book.twb"
        path.write_text(xml, encoding="utf-8")
        return path

    def test_json_出力と_fail_on(self, tmp_path: Path, capsys, minimal_twb_xml: str) -> None:
        path = self._write(tmp_path, minimal_twb_xml)
        code = main(["check", str(path), "--format", "json", "--fail-on", "warning", "--lang", "en"])
        assert code == EXIT_CHECK_FAILED
        report = json.loads(capsys.readouterr().out)
        assert report["workbook"] == "book.twb"
        assert report["summary"]["warning"] >= 1

    def test_既定は_error_のみで失敗(self, tmp_path: Path, capsys, minimal_twb_xml: str) -> None:
        path = self._write(tmp_path, minimal_twb_xml)
        assert main(["check", str(path)]) == EXIT_OK

    def test_レポートをファイルに書く(self, tmp_path: Path, minimal_twb_xml: str) -> None:
        path = self._write(tmp_path, minimal_twb_xml)
        out = tmp_path / "out" / "report.md"
        main(["check", str(path), "--format", "md", "--output", str(out)])
        assert "unused-calc" in out.read_text(encoding="utf-8")

    def test_入力なしは入力エラー(self) -> None:
        assert main(["check"]) == EXIT_INPUT_ERROR

    def test_存在しないファイルは入力エラー(self, tmp_path: Path) -> None:
        assert main(["check", str(tmp_path / "none.twbx")]) == EXIT_INPUT_ERROR

    def test_従来の設計書生成はそのまま動く(self, tmp_path: Path, minimal_twb_xml: str) -> None:
        path = self._write(tmp_path, minimal_twb_xml)
        assert main([str(path), "--no-sample", "--output", str(tmp_path)]) == EXIT_OK
