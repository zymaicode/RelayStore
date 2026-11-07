"""Tests for the steamtools.games probe."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.sources.steamtools import SteamToolsError, probe


def fake_post(payload):
    def post(url, body, timeout):
        payload.append((url, body))
        return payload[0][2] if False else payload[-1][2]

    return post


class ProbeTest(unittest.TestCase):
    def test_in_db(self):
        def post(url, body, timeout):
            self.assertTrue(url.endswith("/api/generate"))
            self.assertEqual(body, {"appId": "400"})
            return {
                "code": 0,
                "message": "ok",
                "data": {
                    "downloadUrl": "https://x/api/files/400/zip",
                    "luaUrl": "https://x/api/files/400/lua",
                    "keyVdfUrl": "https://x/api/files/400/key",
                },
            }

        result = probe(400, post=post)
        self.assertTrue(result.in_db)
        self.assertIn("/400/key", result.key_url)

    def test_not_in_db(self):
        def post(url, body, timeout):
            return {"code": -1, "message": "not_in_db:App 4115450 is not yet in the ManifestHub database."}

        result = probe(4115450, post=post)
        self.assertFalse(result.in_db)
        self.assertIn("not_in_db", result.message)

    def test_error_is_unknown(self):
        def post(url, body, timeout):
            return {"code": -1, "message": "internal error"}

        result = probe(4115450, post=post)
        self.assertIsNone(result.in_db)

    def test_payload_shape(self):
        result = probe(400, post=lambda url, body, timeout: {}).as_dict()
        self.assertEqual(result["appid"], 400)
        self.assertIsNone(result["in_db"])


if __name__ == "__main__":
    unittest.main()
