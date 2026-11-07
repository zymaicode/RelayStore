"""Tests for the CDN client (host fallback, token attempt, path guards)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.sources.cdn import CdnClient, CdnError


class PathTest(unittest.TestCase):
    def test_manifest_path(self):
        client = CdnClient(fetch=lambda url, headers: (200, b"x"))
        self.assertEqual(client.manifest_path(1276160, "8215949335091262124"), "/depot/1276160/manifest/8215949335091262124/5")

    def test_chunk_path_rejects_bad_sha(self):
        client = CdnClient(fetch=lambda url, headers: (200, b"x"))
        with self.assertRaises(CdnError):
            client.chunk_path(1, "zz")


class WalkTest(unittest.TestCase):
    def test_falls_back_to_second_host(self):
        calls = []

        def fetch(url, headers):
            calls.append(url)
            return (401, b"") if "a.example" in url else (200, b"manifest")

        client = CdnClient(hosts=("https://a.example", "https://b.example"), fetch=fetch)
        url, payload = client.fetch_manifest(1, "123")
        self.assertEqual(payload, b"manifest")
        self.assertIn("b.example", url)
        self.assertEqual(len(calls), 2)

    def test_all_hosts_fail_raises_with_attempts(self):
        client = CdnClient(hosts=("https://a.example",), fetch=lambda url, headers: (403, b""))
        with self.assertRaises(CdnError) as ctx:
            client.fetch_manifest(1, "123")
        self.assertEqual(ctx.exception.attempts[0].status, 403)

    def test_token_is_sent_as_bearer(self):
        seen = {}

        def fetch(url, headers):
            seen.update(headers)
            return (200, b"x")

        CdnClient(fetch=fetch).fetch_manifest(1, "123", token="abc")
        self.assertEqual(seen.get("Authorization"), "Bearer abc")


if __name__ == "__main__":
    unittest.main()
