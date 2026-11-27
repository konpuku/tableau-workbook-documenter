"""2 つの Workbook の構造差分と、検出結果の新規 / 解消の差分。

ライブ監視で「直前の状態から何が変わったか」を示すために使う。
比較はモデルから作る軽量スナップショット (dict) 同士で行う。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from ..i18n import JA, Translator
from ..model import Workbook
from .rules import Finding

ADDED = "added"
REMOVED = "removed"
CHANGED = "changed"


@dataclass(frozen=True)
class Change:
    kind: str  # added / removed / changed
    category: str  # calc / parameter / worksheet / dashboard / datasource / action
    target: str
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def snapshot(workbook: Workbook) -> dict[str, dict[str, dict]]:
    """差分比較用に、主要要素を名前 → 属性の辞書へ落とす。"""
    return {
        "datasource": {
            ds.name: {
                "caption": ds.caption,
                "fields": len(ds.fields),
                "connection": ds.connection_class,
                "filters": len(ds.ds_filters),
            }
            for ds in workbook.datasources
        },
        "calc": {
            calc.name: {
                "caption": calc.caption,
                "formula": calc.raw_formula,
                "comment": calc.comment,
            }
            for calc in workbook.calculated_fields
        },
        "parameter": {
            p.name: {
                "caption": p.caption,
                "value": p.current_value,
                "domain": p.domain_type,
                "members": [m.value for m in p.members],
            }
            for p in workbook.parameters
        },
        "worksheet": {
            sheet.name: {
                "columns": sorted(sheet.used_columns),
                "filters": sorted(f.column_ref for f in sheet.filters),
                "datasources": sorted(sheet.datasources),
            }
            for sheet in workbook.worksheets
        },
        "dashboard": {
            dash.name: {
                "sheets": sorted(
                    s.name for s in workbook.worksheets if dash.name in s.dashboards
                ),
            }
            for dash in workbook.dashboards
        },
        "action": {
            action.name or action.caption: {
                "caption": action.caption,
                "kind": action.kind,
                "target": action.target,
            }
            for action in workbook.actions
        },
    }


def diff_snapshots(
    before: dict[str, dict[str, dict]] | None,
    after: dict[str, dict[str, dict]],
    labels: dict[str, str] | None = None,
    t: Translator = JA,
) -> tuple[Change, ...]:
    """スナップショット間の差分。before が None (初回) なら空を返す。

    labels は内部名 → 表示名 (計算フィールドの caption など)。
    """
    if before is None:
        return ()
    labels = labels or {}
    changes: list[Change] = []
    for category, items in after.items():
        previous = before.get(category, {})
        for name in items.keys() - previous.keys():
            changes.append(Change(ADDED, category, labels.get(name, name)))
        for name in previous.keys() - items.keys():
            changes.append(Change(REMOVED, category, labels.get(name, name)))
        for name in items.keys() & previous.keys():
            if items[name] == previous[name]:
                continue
            changed_keys = [
                key
                for key in items[name]
                if items[name].get(key) != previous[name].get(key)
            ]
            changes.append(
                Change(
                    CHANGED,
                    category,
                    labels.get(name, name),
                    _describe(category, changed_keys, previous[name], items[name], t),
                )
            )
    changes.sort(key=lambda c: (c.category, c.kind, c.target))
    return tuple(changes)


def _describe(
    category: str, keys: list[str], before: dict, after: dict, t: Translator
) -> str:
    parts: list[str] = []
    for key in keys:
        if key == "formula":
            parts.append(t("計算式を変更", "formula changed"))
        elif key == "columns":
            added = set(after[key]) - set(before[key])
            removed = set(before[key]) - set(after[key])
            if added:
                parts.append(t("フィールド追加: ", "fields added: ") + ", ".join(sorted(added)))
            if removed:
                parts.append(t("フィールド削除: ", "fields removed: ") + ", ".join(sorted(removed)))
        elif key == "sheets":
            added = set(after[key]) - set(before[key])
            removed = set(before[key]) - set(after[key])
            if added:
                parts.append(t("シート配置: ", "sheets placed: ") + ", ".join(sorted(added)))
            if removed:
                parts.append(t("シート除去: ", "sheets removed: ") + ", ".join(sorted(removed)))
        else:
            parts.append(f"{key}: {before.get(key)!r} → {after.get(key)!r}")
    return "; ".join(parts)


def labels_for(workbook: Workbook) -> dict[str, str]:
    labels = {calc.name: calc.display_name for calc in workbook.calculated_fields}
    labels.update({p.name: p.display_name for p in workbook.parameters})
    labels.update({ds.name: ds.display_name for ds in workbook.datasources})
    return labels


def diff_findings(
    before: Iterable[Finding] | None, after: Iterable[Finding]
) -> tuple[tuple[Finding, ...], tuple[Finding, ...]]:
    """(新規の検出, 解消した検出) を返す。before が None なら新規は空。"""
    after = tuple(after)
    if before is None:
        return (), ()
    before = tuple(before)
    before_ids = {f.id for f in before}
    after_ids = {f.id for f in after}
    return (
        tuple(f for f in after if f.id not in before_ids),
        tuple(f for f in before if f.id not in after_ids),
    )
