"""ワークブック健康診断 (保守リスクの機械検出)。

解析済みの Workbook モデルだけを入力とする純関数群。
検出結果は重要度 (warning / info) 付きの HealthFinding として返す。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .i18n import JA, Translator
from .model import Workbook

SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"

# この深さ以上の依存チェーンを「深い」と judge する
DEEP_DEPENDENCY_THRESHOLD = 4

_BLOCK_COMMENT_PATTERN = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_PATTERN = re.compile(r"//[^\r\n]*")


@dataclass(frozen=True)
class HealthFinding:
    """健康診断の検出結果 1 件。"""

    severity: str
    category: str
    target: str
    message: str


def diagnose(
    workbook: Workbook, t: Translator = JA
) -> tuple[HealthFinding, ...]:
    """全チェックを実行し、警告 -> 情報の順で検出結果を返す。"""
    findings = [
        *_unused_calculated_fields(workbook, t),
        *_unused_parameters(workbook, t),
        *_duplicated_formulas(workbook, t),
        *_extract_row_limits(workbook, t),
        *_orphan_worksheets(workbook, t),
        *_unused_datasources(workbook, t),
        *_deep_dependencies(workbook, t),
        *_comment_coverage(workbook, t),
    ]
    findings.sort(key=lambda f: 0 if f.severity == SEVERITY_WARNING else 1)
    return tuple(findings)


def warning_count(findings: tuple[HealthFinding, ...]) -> int:
    return sum(1 for f in findings if f.severity == SEVERITY_WARNING)


def _unused_calculated_fields(
    workbook: Workbook, t: Translator
) -> list[HealthFinding]:
    used_in_sheets = {
        name for sheet in workbook.worksheets for name in sheet.used_columns
    }
    referenced = {
        dependency
        for calc in workbook.calculated_fields
        for dependency in calc.depends_on
    }
    return [
        HealthFinding(
            severity=SEVERITY_WARNING,
            category=t("未使用の計算フィールド", "Unused calculated field"),
            target=calc.display_name,
            message=t(
                "どのワークシート・計算フィールドからも参照されていません。削除候補です。",
                "Not referenced by any worksheet or calculated field. "
                "Consider deleting it.",
            ),
        )
        for calc in workbook.calculated_fields
        if calc.name not in used_in_sheets and calc.name not in referenced
    ]


def _unused_parameters(
    workbook: Workbook, t: Translator
) -> list[HealthFinding]:
    used_in_sheets = {
        name for sheet in workbook.worksheets for name in sheet.used_columns
    }
    referenced_in_formulas = {
        dependency.split(".")[-1]
        for calc in workbook.calculated_fields
        for dependency in calc.depends_on
    }
    findings = []
    for parameter in workbook.parameters:
        if parameter.name in used_in_sheets:
            continue
        if parameter.name in referenced_in_formulas:
            continue
        if any(
            parameter.name in calc.raw_formula
            for calc in workbook.calculated_fields
        ):
            continue
        findings.append(
            HealthFinding(
                severity=SEVERITY_WARNING,
                category=t("未使用パラメーター", "Unused parameter"),
                target=parameter.display_name,
                message=t(
                    "どのワークシート・計算式からも参照されていません。削除候補です。",
                    "Not referenced by any worksheet or formula. "
                    "Consider deleting it.",
                ),
            )
        )
    return findings


def _duplicated_formulas(
    workbook: Workbook, t: Translator
) -> list[HealthFinding]:
    groups: dict[str, list[str]] = {}
    for calc in workbook.calculated_fields:
        normalized = _normalize_formula(calc.raw_formula)
        if normalized:
            groups.setdefault(normalized, []).append(calc.display_name)
    return [
        HealthFinding(
            severity=SEVERITY_WARNING,
            category=t("重複した計算式", "Duplicate formula"),
            target=", ".join(names),
            message=t(
                "同一の計算式を持つフィールドです。片方に統合できる可能性があります。",
                "These fields have identical formulas. "
                "Consider consolidating them.",
            ),
        )
        for names in groups.values()
        if len(names) > 1
    ]


def _normalize_formula(raw_formula: str) -> str:
    without_comments = _LINE_COMMENT_PATTERN.sub(
        " ", _BLOCK_COMMENT_PATTERN.sub(" ", raw_formula)
    )
    return " ".join(without_comments.split()).lower()


def _extract_row_limits(
    workbook: Workbook, t: Translator
) -> list[HealthFinding]:
    return [
        HealthFinding(
            severity=SEVERITY_WARNING,
            category=t("抽出の行数制限", "Extract row limit"),
            target=datasource.display_name,
            message=t(
                f"抽出に行数制限 ({datasource.extract.row_limit} 行) が"
                "設定されています。サンプル抽出のまま運用していないか確認してください。",
                f"The extract is limited to {datasource.extract.row_limit} rows. "
                "Check that it is not still a sample extract.",
            ),
        )
        for datasource in workbook.datasources
        if datasource.extract is not None and datasource.extract.row_limit
    ]


def _orphan_worksheets(
    workbook: Workbook, t: Translator
) -> list[HealthFinding]:
    return [
        HealthFinding(
            severity=SEVERITY_INFO,
            category=t(
                "ダッシュボード未配置のシート", "Worksheet not on a dashboard"
            ),
            target=sheet.name,
            message=t(
                "どのダッシュボードにも配置されていません (作業用シートの可能性)。",
                "Not placed on any dashboard (it may be a working sheet).",
            ),
        )
        for sheet in workbook.worksheets
        if not sheet.dashboards
    ]


def _unused_datasources(
    workbook: Workbook, t: Translator
) -> list[HealthFinding]:
    used = {
        ds_name for sheet in workbook.worksheets for ds_name in sheet.datasources
    }
    return [
        HealthFinding(
            severity=SEVERITY_INFO,
            category=t("未使用データソース", "Unused data source"),
            target=datasource.display_name,
            message=t(
                "どのワークシートからも使用されていません。",
                "Not used by any worksheet.",
            ),
        )
        for datasource in workbook.datasources
        if datasource.display_name not in used
    ]


def _deep_dependencies(
    workbook: Workbook, t: Translator
) -> list[HealthFinding]:
    depends = {calc.name: calc.depends_on for calc in workbook.calculated_fields}
    display = {calc.name: calc.display_name for calc in workbook.calculated_fields}

    def depth_of(name: str, visiting: frozenset[str]) -> int:
        if name not in depends or name in visiting:
            return 0
        children = [
            depth_of(dep, visiting | {name}) for dep in depends[name]
        ]
        return 1 + (max(children) if children else 0)

    findings = []
    for calc in workbook.calculated_fields:
        depth = depth_of(calc.name, frozenset())
        if depth >= DEEP_DEPENDENCY_THRESHOLD:
            findings.append(
                HealthFinding(
                    severity=SEVERITY_INFO,
                    category=t("深い依存チェーン", "Deep dependency chain"),
                    target=display[calc.name],
                    message=t(
                        f"計算フィールドの依存が {depth} 段あります。"
                        "デバッグしやすいよう整理を検討してください。",
                        f"This calculated field has {depth} levels of "
                        "dependencies. Consider simplifying it.",
                    ),
                )
            )
    return findings


def _comment_coverage(
    workbook: Workbook, t: Translator
) -> list[HealthFinding]:
    total = len(workbook.calculated_fields)
    if total == 0:
        return []
    commented = sum(
        1
        for calc in workbook.calculated_fields
        if calc.comment or calc.inline_comments
    )
    percent = round(commented * 100 / total)
    return [
        HealthFinding(
            severity=SEVERITY_INFO,
            category=t("コメント記載率", "Comment coverage"),
            target=t(f"{commented}/{total} 件", f"{commented} of {total}"),
            message=t(
                f"コメント (Tableau/式内) が記載された計算フィールドは {percent}% です。",
                f"{percent}% of calculated fields have a comment "
                "(in Tableau or in the formula).",
            ),
        )
    ]
