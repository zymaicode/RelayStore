"""Unit tests for the steamcmd appinfo parser (C route, M1-T09)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.model import AppRecord  # noqa: E402
from steam_research.parsers import ParseError, parse_appinfo, parse_appinfo_file  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "contract"
L4D2 = FIXTURES / "steamcmd-550.json"
GTA5 = FIXTURES / "steamcmd-3240220.json"


class ParseFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.l4d2 = parse_appinfo_file(L4D2, 550)

    def test_returns_app_record(self):
        self.assertIsInstance(self.l4d2, AppRecord)

    def test_app_name(self):
        self.assertEqual(self.l4d2.appid, 550)
        self.assertEqual(self.l4d2.name, "Left 4 Dead 2")

    def test_depot_ids_are_numbers(self):
        self.assertEqual(len(self.l4d2.depots), 9)
        self.assertTrue(all(isinstance(d, int) for d in self.l4d2.depots))
        self.assertEqual(self.l4d2.depots, tuple(sorted(self.l4d2.depots)))

    def test_known_manifest(self):
        ref = self.l4d2.manifest_for(551)
        self.assertIsNotNone(ref)
        self.assertEqual(ref.gid, "314878501352141828")
        self.assertEqual(ref.size, 11329675570)
        self.assertEqual(ref.source, "steamcmd")
        self.assertEqual(ref.appid, 550)

    def test_every_public_manifest_parsed(self):
        self.assertEqual(len(self.l4d2.manifests), 9)
        for ref in self.l4d2.manifests:
            self.assertTrue(ref.gid.isdigit(), ref)
            self.assertTrue(15 <= len(ref.gid) <= 20, ref)
            self.assertIsNotNone(ref.size)

    def test_second_fixture(self):
        gta = parse_appinfo_file(GTA5, 3240220)
        self.assertEqual(gta.name, "Grand Theft Auto V Enhanced")
        self.assertEqual(len(gta.depots), 6)
        self.assertEqual(gta.manifest_for(3240221).gid, "7738940149188702855")

    def test_fetched_at_is_iso_utc(self):
        ref = self.l4d2.manifests[0]
        self.assertIn("+00:00", ref.fetched_at)

    def test_source_url(self):
        ref = self.l4d2.manifests[0]
        self.assertEqual(ref.source_url, "https://api.steamcmd.net/v1/info/550")


class SyntheticPayloadTest(unittest.TestCase):
    def base(self):
        return {
            "status": "success",
            "data": {
                "42": {
                    "common": {"name": "Test App"},
                    "depots": {
                        "100": {"manifests": {"public": {"gid": "1234567890123456789", "size": "10"}}},
                        "101": {"manifests": {}},
                        "branches": {"public": {"buildid": "1"}},
                        "baselanguages": ["english"],
                    },
                }
            },
        }

    def test_ignores_non_numeric_depot_keys(self):
        rec = parse_appinfo(self.base(), 42)
        self.assertEqual(rec.depots, (100, 101))
        self.assertEqual([r.depot_id for r in rec.manifests], [100])

    def test_depot_without_public_manifest_is_skipped(self):
        rec = parse_appinfo(self.base(), 42)
        self.assertIsNone(rec.manifest_for(101))

    def test_missing_data_raises(self):
        with self.assertRaises(ParseError):
            parse_appinfo({"status": "success"}, 42)

    def test_unknown_appid_raises(self):
        with self.assertRaises(ParseError):
            parse_appinfo(self.base(), 999)

    def test_invalid_gid_raises(self):
        payload = self.base()
        payload["data"]["42"]["depots"]["100"]["manifests"]["public"]["gid"] = "not-a-gid"
        with self.assertRaises(ParseError):
            parse_appinfo(payload, 42)

    def test_non_dict_payload_raises(self):
        with self.assertRaises(ParseError):
            parse_appinfo([], 42)

    def test_missing_token_flagged(self):
        payload = self.base()
        payload["data"]["42"]["_missing_token"] = True
        with self.assertRaises(ParseError):
            parse_appinfo(payload, 42)

    def test_no_numeric_depots_raises(self):
        payload = self.base()
        payload["data"]["42"]["depots"] = {"branches": {}}
        with self.assertRaises(ParseError):
            parse_appinfo(payload, 42)

    def test_parse_from_raw_json_string(self):
        payload = json.loads(json.dumps(self.base()))
        rec = parse_appinfo(payload)
        self.assertEqual(rec.appid, 42)
        self.assertEqual(rec.name, "Test App")


if __name__ == "__main__":
    unittest.main()
