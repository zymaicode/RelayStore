"""Tests for the manifest mirror fallback."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.manifest import parse_manifest
from steam_research.sources.manifest_mirror import ManifestMirror, MirrorError

FIXTURE = (ROOT / "tests" / "fixtures" / "manifest" / "3dmark-1276160.manifest").read_bytes()
GID = "8215949335091262124"


class MirrorTest(unittest.TestCase):
    def test_url_for(self):
        mirror = ManifestMirror(repos=("a/b",), fetch=lambda url: b"")
        self.assertEqual(
            mirror.url_for("a/b", 1276160, GID),
            "https://raw.githubusercontent.com/a/b/main/1276160_" + GID + ".manifest",
        )

    def test_first_repo_wins(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return FIXTURE

        mirror = ManifestMirror(repos=("a/b",), fetch=fetch)
        manifest, url = mirror.get(1276160, GID)
        self.assertEqual(len(manifest.files), 21)
        self.assertIn("a/b", url)
        self.assertEqual(len(calls), 1)

    def test_falls_through_failures(self):
        def fetch(url):
            if "/a/" in url:
                raise OSError("404")
            return FIXTURE

        mirror = ManifestMirror(repos=("a/b", "c/d"), fetch=fetch)
        manifest, url = mirror.get(1276160, GID)
        self.assertIn("c/d", url)
        self.assertEqual(mirror.attempts[0].status, "OSError")

    def test_all_fail(self):
        def fetch(url):
            raise OSError("404")

        mirror = ManifestMirror(repos=("a/b",), fetch=fetch)
        with self.assertRaises(MirrorError):
            mirror.get(1276160, GID)

    def test_empty_payload_is_not_success(self):
        mirror = ManifestMirror(repos=("a/b", "c/d"), fetch=lambda url: b"" if "/a/" in url else FIXTURE)
        _, url = mirror.get(1276160, GID)
        self.assertIn("c/d", url)


if __name__ == "__main__":
    unittest.main()
