"""Unit tests for the SteamTools Lua config parser/updater (M1-T03)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.parsers import LuaConfig, LuaError, parse_lua  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "lua"
FULL = (FIXTURES / "550.lua").read_text("utf-8")
PLAIN = (FIXTURES / "plain.lua").read_text("utf-8")


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.cfg = parse_lua(FULL)

    def test_appid(self):
        self.assertEqual(self.cfg.appid, 550)

    def test_entries(self):
        self.assertEqual(sorted(self.cfg.entries), [551, 552])
        self.assertEqual(self.cfg.entries[551].gid, "314878501352141828")
        self.assertEqual(self.cfg.entries[551].size, 11329675570)

    def test_render_round_trip(self):
        self.assertEqual(self.cfg.render(), FULL)

    def test_unknown_lines_are_kept(self):
        self.assertIn("addtoken(550", self.cfg.render())
        self.assertIn("-- SteamTools", self.cfg.render())

    def test_plain_file(self):
        cfg = parse_lua(PLAIN)
        self.assertEqual(cfg.appid, 3240220)
        self.assertEqual(cfg.entries, {})

    def test_garbage_lines_do_not_crash(self):
        cfg = parse_lua("this is not lua\naddappid(7)\n@@@\n")
        self.assertEqual(cfg.appid, 7)


class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.cfg = parse_lua(FULL)

    def test_only_manifest_lines_change(self):
        new_text = self.cfg.apply({551: "9999999999999999999"})
        old_lines = self.cfg.render().splitlines()
        new_lines = new_text.splitlines()
        self.assertEqual(len(old_lines), len(new_lines))
        changed = [i for i, (a, b) in enumerate(zip(old_lines, new_lines)) if a != b]
        self.assertEqual(len(changed), 2)  # addappid(551, ...) + setManifestid(551, ...)
        for idx in changed:
            self.assertIn("551", new_lines[idx])

    def test_size_is_kept_when_not_given(self):
        new_text = self.cfg.apply({551: "9999999999999999999"})
        self.assertIn("setManifestid(551, \"9999999999999999999\", 11329675570)", new_text)

    def test_size_is_updated_when_given(self):
        new_text = self.cfg.apply({551: "9999999999999999999"}, sizes={551: 42})
        self.assertIn("setManifestid(551, \"9999999999999999999\", 42)", new_text)

    def test_missing_depot_is_appended(self):
        new_text = self.cfg.apply({700: "1234567890123456789"}, sizes={700: 5})
        self.assertEqual(len(new_text.splitlines()), len(FULL.splitlines()) + 1)
        self.assertIn("setManifestid(700, \"1234567890123456789\", 5)", new_text)

    def test_plain_file_gets_setmanifest(self):
        cfg = parse_lua(PLAIN)
        new_text = cfg.apply({3240221: "7738940149188702855"})
        self.assertIn("addappid(3240220)", new_text)
        self.assertIn("setManifestid(3240221, \"7738940149188702855\")", new_text)

    def test_invalid_gid_rejected(self):
        with self.assertRaises(LuaError):
            self.cfg.apply({551: "nope"})

    def test_unknown_appid_is_kept(self):
        new_text = self.cfg.apply({})
        self.assertEqual(new_text, FULL)


class LuaConfigTypeTest(unittest.TestCase):
    def test_parse_lua_returns_config(self):
        self.assertIsInstance(parse_lua(FULL), LuaConfig)


if __name__ == "__main__":
    unittest.main()
