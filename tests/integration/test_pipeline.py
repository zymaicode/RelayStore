"""Tests for the app-level restore pipeline (offline, injected fakes)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.keys import Keyring
from steam_research.pipeline import restore_app
from steam_research.restore import RestoreReport
from steam_research.sources.appinfo import DepotInfo
from steam_research.sources.manifest_mirror import ManifestMirror

HEX = "ab" * 32


def depots():
    return [
        DepotInfo(depot_id=1, gid="1111111111111111111", size=10),
        DepotInfo(depot_id=2, gid="2222222222222222222", size=20),
        DepotInfo(depot_id=3, gid="3333333333333333333", size=30),
    ]


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "app"
        self.ring = Keyring()
        self.ring.add_hex(1, HEX)
        self.ring.add_hex(2, HEX)
        self.ring.add_hex(3, HEX)

    def tearDown(self):
        self.tmp.cleanup()

    def fake_mirror(self, failing=()):
        def get(depot_id, gid):
            if depot_id in failing:
                from steam_research.sources.manifest_mirror import MirrorError

                raise MirrorError("no mirror")
            return mock.Mock(files=[]), "https://example/" + str(depot_id)

        mirror = mock.Mock()
        mirror.get.side_effect = get
        return mirror

    def fake_restore(self, ok=True):
        def restore(depot_id, gid, key, out_dir, **kwargs):
            return RestoreReport(
                depot_id=depot_id,
                gid=str(gid),
                out_dir=str(out_dir),
                files_total=2,
                files_ok=2 if ok else 1,
                files_failed=0 if ok else 1,
                bytes_written=100,
                seconds=0.1,
            )

        return restore

    def test_all_ok(self):
        with mock.patch("steam_research.pipeline.restore_depot", side_effect=self.fake_restore()):
            report = restore_app(9, self.out, keys=self.ring, depots=depots(), mirror=self.fake_mirror())
        self.assertTrue(report.ok)
        self.assertEqual(report.as_dict()["depots_total"], 3)
        self.assertEqual(report.restored, 3)
        statuses = {depot.depot_id: depot.status for depot in report.depots}
        self.assertEqual(statuses[1], "ok")
        self.assertEqual(statuses[2], "ok")

    def test_missing_manifest(self):
        with mock.patch("steam_research.pipeline.restore_depot", side_effect=self.fake_restore()):
            report = restore_app(
                9, self.out, keys=self.ring, depots=depots(), mirror=self.fake_mirror(failing=(1,))
            )
        statuses = {depot.depot_id: depot.status for depot in report.depots}
        self.assertEqual(statuses[1], "missing_manifest")
        self.assertFalse(report.ok)

    def test_restore_failure_is_isolated(self):
        with mock.patch(
            "steam_research.pipeline.restore_depot", side_effect=self.fake_restore(ok=False)
        ):
            report = restore_app(9, self.out, keys=self.ring, depots=depots(), mirror=self.fake_mirror())
        statuses = {depot.depot_id: depot.status for depot in report.depots}
        self.assertEqual(statuses[1], "failed")

    def test_hubcap_rescues_missing_mirror(self):
        import tempfile

        fixture = (ROOT / "tests" / "fixtures" / "manifest" / "3dmark-1276160.manifest").read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "hub.manifest"
            target.write_bytes(fixture)

            class Hub:
                def fetch_manifest(self, depot_id, gid):
                    return target

            with mock.patch("steam_research.pipeline.restore_depot", side_effect=self.fake_restore()):
                report = restore_app(
                    9,
                    self.out,
                    keys=self.ring,
                    depots=[DepotInfo(depot_id=1, gid="1", size=1)],
                    mirror=self.fake_mirror(failing=(1,)),
                    hubcap=Hub(),
                )
        self.assertEqual(report.depots[0].status, "ok")
        self.assertTrue(report.depots[0].source_url.startswith("hubcap:"))

    def test_state_file_skips_done_depots(self):
        import json

        state = Path(self.tmp.name) / "state.json"
        state.write_text(json.dumps({"1": "ok"}), encoding="utf-8")
        with mock.patch("steam_research.pipeline.restore_depot", side_effect=self.fake_restore()) as restore:
            report = restore_app(
                9,
                self.out,
                keys=self.ring,
                depots=depots(),
                mirror=self.fake_mirror(),
                state_path=state,
            )
        statuses = {depot.depot_id: depot.status for depot in report.depots}
        self.assertEqual(statuses[1], "skipped")
        self.assertEqual(statuses[2], "ok")
        self.assertEqual(restore.call_count, 2)
        saved = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(saved["1"], "ok")
        self.assertEqual(saved["2"], "ok")

    def test_parallel_depot_workers(self):
        with mock.patch("steam_research.pipeline.restore_depot", side_effect=self.fake_restore()):
            report = restore_app(
                9,
                self.out,
                keys=self.ring,
                depots=depots(),
                mirror=self.fake_mirror(),
                depot_workers=3,
            )
        self.assertEqual(len(report.depots), 3)
        self.assertTrue(all(depot.status == "ok" for depot in report.depots))

    def test_only_filter(self):
        with mock.patch("steam_research.pipeline.restore_depot", side_effect=self.fake_restore()):
            report = restore_app(
                9, self.out, keys=self.ring, depots=depots(), mirror=self.fake_mirror(), only=[1]
            )
        statuses = {depot.depot_id: depot.status for depot in report.depots}
        self.assertEqual(statuses[1], "ok")
        self.assertEqual(statuses[2], "skipped")

    def test_max_depot_bytes(self):
        with mock.patch("steam_research.pipeline.restore_depot", side_effect=self.fake_restore()):
            report = restore_app(
                9, self.out, keys=self.ring, depots=depots(), mirror=self.fake_mirror(),
                max_depot_bytes=15,
            )
        statuses = {depot.depot_id: depot.status for depot in report.depots}
        self.assertEqual(statuses[2], "skipped")

    def test_report_dict_shape(self):
        with mock.patch("steam_research.pipeline.restore_depot", side_effect=self.fake_restore()):
            payload = restore_app(
                9, self.out, keys=self.ring, depots=depots(), mirror=self.fake_mirror()
            ).as_dict()
        self.assertEqual(payload["appid"], 9)
        self.assertIn("depots", payload)
        self.assertEqual(payload["files_ok"], 6)


if __name__ == "__main__":
    unittest.main()
