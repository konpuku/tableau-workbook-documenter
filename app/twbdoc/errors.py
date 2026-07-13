"""twbdoc の独自例外定義。"""


class TwbDocError(Exception):
    """twbdoc の全エラーの基底クラス。"""


class InvalidFileError(TwbDocError):
    """入力ファイルが不正な場合のエラー (存在しない・拡張子不正・ZIP破損など)。"""


class ParseError(TwbDocError):
    """XML の解析に失敗した場合のエラー。"""
