"""Integration tests for the hubcap manifest client (M1-T10)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.sources import HubcapClient, HubcapError  # noqa: E402


class HubcapClientTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name)
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, payload=b"manifest-bytes", **kwargs):
        def fetch(url):
            self.calls.append(url)
            return payload

        return HubcapClient("test-key", fetch=fetch, cache_dir=self.cache, **kwargs)

    def test_api_key_is_required(self):
        with self.assertRaises(HubcapError):
            HubcapClient("")

    def test_url_contains_query(self):
        client = self.make()
        url = client.url_for(551, "314878501352141828")
        self.assertIn("depot_id=551", url)
        self.assertIn("manifest_id=314878501352141828", url)
        self.assertIn("api_key=test-key", url)

    def test_fetch_writes_cache_file(self):
        client = self.make(b"VDF-data")
        path = client.fetch_manifest(551, "314878501352141828")
        self.assertTrue(path.is_file())
        self.assertEqual(path.read_bytes(), b"VDF-data")
        self.assertIn("551", path.name)

    def test_second_call_uses_cache(self):
        client = self.make()
        first = client.fetch_manifest(551, "314878501352141828")
        second = client.fetch_manifest(551, "314878501352141828")
        self.assertEqual(first, second)
        self.assertEqual(len(self.calls), 1)

    def test_max_bytes_is_enforced(self):
        client = self.make(b"x" * 100, max_bytes=10)
        with self.assertRaises(HubcapError):
            client.fetch_manifest(551, "314878501352141828")

    def test_empty_response_rejected(self):
        client = self.make(b"")
        with self.assertRaises(HubcapError):
            client.fetch_manifest(551, "314878501352141828")

    def test_transport_error_is_wrapped(self):
        def fetch(url):
            raise TimeoutError("slow")

        client = HubcapClient("k", fetch=fetch, cache_dir=self.cache)
        with self.assertRaises(HubcapError):
            client.fetch_manifest(551, "314878501352141828")

    def test_invalid_gid(self):
        client = self.make()
        with self.assertRaises(HubcapError):
            client.url_for(551, "not-a-gid")

    def test_requires_cache_dir(self):
        client = HubcapClient("k", fetch=lambda url: b"data")
        with self.assertRaises(HubcapError):
            client.fetch_manifest(551, "314878501352141828")


if __name__ == "__main__":
    unittest.main()
