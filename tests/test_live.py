"""ライブ監視 (Studio クライアント・ソース・ランナー・ダッシュボードサーバー) のテスト。

Tableau Studio の External Client API をローカルの偽サーバーで再現する。
"""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from twbdoc.commands import EXIT_STUDIO_UNAVAILABLE
from twbdoc.cli import main
from twbdoc.live.runner import LiveRunner, default_out_dir
from twbdoc.live.server import LiveServer
from twbdoc.live.source import FileSource, Snapshot, StudioSource
from twbdoc.live.studio import (
    StudioClient,
    StudioInstance,
    StudioUnavailable,
    connect,
    read_discovery_files,
)

TOKEN = "secret-token"


class FakeStudio:
    """External Client API の最小実装。document は差し替え可能。"""

    def __init__(self, xml: str, async_document: bool = False) -> None:
        self.xml = xml
        self.unsaved = False
        self.async_document = async_document
        self.document_calls = 0
        self.diagnostics = {"worksheets": []}
        studio = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/v0/health":
                    return self._json({"status": "OK"})
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self._json({"code": "unauthorized"}, 401)
                if self.path == "/v0/workbook":
                    return self._json({
                        "title": "Book", "location": None, "unsavedChanges": studio.unsaved,
                        "worksheets": [{"id": "w1", "name": "売上推移"}],
                        "dashboards": [], "storyboards": [],
                    })
                if self.path == "/v0/workbook/document":
                    studio.document_calls += 1
                    if studio.async_document:
                        body = json.dumps({"id": "op1", "kind": "read", "state": "RUNNING"}).encode()
                        self.send_response(202)
                        self.send_header("Location", "/v0/operations/op1")
                        self.send_header("Retry-After", "0")
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    body = studio.xml.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/xml")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path == "/v0/operations/op1":
                    return self._json({
                        "id": "op1", "kind": "read", "state": "SUCCEEDED",
                        "result": {"document": studio.xml, "payloadVersion": "2026.3"},
                    })
                if self.path == "/v0/workbook/diagnostics":
                    return self._json(studio.diagnostics)
                return self._json({"code": "not-found"}, 404)

            def _json(self, data: dict, status: int = 200) -> None:
                body = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    def instance(self) -> StudioInstance:
        return StudioInstance(base_url=self.base_url, token=TOKEN, pid=1)

    def write_discovery(self, directory: Path, started_at: str = "2026-11-27T00:00:00Z") -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "1.json").write_text(json.dumps({
            "schemaVersion": 1, "pid": 1, "baseUrl": self.base_url, "tokenType": "Bearer",
            "token": TOKEN, "apiVersion": "0.2.9", "startedAt": started_at,
        }), encoding="utf-8")

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def studio(minimal_twb_xml: str):
    fake = FakeStudio(minimal_twb_xml)
    yield fake
    fake.close()


class TestDiscovery:
    def test_localhost_以外の発見ファイルは無視する(self, tmp_path: Path) -> None:
        (tmp_path / "1.json").write_text(json.dumps(
            {"baseUrl": "http://evil.example.com:1", "token": "x", "pid": 1}), encoding="utf-8")
        (tmp_path / "2.json").write_text("not json", encoding="utf-8")
        assert read_discovery_files(tmp_path) == []

    def test_生きているインスタンスに接続する(self, studio: FakeStudio, tmp_path: Path) -> None:
        studio.write_discovery(tmp_path)
        # 古い (死んだ) インスタンスも並べておく
        (tmp_path / "0.json").write_text(json.dumps({
            "baseUrl": "http://127.0.0.1:1", "token": "x", "pid": 0,
            "startedAt": "2099-01-01T00:00:00Z"}), encoding="utf-8")
        client = connect(tmp_path)
        assert client.instance.base_url == studio.base_url
        assert TOKEN not in repr(client.instance)

    def test_起動していなければ_StudioUnavailable(self, tmp_path: Path) -> None:
        with pytest.raises(StudioUnavailable):
            connect(tmp_path)


class TestClient:
    def test_document_を同期で取得(self, studio: FakeStudio) -> None:
        client = StudioClient(studio.instance())
        assert client.health()
        assert b"<workbook" in client.document()
        assert client.workbook()["title"] == "Book"

    def test_202_の非同期操作をポーリングする(self, minimal_twb_xml: str) -> None:
        fake = FakeStudio(minimal_twb_xml, async_document=True)
        try:
            assert b"<workbook" in StudioClient(fake.instance()).document()
        finally:
            fake.close()


class TestStudioSource:
    def test_変化がなければ_None_を返す(self, studio: FakeStudio) -> None:
        source = StudioSource(client=StudioClient(studio.instance()), doc_interval=0)
        first = source.poll()
        assert first is not None and first.title == "Book" and first.source == "studio"
        assert first.sheet_names == {"w1": "売上推移"}
        assert source.poll() is None  # XML 同一
        studio.xml = studio.xml.replace("単独シート", "単独シート改")
        assert source.poll() is not None

    def test_定期取得の間隔内は_document_を取らない(self, studio: FakeStudio) -> None:
        source = StudioSource(client=StudioClient(studio.instance()), doc_interval=3600)
        source.poll()
        source.poll()
        assert studio.document_calls == 1
        studio.unsaved = True  # 未保存フラグが変わったら即取得
        source.poll()
        assert studio.document_calls == 2


class TestRunner:
    def test_編集で新規検出と差分が出て_出力が書かれる(self, studio: FakeStudio, tmp_path: Path) -> None:
        source = StudioSource(client=StudioClient(studio.instance()), doc_interval=0)
        runner = LiveRunner(source, tmp_path / "out")
        assert runner.tick()
        state = runner.snapshot_state()
        assert state["workbook"] == "Book"
        assert state["events"][0]["initial"] is True
        # 計算式を編集 (未保存)
        studio.unsaved = True
        assert "SUM([利益])/SUM([売上])" in studio.xml
        studio.xml = studio.xml.replace("SUM([利益])/SUM([売上])", "SUM([利益])/SUM([売上]) * 100")
        assert runner.tick()
        state = runner.snapshot_state()
        latest = state["events"][0]
        assert latest["unsaved"] is True
        assert any(c["kind"] == "changed" and c["category"] == "calc" for c in latest["changes"])
        assert state["status"]["unsaved"] is True
        out = tmp_path / "out"
        assert (out / "spec.md").read_text(encoding="utf-8")
        report = json.loads((out / "findings.json").read_text(encoding="utf-8"))
        assert report["source"] == "studio"
        assert len((out / "history.jsonl").read_text(encoding="utf-8").splitlines()) == 2

    def test_Studio_停止中はエラー状態を配信する(self, tmp_path: Path) -> None:
        source = StudioSource(discovery_dir=tmp_path)
        runner = LiveRunner(source, None)
        assert runner.tick()
        state = runner.snapshot_state()
        assert state["error"]
        assert state["status"]["connected"] is False
        assert not runner.tick()  # 同じエラーは再配信しない

    def test_解析できない途中状態は前回結果を保持する(self, studio: FakeStudio) -> None:
        source = StudioSource(client=StudioClient(studio.instance()), doc_interval=0)
        runner = LiveRunner(source, None)
        runner.tick()
        before = runner.snapshot_state()["findings"]
        studio.xml = "<workbook"
        runner.tick()
        state = runner.snapshot_state()
        assert state["error"]
        assert state["findings"] == before

    def test_ファイル監視(self, tmp_path: Path, minimal_twb_xml: str) -> None:
        path = tmp_path / "book.twb"
        path.write_text(minimal_twb_xml, encoding="utf-8")
        source = FileSource(path)
        assert source.poll() is not None
        assert source.poll() is None

    def test_既定の出力先はワークブックの隣(self, tmp_path: Path) -> None:
        snap = Snapshot(xml=b"", title="Book", source="studio", location=str(tmp_path / "Book.twb"))
        assert default_out_dir(snap) == tmp_path / "Book.twbdoc"


class TestServer:
    def test_状態_設計書_SSE_を配信する(self, studio: FakeStudio) -> None:
        source = StudioSource(client=StudioClient(studio.instance()), doc_interval=0)
        runner = LiveRunner(source, None)
        runner.tick()
        server = LiveServer(runner, port=0)
        server.start()
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(server.url + "api/state", timeout=5) as response:
                state = json.loads(response.read())
            assert state["workbook"] == "Book"
            with opener.open(server.url + "api/findings", timeout=5) as response:
                assert json.loads(response.read())["schema"] == 1
            with opener.open(server.url + "spec.html", timeout=5) as response:
                assert b"<html" in response.read().lower()
            with opener.open(server.url, timeout=5) as response:
                assert b"twbdoc Live CI" in response.read()
            with opener.open(server.url + "events", timeout=5) as response:
                assert response.readline().startswith(b"event: update")
            request = urllib.request.Request(server.url + "api/state", headers={"Host": "evil.example.com"})
            with pytest.raises(urllib.error.HTTPError) as error:
                opener.open(request, timeout=5)
            assert error.value.code == 403
        finally:
            server.stop()


class TestCheckStudio:
    def test_Studio_の編集中ワークブックを検査する(
        self, studio: FakeStudio, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        studio.write_discovery(tmp_path)
        studio.unsaved = True
        monkeypatch.setenv("TABLEAU_EXTERNAL_API_DISCOVERY_DIR", str(tmp_path))
        main(["check", "--studio", "--format", "json"])
        report = json.loads(capsys.readouterr().out)
        assert report["source"] == "studio"
        assert report["unsaved"] is True

    def test_Studio_が無ければ終了コード_6(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("TABLEAU_EXTERNAL_API_DISCOVERY_DIR", str(tmp_path))
        assert main(["check", "--studio"]) == EXIT_STUDIO_UNAVAILABLE
