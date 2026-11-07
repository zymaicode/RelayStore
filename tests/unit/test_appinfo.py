"""Tests for the generic VDF parser and steamcmd appinfo source."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.parsers.vdf import VdfError, parse_vdf
from steam_research.sources.appinfo import (
    AppInfoError,
    depots_from_app_info,
    extract_block,
    parse_app_info,
)

FIXTURE = ROOT / "tests" / "fixtures" / "appinfo" / "620.raw.txt"


class VdfTest(unittest.TestCase):
    def test_nested(self):
        text = '"root"\n{\n  "a" "1"\n  "b"\n  {\n    "c" "2"\n  }\n}\n'
        parsed = parse_vdf(text)
        self.assertEqual(parsed["root"]["a"], "1")
        self.assertEqual(parsed["root"]["b"]["c"], "2")

    def test_comments_and_bare_tokens(self):
        text = '"root"\n{\n  // comment\n  "a" 42\n}\n'
        self.assertEqual(parse_vdf(text)["root"]["a"], "42")

    def test_unterminated_string_reports_line(self):
        with self.assertRaises(VdfError) as ctx:
            parse_vdf('"root"\n{\n"a" "oops\n}\n')
        self.assertEqual(ctx.exception.line, 3)

    def test_missing_value(self):
        with self.assertRaises(VdfError):
            parse_vdf('"root"\n{\n"a"\n}\n')


class AppInfoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = FIXTURE.read_text(encoding="utf-8")
        cls.info = parse_app_info(cls.raw, 620)

    def test_extract_block(self):
        block = extract_block(self.raw, 620)
        self.assertTrue(block.startswith('"620"'))
        self.assertEqual(block.count("{"), block.count("}"))

    def test_missing_appid(self):
        with self.assertRaises(AppInfoError):
            extract_block(self.raw, 999999)

    def test_common_name(self):
        self.assertEqual(self.info["common"]["name"], "Portal 2")

    def test_depots(self):
        depots = depots_from_app_info(self.info)
        self.assertEqual(len(depots), 10)
        ids = [depot.depot_id for depot in depots]
        self.assertEqual(ids, sorted(ids))
        first = depots[0]
        self.assertEqual(first.gid, "9044256803759256265")
        self.assertEqual(first.size, 12677678229)

    def test_depot_lookup_by_id(self):
        depots = {depot.depot_id: depot for depot in depots_from_app_info(self.info)}
        self.assertEqual(depots[624].gid, "3651103799462409440")
        self.assertEqual(depots[624].size, 20537496)

    def test_no_depots(self):
        self.assertEqual(depots_from_app_info({"common": {}}), ())


if __name__ == "__main__":
    unittest.main()
