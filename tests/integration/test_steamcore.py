"""Cross-checks the Go prototype (tools/steamcore) against the Python decoder."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.depot import decode_chunk

BINARY = ROOT / "tools" / "steamcore" / "steamcore.exe"
CHUNK = ROOT / "tests" / "reports" / "sample-chunk.bin"
KEYS = ROOT / "src" / "data" / "keys" / "merged.json"
EXPECTED_SHA1 = "391d06c90755f477114c8c24328a99c907b18f20"


@unittest.skipUnless(BINARY.is_file() and CHUNK.is_file() and KEYS.is_file(), "Go prototype fixture missing")
class GoCoreTest(unittest.TestCase):
    def test_go_matches_python(self):
        key = json.loads(KEYS.read_text(encoding="utf-8"))["1276160"]
        completed = subprocess.run(
            [str(BINARY), "decode", "-in", str(CHUNK), "-key", key, "-sha1", EXPECTED_SHA1, "-iter", "1"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("match=true", completed.stdout)

    def test_manifest_parity(self):
        """Go manifest parser must agree with the Python one (files/chunks/bytes)."""
        from steam_research.manifest import parse_manifest

        manifest_path = ROOT / "tests" / "fixtures" / "manifest" / "3dmark-1276160.manifest"
        completed = subprocess.run(
            [str(BINARY), "manifest", "-in", str(manifest_path), "-json"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        go_stats = json.loads(completed.stdout)
        python_manifest = parse_manifest(manifest_path.read_bytes())
        self.assertEqual(go_stats["files"], len(python_manifest.files))
        self.assertEqual(go_stats["chunks"], len(set(c.sha for c in python_manifest.chunks())))
        self.assertEqual(go_stats["bytes"], sum(f.size for f in python_manifest.files))

    def test_coverage_matches_python(self):
        """Go coverage must agree with the Python coverage report for the same appid."""
        import subprocess as sp

        from steam_research.coverage import check_coverage
        from steam_research.keys import Keyring
        from steam_research.sources.manifest_index import ManifestIndex

        keys_path = ROOT / "src" / "data" / "keys" / "merged.json"
        index_path = ROOT / "tests" / "reports" / "mirror-index.json"
        cache_dir = ROOT / "src" / "data" / "appinfo"
        if not (cache_dir / "480.json").is_file():
            self.skipTest("appinfo cache for 480 missing")
        completed = sp.run(
            [
                str(BINARY), "coverage",
                "-appid", "480",
                "-keys", str(keys_path),
                "-index", str(index_path),
                "-cache", str(cache_dir),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        go_report = json.loads(completed.stdout)
        python_report = check_coverage(
            480,
            keys=Keyring.from_json_files([keys_path]),
            index=ManifestIndex.load(index_path),
            appinfo_cache=str(cache_dir),
        ).as_dict()
        self.assertEqual(go_report["downloadable"], python_report["downloadable"])
        self.assertEqual(go_report["depots_total"], python_report["depots_total"])
        self.assertEqual(go_report["size_bytes"], python_report["size_bytes"])

    def test_python_matches_expected(self):
        import hashlib

        key = bytes.fromhex(json.loads(KEYS.read_text(encoding="utf-8"))["1276160"])
        plain = decode_chunk(CHUNK.read_bytes(), key)
        self.assertEqual(hashlib.sha1(plain).hexdigest(), EXPECTED_SHA1)


if __name__ == "__main__":
    unittest.main()
