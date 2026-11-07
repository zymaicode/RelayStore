"""Unit tests for sha1/size verification and path safety (M1-T06)."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.verify import (  # noqa: E402
    VerifyError,
    sha1_file,
    safe_join,
    verify_file,
)


class VerifyFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "blob.bin"
        self.path.write_bytes(b"manifest-content" * 1000)
        self.digest = hashlib.sha1(self.path.read_bytes()).hexdigest()
        self.size = self.path.stat().st_size

    def tearDown(self):
        self.tmp.cleanup()

    def test_sha1_file(self):
        self.assertEqual(sha1_file(self.path), self.digest)

    def test_sha1_streaming_chunks(self):
        self.assertEqual(sha1_file(self.path, chunk_size=7), self.digest)

    def test_ok(self):
        report = verify_file(self.path, sha1=self.digest, size=self.size)
        self.assertTrue(report.ok)
        self.assertEqual([c.status for c in report.checks], ["OK", "OK"])

    def test_sha1_mismatch(self):
        report = verify_file(self.path, sha1="0" * 40, size=self.size)
        self.assertFalse(report.ok)
        self.assertEqual(report.checks[0].status, "FAIL")

    def test_size_mismatch(self):
        report = verify_file(self.path, sha1=self.digest, size=self.size + 1)
        self.assertFalse(report.ok)
        self.assertEqual(report.checks[-1].status, "FAIL")

    def test_requires_at_least_one_expectation(self):
        with self.assertRaises(VerifyError):
            verify_file(self.path)

    def test_missing_file(self):
        with self.assertRaises(VerifyError):
            verify_file(Path(self.tmp.name) / "nope.bin", sha1=self.digest)

    def test_bad_sha1_format(self):
        with self.assertRaises(VerifyError):
            verify_file(self.path, sha1="xyz")

    def test_report_as_dict(self):
        report = verify_file(self.path, sha1=self.digest, size=self.size)
        payload = report.as_dict()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["checks"]), 2)


class SafeJoinTest(unittest.TestCase):
    def test_relative_path(self):
        root = Path("C:/games/lib")
        self.assertEqual(safe_join(root, "sub/file.bin"), root / "sub" / "file.bin")

    def test_traversal_rejected(self):
        with self.assertRaises(VerifyError):
            safe_join(Path("C:/games/lib"), "../evil.bin")

    def test_absolute_rejected(self):
        with self.assertRaises(VerifyError):
            safe_join(Path("C:/games/lib"), "C:/Windows/system32/x.dll")

    def test_ads_rejected(self):
        with self.assertRaises(VerifyError):
            safe_join(Path("C:/games/lib"), "file.bin:stream")

    def test_empty_rejected(self):
        with self.assertRaises(VerifyError):
            safe_join(Path("C:/games/lib"), "  ")


if __name__ == "__main__":
    unittest.main()
