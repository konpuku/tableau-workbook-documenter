"""命名規則のルール。

- naming-convention   : チームで決めた正規表現 (.twbdoc.json の "naming") に合わない名前
- naming-kind-mismatch: 名前が別の種類の規則に合っている (lod_ なのに LOD 式でない等)。
                        種類を名前に入れたときに、式の変更で名前と中身がずれる問題を見つける
- naming-whitespace   : 前後の空白・連続した空白・全角スペース (設定不要)

計算フィールドの名前 (caption) を変えても、式は内部名で参照しているため
参照は壊れない。修正のヒントにはその旨を書く。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterator

from ..i18n import Translator
from ..model import CalculatedField, Workbook

if TYPE_CHECKING:  # 循環 import 回避
    from .rules import Finding

KIND_CALC = "calc"
KIND_LOD_CALC = "lod-calc"
KIND_TABLE_CALC = "table-calc"
KIND_BOOLEAN_CALC = "boolean-calc"
KIND_PARAMETER = "parameter"
KIND_WORKSHEET = "worksheet"
KIND_DASHBOARD = "dashboard"

# 種類 → (日本語, 英語)。キーは .twbdoc.json の naming でも使う。
KIND_LABELS: dict[str, tuple[str, str]] = {
    KIND_CALC: ("計算フィールド", "calculated field"),
    KIND_LOD_CALC: ("LOD 計算", "LOD calculation"),
    KIND_TABLE_CALC: ("表計算", "table calculation"),
    KIND_BOOLEAN_CALC: ("ブール型の計算フィールド", "boolean calculated field"),
    KIND_PARAMETER: ("パラメーター", "parameter"),
    KIND_WORKSHEET: ("ワークシート", "worksheet"),
    KIND_DASHBOARD: ("ダッシュボード", "dashboard"),
}

# 計算フィールドの細かい種類は、規則が無ければ「計算フィールド」の規則を使う
_FALLBACK = {
    KIND_LOD_CALC: KIND_CALC,
    KIND_TABLE_CALC: KIND_CALC,
    KIND_BOOLEAN_CALC: KIND_CALC,
}

# ひな形 ("preset")。よく使われる接頭辞の規則。個別の規則で上書きできる。
PRESETS: dict[str, dict[str, tuple[str, tuple[str, str]]]] = {
    "prefix": {
        KIND_CALC: (r"^c_", ("計算フィールドは c_ で始める", "Calculated fields start with c_")),
        KIND_LOD_CALC: (r"^lod_", ("LOD 計算は lod_ で始める", "LOD calculations start with lod_")),
        KIND_TABLE_CALC: (r"^tc_", ("表計算は tc_ で始める", "Table calculations start with tc_")),
        KIND_PARAMETER: (r"^p_", ("パラメーターは p_ で始める", "Parameters start with p_")),
    },
}

_SHEET_KINDS = frozenset({KIND_WORKSHEET, KIND_DASHBOARD})
_FIELD_KINDS = frozenset(KIND_LABELS) - _SHEET_KINDS

_LOD = re.compile(r"\{\s*(FIXED|INCLUDE|EXCLUDE)\b", re.IGNORECASE)
_TABLE_FUNCTION = re.compile(
    r"\b(WINDOW_\w+|RUNNING_\w+|INDEX|RANK\w*|FIRST|LAST|LOOKUP|"
    r"PREVIOUS_VALUE|SIZE|TOTAL)\s*\(",
    re.IGNORECASE,
)
_SPACE_RUN = re.compile(r" {2,}")
_FULL_WIDTH_SPACE = "　"


@dataclass(frozen=True)
class NamingRule:
    pattern: re.Pattern[str]
    description: str = ""


@dataclass(frozen=True)
class NamingConfig:
    """.twbdoc.json の "naming"。kind → NamingRule。"""

    rules: dict[str, NamingRule] = field(default_factory=dict)

    def rule_for(self, kind: str) -> tuple[str, NamingRule] | None:
        """kind の規則 (無ければ代わりに使う種類の規則) を (使った種類, 規則) で返す。"""
        if kind in self.rules:
            return kind, self.rules[kind]
        fallback = _FALLBACK.get(kind)
        if fallback and fallback in self.rules:
            return fallback, self.rules[fallback]
        return None


def kind_label(kind: str, t: Translator) -> str:
    pair = KIND_LABELS.get(kind)
    return t(*pair) if pair else kind


def calc_kind(calc: CalculatedField) -> str:
    """計算フィールドの種類 (LOD → 表計算 → ブール型 → 計算フィールド の順に判定)。"""
    from .rules import _strip_literals_and_comments

    formula = _strip_literals_and_comments(calc.raw_formula)
    if _LOD.search(formula):
        return KIND_LOD_CALC
    if calc.table_calc is not None or _TABLE_FUNCTION.search(formula):
        return KIND_TABLE_CALC
    if calc.datatype == "boolean":
        return KIND_BOOLEAN_CALC
    return KIND_CALC


def named_items(workbook: Workbook) -> Iterator[tuple[str, str]]:
    """(種類, 名前) を列挙する。計算フィールド・パラメーターは表示名で見る。"""
    for calc in workbook.calculated_fields:
        if calc.caption:
            yield calc_kind(calc), calc.caption
    for parameter in workbook.parameters:
        yield KIND_PARAMETER, parameter.display_name
    for sheet in workbook.worksheets:
        yield KIND_WORKSHEET, sheet.name
    for dashboard in workbook.dashboards:
        yield KIND_DASHBOARD, dashboard.name


def _fix_tools(kind: str) -> tuple[str, ...]:
    from .rules import RENAME_FIELD_TOOLS

    if kind in (KIND_WORKSHEET, KIND_DASHBOARD):
        return ("rename-sheet",)
    return RENAME_FIELD_TOOLS


def _rename_hint(kind: str, t: Translator) -> str:
    if kind in (KIND_WORKSHEET, KIND_DASHBOARD):
        return t("シート名を変更する。", "Rename the sheet.")
    return t(
        "名前を変更する (式は内部名で参照しているため、名前を変えても参照は壊れません)。",
        "Rename it (formulas refer to fields by internal name, so renaming does "
        "not break references).",
    )


def naming_conventions(
    workbook: Workbook, t: Translator, config: NamingConfig
) -> list[Finding]:
    from .rules import SEVERITY_WARNING, _make

    if not config.rules:
        return []
    findings: list[Finding] = []
    for kind, name in named_items(workbook):
        resolved = config.rule_for(kind)
        if resolved is None:
            continue
        _, rule = resolved
        if rule.pattern.search(name):
            continue
        label = kind_label(kind, t)
        mismatch = _matching_other_kind(kind, name, config)
        if mismatch is not None:
            other_label = kind_label(mismatch, t)
            findings.append(
                _make(
                    "naming-kind-mismatch",
                    SEVERITY_WARNING,
                    t("名前と中身のずれ", "Name does not match the content"),
                    name,
                    t(
                        f"名前は{other_label}の規則に合っていますが、中身は{label}です。"
                        "式を変えたときに名前が追従していない可能性があります。",
                        f"The name follows the {other_label} rule, but this is a "
                        f"{label}. The name may not have been updated when the "
                        "formula changed.",
                    ),
                    _expected(rule, t) + " " + _rename_hint(kind, t),
                    _fix_tools(kind),
                )
            )
            continue
        findings.append(
            _make(
                "naming-convention",
                SEVERITY_WARNING,
                t("命名規則に合わない名前", "Name does not follow the convention"),
                name,
                t(
                    f"{label}の命名規則に合いません。",
                    f"This {label} does not follow the naming convention.",
                )
                + " "
                + _expected(rule, t),
                _rename_hint(kind, t),
                _fix_tools(kind),
            )
        )
    return findings


def _expected(rule: NamingRule, t: Translator) -> str:
    if rule.description:
        return t(f"規則: {rule.description}", f"Rule: {rule.description}")
    return t(f"規則: {rule.pattern.pattern}", f"Rule: {rule.pattern.pattern}")


def _matching_other_kind(kind: str, name: str, config: NamingConfig) -> str | None:
    """name が自分以外の種類 (同じ規則を共有する種類は除く) の規則に合えばその種類。"""
    own = config.rule_for(kind)
    own_kind = own[0] if own else kind
    family = _SHEET_KINDS if kind in _SHEET_KINDS else _FIELD_KINDS
    for other, rule in config.rules.items():
        # フィールド同士・シート同士だけを比べる (シート名の緩い規則に
        # 計算フィールドの名前が合っても、ずれとはいえないため)
        if other in (kind, own_kind) or other not in family:
            continue
        if rule.pattern.search(name):
            return other
    return None


def naming_whitespace(workbook: Workbook, t: Translator) -> list[Finding]:
    from .rules import SEVERITY_INFO, _make

    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for kind, name in named_items(workbook):
        problems: list[str] = []
        if name != name.strip(" \t" + _FULL_WIDTH_SPACE):
            problems.append(t("前後に空白", "leading or trailing spaces"))
        if _SPACE_RUN.search(name):
            problems.append(t("連続した空白", "repeated spaces"))
        if _FULL_WIDTH_SPACE in name:
            problems.append(t("全角スペース", "full-width spaces"))
        if not problems or (kind, name) in seen:
            continue
        seen.add((kind, name))
        findings.append(
            _make(
                "naming-whitespace",
                SEVERITY_INFO,
                t("名前の空白", "Whitespace in a name"),
                name,
                t(
                    f"{kind_label(kind, t)}の名前に" + "・".join(problems) + "があります。",
                    f"This {kind_label(kind, t)} name has " + ", ".join(problems) + ".",
                ),
                _rename_hint(kind, t),
                _fix_tools(kind),
            )
        )
    return findings
