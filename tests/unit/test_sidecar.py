"""Tests for the local sidecar (HTTP + JSON-RPC + SSE)."""

from __future__ import annotations

import json
import sys
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.sidecar import SidecarService, serve


def call(port, token, method, params=None, timeout=10):
    body = json.dumps({"method": method, "params": params or {}}).encode()
    request = urllib.request.Request(
        "http://127.0.0.1:%d/rpc" % port,
        data=body,
        headers={"Content-Type": "application/json", "X-Sidecar-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode())


class SidecarTest(unittest.TestCase):
    def setUp(self):
        self.service = SidecarService(
            coverage_fn=lambda appid: {"appid": appid, "downloadable": True},
        )
        self.server, self.thread, self.port, self.token = serve(self.service, token="t0k")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_requires_token(self):
        request = urllib.request.Request(
            "http://127.0.0.1:%d/rpc" % self.port,
            data=b'{"method":"ping"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(ctx.exception.code, 401)

    def test_ping(self):
        result = call(self.port, self.token, "ping")
        self.assertTrue(result["ok"])
        self.assertTrue(result["result"]["pong"])

    def test_unknown_method(self):
        request = urllib.request.Request(
            "http://127.0.0.1:%d/rpc" % self.port,
            data=json.dumps({"method": "nope"}).encode(),
            headers={"Content-Type": "application/json", "X-Sidecar-Token": self.token},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(ctx.exception.code, 400)

    def test_coverage_uses_injected_service(self):
        result = call(self.port, self.token, "coverage.check", {"appid": 480})
        self.assertEqual(result["result"]["appid"], 480)
        self.assertTrue(result["result"]["downloadable"])

    def test_restore_events_stream(self):
        def fake_restore(job, appid, target, depot_workers, workers):
            job.push({"type": "progress", "line": "depot 1 ok"})
            return {"appid": appid, "ok": True}

        self.service.restore_fn = fake_restore
        started = call(self.port, self.token, "restore.start", {"appid": 480, "target": "out"})
        job_id = started["result"]["jobId"]
        deadline = time.time() + 10
        events = []
        while time.time() < deadline:
            events = self.service.jobs[job_id].snapshot(0)
            if self.service.jobs[job_id].done:
                break
            time.sleep(0.1)
        kinds = [event.get("type") for event in events]
        self.assertIn("started", kinds)
        self.assertIn("done", kinds)


if __name__ == "__main__":
    unittest.main()
