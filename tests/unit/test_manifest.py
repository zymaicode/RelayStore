"""Unit tests for the depot manifest reader (protobuf sections)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.manifest import (
    END_MAGIC,
    PAYLOAD_MAGIC,
    ManifestError,
    parse_manifest,
    parse_manifest_file,
)

FIXTURE = ROOT / "tests" / "fixtures" / "manifest" / "3dmark-1276160.manifest"


def varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def field_varint(number: int, value: int) -> bytes:
    return varint(number << 3) + varint(value)


def field_bytes(number: int, payload: bytes) -> bytes:
    return varint((number << 3) | 2) + varint(len(payload)) + payload


def field_fixed32(number: int, value: int) -> bytes:
    return varint((number << 3) | 5) + value.to_bytes(4, "little")


def make_manifest(files) -> bytes:
    mappings = b""
    for names, chunks in files:
        entry = b"".join(field_bytes(1, name.encode()) for name in names)
        for sha, crc, cb_original, cb_compressed in chunks:
            chunk = (
                field_bytes(1, bytes.fromhex(sha))
                + field_fixed32(2, crc)
                + field_varint(3, 0)
                + field_varint(4, cb_original)
                + field_varint(5, cb_compressed)
            )
            entry += field_bytes(6, chunk)
        mappings += field_bytes(1, entry)
    payload = mappings
    body = PAYLOAD_MAGIC.to_bytes(4, "little") + len(payload).to_bytes(4, "little") + payload
    return body + END_MAGIC.to_bytes(4, "little")


SHA = "391d06c90755f477114c8c24328a99c907b18f20"


class SyntheticTest(unittest.TestCase):
    def setUp(self):
        self.data = make_manifest([(["dir/file.bin"], [(SHA, 1234, 1048576, 191584)])])

    def test_parses_file_and_chunk(self):
        manifest = parse_manifest(self.data)
        self.assertEqual(len(manifest.files), 1)
        self.assertEqual(manifest.files[0].names, ("dir/file.bin",))
        self.assertEqual(manifest.chunk_count, 1)
        chunk = next(manifest.chunks())
        self.assertEqual(chunk.sha, SHA)
        self.assertEqual(chunk.crc, 1234)
        self.assertEqual(chunk.cb_original, 1048576)
        self.assertEqual(chunk.cb_compressed, 191584)

    def test_file_size_sums_chunks(self):
        self.assertEqual(parse_manifest(self.data).files[0].size, 1048576)

    def test_bad_magic(self):
        with self.assertRaises(ManifestError):
            parse_manifest(b"\x00" * 16)

    def test_missing_end_marker(self):
        with self.assertRaises(ManifestError):
            parse_manifest(self.data[:-4])

    def test_truncated_section(self):
        with self.assertRaises(ManifestError):
            parse_manifest(self.data[:12])


class RealFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = parse_manifest_file(FIXTURE)

    def test_counts(self):
        self.assertEqual(len(self.manifest.files), 21)
        self.assertEqual(self.manifest.chunk_count, 405)

    def test_metadata(self):
        self.assertEqual(self.manifest.metadata["depot_id"], 1276160)
        self.assertEqual(self.manifest.metadata["gid_manifest"], 8215949335091262124)
        self.assertTrue(self.manifest.has_signature)

    def test_known_chunk(self):
        target = "391d06c90755f477114c8c24328a99c907b18f20"
        match = [chunk for chunk in self.manifest.chunks() if chunk.sha == target]
        self.assertEqual(len(match), 1)
        self.assertEqual(match[0].cb_compressed, 191584)
        self.assertEqual(match[0].cb_original, 1048576)


if __name__ == "__main__":
    unittest.main()
