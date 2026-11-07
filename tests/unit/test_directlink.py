"""Unit tests for the direct-link orchestration (offline, injected fetch)."""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.directlink import (
    DEFAULT_CDN,
    DEFAULT_REPO,
    DirectLink,
    DirectLinkError,
    chunk_url,
    manifest_url,
)

SHA = "391d06c90755f477114c8c24328a99c907b18f20"
GID = "8215949335091262124"


def varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def field_bytes(number: int, payload: bytes) -> bytes:
    return varint((number << 3) | 2) + varint(len(payload)) + payload


def field_varint(number: int, value: int) -> bytes:
    return varint(number << 3) + varint(value)


def field_fixed32(number: int, value: int) -> bytes:
    return varint((number << 3) | 5) + value.to_bytes(4, "little")


def make_manifest(sha: str, cb_original: int, cb_compressed: int) -> bytes:
    chunk = (
        field_bytes(1, bytes.fromhex(sha))
        + field_fixed32(2, 7)
        + field_varint(3, 0)
        + field_varint(4, cb_original)
        + field_varint(5, cb_compressed)
    )
    entry = field_bytes(1, b"file.bin") + field_bytes(6, chunk)
    payload = field_bytes(1, entry)
    body = (0x71F617D0).to_bytes(4, "little") + len(payload).to_bytes(4, "little") + payload
    return body + (0x32C415AB).to_bytes(4, "little")


class UrlTest(unittest.TestCase):
    def test_manifest_url(self):
        self.assertEqual(
            manifest_url(1276160, GID),
            "https://raw.githubusercontent.com/" + DEFAULT_REPO + "/main/1276160_" + GID + ".manifest",
        )

    def test_chunk_url(self):
        self.assertEqual(chunk_url(1276160, SHA), DEFAULT_CDN + "/depot/1276160/chunk/" + SHA)

    def test_manifest_url_rejects_bad_gid(self):
        with self.assertRaises(DirectLinkError):
            manifest_url(1276160, "abc")

    def test_chunk_url_rejects_bad_sha(self):
        with self.assertRaises(DirectLinkError):
            chunk_url(1276160, "zz")


class FetchTest(unittest.TestCase):
    def test_get_manifest_parses(self):
        payload = make_manifest(SHA, 1048576, 191584)
        link = DirectLink(fetch=lambda url: payload)
        manifest = link.get_manifest(1276160, GID)
        self.assertEqual(manifest.chunk_count, 1)
        self.assertEqual(manifest.files[0].names, ("file.bin",))

    def test_verify_first_chunk_success(self):
        payload = make_manifest(SHA, 3, 2)
        cipher = b"\x00\x01"
        link = DirectLink(fetch=lambda url: payload if url.endswith(".manifest") else cipher)
        manifest = link.get_manifest(1276160, GID)
        with mock.patch("steam_research.directlink.decode_chunk", return_value=b"abc"):
            result = link.verify_first_chunk(1276160, manifest, b"k" * 32)
        self.assertEqual(result.plain_bytes, 3)
        self.assertEqual(result.chunk_sha, SHA)

    def test_chunk_size_mismatch(self):
        payload = make_manifest(SHA, 3, 5)
        link = DirectLink(fetch=lambda url: payload if url.endswith(".manifest") else b"\x00")
        manifest = link.get_manifest(1276160, GID)
        with self.assertRaises(DirectLinkError):
            link.verify_first_chunk(1276160, manifest, b"k" * 32)

    def test_empty_manifest(self):
        manifest = mock.Mock()
        manifest.chunks.return_value = iter(())
        link = DirectLink(fetch=lambda url: b"")
        with self.assertRaises(DirectLinkError):
            link.verify_first_chunk(1276160, manifest, b"k" * 32)


if __name__ == "__main__":
    unittest.main()
