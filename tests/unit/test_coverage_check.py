"""Tests for the read-only coverage check."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.coverage import check_coverage
from steam_research.keys import Keyring
from steam_research.sources.appinfo import DepotInfo
from steam_research.sources.manifest_index import ManifestIndex

HEX = "ab" * 32


class CoverageTest(unittest.TestCase):
    def setUp(self):
        self.depots = [
            DepotInfo(depot_id=1, gid="1111111111111111111", size=100),
            DepotInfo(depot_id=2, gid="2222222222222222222", size=200),
        ]
        self.keys = Keyring()
        self.keys.add_hex(1, HEX)
        self.keys.add_hex(2, HEX)
        self.index = ManifestIndex(gids={2: ["9999999999999999999"]})

    def test_fully_downloadable(self):
        report = check_coverage(
            7,
            keys=self.keys,
            index=self.index,
            depots=[
                DepotInfo(depot_id=1, gid="1111111111111111111", size=100),
                DepotInfo(depot_id=2, gid="2222222222222222222", size=200),
            ],
            head=lambda url: 200,
        )
        self.assertEqual(report.total_bytes, 300)
        self.assertEqual(report.keys_ok, 2)
        self.assertEqual(report.manifests_current, 2)
        self.assertEqual(report.downloadable_depots, 2)
        self.assertTrue(report.as_dict()["downloadable"])

    def test_missing_key_and_manifest(self):
        report = check_coverage(
            7,
            keys=self.keys,
            index=ManifestIndex(),
            depots=[DepotInfo(depot_id=2, gid="2222222222222222222", size=5)],
            head=lambda url: 404,
        )
        payload = report.as_dict()
        self.assertFalse(payload["downloadable"])
        self.assertEqual(payload["downloadable_depots"], 0)
        self.assertEqual(payload["depots"][0]["manifest_status"], 404)

    def test_steamtools_probe_is_reported(self):
        class Probe:
            def as_dict(self):
                return {"appid": 7, "in_db": False, "message": "not_in_db"}

        report = check_coverage(
            7,
            keys=self.keys,
            index=self.index,
            depots=[DepotInfo(depot_id=1, gid="1", size=1)],
            head=lambda url: 404,
            steamtools_probe=lambda appid: Probe(),
        )
        self.assertEqual(report.as_dict()["steamtools"]["in_db"], False)

    def test_hubcap_manifest_counts_as_available(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "m.manifest"
            target.write_bytes(b"x" * 10)

            class Hub:
                def fetch_manifest(self, depot_id, gid):
                    return target

            report = check_coverage(
                7,
                keys=self.keys,
                index=ManifestIndex(),
                depots=[DepotInfo(depot_id=1, gid="1", size=1)],
                head=lambda url: 404,
                hubcap=Hub(),
            )
        item = report.depots[0]
        self.assertTrue(str(item.manifest_status).startswith("hubcap:10"))
        self.assertEqual(report.downloadable_depots, 1)

    def test_index_any_build_counts(self):
        report = check_coverage(
            7,
            keys=self.keys,
            index=self.index,
            depots=[DepotInfo(depot_id=2, gid="2222222222222222222", size=5)],
            head=lambda url: 404,
        )
        self.assertEqual(report.depots[0].index_gids, 1)


if __name__ == "__main__":
    unittest.main()
