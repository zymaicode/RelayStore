"""Unit tests for the provider chain / degradation logic (M1-T05)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.catalog import Catalog  # noqa: E402
from steam_research.model import AppRecord, ManifestRef  # noqa: E402
from steam_research.resolver import (  # noqa: E402
    CallableProvider,
    ResolveError,
    Resolver,
)


def record(appid=550, gid="314878501352141828"):
    return AppRecord(
        appid=appid,
        name="Left 4 Dead 2",
        depots=(551,),
        manifests=(ManifestRef(appid, 551, gid, size=1, source="test", fetched_at="2026-11-06T00:00:00+00:00"),),
    )


def boom(appid):
    raise RuntimeError("source down")


class ResolverTest(unittest.TestCase):
    def test_first_provider_wins(self):
        resolver = Resolver([CallableProvider("a", lambda appid: record()), CallableProvider("b", boom)])
        result = resolver.resolve(550)
        self.assertEqual(result.used, "a")
        self.assertEqual(len(result.attempts), 1)
        self.assertFalse(result.degraded)

    def test_degrades_to_next_provider(self):
        resolver = Resolver([CallableProvider("a", boom), CallableProvider("b", lambda appid: record())])
        result = resolver.resolve(550)
        self.assertEqual(result.used, "b")
        self.assertTrue(result.degraded)
        self.assertFalse(result.attempts[0].ok)
        self.assertIn("RuntimeError", result.attempts[0].error)

    def test_none_means_miss_not_success(self):
        resolver = Resolver([CallableProvider("a", lambda appid: None), CallableProvider("b", lambda appid: record())])
        result = resolver.resolve(550)
        self.assertEqual(result.used, "b")
        self.assertEqual(result.attempts[0].error, "no data")

    def test_falls_back_to_cache(self):
        catalog = Catalog(":memory:")
        try:
            catalog.upsert(record())
            resolver = Resolver([CallableProvider("a", boom)], cache=catalog)
            result = resolver.resolve(550)
            self.assertEqual(result.used, "cache")
            self.assertTrue(result.record.manifest_for(551))
        finally:
            catalog.close()

    def test_raises_when_everything_fails(self):
        resolver = Resolver([CallableProvider("a", boom), CallableProvider("b", lambda appid: None)])
        with self.assertRaises(ResolveError) as ctx:
            resolver.resolve(550)
        self.assertIn("550", str(ctx.exception))
        self.assertEqual(len(ctx.exception.attempts), 2)

    def test_success_is_stored_in_cache(self):
        catalog = Catalog(":memory:")
        try:
            resolver = Resolver([CallableProvider("a", lambda appid: record())], cache=catalog)
            resolver.resolve(550)
            self.assertEqual(catalog.stats()["apps"], 1)
        finally:
            catalog.close()

    def test_attempt_payload(self):
        resolver = Resolver([CallableProvider("a", lambda appid: record())])
        payload = resolver.resolve(550).as_dict()
        self.assertEqual(payload["used"], "a")
        self.assertTrue(payload["attempts"][0]["ok"])


if __name__ == "__main__":
    unittest.main()
