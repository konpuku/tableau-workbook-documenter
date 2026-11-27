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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Iterable

from ..errors import InvalidFileError
from ..i18n import JA, Translator
from .rules import SEVERITY_ORDER, Finding

CONFIG_FILE_NAME = ".twbdoc.json"
OFF = "off"
FAIL_ON_CHOICES = ("error", "warning", "info", "never")


@dataclass(frozen=True)
class CheckConfig:
    severities: dict[str, str] = field(default_factory=dict)
    ignore_ids: frozenset[str] = frozenset()
    ignore_pairs: frozenset[tuple[str, str]] = frozenset()
    fail_on: str = "error"

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
    )
