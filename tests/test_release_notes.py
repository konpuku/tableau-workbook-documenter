"""リリースノート (.github/release-notes/<タグ>.md) の形式検査。

.github/workflows/release.yml は、タグと同じ名前のファイルを探し、1 行目の「# 」見出しを
リリースのタイトル、2 行目以降を本文として GitHub Release を作る。
ファイル名や見出しが崩れていると、自動生成のノートに切り替わったり、
タイトルが本文に入ったりするため、ここで検査する。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
NOTES_DIR = ROOT_DIR / ".github" / "release-notes"
TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+$")

NOTE_FILES = sorted(NOTES_DIR.glob("*.md")) if NOTES_DIR.is_dir() else []


@pytest.mark.parametrize("path", NOTE_FILES, ids=lambda p: p.name)
class TestReleaseNotes:
    def test_ファイル名がタグの形式(self, path: Path) -> None:
        assert TAG_PATTERN.match(path.stem), (
            f"{path.name}: ファイル名は v<major>.<minor>.<patch>.md にしてください"
        )

    def test_1_行目がタグで始まる見出し(self, path: Path) -> None:
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        assert first_line.startswith(f"# {path.stem}"), (
            f"{path.name}: 1 行目は「# {path.stem} <タイトル>」の見出しにしてください"
        )

    def test_本文がある(self, path: Path) -> None:
        body = path.read_text(encoding="utf-8").splitlines()[1:]
        assert "".join(body).strip(), f"{path.name}: 2 行目以降に本文を書いてください"


def test_リリースノートのフォルダがある() -> None:
    assert NOTE_FILES, ".github/release-notes/ にリリースノートがありません"
