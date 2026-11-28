"""CI チェックのルール群。

health.py の健康診断 (設計書第 12 章) をそのまま流用し、ルール ID・
安定 ID・修正ヒントを付けた Finding に変換する。加えて CI 向けの
追加ルール (参照切れ・既定名のシート・コピー名の計算フィールド等) を持つ。

すべて Workbook モデルのみを入力とする純関数。Tableau Studio の
External Client API から得たワークシート診断 (無効フィールド) は
任意入力として受け取る。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Callable, Iterable

from .. import health
from ..health import HealthFinding
from ..i18n import JA, Translator
from ..model import CalculatedField, Workbook
from .naming_rules import naming_conventions, naming_whitespace
from .style_rules import inconsistent_font_families, inconsistent_font_sizes

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"
SEVERITY_ORDER = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 1, SEVERITY_INFO: 2}

# コメントなしで「複雑」とみなす計算式の長さ (コメント・空白除去後の文字数)
COMPLEX_FORMULA_LENGTH = 120

_DEFAULT_SHEET_NAME = re.compile(
    r"^(sheet|シート|dashboard|ダッシュボード|story|ストーリー)\s*\d+$",
    re.IGNORECASE,
)
_COPY_CAPTION = re.compile(
    r"(\((copy|コピー)(\s*\d+)?\)|のコピー|\s-\s?copy)$", re.IGNORECASE
)
_DEFAULT_CALC_CAPTION = re.compile(
    r"^(calculation|計算)\s*\d*$", re.IGNORECASE
)
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"")
_QUALIFIED_REF = re.compile(r"(\[[^\[\]]+\])(?:\.(\[[^\[\]]+\]))?")


@dataclass(frozen=True)
class Finding:
    """CI の検出結果 1 件。

    id はルールと対象から決まる安定 ID。ワークブックを編集しても
    同じ問題なら同じ ID になるため、新規 / 解消の判定や除外設定に使える。
    """

    id: str
    rule: str
    severity: str
    category: str
    target: str
    message: str
    fix_hint: str = ""
    # 修正に使える Tableau MCP ツール名 (Tableau Agent スキル向け)
    fix_tools: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        data = asdict(self)
        data["fix_tools"] = list(self.fix_tools)
        return data


def finding_id(rule: str, target: str) -> str:
    digest = hashlib.sha1(f"{rule}\0{target}".encode("utf-8")).hexdigest()
    return f"{rule}:{digest[:10]}"


def _make(
    rule: str,
    severity: str,
    category: str,
    target: str,
    message: str,
    fix_hint: str = "",
    fix_tools: tuple[str, ...] = (),
) -> Finding:
    return Finding(
        id=finding_id(rule, target),
        rule=rule,
        severity=severity,
        category=category,
        target=target,
        message=message,
        fix_hint=fix_hint,
        fix_tools=fix_tools,
    )


# --- health.py の既存チェック -------------------------------------------------

_HealthCheck = Callable[[Workbook, Translator], list[HealthFinding]]


def _health_rules(
    t: Translator,
) -> list[tuple[str, _HealthCheck, str, tuple[str, ...]]]:
    """(ルール ID, health のチェック関数, 修正ヒント, 修正ツール)。"""
    return [
        (
            "unused-calc",
            health._unused_calculated_fields,
            t(
                "データペインで右クリック→削除。残す場合は用途をコメントに記載。"
                "(External Client API に計算フィールド削除は無いため手動で削除)",
                "Delete it from the Data pane (right-click > Delete), or "
                "document why it is kept. (The External Client API cannot "
                "delete calculated fields, so delete it by hand.)",
            ),
            ("search-workbook-fields",),
        ),
        (
            "unused-parameter",
            health._unused_parameters,
            t(
                "データペインからパラメーターを削除するか、用途をコメントに記載。",
                "Delete the parameter from the Data pane, or document its "
                "purpose.",
            ),
            ("search-workbook-fields",),
        ),
        (
            "duplicate-formula",
            health._duplicated_formulas,
            t(
                "1 つを残し、他のフィールドの参照を置き換えてから削除。",
                "Keep one field, repoint the references to it, then delete "
                "the others.",
            ),
            ("search-workbook-fields", "author-calc"),
        ),
        (
            "extract-row-limit",
            health._extract_row_limits,
            t(
                "抽出の編集で行数制限を外し、抽出を更新。",
                "Remove the row limit in Edit Extract and refresh the extract.",
            ),
            ("refresh-datasource",),
        ),
        (
            "orphan-worksheet",
            health._orphan_worksheets,
            t(
                "作業用なら非表示にするか削除。公開するならダッシュボードへ配置。",
                "Hide or delete it if it is a scratch sheet, or place it on a "
                "dashboard.",
            ),
            ("delete-sheet", "apply-dashboard"),
        ),
        (
            "unused-datasource",
            health._unused_datasources,
            t(
                "データ→閉じる でワークブックから外す。",
                "Close it (Data > Close Data Source).",
            ),
            (),
        ),
        (
            "deep-dependency",
            health._deep_dependencies,
            t(
                "中間の計算フィールドを統合・整理する。",
                "Merge or simplify the intermediate calculated fields.",
            ),
            ("author-calc",),
        ),
        (
            "comment-coverage",
            health._comment_coverage,
            "",
            (),
        ),
    ]


def _from_health(
    workbook: Workbook, t: Translator
) -> list[Finding]:
    findings: list[Finding] = []
    for rule, check, hint, tools in _health_rules(t):
        for item in check(workbook, t):
            target, message = item.target, item.message
            if rule in _WORKBOOK_LEVEL_RULES:
                # 対象が件数 ("1/3 件") だと編集のたびに ID が変わり、
                # 同じ指摘が「新規」と「解消」を繰り返すため、対象名を固定する
                target = t("計算フィールド全体", "All calculated fields")
                message = f"{message} ({item.target})"
            findings.append(
                _make(rule, item.severity, item.category, target, message, hint, tools)
            )
    return findings


# ワークブック全体で 1 件だけ出るルール (対象名を固定して ID を安定させる)
_WORKBOOK_LEVEL_RULES = frozenset({"comment-coverage"})


# --- CI 向けの追加ルール ------------------------------------------------------


def _default_sheet_names(workbook: Workbook, t: Translator) -> list[Finding]:
    names = [sheet.name for sheet in workbook.worksheets] + [
        dashboard.name for dashboard in workbook.dashboards
    ]
    return [
        _make(
            "default-sheet-name",
            SEVERITY_INFO,
            t("既定名のままのシート", "Sheet with a default name"),
            name,
            t(
                "既定の名前のままです。内容がわかる名前に変更してください。",
                "The sheet still has its default name. Give it a "
                "descriptive name.",
            ),
            t("シート名を変更する。", "Rename the sheet."),
            ("rename-sheet",),
        )
        for name in names
        if _DEFAULT_SHEET_NAME.match(name.strip())
    ]


def _placeholder_calc_names(
    workbook: Workbook, t: Translator
) -> list[Finding]:
    findings: list[Finding] = []
    for calc in workbook.calculated_fields:
        caption = calc.caption.strip()
        if not caption:
            continue
        if _COPY_CAPTION.search(caption) or _DEFAULT_CALC_CAPTION.match(caption):
            findings.append(
                _make(
                    "placeholder-calc-name",
                    SEVERITY_INFO,
                    t(
                        "仮の名前の計算フィールド",
                        "Calculated field with a placeholder name",
                    ),
                    calc.display_name,
                    t(
                        "コピーや既定の名前のままです。意味のわかる名前に変更してください。",
                        "The name looks like a copy or a default. Give it a "
                        "meaningful name.",
                    ),
                    t(
                        "計算フィールドの名前を変更する。",
                        "Rename the calculated field.",
                    ),
                    ("author-calc",),
                )
            )
    return findings


def _uncommented_complex_calcs(
    workbook: Workbook, t: Translator
) -> list[Finding]:
    findings: list[Finding] = []
    for calc in workbook.calculated_fields:
        if calc.comment or calc.inline_comments:
            continue
        length = len(health._normalize_formula(calc.raw_formula))
        if length < COMPLEX_FORMULA_LENGTH:
            continue
        findings.append(
            _make(
                "uncommented-complex-calc",
                SEVERITY_INFO,
                t(
                    "コメントのない複雑な計算式",
                    "Complex formula without a comment",
                ),
                calc.display_name,
                t(
                    f"{length} 文字の計算式にコメントがありません。"
                    "意図を // コメントで残してください。",
                    f"This {length}-character formula has no comment. "
                    "Explain its intent with a // comment.",
                ),
                t(
                    "計算式の先頭に // で目的・前提を追記する。",
                    "Add a // comment at the top describing its purpose.",
                ),
                ("author-calc", "validate-calculated-field"),
            )
        )
    return findings


def _known_field_names(workbook: Workbook) -> tuple[set[str], set[str]]:
    """(既知のフィールド内部名, 既知のデータソース名) を返す。名前は [..] 形式。"""
    fields: set[str] = set()
    datasources: set[str] = {"[Parameters]"}
    for datasource in workbook.datasources:
        datasources.add(f"[{datasource.name}]")
        for field in datasource.fields:
            fields.add(field.name)
            if field.caption:
                fields.add(f"[{field.caption}]")
        for column in datasource.metadata_columns:
            fields.add(f"[{column.name}]")
        for table in datasource.logical_tables:
            for column in table.columns:
                fields.add(f"[{column.name}]")
        fields.update(datasource.group_names)
        for change in datasource.field_changes:
            fields.add(_bracket(change.name))
            if change.new_name:
                fields.add(_bracket(change.new_name))
    for calc in workbook.calculated_fields:
        fields.add(calc.name)
        if calc.caption:
            fields.add(f"[{calc.caption}]")
    for parameter in workbook.parameters:
        fields.add(parameter.name)
        if parameter.caption:
            fields.add(f"[{parameter.caption}]")
    return fields, datasources


def _bracket(name: str) -> str:
    return name if name.startswith("[") else f"[{name}]"


def _strip_literals_and_comments(formula: str) -> str:
    without_comments = health._LINE_COMMENT_PATTERN.sub(
        " ", health._BLOCK_COMMENT_PATTERN.sub(" ", formula)
    )
    return _STRING_LITERAL.sub("''", without_comments)


def unresolved_references(
    calc: CalculatedField, fields: set[str], datasources: set[str]
) -> tuple[str, ...]:
    """計算式内で、ワークブック内のどのフィールドにも解決できない参照。"""
    missing: list[str] = []
    for first, second in _QUALIFIED_REF.findall(
        _strip_literals_and_comments(calc.raw_formula)
    ):
        if second:
            if first not in datasources:
                # [論理テーブル].[列] 形式など: どちらかが既知なら解決済みとみなす
                if second in fields or first in fields:
                    continue
                ref = f"{first}.{second}"
            elif second in fields:
                continue
            else:
                ref = f"{first}.{second}"
        else:
            if first.startswith("[:") or first in fields or first in datasources:
                continue
            ref = first
        if ref not in missing:
            missing.append(ref)
    return tuple(missing)


def _broken_references(workbook: Workbook, t: Translator) -> list[Finding]:
    fields, datasources = _known_field_names(workbook)
    # 列定義が 1 つも無いデータソース (メタデータ無しの公開データソース等) の
    # 計算フィールドは判定できないため対象外にする
    checkable = {
        datasource.name
        for datasource in workbook.datasources
        if datasource.fields
        or datasource.metadata_columns
        or any(table.columns for table in datasource.logical_tables)
    }
    findings: list[Finding] = []
    for calc in workbook.calculated_fields:
        if calc.datasource and calc.datasource not in checkable:
            continue
        missing = unresolved_references(calc, fields, datasources)
        if not missing:
            continue
        findings.append(
            _make(
                "broken-reference",
                SEVERITY_WARNING,
                t("参照先が見つからない計算式", "Unresolved field reference"),
                calc.display_name,
                t(
                    "ワークブック内に見つからないフィールドを参照しています: "
                    + ", ".join(missing),
                    "References fields that are not in the workbook: "
                    + ", ".join(missing),
                ),
                t(
                    "validate-calculated-field で式を検証し、正しいフィールドに置き換える。",
                    "Validate the formula and point it at existing fields.",
                ),
                ("validate-calculated-field", "author-calc"),
            )
        )
    return findings


def studio_invalid_fields(
    diagnostics: dict | None,
    sheet_names: dict[str, str],
    t: Translator = JA,
) -> list[Finding]:
    """External Client API の /v0/workbook/diagnostics を Finding に変換する。

    sheet_names はワークシート ID → 名前 (/v0/workbook の worksheets から作る)。
    """
    if not diagnostics:
        return []
    findings: list[Finding] = []
    for sheet in diagnostics.get("worksheets", []) or []:
        sheet_name = sheet_names.get(sheet.get("worksheetId", ""), "") or sheet.get(
            "worksheetId", ""
        )
        for invalid in sheet.get("invalidFields", []) or []:
            label = invalid.get("fieldCaption") or invalid.get("fieldName", "")
            target = f"{sheet_name} / {label}"
            findings.append(
                _make(
                    "invalid-field",
                    SEVERITY_ERROR,
                    t("ワークシート上の無効なフィールド", "Invalid field on a worksheet"),
                    target,
                    t(
                        f"シェルフ「{invalid.get('shelf', '')}」のフィールドが無効です"
                        f" ({invalid.get('reason', '')})。",
                        f"A field on the {invalid.get('shelf', '')} shelf is "
                        f"invalid ({invalid.get('reason', '')}).",
                    ),
                    t(
                        "フィールドを置き換えるか、シェルフから外す。",
                        "Replace the field or remove it from the shelf.",
                    ),
                    ("remove-field", "refine-worksheet"),
                )
            )
    return findings


_EXTRA_RULES: tuple[Callable[[Workbook, Translator], list[Finding]], ...] = (
    _broken_references,
    _default_sheet_names,
    _placeholder_calc_names,
    _uncommented_complex_calcs,
)

RULE_IDS = (
    "invalid-field",
    "broken-reference",
    "unused-calc",
    "unused-parameter",
    "duplicate-formula",
    "extract-row-limit",
    "orphan-worksheet",
    "unused-datasource",
    "deep-dependency",
    "comment-coverage",
    "default-sheet-name",
    "placeholder-calc-name",
    "uncommented-complex-calc",
    "inconsistent-font-size",
    "inconsistent-font-family",
    "naming-convention",
    "naming-kind-mismatch",
    "naming-whitespace",
)


def run_checks(
    workbook: Workbook,
    t: Translator = JA,
    extra: Iterable[Finding] = (),
    config: "CheckConfig | None" = None,
) -> tuple[Finding, ...]:
    """全ルールを実行し、重要度 → ルール → 対象の順に並べて返す。"""
    from .config import CheckConfig  # 循環 import 回避

    config = config or CheckConfig()
    findings = [*extra, *_from_health(workbook, t)]
    for rule in _EXTRA_RULES:
        findings.extend(rule(workbook, t))
    for style_rule in (inconsistent_font_sizes, inconsistent_font_families):
        findings.extend(style_rule(workbook, t, config.style))
    findings.extend(naming_conventions(workbook, t, config.naming))
    findings.extend(naming_whitespace(workbook, t))
    applied = config.apply(findings)
    applied.sort(
        key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.rule, f.target)
    )
    return tuple(applied)


def count_by_severity(findings: Iterable[Finding]) -> dict[str, int]:
    counts = {SEVERITY_ERROR: 0, SEVERITY_WARNING: 0, SEVERITY_INFO: 0}
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
    return counts
