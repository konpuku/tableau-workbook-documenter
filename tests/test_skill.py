"""Tableau Agent スキル (app/skills/twbdoc-ci/SKILL.md) の内容のテスト。"""

from __future__ import annotations

import re
from pathlib import Path

from twbdoc.ci.rules import RULE_IDS

SKILL = Path(__file__).resolve().parents[1] / "app" / "skills" / "twbdoc-ci" / "SKILL.md"


def _fix_table_rows() -> dict[str, str]:
    """修正方法の表の 1 列目 (ルール ID) → 行全体。"""
    rows: dict[str, str] = {}
    for line in SKILL.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        for rule in re.findall(r"`([a-z-]+)`", line.split("|")[1]):
            rows[rule] = line
    return rows


def test_全ルールの直し方が書かれている() -> None:
    assert set(RULE_IDS) <= set(_fix_table_rows())


def test_既存の修正に_author_calc_を案内しない() -> None:
    # author-calc は新しい計算フィールドを作るツール。既存の修正は apply-datasource (#38)
    text = SKILL.read_text(encoding="utf-8")
    assert "apply-datasource" in text and "get-datasource-xml" in text
    for rule, row in _fix_table_rows().items():
        if rule == "magic-number":  # 名前付きの定数を新しく作るときだけ使う
            continue
        assert "author-calc" not in row, rule


def test_本文に区切り線の_dash_を使わない() -> None:
    # Tableau Agent の skill-creator の規則: --- は frontmatter の開始と終了だけ
    lines = SKILL.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---"
    assert [i for i, line in enumerate(lines) if line.strip() == "---"][1:] == [
        lines.index("---", 1)
    ]
