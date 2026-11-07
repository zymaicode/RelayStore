"""Tests for depot key sources."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.keys import KeyError_, Keyring

HEX = "ab" * 32


class KeyringTest(unittest.TestCase):
    def test_add_and_get(self):
        ring = Keyring()
        ring.add_hex(551, HEX)
        self.assertEqual(ring.get(551), bytes.fromhex(HEX))
        self.assertTrue(ring.has(551))
        self.assertEqual(len(ring), 1)

    def test_bad_key(self):
        with self.assertRaises(KeyError_):
            Keyring().add_hex(1, "zz")

    def test_from_json_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "depotkeys.json"
            path.write_text(json.dumps({"551": HEX, "not-a-depot": HEX}), encoding="utf-8")
            ring = Keyring.from_json_files([path, Path(tmp) / "missing.json"])
        self.assertEqual(len(ring), 1)
        self.assertEqual(ring.get(551), bytes.fromhex(HEX))
        self.assertIn("depotkeys.json", ring.sources)

    def test_from_config_vdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.vdf"
            path.write_text(
                '"InstallConfigStore"\n{\n  "Software"\n  {\n    "Valve"\n    {\n      "Steam"\n      {\n'
                '        "depots"\n        {\n          "3240221"\n          {\n            "DecryptionKey" "'
                + HEX
                + '"\n          }\n        }\n      }\n    }\n  }\n}\n',
                encoding="utf-8",
            )
            ring = Keyring.from_config_vdf(path)
        self.assertEqual(ring.get(3240221), bytes.fromhex(HEX))

    def test_from_vdf_text_with_steamtools_shape(self):
        text = (
            '"depots"\n{\n  "4115451"\n  {\n    "DecryptionKey" "' + HEX + '"\n  }\n}\n'
        )
        ring = Keyring.from_vdf_text(text, source="steamtools-4115450")
        self.assertEqual(ring.get(4115451), bytes.fromhex(HEX))
        self.assertIn("steamtools-4115450", ring.sources)

    def test_missing_config(self):
        with self.assertRaises(KeyError_):
            Keyring.from_config_vdf(Path("nope.vdf"))


if __name__ == "__main__":
    unittest.main()
