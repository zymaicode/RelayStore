"""Integration tests for the hubcap-check CLI command (M1-T10 helper)."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.cli import main  # noqa: E402
from steam_research.sources import HubcapError  # noqa: E402

GOOD = "smm_" + "0f" * 48
STATS = {
    "username": "tester",
    "daily_usage": 3,
    "daily_limit": 25,
    "can_make_requests": True,
    "expires_at": "2026-12-01T00:00:00Z",
    "raw": {},
}


def run(argv):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class HubcapCheckCliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env_file = Path(self.tmp.name) / ".env"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_key_exits_2(self):
        code, out, _ = run(["hubcap-check", "--env-file", str(self.env_file), "--key-env", "NOPE_KEY"])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out)["key_ok"])

    def test_bad_format_exits_2_without_network(self):
        code, out, _ = run(["hubcap-check", "--key", "smm_short", "--env-file", str(self.env_file)])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(out)["key_ok"])

    def test_key_from_env_file(self):
        self.env_file.write_text("HUBBCAP_API_KEY=" + GOOD + "\n", encoding="utf-8")
        with mock.patch("steam_research.cli.hubcap_stats", return_value=STATS) as stats:
            code, out, _ = run(["hubcap-check", "--env-file", str(self.env_file)])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["key_ok"])
        self.assertEqual(payload["stats"]["daily_limit"], 25)
        self.assertEqual(stats.call_args[0][0], GOOD)

    def test_key_is_masked_in_output(self):
        with mock.patch("steam_research.cli.hubcap_stats", return_value=STATS):
            code, out, _ = run(["hubcap-check", "--key", GOOD, "--env-file", str(self.env_file)])
        self.assertEqual(code, 0)
        self.assertNotIn(GOOD, out)
        self.assertIn("smm_0f0f...", out)

    def test_quota_exhausted_exits_4(self):
        exhausted = dict(STATS, can_make_requests=False, daily_usage=25)
        with mock.patch("steam_research.cli.hubcap_stats", return_value=exhausted):
            code, out, _ = run(["hubcap-check", "--key", GOOD, "--env-file", str(self.env_file)])
        self.assertEqual(code, 4)
        self.assertIn("daily limit reached", json.loads(out)["reason"])

    def test_stats_error_exits_5(self):
        with mock.patch("steam_research.cli.hubcap_stats", side_effect=HubcapError("boom")):
            code, out, _ = run(["hubcap-check", "--key", GOOD, "--env-file", str(self.env_file)])
        self.assertEqual(code, 5)
        self.assertIn("boom", json.loads(out)["error"])

    def test_fetch_manifest_uses_client(self):
        blob = Path(self.tmp.name) / "x.manifest"
        blob.write_bytes(b"VDF")
        with mock.patch("steam_research.cli.hubcap_stats", return_value=STATS), mock.patch(
            "steam_research.cli.HubcapClient"
        ) as client_cls:
            client_cls.return_value.fetch_manifest.return_value = blob
            code, out, _ = run(
                [
                    "hubcap-check",
                    "--key",
                    GOOD,
                    "--env-file",
                    str(self.env_file),
                    "--fetch",
                    "551:314878501352141828",
                    "--cache-dir",
                    self.tmp.name,
                ]
            )
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["fetched"][0]["depot"], 551)
        self.assertEqual(payload["fetched"][0]["bytes"], 3)

    def test_bad_fetch_spec_exits_2(self):
        with mock.patch("steam_research.cli.hubcap_stats", return_value=STATS):
            code, _, err = run(["hubcap-check", "--key", GOOD, "--env-file", str(self.env_file), "--fetch", "551"])
        self.assertEqual(code, 2)
        self.assertIn("DEPOT:GID", err)


if __name__ == "__main__":
    unittest.main()
