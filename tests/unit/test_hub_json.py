"""Unit tests for the ManifestHub JSON normaliser (M1-T02)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.model import AccessToken, AppRecord, DepotKey  # noqa: E402
from steam_research.parsers import (  # noqa: E402
    HubJsonError,
    detect_json_shape,
    parse_hub_json,
    parse_hub_json_file,
)

FIXTURES = ROOT / "tests" / "fixtures" / "hub"
TOKENS = FIXTURES / "tokens.sample.json"
KEYS = FIXTURES / "depotkeys.sample.json"
MAP = FIXTURES / "manifest_map.sample.json"
RECORD = FIXTURES / "manifest_record.sample.json"


class ShapeDetectionTest(unittest.TestCase):
    def test_detects_token_map(self):
        self.assertEqual(detect_json_shape(json.loads(TOKENS.read_text("utf-8"))), "tokens")

    def test_detects_depot_key_map(self):
        self.assertEqual(detect_json_shape(json.loads(KEYS.read_text("utf-8"))), "depot_keys")

    def test_detects_manifest_map(self):
        self.assertEqual(detect_json_shape(json.loads(MAP.read_text("utf-8"))), "manifest_map")

    def test_detects_manifest_record(self):
        self.assertEqual(detect_json_shape(json.loads(RECORD.read_text("utf-8"))), "manifest_record")

    def test_rejects_non_object(self):
        with self.assertRaises(HubJsonError):
            detect_json_shape([1, 2, 3])

    def test_rejects_unknown_shape(self):
        with self.assertRaises(HubJsonError):
            detect_json_shape({"hello": "world", "n": 1})


class TokenParsingTest(unittest.TestCase):
    def test_tokens_are_normalised(self):
        tokens = parse_hub_json_file(TOKENS)
        self.assertEqual(len(tokens), 2)
        self.assertTrue(all(isinstance(t, AccessToken) for t in tokens))
        self.assertEqual([t.appid for t in tokens], [550, 3240220])
        self.assertEqual(tokens[0].token, "691935366181")

    def test_token_source_is_recorded(self):
        tokens = parse_hub_json({"42": "123456"})
        self.assertEqual(tokens[0].source, "manifesthub.tokens")
        self.assertTrue(tokens[0].fetched_at.endswith("+00:00"))

    def test_non_numeric_appid_rejected(self):
        with self.assertRaises(HubJsonError):
            parse_hub_json({"not-an-app": "123456"})

    def test_empty_token_rejected(self):
        with self.assertRaises(HubJsonError):
            parse_hub_json({"42": "   "})


class DepotKeyParsingTest(unittest.TestCase):
    def test_keys_are_normalised(self):
        keys = parse_hub_json_file(KEYS)
        self.assertEqual([k.depot_id for k in keys], [785481, 1457450])
        self.assertTrue(all(isinstance(k, DepotKey) for k in keys))
        self.assertEqual(len(keys[0].key_hex), 40)

    def test_short_key_rejected(self):
        with self.assertRaises(HubJsonError):
            parse_hub_json({"100": "abc"})

    def test_non_hex_key_rejected(self):
        with self.assertRaises(HubJsonError):
            parse_hub_json({"100": "zz" * 20})


class ManifestParsingTest(unittest.TestCase):
    def test_manifest_map(self):
        rec = parse_hub_json_file(MAP)
        self.assertIsInstance(rec, AppRecord)
        self.assertEqual(rec.appid, 550)
        self.assertEqual(rec.depots, (551, 552))
        self.assertEqual(rec.manifest_for(551).gid, "314878501352141828")
        self.assertEqual(rec.manifests[0].source, "manifesthub")

    def test_manifest_record(self):
        rec = parse_hub_json_file(RECORD)
        self.assertEqual(rec.appid, 3240220)
        self.assertEqual(rec.name, "Grand Theft Auto V Enhanced")
        self.assertEqual(len(rec.manifests), 2)
        self.assertEqual(rec.manifest_for(3240222).size, 34299685325)

    def test_manifest_map_with_multiple_apps_needs_appid(self):
        payload = {"1": {"10": "1111111111"}, "2": {"20": "2222222222"}}
        with self.assertRaises(HubJsonError):
            parse_hub_json(payload)
        rec = parse_hub_json(payload, appid=2)
        self.assertEqual(rec.depots, (20,))

    def test_bad_gid_rejected(self):
        with self.assertRaises(HubJsonError):
            parse_hub_json({"550": {"551": "not-a-gid"}})

    def test_missing_appid_in_record(self):
        with self.assertRaises(HubJsonError):
            parse_hub_json({"name": "x", "depots": []})


if __name__ == "__main__":
    unittest.main()
