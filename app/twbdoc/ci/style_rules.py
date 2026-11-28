"""書式の一貫性のルール (フォントサイズ・フォント名のばらつき)。

ワークブックの TextStyle (parsers/text_styles.py) だけを入力にする。
基準は .twbdoc.json の "style" で決められ、決めていなければワークブック内の
多数派を基準にする。
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..i18n import Translator
from ..model import TextStyle, Workbook
from ..parsers.text_styles import (
    OWNER_DASHBOARD,
    OWNER_WORKSHEET,
    SOURCE_FORMAT,
)

if TYPE_CHECKING:  # 循環 import 回避
    from .rules import Finding

FORMAT_PREFIX = "format:"

# 役割のキー → (日本語, 英語)。キーは .twbdoc.json の style.font_sizes でも使う。
# ここに無い役割 (マークラベル・ダッシュボードのテキスト等) は意図して
# サイズを変えることが多いため、既定ではばらつきを判定しない。
ROLE_LABELS: dict[str, tuple[str, str]] = {
    "worksheet-title": ("シートのタイトル", "worksheet title"),
    "dashboard-title": ("ダッシュボードのタイトル", "dashboard title"),
    "tooltip": ("ツールヒント", "tooltip"),
    "caption": ("キャプション", "caption"),
    "format:worksheet": ("ワークシートの書式", "worksheet format"),
    "format:title": ("タイトルの書式", "title format"),
    "format:axis-title": ("軸タイトルの書式", "axis title format"),
    "format:header": ("ヘッダーの書式", "header format"),
    "format:legend-title": ("凡例タイトルの書式", "legend title format"),
    "format:tooltip": ("ツールヒントの書式", "tooltip format"),
    "format:field-labels": ("フィールドラベルの書式", "field label format"),
    "format:quick-filter-title": ("フィルターのタイトルの書式", "filter title format"),
}
DEFAULT_SIZE_ROLES = frozenset(ROLE_LABELS)
DEFAULT_MAX_FONT_FAMILIES = 3

# フォント名の末尾の太さ (Tableau Book / Tableau Medium 等は同じファミリーとみなす)
_WEIGHT_SUFFIX = re.compile(
    r"\s+(thin|extra\s*light|light|book|regular|normal|medium|semi\s*bold|"
    r"demi\s*bold|bold|extra\s*bold|black|heavy)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class StyleConfig:
    """.twbdoc.json の "style"。"""

    font_families: tuple[str, ...] = ()
    font_sizes: dict[str, float] = field(default_factory=dict)
    max_font_families: int = DEFAULT_MAX_FONT_FAMILIES


def role_key(style: TextStyle) -> str:
    return f"{FORMAT_PREFIX}{style.role}" if style.source == SOURCE_FORMAT else style.role


def role_label(key: str, t: Translator) -> str:
    pair = ROLE_LABELS.get(key)
    return t(*pair) if pair else key


def font_family(name: str) -> str:
    """'Tableau Medium' -> 'tableau' のように太さを除いた小文字のファミリー名。"""
    base = name.strip()
    while True:
        stripped = _WEIGHT_SUFFIX.sub("", base)
        if stripped == base or not stripped:
            break
        base = stripped
    return base.lower()


def _format_size(size: float) -> str:
    return f"{size:g}pt"


def _owner_label(style: TextStyle, t: Translator) -> str:
    return style.owner or t("ワークブック全体", "Whole workbook")


def inconsistent_font_sizes(
    workbook: Workbook, t: Translator, config: StyleConfig
) -> list[Finding]:
    from .rules import SEVERITY_INFO, SEVERITY_WARNING, _make

    by_role: dict[str, dict[str, float]] = defaultdict(dict)
    for style in workbook.text_styles:
        if style.font_size is None:
            continue
        if style.owner_kind not in (OWNER_WORKSHEET, OWNER_DASHBOARD):
            continue
        key = role_key(style)
        if key not in DEFAULT_SIZE_ROLES and key not in config.font_sizes:
            continue
        # 同じシートに同じ役割が複数ある場合 (ペインごとのツールヒント等) は最初の 1 つ
        by_role[key].setdefault(_owner_label(style, t), style.font_size)

    findings: list[Finding] = []
    category = t("フォントサイズのばらつき", "Inconsistent font size")
    tools = ("format-worksheets",)
    for key in sorted(by_role):
        owners = by_role[key]
        label = role_label(key, t)
        standard = config.font_sizes.get(key)
        if standard is not None:
            for owner, size in sorted(owners.items()):
                if size == standard:
                    continue
                findings.append(
                    _make(
                        "inconsistent-font-size",
                        SEVERITY_WARNING,
                        category,
                        f"{owner} / {label}",
                        t(
                            f"{label}が {_format_size(size)} です "
                            f"(チームの基準は {_format_size(standard)})。",
                            f"The {label} is {_format_size(size)} "
                            f"(the team standard is {_format_size(standard)}).",
                        ),
                        t(
                            f"{label}を {_format_size(standard)} にそろえる。",
                            f"Set the {label} to {_format_size(standard)}.",
                        ),
                        tools,
                    )
                )
            continue
        counts = Counter(owners.values())
        if len(counts) < 2:
            continue
        ranked = counts.most_common()
        mode, mode_count = ranked[0]
        if mode_count >= 2 and mode_count > ranked[1][1]:
            for owner, size in sorted(owners.items()):
                if size == mode:
                    continue
                findings.append(
                    _make(
                        "inconsistent-font-size",
                        SEVERITY_INFO,
                        category,
                        f"{owner} / {label}",
                        t(
                            f"{label}が {_format_size(size)} です "
                            f"(このワークブックでは {_format_size(mode)} が "
                            f"{mode_count} か所で使われています)。",
                            f"The {label} is {_format_size(size)} "
                            f"({_format_size(mode)} is used in {mode_count} "
                            "places in this workbook).",
                        ),
                        t(
                            f"意図した違いでなければ {_format_size(mode)} にそろえる。"
                            "基準は .twbdoc.json の style.font_sizes で決められます。",
                            f"Unless intended, set it to {_format_size(mode)}. "
                            "Set the standard in style.font_sizes in .twbdoc.json.",
                        ),
                        tools,
                    )
                )
        else:
            # 多数派が決まらない (2 か所で違う、同数で割れている) ときは役割単位で 1 件
            usage = ", ".join(
                f"{_format_size(size)} ({', '.join(sorted(o for o, s in owners.items() if s == size))})"
                for size, _ in sorted(counts.items())
            )
            findings.append(
                _make(
                    "inconsistent-font-size",
                    SEVERITY_INFO,
                    category,
                    label,
                    t(
                        f"{label}のサイズがそろっていません: {usage}",
                        f"The {label} sizes differ: {usage}",
                    ),
                    t(
                        "どれかにそろえる。基準は .twbdoc.json の style.font_sizes で決められます。",
                        "Pick one size. Set the standard in style.font_sizes in .twbdoc.json.",
                    ),
                    tools,
                )
            )
    return findings


def inconsistent_font_families(
    workbook: Workbook, t: Translator, config: StyleConfig
) -> list[Finding]:
    from .rules import SEVERITY_INFO, SEVERITY_WARNING, _make

    usage: dict[str, list[str]] = defaultdict(list)  # フォント名 → 使っている場所
    for style in workbook.text_styles:
        for name in style.font_names:
            owner = _owner_label(style, t)
            if owner not in usage[name]:
                usage[name].append(owner)
    if not usage:
        return []

    findings: list[Finding] = []
    category = t("フォントのばらつき", "Inconsistent font")
    tools = ("format-worksheets",)

    # 1. 大文字・小文字だけ違う表記ゆれ
    spellings: dict[str, list[str]] = defaultdict(list)
    for name in usage:
        spellings[name.lower()].append(name)
    for variants in spellings.values():
        if len(variants) < 2:
            continue
        variants.sort()
        findings.append(
            _make(
                "inconsistent-font-family",
                SEVERITY_INFO,
                category,
                " / ".join(variants),
                t(
                    "同じフォントの表記が大文字・小文字で違います: " + ", ".join(variants),
                    "The same font is spelled with different case: " + ", ".join(variants),
                ),
                t("表記をそろえる。", "Use one spelling."),
                tools,
            )
        )

    # 2. 許可リストにないフォント / ファミリーが多すぎる
    if config.font_families:
        allowed = {name.lower() for name in config.font_families}
        for name in sorted(usage):
            if name.lower() in allowed:
                continue
            places = usage[name]
            shown = ", ".join(places[:5]) + (t(" ほか", " and more") if len(places) > 5 else "")
            findings.append(
                _make(
                    "inconsistent-font-family",
                    SEVERITY_WARNING,
                    category,
                    name,
                    t(
                        f"チームで決めたフォント以外が使われています ({shown})。",
                        f"This font is not in the team's list ({shown}).",
                    ),
                    t(
                        "許可されたフォント (" + ", ".join(config.font_families) + ") に変える。",
                        "Change it to an allowed font (" + ", ".join(config.font_families) + ").",
                    ),
                    tools,
                )
            )
    else:
        families: dict[str, list[str]] = defaultdict(list)
        for name in usage:
            families[font_family(name)].append(name)
        if len(families) > config.max_font_families:
            listed = ", ".join(sorted(min(names) for names in families.values()))
            findings.append(
                _make(
                    "inconsistent-font-family",
                    SEVERITY_INFO,
                    category,
                    t("ワークブック全体", "Whole workbook"),
                    t(
                        f"{len(families)} 種類のフォントが使われています: {listed}",
                        f"{len(families)} font families are used: {listed}",
                    ),
                    t(
                        "使うフォントを絞る。.twbdoc.json の style.font_families で決められます。",
                        "Use fewer fonts. Set the list in style.font_families in .twbdoc.json.",
                    ),
                    tools,
                )
            )
    return findings
