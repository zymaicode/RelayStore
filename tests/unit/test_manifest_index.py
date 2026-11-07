"""Tests for the manifest index and any-build fallback."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.sources.manifest_index import ManifestIndex
from steam_research.sources.manifest_mirror import ManifestMirror, MirrorError


class IndexTest(unittest.TestCase):
    def test_from_filelist(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "files.txt"
            path.write_text(
                "1276160_8215949335091262124.manifest\n"
                "1276160_1111111111111111111.manifest\n"
                "notamanifest.txt\n",
                encoding="utf-8",
            )
            index = ManifestIndex.from_filelist(path)
        self.assertEqual(len(index), 1)
        self.assertEqual(set(index.gids[1276160]), {"8215949335091262124", "1111111111111111111"})

    def test_candidates_puts_current_first_then_newest(self):
        index = ManifestIndex(gids={5: ["100", "300", "200"]})
        self.assertEqual(index.candidates(5, "200"), ["200", "300", "100"])
        self.assertEqual(index.candidates(5), ["300", "200", "100"])

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.json"
            ManifestIndex(gids={7: ["9", "8"]}).save(path)
            loaded = ManifestIndex.load(path)
        self.assertEqual(loaded.gids[7], ["9", "8"])


class FallbackTest(unittest.TestCase):
    def setUp(self):
        self.manifest = (ROOT / "tests" / "fixtures" / "manifest" / "3dmark-1276160.manifest").read_bytes()

    def test_uses_current_when_present(self):
        mirror = ManifestMirror(repos=("a/b",), templates=("https://x/{depot}_{gid}.manifest",), fetch=lambda url: self.manifest)
        index = ManifestIndex(gids={1: ["222", "111"]})
        _, url, used = mirror.get_with_fallback(1, "222", index)
        self.assertEqual(used, "222")
        self.assertIn("222", url)

    def test_falls_back_to_available_build(self):
        seen = []

        def fetch(url):
            seen.append(url)
            if "999" in url:
                raise OSError("404")
            return self.manifest

        mirror = ManifestMirror(repos=("a/b",), templates=("https://x/{depot}_{gid}.manifest",), fetch=fetch)
        index = ManifestIndex(gids={1: ["888", "777"]})
        _, _, used = mirror.get_with_fallback(1, "999", index)
        self.assertEqual(used, "888")
        self.assertTrue(any("999" in url for url in seen))

    def test_no_index_means_single_gid(self):
        mirror = ManifestMirror(repos=("a/b",), templates=("https://x/{depot}_{gid}.manifest",), fetch=lambda url: b"")
        with self.assertRaises(MirrorError):
            mirror.get_with_fallback(1, "999", None)


if __name__ == "__main__":
    unittest.main()
