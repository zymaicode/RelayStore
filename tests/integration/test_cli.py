"""Integration tests for the CLI surface (M1-T07)."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.cli import main  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
ACF = FIXTURES / "acf" / "appmanifest_550.sample.acf"
BAD_ACF = FIXTURES / "acf" / "malformed_bad_token.acf"


def run(argv):
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "catalog.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_then_query(self):
        code, out, _ = run(["import-acf", str(ACF), "--db", self.db])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["imported"][0]["appid"], 550)
        self.assertEqual(payload["stats"]["apps"], 1)

        code, out, _ = run(["query", "550", "--db", self.db, "--offline"])
        self.assertEqual(code, 0)
        record = json.loads(out)
        self.assertTrue(record["found"])
        self.assertEqual(record["depots"], [551, 552])
        self.assertEqual(record["manifests"][0]["gid"], "314878501352141828")
        self.assertTrue(record["offline"])

    def test_query_missing_appid_exits_3(self):
        code, out, _ = run(["query", "999", "--db", self.db])
        self.assertEqual(code, 3)
        self.assertFalse(json.loads(out)["found"])

    def test_doctor(self):
        run(["import-acf", str(ACF), "--db", self.db])
        code, out, _ = run(["doctor", "--db", self.db])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertTrue(payload["db_exists"])
        self.assertEqual(payload["stats"]["manifests"], 2)

    def test_report_writes_markdown(self):
        out_dir = Path(self.tmp.name) / "reports"
        code, out, _ = run(
            ["report", "--repo", "hub-a=" + str(FIXTURES), "--out", str(out_dir)]
        )
        self.assertEqual(code, 0)
        target = Path(json.loads(out)["report"])
        self.assertTrue(target.is_file())
        text = target.read_text(encoding="utf-8")
        self.assertIn("ManifestHub coverage report", text)
        self.assertIn("| hub-a |", text)

    def test_bad_acf_exits_2(self):
        code, _, err = run(["import-acf", str(BAD_ACF), "--db", self.db])
        self.assertEqual(code, 2)
        self.assertIn("error:", err)

    def test_no_command_prints_help(self):
        code, out, _ = run([])
        self.assertEqual(code, 2)
        self.assertIn("usage", out.lower())

    def test_bad_repo_argument(self):
        code, _, err = run(["report", "--repo", "broken", "--out", self.tmp.name])
        self.assertEqual(code, 2)
        self.assertIn("NAME=PATH", err)


if __name__ == "__main__":
    unittest.main()
