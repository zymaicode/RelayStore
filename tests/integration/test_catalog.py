"""Integration tests for the SQLite catalog: idempotent upsert + history (M1-T04)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.catalog import Catalog  # noqa: E402
from steam_research.model import AccessToken, AppRecord, DepotKey, ManifestRef  # noqa: E402


def make_record(appid=550, gid="314878501352141828", size=11329675570, fetched="2026-11-06T00:00:00+00:00"):
    return AppRecord(
        appid=appid,
        name="Left 4 Dead 2",
        depots=(551, 552),
        manifests=(
            ManifestRef(550, 551, gid, size=size, source="acf", source_url="D:/Steam/appmanifest_550.acf", fetched_at=fetched),
            ManifestRef(550, 552, "8555994540167139077", size=3634678710, source="acf", fetched_at=fetched),
        ),
    )


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "catalog.db"
        self.catalog = Catalog(self.path)

    def tearDown(self):
        self.catalog.close()
        self.tmp.cleanup()

    def test_upsert_then_query(self):
        self.catalog.upsert(make_record())
        rec = self.catalog.query(550)
        self.assertIsNotNone(rec)
        self.assertEqual(rec.appid, 550)
        self.assertEqual(rec.name, "Left 4 Dead 2")
        self.assertEqual(rec.depots, (551, 552))
        self.assertEqual(rec.manifest_for(551).gid, "314878501352141828")

    def test_repeated_upsert_is_idempotent(self):
        for _ in range(3):
            self.catalog.upsert(make_record())
        self.assertEqual(self.catalog.stats()["manifests"], 2)
        self.assertEqual(self.catalog.stats()["apps"], 1)

    def test_new_gid_keeps_history(self):
        self.catalog.upsert(make_record())
        self.catalog.upsert(make_record(gid="1111111111111111111", fetched="2026-11-07T00:00:00+00:00"))
        rec = self.catalog.query(550)
        self.assertEqual(rec.manifest_for(551).gid, "1111111111111111111")
        history = self.catalog.history(550, 551)
        self.assertEqual([row["gid"] for row in history], ["314878501352141828", "1111111111111111111"])

    def test_query_missing_appid(self):
        self.assertIsNone(self.catalog.query(999))

    def test_tokens_are_idempotent(self):
        tokens = (AccessToken(550, "691935366181", "manifesthub.tokens", "2026-11-06T00:00:00+00:00"),)
        self.catalog.upsert_tokens(tokens)
        self.catalog.upsert_tokens(tokens)
        self.assertEqual(self.catalog.stats()["tokens"], 1)
        self.assertEqual(self.catalog.token_for(550), "691935366181")

    def test_depot_keys_are_idempotent(self):
        keys = (DepotKey(785481, "08" * 20, "manifesthub.depotkeys", "2026-11-06T00:00:00+00:00"),)
        self.catalog.upsert_depot_keys(keys)
        self.catalog.upsert_depot_keys(keys)
        self.assertEqual(self.catalog.stats()["depot_keys"], 1)
        self.assertEqual(self.catalog.depot_key(785481), "08" * 20)

    def test_sources_breakdown(self):
        self.catalog.upsert(make_record())
        self.assertEqual(self.catalog.sources(), {"acf": 2})

    def test_persists_across_reopen(self):
        self.catalog.upsert(make_record())
        self.catalog.close()
        reopened = Catalog(self.path)
        try:
            self.assertEqual(reopened.query(550).appid, 550)
        finally:
            reopened.close()
        self.catalog = Catalog(":memory:")


if __name__ == "__main__":
    unittest.main()
