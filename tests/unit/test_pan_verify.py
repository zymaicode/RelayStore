"""Tests for batch verification + hard-delete guards."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.pan_verify import (
    FileRecord,
    VerifyError,
    hard_delete,
    hash_file,
    safe_target,
    sniff,
    three_round_check,
    verify_batch,
)


class HashTest(unittest.TestCase):
    def test_hash_and_sniff(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.bin"
            path.write_bytes(b"MZ" + b"\x00" * 10)
            size, sha256, md5 = hash_file(path)
            self.assertEqual(size, 12)
            self.assertEqual(len(sha256), 64)
            self.assertEqual(len(md5), 32)
            self.assertEqual(sniff(path), ("pe-executable", "high"))

    def test_sniff_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.bin"
            path.write_bytes(b"hello")
            self.assertEqual(sniff(path), ("unknown", "low"))


class GuardTest(unittest.TestCase):
    def test_safe_target_flattens(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = Path(tmp)
            target = safe_target(batch, "a/b/c.rar")
            self.assertEqual(target.name, "c.rar")

    def test_safe_target_flattens_traversal_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = safe_target(Path(tmp), "../../evil.rar")
            self.assertEqual(target.name, "evil.rar")
            self.assertEqual(target.parent, Path(tmp).resolve())

    def test_hard_delete_refuses_outside_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            root.mkdir()
            outside = Path(tmp) / "outside"
            outside.mkdir()
            with self.assertRaises(VerifyError):
                hard_delete(outside, root)
            self.assertTrue(outside.exists())


class BatchTest(unittest.TestCase):
    def make_remote(self, payload=b"data"):
        def download(name, target):
            target.write_bytes(payload + name.encode())

        return download

    def test_batch_verifies_then_deletes(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "log.jsonl"
            report = verify_batch(
                "batch-001",
                [("a.rar", 0), ("b.rar", 0)],
                Path(tmp) / "root",
                self.make_remote(),
                delete=True,
                log_path=log,
            )
            self.assertTrue(report.deleted)
            self.assertFalse((Path(tmp) / "root" / "batch-001").exists())
            self.assertEqual(len(report.files), 2)
            entries = log.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(json.loads(entries[-1])["batch_id"], "batch-001")

    def test_tampered_file_blocks_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            report = verify_batch(
                "batch-002",
                [("a.rar", 0)],
                root,
                self.make_remote(),
                delete=False,
            )
            target = Path(report.files[0].path)
            target.write_bytes(b"corrupted")
            problems = three_round_check(root / "batch-002", report.files, root)
            self.assertTrue(any("size mismatch" in p or "sha256 mismatch" in p for p in problems))

    def test_existing_batch_dir_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            (root / "batch-003").mkdir(parents=True)
            with self.assertRaises(VerifyError):
                verify_batch("batch-003", [], root, self.make_remote())

    def test_unexpected_extra_file_blocks_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            report = verify_batch("batch-004", [("a.rar", 0)], root, self.make_remote(), delete=False)
            (root / "batch-004" / "extra.exe").write_bytes(b"MZ")
            problems = three_round_check(root / "batch-004", report.files, root)
            self.assertTrue(any("unexpected entry" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
