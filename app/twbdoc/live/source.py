"""ライブ監視の入力ソース。

- StudioSource: Tableau Studio の External Client API をポーリングし、
  未保存を含む編集中のワークブック XML を取得する。
- FileSource  : 保存済みの .twb / .twbx を mtime で監視する (Studio が使えない場合)。

どちらも poll() で「前回から XML が変わったときだけ」Snapshot を返す。
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ..i18n import JA, Translator
from ..loader import read_workbook_xml_bytes
from .studio import StudioClient, StudioError, connect


@dataclass(frozen=True)
class Snapshot:
    xml: bytes
    title: str
    source: str  # "studio" / "file"
    location: str | None = None
    unsaved: bool = False
    diagnostics: dict | None = None
    sheet_names: dict[str, str] = field(default_factory=dict)
    fetched_at: datetime = field(default_factory=datetime.now)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.xml).hexdigest()


class Source(Protocol):
    name: str

    def poll(self) -> Snapshot | None: ...

    def status(self) -> dict: ...


class StudioSource:
    """Studio をポーリングする。

    /v0/workbook (軽量) は毎回、/v0/workbook/document (重い) は
    シート構成・未保存フラグが変わったとき、または doc_interval 経過ごとに取る。
    計算式の編集はシート一覧に現れないため、定期取得で拾う。
    """

    name = "studio"

    def __init__(
        self,
        workbook: str | None = None,
        doc_interval: float = 5.0,
        discovery_dir: Path | None = None,
        client: StudioClient | None = None,
    ) -> None:
        self.workbook = workbook
        self.doc_interval = doc_interval
        self.discovery_dir = discovery_dir
        self._client = client
        self._last_fingerprint: tuple | None = None
        self._last_doc_at = 0.0
        self._last_digest: str | None = None
        self._connected = False
        self._last_info: dict = {}
        self._last_error = ""

    def _ensure_client(self) -> StudioClient:
        if self._client is None:
            self._client = connect(self.discovery_dir, self.workbook)
        return self._client

    def poll(self) -> Snapshot | None:
        try:
            client = self._ensure_client()
            info = client.workbook()
        except StudioError as error:
            self._client = None
            self._connected = False
            self._last_error = str(error)
            raise
        self._connected = True
        self._last_error = ""
        self._last_info = info
        sheets = tuple(
            sorted(
                (s.get("id", ""), s.get("name", ""))
                for kind in ("worksheets", "dashboards", "storyboards")
                for s in info.get(kind, []) or []
            )
        )
        fingerprint = (
            info.get("title"),
            info.get("location"),
            bool(info.get("unsavedChanges")),
            sheets,
        )
        now = time.monotonic()
        due = now - self._last_doc_at >= self.doc_interval
        if fingerprint == self._last_fingerprint and not due:
            return None
        self._last_fingerprint = fingerprint
        self._last_doc_at = now
        xml = client.document()
        digest = hashlib.sha256(xml).hexdigest()
        if digest == self._last_digest:
            return None
        self._last_digest = digest
        try:
            diagnostics = client.diagnostics()
        except StudioError:
            diagnostics = None
        return Snapshot(
            xml=xml,
            title=str(info.get("title") or "workbook"),
            source=self.name,
            location=info.get("location"),
            unsaved=bool(info.get("unsavedChanges")),
            diagnostics=diagnostics,
            sheet_names={
                s.get("id", ""): s.get("name", "")
                for s in info.get("worksheets", []) or []
            },
        )

    def status(self) -> dict:
        return {
            "source": self.name,
            "connected": self._connected,
            "title": self._last_info.get("title"),
            "location": self._last_info.get("location"),
            "unsaved": bool(self._last_info.get("unsavedChanges")),
            "error": self._last_error,
        }


class FileSource:
    """保存済みファイルを監視する。未保存の変更は検知できない。"""

    name = "file"

    def __init__(self, path: Path, t: Translator = JA) -> None:
        self.path = path
        self.t = t
        self._last_mtime: float | None = None
        self._last_digest: str | None = None
        self._last_error = ""

    def poll(self) -> Snapshot | None:
        try:
            mtime = self.path.stat().st_mtime
        except OSError as error:
            self._last_error = str(error)
            raise
        if mtime == self._last_mtime:
            return None
        self._last_mtime = mtime
        xml = read_workbook_xml_bytes(self.path, self.t)
        digest = hashlib.sha256(xml).hexdigest()
        if digest == self._last_digest:
            return None
        self._last_digest = digest
        self._last_error = ""
        return Snapshot(
            xml=xml,
            title=self.path.stem,
            source=self.name,
            location=str(self.path),
        )

    def status(self) -> dict:
        return {
            "source": self.name,
            "connected": not self._last_error,
            "title": self.path.stem,
            "location": str(self.path),
            "unsaved": False,
            "error": self._last_error,
        }
