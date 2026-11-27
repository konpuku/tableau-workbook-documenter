"""Tableau Studio (Tableau Desktop 2026.3.1+) の External Client API クライアント。

Studio は起動ごとに発見ファイル
    Windows: %LOCALAPPDATA%/Tableau/Tableau/ExternalApi/<pid>.json
    macOS  : ~/Library/Application Support/Tableau/Tableau/ExternalApi/<pid>.json
に baseUrl と Bearer トークンを書き出す。これを読んでローカル REST を呼ぶ。
(ヘルプ > 設定とパフォーマンス > External Client API Access を有効化して再起動が必要)

使うエンドポイント (すべて読み取り専用):
    GET /v0/health               生存確認 (認証不要)
    GET /v0/workbook             開いているワークブックのメタ情報とシート一覧
    GET /v0/workbook/document    ワークブック全体の XML (未保存の変更を含む)
    GET /v0/workbook/diagnostics ワークシートの無効フィールド診断
    GET /v0/operations/{id}      202 応答時の非同期ポーリング

標準ライブラリ (urllib) のみ。トークンはログ・例外メッセージに含めない。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

USER_AGENT = "twbdoc-live-ci"
DISCOVERY_DIR_ENV = "TABLEAU_EXTERNAL_API_DISCOVERY_DIR"
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
_TERMINAL_STATES = {"SUCCEEDED", "FAILED", "CANCELLED"}


class StudioError(Exception):
    """Studio に接続できない / API がエラーを返した。"""


class StudioUnavailable(StudioError):
    """Studio が起動していない、または External Client API が無効。"""


@dataclass(frozen=True)
class StudioInstance:
    base_url: str
    token: str
    pid: int
    api_version: str = ""
    started_at: str = ""
    discovery_file: str = ""

    def __repr__(self) -> str:  # トークンを表示しない
        return (
            f"StudioInstance(base_url={self.base_url!r}, pid={self.pid}, "
            f"api_version={self.api_version!r})"
        )


def default_discovery_dir() -> Path:
    override = os.environ.get(DISCOVERY_DIR_ENV)
    if override:
        return Path(override)
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "Tableau" / "Tableau" / "ExternalApi"


def read_discovery_files(directory: Path | None = None) -> list[StudioInstance]:
    """発見ファイルを新しい順に返す (localhost 以外を指すものは無視する)。"""
    directory = directory or default_discovery_dir()
    instances: list[StudioInstance] = []
    if not directory.is_dir():
        return instances
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        base_url = str(data.get("baseUrl", "")).rstrip("/")
        token = str(data.get("token", ""))
        if not base_url or not token or not _is_local(base_url):
            continue
        try:
            pid = int(data.get("pid", 0))
        except (TypeError, ValueError):
            pid = 0
        instances.append(
            StudioInstance(
                base_url=base_url,
                token=token,
                pid=pid,
                api_version=str(data.get("apiVersion", "")),
                started_at=str(data.get("startedAt", "")),
                discovery_file=str(path),
            )
        )
    instances.sort(key=lambda i: i.started_at, reverse=True)
    return instances


def _is_local(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme == "http" and (parsed.hostname or "") in _LOCAL_HOSTS


class StudioClient:
    """1 つの Studio インスタンスへの読み取り専用クライアント。"""

    def __init__(
        self,
        instance: StudioInstance,
        timeout: float = 30.0,
        operation_timeout: float = 60.0,
    ) -> None:
        self.instance = instance
        self.timeout = timeout
        self.operation_timeout = operation_timeout

    # --- 公開 API ---------------------------------------------------------

    def health(self) -> bool:
        try:
            status, _, body = self._request("/v0/health", auth=False)
        except StudioError:
            return False
        return status == 200 and b"OK" in body.upper()

    def workbook(self) -> dict:
        return self._get_json("/v0/workbook")

    def diagnostics(self) -> dict:
        return self._get_json("/v0/workbook/diagnostics")

    def document(self) -> bytes:
        """開いているワークブック全体の XML を返す (未保存の変更を含む)。"""
        status, headers, body = self._request("/v0/workbook/document")
        if status == 202:
            operation = self._await_operation(headers, body)
            result = operation.get("result") or {}
            document = result.get("document")
            if not isinstance(document, str):
                raise StudioError("operation result has no document")
            return document.encode("utf-8")
        return body

    # --- 内部 ---------------------------------------------------------------

    def _get_json(self, path: str) -> dict:
        status, headers, body = self._request(path)
        if status == 202:
            return self._await_operation(headers, body).get("result") or {}
        try:
            return json.loads(body.decode("utf-8"))
        except ValueError as error:
            raise StudioError(f"invalid JSON from {path}") from error

    def _await_operation(self, headers: dict[str, str], body: bytes) -> dict:
        try:
            operation = json.loads(body.decode("utf-8") or "{}")
        except ValueError:
            operation = {}
        location = headers.get("location") or (
            f"/v0/operations/{operation.get('id')}" if operation.get("id") else ""
        )
        if not location:
            raise StudioError("202 response without an operation location")
        deadline = time.monotonic() + self.operation_timeout
        while operation.get("state") not in _TERMINAL_STATES:
            if operation.get("blockingWindows"):
                raise StudioError(
                    "Tableau is showing a dialog that needs a decision; "
                    "close it in Tableau and retry"
                )
            if time.monotonic() > deadline:
                raise StudioError("timed out waiting for the Tableau operation")
            time.sleep(_retry_after(headers))
            status, headers, body = self._request(location)
            try:
                operation = json.loads(body.decode("utf-8"))
            except ValueError as error:
                raise StudioError("invalid operation response") from error
        if operation.get("state") != "SUCCEEDED":
            error = operation.get("error") or {}
            raise StudioError(
                f"operation {operation.get('state')}: "
                f"{error.get('code', '')} {error.get('message', '')}".strip()
            )
        return operation

    def _request(
        self, path: str, auth: bool = True
    ) -> tuple[int, dict[str, str], bytes]:
        url = urllib.parse.urljoin(self.instance.base_url + "/", path.lstrip("/"))
        if not _is_local(url):
            raise StudioError("refusing to call a non-local URL")
        request = urllib.request.Request(url, method="GET")
        request.add_header("User-Agent", USER_AGENT)
        if auth:
            request.add_header("Authorization", f"Bearer {self.instance.token}")
        # localhost 呼び出しにプロキシを使わない
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=self.timeout) as response:
                headers = {k.lower(): v for k, v in response.headers.items()}
                return response.status, headers, response.read()
        except urllib.error.HTTPError as error:
            detail = _problem_detail(error)
            if error.code == 503:
                raise StudioUnavailable(f"API unavailable (503 {detail})") from None
            raise StudioError(f"HTTP {error.code} for {path} {detail}".strip()) from None
        except (urllib.error.URLError, OSError) as error:
            raise StudioUnavailable(f"cannot reach Tableau Studio ({error})") from None


def _retry_after(headers: dict[str, str]) -> float:
    try:
        return min(max(float(headers.get("retry-after", "1")), 0.2), 5.0)
    except ValueError:
        return 1.0


def _problem_detail(error: urllib.error.HTTPError) -> str:
    try:
        data = json.loads(error.read().decode("utf-8"))
    except (ValueError, OSError):
        return ""
    return str(data.get("code") or data.get("title") or "")


def connect(
    discovery_dir: Path | None = None,
    workbook: str | None = None,
) -> StudioClient:
    """生きている Studio インスタンスに接続する。

    workbook を指定すると、そのタイトルまたはパスのワークブックを開いている
    インスタンスを選ぶ (複数の Tableau を起動している場合用)。
    """
    candidates = read_discovery_files(discovery_dir)
    if not candidates:
        raise StudioUnavailable(
            "no Tableau Studio discovery file found; start Tableau Desktop and "
            "turn on Help > Settings & Performance > External Client API Access"
        )
    for instance in candidates:
        client = StudioClient(instance)
        if not client.health():
            continue
        if workbook is None:
            return client
        try:
            info = client.workbook()
        except StudioError:
            continue
        wanted = workbook.lower()
        if wanted in {
            str(info.get("title", "")).lower(),
            str(info.get("location") or "").lower(),
        } or wanted in str(info.get("location") or "").lower():
            return client
    raise StudioUnavailable(
        "Tableau Studio is not running (or the External Client API is off)"
        + (f", or no instance has '{workbook}' open" if workbook else "")
    )
