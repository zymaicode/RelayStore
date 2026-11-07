"""Unit tests for the coverage report generator (M1-T08)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.reports.coverage import collect, render_markdown, scan_repo  # noqa: E402


class CoverageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name) / "hub-a"
        self.repo.mkdir()
        (self.repo / "a.lua").write_text("addappid(550)\n", encoding="utf-8")
        (self.repo / "b.lua").write_text("addappid(551)\n", encoding="utf-8")
        (self.repo / "appaccesstokens.json").write_text(
            json.dumps({"550": "123456", "3240220": "654321"}), encoding="utf-8"
        )
        (self.repo / "depotkeys.json").write_text(
            json.dumps({"551": "aa" * 20}), encoding="utf-8"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan_counts(self):
        stats = scan_repo(self.repo, "hub-a")
        self.assertEqual(stats.name, "hub-a")
        self.assertEqual(stats.files, 4)
        self.assertEqual(stats.lua_files, 2)
        self.assertEqual(stats.json_files, 2)
        self.assertEqual(stats.tokens, 2)
        self.assertEqual(stats.depot_keys, 1)
        self.assertGreater(stats.bytes_total, 0)

    def test_unreadable_json_is_flagged(self):
        bad = Path(self.tmp.name) / "hub-b"
        bad.mkdir()
        (bad / "depotkeys.json").write_text("{not json", encoding="utf-8")
        stats = scan_repo(bad, "hub-b")
        self.assertEqual(stats.depot_keys, 0)
        self.assertEqual(stats.json_files, 1)

    def test_render_markdown(self):
        rows = collect([("hub-a", self.repo)])
        text = render_markdown(rows, generated_at="2026-11-06T00:00:00+00:00")
        self.assertIn("| repo | files |", text)
        self.assertIn("| hub-a | 4 | 2 | 2 | 2 | 1 |", text)
        self.assertIn("**total**", text)
        self.assertIn("2026-11-06T00:00:00+00:00", text)

    def test_missing_repo_raises(self):
        with self.assertRaises(FileNotFoundError):
            scan_repo(Path(self.tmp.name) / "nope")


if __name__ == "__main__":
    unittest.main()
