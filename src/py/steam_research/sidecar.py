"""Local HTTP + JSON-RPC sidecar for the Tauri GUI (S1).

Why a sidecar: the GUI shell (Tauri/Rust) must not embed the Python core; it talks
to this process over 127.0.0.1 with a shared token, and receives progress as SSE.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse


class SidecarError(ValueError):
    """Raised for bad requests (unknown method, missing params, bad token)."""


@dataclass
class Job:
    id: str
    appid: int
    cancel: threading.Event = field(default_factory=threading.Event)
    events: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    done: bool = False

    def push(self, event: dict) -> None:
        with self.lock:
            self.events.append(event)

    def snapshot(self, since: int = 0) -> "list[dict]":
        with self.lock:
            return list(self.events[since:])


class SidecarService:
    """Business methods; every dependency is injectable so tests stay offline."""

    def __init__(
        self,
        *,
        keys_path: str | Path | None = None,
        index_path: str | Path | None = None,
        appinfo_cache: str | Path | None = None,
        coverage_fn: Callable | None = None,
        restore_fn: Callable | None = None,
    ) -> None:
        self.keys_path = keys_path
        self.index_path = index_path
        self.appinfo_cache = appinfo_cache
        self.coverage_fn = coverage_fn
        self.restore_fn = restore_fn
        self.jobs: dict[str, Job] = {}
        self.jobs_lock = threading.Lock()

    # -- coverage -----------------------------------------------------------
    def coverage_check(self, appid: int) -> dict:
        if self.coverage_fn is not None:
            return self.coverage_fn(int(appid))
        from .coverage import check_coverage
        from .keys import Keyring
        from .sources.manifest_index import ManifestIndex

        ring = Keyring.from_json_files([self.keys_path]) if self.keys_path else None
        index = ManifestIndex.load(self.index_path) if self.index_path else None
        report = check_coverage(
            int(appid),
            keys=ring,
            index=index,
            appinfo_cache=str(self.appinfo_cache) if self.appinfo_cache else None,
        )
        return report.as_dict()

    # -- restore ------------------------------------------------------------
    def restore_start(self, appid: int, target: str, depot_workers: int = 2, workers: int = 6) -> dict:
        job = Job(id=uuid.uuid4().hex[:12], appid=int(appid))
        with self.jobs_lock:
            self.jobs[job.id] = job

        def run() -> None:
            job.push({"type": "started", "jobId": job.id, "appid": job.appid})
            try:
                if self.restore_fn is not None:
                    result = self.restore_fn(
                        job, appid=int(appid), target=target, depot_workers=depot_workers, workers=workers
                    )
                else:
                    from .keys import Keyring
                    from .pipeline import restore_app
                    from .sources.manifest_index import ManifestIndex

                    ring = Keyring.from_json_files([self.keys_path]) if self.keys_path else Keyring()
                    index = ManifestIndex.load(self.index_path) if self.index_path else None
                    report = restore_app(
                        int(appid),
                        target,
                        keys=ring,
                        index=index,
                        depot_workers=depot_workers,
                        workers=workers,
                        state_path=str(Path(target) / ".sidecar-state.json"),
                        on_progress=lambda line: job.push({"type": "progress", "line": line}),
                        should_stop=job.cancel.is_set,
                    )
                    result = report.as_dict()
                job.push({"type": "done", "result": result})
            except Exception as exc:  # noqa: BLE001 - surfaced to the GUI
                job.push({"type": "error", "error": type(exc).__name__ + ": " + str(exc)})
            finally:
                job.done = True

        threading.Thread(target=run, daemon=True).start()
        return {"jobId": job.id}

    def restore_cancel(self, job_id: str) -> dict:
        with self.jobs_lock:
            job = self.jobs.get(job_id)
        if job is None:
            raise SidecarError("unknown job: " + str(job_id))
        job.cancel.set()
        return {"cancelled": True, "jobId": job_id}

    # -- data / runtime -----------------------------------------------------
    def data_sync(self) -> dict:
        keys = 0
        if self.keys_path and Path(self.keys_path).is_file():
            try:
                keys = len(json.loads(Path(self.keys_path).read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                keys = 0
        depots = 0
        if self.index_path and Path(self.index_path).is_file():
            try:
                payload = json.loads(Path(self.index_path).read_text(encoding="utf-8"))
                depots = len(payload.get("depots", {})) if "depots" in payload else len(payload)
            except Exception:  # noqa: BLE001
                depots = 0
        return {"keysCount": keys, "indexDepots": depots, "updated": False}

    def runtime_deploy(self, appid: int, target: str) -> dict:
        return {"ok": False, "reason": "runtime layer is a S3 feature", "appid": int(appid)}

    # -- dispatch -----------------------------------------------------------
    def dispatch(self, method: str, params: dict) -> dict:
        if method == "coverage.check":
            return self.coverage_check(int(params.get("appid") or 0))
        if method == "restore.start":
            return self.restore_start(
                int(params.get("appid") or 0),
                str(params.get("target") or ""),
                int(params.get("depotWorkers") or 2),
                int(params.get("workers") or 6),
            )
        if method == "restore.cancel":
            return self.restore_cancel(str(params.get("jobId") or ""))
        if method == "data.sync":
            return self.data_sync()
        if method == "runtime.deploy":
            return self.runtime_deploy(int(params.get("appid") or 0), str(params.get("target") or ""))
        if method == "ping":
            return {"pong": True, "time": time.time()}
        raise SidecarError("unknown method: " + method)


def make_handler(service: SidecarService, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "steam-sidecar/0.1"

        def log_message(self, *args) -> None:  # keep stdout clean for the GUI
            return

        def _authorized(self, parsed=None) -> bool:
            if self.headers.get("X-Sidecar-Token") == token:
                return True
            if parsed is not None:
                query = parse_qs(parsed.query)
                return (query.get("token") or [""])[0] == token
            return False

        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _serve_static(self, name: str) -> None:
            target = Path(__file__).parent / "webui" / name
            if not target.is_file():
                self._send(404, {"error": "not found"})
                return
            body = target.read_bytes()
            ctype = "text/html; charset=utf-8" if name.endswith(".html") else "application/javascript; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - stdlib naming
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/index.html"):
                self._serve_static("index.html")
                return
            if parsed.path == "/app.js":
                self._serve_static("app.js")
                return
            if parsed.path == "/session":
                self._send(200, {"host": self.server.server_address[0], "port": self.server.server_address[1], "token": token})
                return
            if parsed.path != "/events":
                self._send(404, {"error": "not found"})
                return
            if not self._authorized(parsed):
                self._send(401, {"error": "bad token"})
                return
            query = parse_qs(parsed.query)
            job_id = (query.get("job") or [""])[0]
            since = int((query.get("since") or ["0"])[0])
            job = service.jobs.get(job_id)
            if job is None:
                self._send(404, {"error": "unknown job"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            cursor = since
            deadline = time.time() + 300
            while time.time() < deadline:
                events = job.snapshot(cursor)
                for event in events:
                    chunk = "data: " + json.dumps(event, ensure_ascii=False) + "\n\n"
                    self.wfile.write(chunk.encode("utf-8"))
                    self.wfile.flush()
                    cursor += 1
                if job.done:
                    break
                time.sleep(0.2)

        def do_POST(self) -> None:  # noqa: N802 - stdlib naming
            if self.path != "/rpc":
                self._send(404, {"error": "not found"})
                return
            if not self._authorized():
                self._send(401, {"error": "bad token"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:  # noqa: BLE001
                self._send(400, {"error": "bad json"})
                return
            method = str(payload.get("method") or "")
            params = payload.get("params") or {}
            try:
                result = service.dispatch(method, params)
            except SidecarError as exc:
                self._send(400, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:  # noqa: BLE001
                self._send(500, {"ok": False, "error": type(exc).__name__ + ": " + str(exc)})
                return
            self._send(200, {"ok": True, "result": result})

    return Handler


def serve(
    service: "SidecarService | None" = None,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    token: str = "",
    port_file: str | Path | None = None,
):
    """Start the sidecar; returns (server, thread). Writes the chosen port to port_file."""
    service = service or SidecarService()
    token = token or uuid.uuid4().hex
    server = ThreadingHTTPServer((host, int(port)), make_handler(service, token))
    actual = server.server_address[1]
    if port_file:
        Path(port_file).write_text(
            json.dumps({"host": host, "port": actual, "token": token}), encoding="utf-8"
        )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, actual, token
