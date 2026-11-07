"""Unit tests for hubcap key validation + quota stats (M1-T10 helper)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.sources import HubcapError, hubcap_stats, is_valid_key  # noqa: E402

GOOD = "smm_" + "0f" * 48


class KeyFormatTest(unittest.TestCase):
    def test_valid_key(self):
        self.assertTrue(is_valid_key(GOOD))
        self.assertEqual(len(GOOD), 100)

    def test_rejects_wrong_prefix(self):
        self.assertFalse(is_valid_key("abc_" + "0f" * 48))

    def test_rejects_wrong_length(self):
        self.assertFalse(is_valid_key("smm_" + "0f" * 47))

    def test_rejects_uppercase_hex(self):
        self.assertFalse(is_valid_key("smm_" + "0F" * 48))

    def test_rejects_empty(self):
        self.assertFalse(is_valid_key(""))


class StatsTest(unittest.TestCase):
    def test_parses_stats_payload(self):
        payload = {
            "username": "tester",
            "daily_usage": 3,
            "daily_limit": 25,
            "can_make_requests": True,
            "api_key_expires_at": "2026-12-01T00:00:00Z",
        }
        calls = []

        def fetch(url):
            calls.append(url)
            return json.dumps(payload).encode("utf-8")

        stats = hubcap_stats(GOOD, fetch=fetch)
        self.assertEqual(stats["username"], "tester")
        self.assertEqual(stats["daily_usage"], 3)
        self.assertEqual(stats["daily_limit"], 25)
        self.assertTrue(stats["can_make_requests"])
        self.assertEqual(stats["expires_at"], "2026-12-01T00:00:00Z")
        self.assertIn("api_key=" + GOOD, calls[0])

    def test_invalid_key_is_rejected_before_network(self):
        def fetch(url):
            raise AssertionError("network must not be touched")

        with self.assertRaises(HubcapError):
            hubcap_stats("bad", fetch=fetch)

    def test_bad_json_raises(self):
        with self.assertRaises(HubcapError):
            hubcap_stats(GOOD, fetch=lambda url: b"<html>error</html>")

    def test_transport_error_wrapped(self):
        def fetch(url):
            raise TimeoutError("slow")

        with self.assertRaises(HubcapError):
            hubcap_stats(GOOD, fetch=fetch)


if __name__ == "__main__":
    unittest.main()
