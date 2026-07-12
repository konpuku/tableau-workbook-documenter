"""Tableau のフィールド参照文字列を可読化する共通ユーティリティ。

twb 内では '[データソース].[usr:Calculation_xxx:qk]' や
'[none:Category:nk]'、'[sum:Profit:qk]' のような参照形式が使われる。
"""

from __future__ import annotations

import re

_FIELD_REF_PATTERN = re.compile(r"\[([^\[\]]+)\]")
_DERIVATION_PATTERN = re.compile(r"^([a-z]+):(.+?)(?::[a-z]+)?$")

DERIVATION_LABELS = {
    "sum": "合計",
    "avg": "平均",
    "min": "最小",
    "max": "最大",
    "cnt": "個数",
    "ctd": "個別カウント",
    "med": "中央値",
    "yr": "年",
    "qr": "四半期",
    "mn": "月",
    "my": "年月",
    "dy": "日",
    "usr": "",
    "none": "",
    "attr": "属性",
}

SPECIAL_FIELD_LABELS = {
    ":Measure Names": "メジャーネーム",
    ":Measure Values": "メジャーバリュー",
}


def humanize_field_ref(ref: str, caption_map: dict[str, str]) -> str:
    """フィールド参照を人間が読める名前に変換する。

    例: '[Sample - Superstore].[usr:Calculation_100:qk]' -> '利益率'
        '[sum:Profit:qk]' -> 'Profit (合計)'
    """
    tokens = _FIELD_REF_PATTERN.findall(ref)
    token = tokens[-1] if tokens else ref
    special = SPECIAL_FIELD_LABELS.get(token)
    if special is not None:
        return special
    derivation, base = split_derivation(token)
    display = caption_map.get(f"[{base}]", f"[{base}]").strip("[]")
    label = DERIVATION_LABELS.get(derivation, derivation)
    if label:
        return f"{display} ({label})"
    return display


def split_derivation(token: str) -> tuple[str, str]:
    """'sum:Profit:qk' -> ('sum', 'Profit')。装飾がなければ ('', token)。"""
    match = _DERIVATION_PATTERN.match(token)
    if match is None:
        return "", token
    return match.group(1), match.group(2)


def find_referenced_names(formula: str, known_names: frozenset[str]) -> tuple[str, ...]:
    """数式内で参照されている既知の内部名 ('[xxx]' 形式) を出現順・重複なしで返す。"""
    found: list[str] = []
    for token in _FIELD_REF_PATTERN.findall(formula):
        name = f"[{token}]"
        if name in known_names and name not in found:
            found.append(name)
    return tuple(found)
