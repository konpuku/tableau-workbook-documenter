"""ライブダッシュボードのローカル HTTP サーバー (127.0.0.1 のみ)。

    GET /               ダッシュボード (assets/live.html)
    GET /events         Server-Sent Events。状態が変わると "update" を送る
    GET /api/state      状態 (接続・検出・変更履歴)
    GET /api/findings   CI レポート (python -m twbdoc check --format json と同形式)
    GET /spec.html      最新の設計書 HTML
    GET /spec.md        最新の設計書 Markdown

DNS リバインディング対策として Host ヘッダーが localhost 系のときだけ応答する。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .runner import LiveRunner

ASSET_PATH = Path(__file__).resolve().parents[1] / "assets" / "live.html"
SSE_HEARTBEAT_SECONDS = 15.0
_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def make_handler(runner: LiveRunner) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "twbdoc-live"

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return  # コンソールを汚さない

        def do_GET(self) -> None:  # noqa: N802
            if not self._host_allowed():
                self._send(403, "text/plain; charset=utf-8", b"forbidden")
                return
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                self._send(200, "text/html; charset=utf-8", ASSET_PATH.read_bytes())
            elif path == "/api/state":
                self._send_json(runner.snapshot_state())
            elif path == "/api/findings":
                self._send_json(runner.report())
            elif path == "/spec.html":
                body = runner.spec("html") or "<p>waiting for the workbook…</p>"
                self._send(200, "text/html; charset=utf-8", body.encode("utf-8"))
            elif path == "/spec.md":
                self._send(200, "text/markdown; charset=utf-8", runner.spec("md").encode("utf-8"))
            elif path == "/events":
                self._stream_events()
            else:
                self._send(404, "text/plain; charset=utf-8", b"not found")

        def _host_allowed(self) -> bool:
            host = (self.headers.get("Host") or "").strip()
            if host.startswith("["):
                name = host.split("]", 1)[0] + "]"
            else:
                name = host.rsplit(":", 1)[0] if ":" in host else host
            return name in _ALLOWED_HOSTS

        def _send_json(self, data: dict) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)

        def _send(self, status: int, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _stream_events(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            version = -1
            try:
                while True:
                    current = runner.wait_for_change(version, SSE_HEARTBEAT_SECONDS)
                    if current != version:
                        version = current
                        self.wfile.write(f"event: update\ndata: {version}\n\n".encode())
                    else:
                        self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    if runner.stopped:
                        return
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return

    return Handler


class LiveServer:
    def __init__(self, runner: LiveRunner, port: int = 8765, host: str = "127.0.0.1") -> None:
        self.runner = runner
        self.httpd = ThreadingHTTPServer((host, port), make_handler(runner))
        self.httpd.daemon_threads = True
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self.httpd.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start(self) -> None:
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.runner.stop()
        self.httpd.shutdown()
        self.httpd.server_close()
