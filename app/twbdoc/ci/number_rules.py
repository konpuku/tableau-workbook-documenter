"""直書きの数値 (マジックナンバー) のルール。

- magic-number: 比較 (> / = / <= など) に直書きされた数値がある計算フィールド。
                同じ数値が 2 つ以上の計算式の比較に出てくる場合は「警告」に上げる
                (しきい値を変えるときに直し忘れる恐れがあるため)。

対象は「比較のすぐ隣にある数値」だけにする。関数の引数 (SPLIT の何番目、
LEFT の文字数、ROUND の桁数、DATEADD の量、MAKEPOINT の座標など) や
掛け算・割り算 (丸め・単位換算) は、手元のワークブックで調べるとほぼ
しきい値ではなかったため対象外。0 / 1 / -1 / 100、表計算の位置
(INDEX() / SIZE() / FIRST() / LAST()) との比較、パラメーターとの比較
([Parameters].[選択] = 2 はリストの選択肢の番号で、しきい値ではない) も対象外。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterator

from ..i18n import Translator
from ..model import CalculatedField, Workbook

if TYPE_CHECKING:  # 循環 import 回避
    from .rules import Finding

# 指摘しない数値 (.twbdoc.json の magic_numbers.allow で追加できる)
DEFAULT_ALLOWED = frozenset({0.0, 1.0, -1.0, 100.0})
# 4 桁の整数がこの範囲なら年とみなし、相対日付の書き方も提案する
YEAR_RANGE = (1900, 2100)
# 同じ数値がこの数以上の計算式に出てきたら警告にする
REPEAT_THRESHOLD = 2
# メッセージに並べる「ほかの計算式」の上限
_MAX_OTHERS = 5

_COMPARISON = frozenset({"<", ">", "<=", ">=", "=", "==", "!=", "<>"})
# 表計算の位置を返す関数。これとの比較はしきい値ではない
_POSITION_FUNCTIONS = frozenset({"INDEX", "SIZE", "FIRST", "LAST"})
# 直後の数値を単項マイナスにできる直前のトークン
_KEYWORDS = frozenset(
    {"IF", "THEN", "ELSE", "ELSEIF", "WHEN", "CASE", "AND", "OR", "NOT", "RETURN"}
)

_TOKEN = re.compile(
    r"""
    (?P<ref>\[[^\]]*\](?:\.\[[^\]]*\])?)      # フィールド参照
  | (?P<date>\#[^#]*\#)                      # 日付リテラル
  | (?P<word>[A-Za-z_]\w*)                   # 関数名・キーワード
  | (?P<num>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)
  | (?P<op><=|>=|<>|!=|==|[-+*/%^<>=])
  | (?P<punct>[(),{}:])
  | (?P<other>\S)
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class MagicNumberConfig:
    # 既定の対象外 (0 / 1 / -1 / 100) に加えて指摘しない数値
    allow: frozenset[float] = frozenset()

    def allowed(self, value: float) -> bool:
        return value in DEFAULT_ALLOWED or value in self.allow


@dataclass(frozen=True)
class _Token:
    kind: str
    text: str
    # ")" のときに閉じた関数名 (大文字)。位置関数との比較の判定に使う
    closes: str = ""


def _tokens(formula: str) -> list[_Token]:
    from .rules import _strip_literals_and_comments

    tokens: list[_Token] = []
    calls: list[str] = []
    for match in _TOKEN.finditer(_strip_literals_and_comments(formula)):
        kind = match.lastgroup or "other"
        text = match.group()
        if text == "(":
            previous = tokens[-1] if tokens else None
            calls.append(previous.text.upper() if previous and previous.kind == "word" else "")
            tokens.append(_Token("punct", text))
        elif text == ")":
            tokens.append(_Token("punct", text, calls.pop() if calls else ""))
        else:
            tokens.append(_Token(kind, text))
    return tokens


def _is_operand_start(token: _Token | None) -> bool:
    """この直後に来る "-" が単項マイナス (負の数) になる位置か。"""
    if token is None:
        return True
    if token.kind == "op" or token.text in ("(", ",", "{", ":"):
        return True
    return token.kind == "word" and token.text.upper() in _KEYWORDS


def _is_expression_start(token: _Token | None) -> bool:
    """この直後から新しい式 (比較の左辺) が始まる位置か。[a] * 2 > 10 の 2 は除く。"""
    return token is None or (token.kind != "op" and _is_operand_start(token))


def _is_not_threshold_partner(token: _Token | None, closing: bool) -> bool:
    """比較の相手が表計算の位置関数かパラメーターなら True (しきい値ではない)。

    closing=True は相手が比較の左側 (トークンは ")" か参照)、False は右側
    (トークンは関数名か参照)。
    """
    if token is None:
        return False
    if token.kind == "ref":
        return token.text.startswith("[Parameters].")
    if closing:
        return token.closes in _POSITION_FUNCTIONS
    return token.kind == "word" and token.text.upper() in _POSITION_FUNCTIONS


def compared_numbers(formula: str) -> Iterator[tuple[str, float]]:
    """比較のすぐ隣に直書きされた数値を (書かれたとおりの文字列, 値) で返す。"""
    tokens = _tokens(formula)
    for index, token in enumerate(tokens):
        if token.kind != "num":
            continue
        start = index
        text = token.text
        if (
            index >= 1
            and tokens[index - 1].text == "-"
            and _is_operand_start(tokens[index - 2] if index >= 2 else None)
        ):
            start = index - 1
            text = "-" + text
        before = tokens[start - 1] if start >= 1 else None
        after = tokens[index + 1] if index + 1 < len(tokens) else None
        if before is not None and before.text in _COMPARISON:
            # [x] > 10 : 比較の相手 (演算子の左) が位置関数・パラメーターなら対象外
            if _is_not_threshold_partner(tokens[start - 2] if start >= 2 else None, True):
                continue
        elif after is not None and after.text in _COMPARISON and _is_expression_start(before):
            # 10 < [x] : 数値が比較の左側。相手が位置関数・パラメーターなら対象外
            partner = tokens[index + 2] if index + 2 < len(tokens) else None
            if _is_not_threshold_partner(partner, False):
                continue
        else:
            continue
        try:
            value = float(text)
        except ValueError:
            continue
        yield text, value


def _is_year(text: str, value: float) -> bool:
    return text.isdigit() and len(text) == 4 and YEAR_RANGE[0] <= value <= YEAR_RANGE[1]


def magic_numbers(
    workbook: Workbook, t: Translator, config: MagicNumberConfig
) -> list[Finding]:
    from .rules import SEVERITY_INFO, SEVERITY_WARNING, _make

    per_calc: list[tuple[CalculatedField, dict[float, str]]] = []
    users: dict[float, set[str]] = {}
    for calc in workbook.calculated_fields:
        numbers: dict[float, str] = {}
        for text, value in compared_numbers(calc.raw_formula):
            if config.allowed(value):
                continue
            numbers.setdefault(value, text)
            users.setdefault(value, set()).add(calc.display_name)
        if numbers:
            per_calc.append((calc, numbers))

    findings: list[Finding] = []
    for calc, numbers in per_calc:
        name = calc.display_name
        listed = ", ".join(numbers.values())
        message = t(
            f"比較に数値が直書きされています: {listed}。しきい値の意味が読み手に伝わらず、"
            "値を変えるときに計算式を探して直す必要があります。",
            f"Numbers are hard-coded in comparisons: {listed}. Readers cannot tell "
            "what the threshold means, and changing it means finding every formula.",
        )
        severity = SEVERITY_INFO
        for value, text in numbers.items():
            others = sorted(users[value] - {name})
            if len(others) + 1 < REPEAT_THRESHOLD:
                continue
            severity = SEVERITY_WARNING
            shown = ", ".join(others[:_MAX_OTHERS])
            if len(others) > _MAX_OTHERS:
                shown += t(f" ほか {len(others) - _MAX_OTHERS} 件", f" and {len(others) - _MAX_OTHERS} more")
            message += t(
                f" {text} は次の計算式でも使われています: {shown}。変更漏れの恐れがあります。",
                f" {text} is also used in: {shown}. Some may be missed when it changes.",
            )
        hint = t(
            "利用者が値を変えたいならパラメーターに、固定の値なら名前の付いた計算フィールド"
            " (例: 目標利益率 = 0.1) にして、計算式からはその名前で参照してください。"
            "同じ数値を使う計算式はまとめて置き換えます。",
            "Turn it into a parameter if users should change it, or into a named "
            "calculated field (for example Target Margin = 0.1) if it is fixed, and refer "
            "to it by name. Replace it in every formula that uses the same number.",
        )
        years = [text for value, text in numbers.items() if _is_year(text, value)]
        if years:
            listed_years = ", ".join(years)
            hint += t(
                f" 年 ({listed_years}) は毎年書き換えが必要になります。"
                "DATEDIFF('year', [日付], TODAY()) = 0 のような相対日付か、年のパラメーターにしてください。",
                f" Years ({listed_years}) need editing every year. Use a relative date such "
                "as DATEDIFF('year', [Date], TODAY()) = 0, or a year parameter.",
            )
        findings.append(
            _make(
                "magic-number",
                severity,
                t("直書きの数値", "Hard-coded number"),
                name,
                message,
                hint,
                ("author-parameter", "author-calc", "validate-calculated-field"),
            )
        )
    return findings
