"""ライブ監視ループ: 取得 → 解析 → CI チェック → 差分 → 出力 → 通知。"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Union

from ..ci.config import CheckConfig
from ..ci.diff import diff_findings, diff_snapshots, labels_for, snapshot
from ..ci.report import to_json, to_report_dict
from ..ci.rules import Finding, count_by_severity, run_checks, studio_invalid_fields
from ..errors import TwbDocError
from ..i18n import JA, Translator
from ..loader import parse_workbook_xml_bytes
from ..parsers import parse_workbook
from ..renderers import render
from ..renderers.html import render_html
from .source import Snapshot, Source
from .studio import StudioError

MAX_EVENTS = 100

OutDir = Union[Path, Callable[[Snapshot], "Path | None"], None]


def default_out_dir(snap: Snapshot) -> Path:
    """保存済みならワークブックの隣の <名前>.twbdoc/、未保存ならカレントの twbdoc_live/。"""
    if snap.location:
        location = Path(snap.location)
        return location.parent / f"{location.stem}.twbdoc"
    return Path.cwd() / "twbdoc_live"


@dataclass
class LiveState:
    """ダッシュボードに配信する状態。version が変わるたびに SSE で通知する。"""

    lang: str = "ja"
    version: int = 0
    status: dict = field(default_factory=dict)
    workbook: str = ""
    updated_at: str = ""
    digest: str = ""
    error: str = ""
    findings: tuple[Finding, ...] = ()
    new_ids: tuple[str, ...] = ()
    events: list[dict] = field(default_factory=list)
    spec_markdown: str = ""
    spec_html: str = ""
    out_dir: str = ""

    def to_dict(self) -> dict:
        return {
            "lang": self.lang,
            "version": self.version,
            "status": self.status,
            "workbook": self.workbook,
            "updated_at": self.updated_at,
            "error": self.error,
            "summary": count_by_severity(self.findings),
            "findings": [
                {**f.to_dict(), "is_new": f.id in self.new_ids} for f in self.findings
            ],
            "events": self.events,
            "out_dir": self.out_dir,
        }


class LiveRunner:
    def __init__(
        self,
        source: Source,
        out_dir: OutDir,
        config: CheckConfig | None = None,
        t: Translator = JA,
        interval: float = 2.0,
    ) -> None:
        self.source = source
        self.out_dir = out_dir
        self.config = config or CheckConfig()
        self.t = t
        self.interval = interval
        self.state = LiveState(lang=t("ja", "en"))
        self.changed = threading.Condition()
        self._stop = threading.Event()
        self._prev_snapshot: dict | None = None
        self._prev_findings: tuple[Finding, ...] | None = None
        self._last_out = ""

    # --- ループ ---------------------------------------------------------------

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def wait(self, seconds: float) -> None:
        self._stop.wait(seconds)

    def stop(self) -> None:
        self._stop.set()
        with self.changed:
            self.changed.notify_all()

    def run_forever(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self.interval)

    def tick(self) -> bool:
        """1 回ポーリングする。状態が更新されたら True。"""
        try:
            snap = self.source.poll()
        except (StudioError, TwbDocError, OSError) as error:
            return self._publish(status=self.source.status(), error=str(error))
        if snap is None:
            status = self.source.status()
            if status != self.state.status or self.state.error:
                return self._publish(status=status, error="")
            return False
        try:
            self.process(snap)
        except (TwbDocError, ValueError) as error:
            # 解析できない途中状態でも前回の結果は残す
            return self._publish(status=self.source.status(), error=str(error))
        return True

    # --- 処理 ---------------------------------------------------------------

    def process(self, snap: Snapshot) -> None:
        t = self.t
        source_file = f"{snap.title}.twb"
        root = parse_workbook_xml_bytes(snap.xml, source_file, t)
        workbook = parse_workbook(root, source_file=source_file)
        extra = studio_invalid_fields(snap.diagnostics, snap.sheet_names, t)
        findings = run_checks(workbook, t, extra, self.config)
        current = snapshot(workbook)
        changes = diff_snapshots(self._prev_snapshot, current, labels_for(workbook), t)
        new, resolved = diff_findings(self._prev_findings, findings)
        markdown = render(workbook, generated_at=snap.fetched_at, samples=None, t=t)
        html = render_html(
            markdown,
            title=f"{snap.title} " + t("設計書", "Documentation"),
            load_image=lambda _src: None,
            t=t,
        )
        at = snap.fetched_at.isoformat(timespec="seconds")
        event = {
            "at": at,
            "unsaved": snap.unsaved,
            "initial": self._prev_snapshot is None,
            "changes": [c.to_dict() for c in changes],
            "new": [{"id": f.id, "rule": f.rule, "target": f.target, "severity": f.severity} for f in new],
            "resolved": [{"id": f.id, "rule": f.rule, "target": f.target, "severity": f.severity} for f in resolved],
            "summary": count_by_severity(findings),
        }
        report = to_report_dict(snap.title, findings, snap.fetched_at, snap.source)
        self._write_outputs(snap, markdown, html, report, event)
        self._prev_snapshot = current
        self._prev_findings = findings
        with self.changed:
            state = self.state
            state.workbook = snap.title
            state.updated_at = at
            state.digest = snap.digest
            state.findings = findings
            state.new_ids = tuple(f.id for f in new)
            if event["initial"] or changes or new or resolved:
                state.events = [event, *state.events][:MAX_EVENTS]
            state.spec_markdown = markdown
            state.spec_html = html
            state.status = self.source.status()
            state.error = ""
            state.out_dir = self._last_out
            state.version += 1
            self.changed.notify_all()

    def _publish(self, status: dict, error: str) -> bool:
        with self.changed:
            if status == self.state.status and error == self.state.error:
                return False
            self.state.status = status
            self.state.error = error
            self.state.version += 1
            self.changed.notify_all()
        return True

    def _write_outputs(
        self, snap: Snapshot, markdown: str, html: str, report: dict, event: dict
    ) -> None:
        out = self.out_dir(snap) if callable(self.out_dir) else self.out_dir
        if out is None:
            return
        self._last_out = str(out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "spec.md").write_text(markdown, encoding="utf-8")
        (out / "spec.html").write_text(html, encoding="utf-8")
        (out / "findings.json").write_text(to_json(report) + "\n", encoding="utf-8")
        with (out / "history.jsonl").open("a", encoding="utf-8") as history:
            history.write(json.dumps(event, ensure_ascii=False) + "\n")

    def wait_for_change(self, version: int, timeout: float) -> int:
        """state.version が version から変わるまで待ち、現在の version を返す。"""
        deadline = time.monotonic() + timeout
        with self.changed:
            while self.state.version == version and not self._stop.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.changed.wait(remaining)
            return self.state.version

    def snapshot_state(self) -> dict:
        with self.changed:
            return self.state.to_dict()

    def spec(self, kind: str) -> str:
        with self.changed:
            return self.state.spec_html if kind == "html" else self.state.spec_markdown

    def report(self) -> dict:
        with self.changed:
            return to_report_dict(
                self.state.workbook or "",
                self.state.findings,
                datetime.now(),
                self.state.status.get("source", ""),
            )
