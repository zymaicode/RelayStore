"""Tests for the Xunlei share lister (offline, injected transport)."""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.sources.xunlei_share import (
    SALTS,
    captcha_sign,
    captcha_token,
    list_share,
    parse_share_url,
    walk_share,
)


class SignTest(unittest.TestCase):
    def test_captcha_sign_is_deterministic(self):
        a = captcha_sign("1700000000000", "0011223344556677")
        b = captcha_sign("1700000000000", "0011223344556677")
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("1."))
        self.assertEqual(len(a), 2 + 32)

    def test_captcha_sign_matches_manual_chain(self):
        timestamp, device = "1700000000000", "0011223344556677"
        current = "Xqp0kJBXWhwaTpB6" + "1.92.89" + "pan.xunlei.com" + device + timestamp
        for salt in SALTS:
            current = hashlib.md5((current + salt).encode()).hexdigest()
        self.assertEqual(captcha_sign(timestamp, device), "1." + current)


class ShareUrlTest(unittest.TestCase):
    def test_parse_with_pwd(self):
        share_id, pwd = parse_share_url("https://pan.xunlei.com/s/ABC123?pwd=8awk#")
        self.assertEqual(share_id, "ABC123")
        self.assertEqual(pwd, "8awk")

    def test_parse_without_pwd(self):
        share_id, pwd = parse_share_url("https://pan.xunlei.com/s/ABC123")
        self.assertEqual((share_id, pwd), ("ABC123", ""))

    def test_parse_rejects_empty(self):
        with self.assertRaises(Exception):
            parse_share_url("https://pan.xunlei.com/")


class ListingTest(unittest.TestCase):
    def transport_factory(self, pages):
        def transport(url, headers, body, timeout):
            if "captcha/init" in url:
                return {"captcha_token": "tok"}
            if "/share/detail" in url:
                return {"files": pages.get("detail", [])}
            return {"files": pages.get("root", []), "pass_code_token": "pct"}

        return transport

    def test_list_root(self):
        pages = {
            "root": [
                {"kind": "drive#folder", "id": "f1", "name": "dir", "size": "0"},
                {"kind": "drive#file", "id": "x1", "name": "a.bin", "size": "10"},
            ]
        }
        listing = list_share("S", "p", transport=self.transport_factory(pages))
        self.assertEqual(len(listing.entries), 2)
        self.assertEqual(listing.entries[0].kind, "folder")
        self.assertEqual(listing.entries[1].size, 10)
        self.assertEqual(listing.pass_code_token, "pct")

    def test_walk_expands_folders(self):
        pages = {
            "root": [{"kind": "drive#folder", "id": "f1", "name": "dir", "size": "0"}],
            "detail": [{"kind": "drive#file", "id": "x1", "name": "a.bin", "size": "10"}],
        }
        entries = walk_share("S", "p", transport=self.transport_factory(pages))
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].name, "dir/a.bin")

    def test_captcha_token_requires_value(self):
        def transport(url, headers, body, timeout):
            return {}

        with self.assertRaises(Exception):
            captcha_token("0011223344556677", transport=transport)


if __name__ == "__main__":
    unittest.main()
