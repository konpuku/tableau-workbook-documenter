"""CI チェックの設定 (.twbdoc.json)。

Python 3.10 でも動くよう、TOML ではなく JSON を使う。

例:
    {
      "rules": {
        "orphan-worksheet": "off",
        "default-sheet-name": "warning"
      },
      "ignore": [
        "unused-calc:3f2a9c1b0d",
        {"rule": "unused-calc", "target": "検証用フラグ"}
      ],
      "fail_on": "warning"
    }

rules はルール ID → 重要度 (error / warning / info) または off。
ignore は Finding の安定 ID、または rule と target の組で指定する。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable

from ..errors import InvalidFileError
from ..i18n import JA, Translator
from .rules import SEVERITY_ORDER, Finding
from .naming_rules import KIND_LABELS, PRESETS, NamingConfig, NamingRule
from .style_rules import FORMAT_PREFIX, ROLE_LABELS, StyleConfig

CONFIG_FILE_NAME = ".twbdoc.json"
OFF = "off"
FAIL_ON_CHOICES = ("error", "warning", "info", "never")


@dataclass(frozen=True)
class CheckConfig:
    severities: dict[str, str] = field(default_factory=dict)
    ignore_ids: frozenset[str] = frozenset()
    ignore_pairs: frozenset[tuple[str, str]] = frozenset()
    fail_on: str = "error"
    style: StyleConfig = field(default_factory=StyleConfig)
    naming: NamingConfig = field(default_factory=NamingConfig)

    def apply(self, findings: Iterable[Finding]) -> list[Finding]:
        result: list[Finding] = []
        for finding in findings:
            if finding.id in self.ignore_ids:
                continue
            if (finding.rule, finding.target) in self.ignore_pairs:
                continue
            override = self.severities.get(finding.rule)
            if override == OFF:
                continue
            if override:
                finding = replace(finding, severity=override)
            result.append(finding)
        return result


def should_fail(findings: Iterable[Finding], fail_on: str) -> bool:
    """fail_on 以上の重要度の検出があれば True。"""
    if fail_on == "never":
        return False
    threshold = SEVERITY_ORDER[fail_on]
    return any(SEVERITY_ORDER.get(f.severity, 9) <= threshold for f in findings)


def find_config(start: Path) -> Path | None:
    """start から親フォルダへ遡って .twbdoc.json を探す。"""
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for directory in (current, *current.parents):
        candidate = directory / CONFIG_FILE_NAME
        if candidate.is_file():
            return candidate
    return None


def load_config(path: Path | None, t: Translator = JA) -> CheckConfig:
    if path is None:
        return CheckConfig()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise InvalidFileError(
            t(
                f"設定ファイルを読み込めません: {path} ({error})",
                f"Cannot read the config file: {path} ({error})",
            )
        ) from error
    if not isinstance(data, dict):
        raise InvalidFileError(
            t(
                f"設定ファイルの形式が不正です: {path}",
                f"Invalid config file: {path}",
            )
        )
    severities: dict[str, str] = {}
    for rule, value in (data.get("rules") or {}).items():
        value = str(value).lower()
        if value != OFF and value not in SEVERITY_ORDER:
            raise InvalidFileError(
                t(
                    f"重要度の指定が不正です ({rule}: {value})",
                    f"Invalid severity ({rule}: {value})",
                )
            )
        severities[str(rule)] = value
    ignore_ids: set[str] = set()
    ignore_pairs: set[tuple[str, str]] = set()
    for entry in data.get("ignore") or []:
        if isinstance(entry, str):
            ignore_ids.add(entry)
        elif isinstance(entry, dict) and "rule" in entry and "target" in entry:
            ignore_pairs.add((str(entry["rule"]), str(entry["target"])))
    fail_on = str(data.get("fail_on", "error")).lower()
    if fail_on not in FAIL_ON_CHOICES:
        fail_on = "error"
    return CheckConfig(
        severities=severities,
        ignore_ids=frozenset(ignore_ids),
        ignore_pairs=frozenset(ignore_pairs),
        fail_on=fail_on,
        style=_load_style(data.get("style"), t),
        naming=_load_naming(data.get("naming"), t),
    )


def _load_naming(data: object, t: Translator) -> NamingConfig:
    """"naming": {"preset": "prefix", "<種類>": {"pattern": 正規表現, "description": 説明} | 正規表現}"""
    if data is None:
        return NamingConfig()
    if not isinstance(data, dict):
        raise InvalidFileError(t("naming の形式が不正です", "Invalid naming section"))
    rules: dict[str, NamingRule] = {}
    preset = data.get("preset")
    if preset is not None:
        if preset not in PRESETS:
            raise InvalidFileError(
                t(
                    f"naming.preset が不正です: {preset} (使えるもの: {', '.join(PRESETS)})",
                    f"Unknown naming.preset: {preset} (available: {', '.join(PRESETS)})",
                )
            )
        for kind, (pattern, description) in PRESETS[preset].items():
            rules[kind] = NamingRule(re.compile(pattern), t(*description))
    for kind, value in data.items():
        if kind == "preset":
            continue
        if kind not in KIND_LABELS:
            raise InvalidFileError(
                t(
                    f"naming の種類が不正です: {kind} (使える種類: {', '.join(KIND_LABELS)})",
                    f"Unknown kind in naming: {kind} (valid kinds: {', '.join(KIND_LABELS)})",
                )
            )
        if isinstance(value, str):
            pattern, description = value, ""
        elif isinstance(value, dict) and isinstance(value.get("pattern"), str):
            pattern, description = value["pattern"], str(value.get("description", ""))
        else:
            raise InvalidFileError(
                t(
                    f"naming.{kind} は正規表現の文字列か "
                    '{"pattern": ..., "description": ...} にしてください',
                    f"naming.{kind} must be a regular expression or "
                    '{"pattern": ..., "description": ...}',
                )
            )
        try:
            rules[kind] = NamingRule(re.compile(pattern), description)
        except re.error as error:
            raise InvalidFileError(
                t(
                    f"naming.{kind} の正規表現が不正です: {pattern} ({error})",
                    f"Invalid regular expression in naming.{kind}: {pattern} ({error})",
                )
            ) from error
    return NamingConfig(rules=rules)


def _load_style(data: object, t: Translator) -> StyleConfig:
    """"style": {"font_families": [...], "font_sizes": {役割: pt}, "max_font_families": n}"""
    if data is None:
        return StyleConfig()
    if not isinstance(data, dict):
        raise InvalidFileError(t("style の形式が不正です", "Invalid style section"))
    families = data.get("font_families") or []
    if not isinstance(families, list) or not all(isinstance(f, str) for f in families):
        raise InvalidFileError(
            t("style.font_families はフォント名の配列にしてください",
              "style.font_families must be a list of font names")
        )
    sizes: dict[str, float] = {}
    for key, value in (data.get("font_sizes") or {}).items():
        if key not in ROLE_LABELS and not str(key).startswith(FORMAT_PREFIX):
            raise InvalidFileError(
                t(
                    f"style.font_sizes の役割が不正です: {key} "
                    f"(使える役割: {', '.join(ROLE_LABELS)})",
                    f"Unknown role in style.font_sizes: {key} "
                    f"(valid roles: {', '.join(ROLE_LABELS)})",
                )
            )
        try:
            size = float(value)
        except (TypeError, ValueError):
            size = 0.0
        if size <= 0:
            raise InvalidFileError(
                t(f"style.font_sizes.{key} のサイズが不正です: {value}",
                  f"Invalid size for style.font_sizes.{key}: {value}")
            )
        sizes[str(key)] = size
    max_families = data.get("max_font_families", StyleConfig().max_font_families)
    if not isinstance(max_families, int) or max_families < 1:
        raise InvalidFileError(
            t("style.max_font_families は 1 以上の整数にしてください",
              "style.max_font_families must be an integer of 1 or more")
        )
    return StyleConfig(
        font_families=tuple(families),
        font_sizes=sizes,
        max_font_families=max_families,
    )
