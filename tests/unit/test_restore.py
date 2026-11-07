"""Unit tests for depot restore/assembly (offline, mocked decode)."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.manifest import parse_manifest
from steam_research.restore import RestoreError, restore_depot


def varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def fb(number: int, payload: bytes) -> bytes:
    return varint((number << 3) | 2) + varint(len(payload)) + payload


def fv(number: int, value: int) -> bytes:
    return varint(number << 3) + varint(value)


def make_manifest(path: str, chunks, sha_content: str, size: int) -> bytes:
    entry = fb(1, path.encode()) + fv(2, size) + fb(5, bytes.fromhex(sha_content))
    for sha, offset, cb in chunks:
        body = fb(1, bytes.fromhex(sha)) + fv(3, offset) + fv(4, cb) + fv(5, len(b"cipher"))
        entry += fb(6, body)
    payload = fb(1, entry)
    return (0x71F617D0).to_bytes(4, "little") + len(payload).to_bytes(4, "little") + payload + (0x32C415AB).to_bytes(4, "little")


class RestoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "out"
        self.part_a = b"AAA"
        self.part_b = b"BBB"
        self.content = self.part_a + self.part_b
        self.sha_a = hashlib.sha1(self.part_a).hexdigest()
        self.sha_b = hashlib.sha1(self.part_b).hexdigest()
        self.sha_content = hashlib.sha1(self.content).hexdigest()
        self.manifest_bytes = make_manifest(
            "dir/file.bin",
            [(self.sha_a, 0, len(self.part_a)), (self.sha_b, 3, len(self.part_b))],
            self.sha_content,
            len(self.content),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def fake_link(self):
        manifest = parse_manifest(self.manifest_bytes)
        link = mock.Mock()
        link.get_manifest.return_value = manifest
        link.get_chunk.side_effect = lambda depot, sha: b"cipher"
        return link

    def test_restore_assembles_and_verifies(self):
        link = self.fake_link()
        payloads = {self.sha_a: self.part_a, self.sha_b: self.part_b}

        def fake_decode(cipher, key):
            return payloads.popitem()[1] if False else None

        with mock.patch("steam_research.restore.decode_chunk", side_effect=lambda cipher, key: payloads.pop(next(iter(payloads)))):
            report = restore_depot(1, "123", b"k" * 32, self.out, link=link, workers=1)
        self.assertTrue(report.ok, report.errors)
        self.assertEqual(report.files_ok, 1)
        self.assertEqual((self.out / "dir" / "file.bin").read_bytes(), self.content)

    def test_unsafe_path_is_rejected(self):
        manifest_bytes = make_manifest("../evil.bin", [(self.sha_a, 0, 3)], self.sha_content, 3)
        link = mock.Mock()
        link.get_manifest.return_value = parse_manifest(manifest_bytes)
        link.get_chunk.return_value = b"cipher"
        with mock.patch("steam_research.restore.decode_chunk", return_value=self.part_a):
            report = restore_depot(1, "1", b"k" * 32, self.out, link=link, workers=1)
        self.assertFalse(report.ok)
        self.assertIn("unsafe path", " ".join(report.errors))

    def test_directory_entries_are_not_written_as_files(self):
        manifest_bytes = make_manifest("dlc", [], "", 0)
        link = mock.Mock()
        link.get_manifest.return_value = parse_manifest(manifest_bytes)
        link.get_chunk.return_value = b"cipher"
        report = restore_depot(1, "1", b"k" * 32, self.out, link=link, workers=1)
        self.assertTrue((self.out / "dlc").is_dir())
        self.assertFalse((self.out / "dlc").is_file())
        self.assertEqual(report.directories, 1)
        self.assertEqual(report.files_total, 0)

    def test_chunk_failure_aborts(self):
        link = mock.Mock()
        link.get_manifest.return_value = parse_manifest(self.manifest_bytes)
        link.get_chunk.side_effect = RuntimeError("cdn down")
        report = restore_depot(1, "1", b"k" * 32, self.out, link=link, workers=1)
        self.assertFalse(report.ok)
        self.assertEqual(report.files_failed, report.files_total)


if __name__ == "__main__":
    unittest.main()
