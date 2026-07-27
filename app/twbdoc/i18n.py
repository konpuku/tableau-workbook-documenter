"""出力言語の判定と切り替え。

日本語 (ja) と英語 (en) に対応する。文言は「日本語, 英語」のペアで
使用箇所に直接書き、Translator が実行環境に応じて選択する。
用語は Tableau 公式ヘルプ (help.tableau.com) の表記に合わせる。
"""

from __future__ import annotations

import locale
import os

JAPANESE = "ja"
ENGLISH = "en"
AUTO = "auto"

LANGUAGE_CHOICES = (AUTO, JAPANESE, ENGLISH)

# 言語を明示指定する環境変数 (自動判定より優先)
LANG_ENV_VAR = "TWBDOC_LANG"

# Windows の言語 ID (LANGID) の下位 10 bit が日本語を示す値
_LANG_JAPANESE_PRIMARY = 0x11


class Translator:
    """言語に応じて文言を選ぶ。

    使い方:
        t = Translator("en")
        t("計算フィールド", "Calculated Field")  -> "Calculated Field"
    """

    def __init__(self, language: str = JAPANESE) -> None:
        self.language = ENGLISH if language == ENGLISH else JAPANESE

    def __call__(self, japanese: str, english: str) -> str:
        return english if self.language == ENGLISH else japanese

    @property
    def is_english(self) -> bool:
        return self.language == ENGLISH


JA = Translator(JAPANESE)
EN = Translator(ENGLISH)


def detect_language(override: str | None = None) -> str:
    """出力言語を決定する。

    優先順位: 明示指定 (--lang) > 環境変数 TWBDOC_LANG > 実行環境の言語。
    判定できない場合は英語とする。
    """
    explicit = _normalize(override)
    if explicit is not None:
        return explicit
    from_env = _normalize(os.environ.get(LANG_ENV_VAR))
    if from_env is not None:
        return from_env
    return _detect_from_environment()


def get_translator(override: str | None = None) -> Translator:
    """判定結果に対応する Translator を返す。"""
    return Translator(detect_language(override))


def _normalize(value: str | None) -> str | None:
    """'ja' / 'ja-JP' / 'en_US' などを ja / en に正規化する。"""
    if not value:
        return None
    lowered = value.strip().lower()
    if lowered == AUTO:
        return None
    if lowered.startswith(JAPANESE):
        return JAPANESE
    if lowered.startswith(ENGLISH):
        return ENGLISH
    return None


def _detect_from_environment() -> str:
    """Windows の表示言語 (無ければロケール環境変数) から判定する。"""
    windows_language = _detect_windows_ui_language()
    if windows_language is not None:
        return windows_language
    for variable in ("LC_ALL", "LC_MESSAGES", "LANG"):
        normalized = _normalize(os.environ.get(variable))
        if normalized is not None:
            return normalized
    try:
        current = locale.getlocale()[0]
    except ValueError:  # 未設定のロケールでは例外になることがある
        current = None
    return _normalize(current) or ENGLISH


def _detect_windows_ui_language() -> str | None:
    """Windows の表示言語を取得する (Windows 以外・失敗時は None)。"""
    try:
        import ctypes

        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except (AttributeError, OSError, ImportError):
        return None
    if not langid:
        return None
    return JAPANESE if (langid & 0x3FF) == _LANG_JAPANESE_PRIMARY else ENGLISH
