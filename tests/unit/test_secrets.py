"""Unit tests for secret resolution (.env + environment) (M1-T10 helper)."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.secrets import parse_env_file, resolve_secret  # noqa: E402


class EnvFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / ".env"

    def tearDown(self):
        self.tmp.cleanup()

    def test_parses_pairs_and_ignores_noise(self):
        self.path.write_text(
            "# comment\n"
            "\n"
            "HUBBCAP_API_KEY=smm_abc\n"
            "QUOTED=\"value with spaces\"\n"
            "EXPORT_LIKE = smm_xyz \n"
            "invalid line without equals\n",
            encoding="utf-8",
        )
        values = parse_env_file(self.path)
        self.assertEqual(values["HUBBCAP_API_KEY"], "smm_abc")
        self.assertEqual(values["QUOTED"], "value with spaces")
        self.assertEqual(values["EXPORT_LIKE"], "smm_xyz")
        self.assertNotIn("invalid line without equals", values)

    def test_missing_file_is_empty(self):
        self.assertEqual(parse_env_file(Path(self.tmp.name) / "nope.env"), {})


class ResolveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / ".env"
        self.path.write_text("HUBBCAP_API_KEY=smm_from_file\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_environment_wins(self):
        value = resolve_secret(
            "HUBBCAP_API_KEY",
            env_file=self.path,
            environ={"HUBBCAP_API_KEY": "smm_from_env"},
        )
        self.assertEqual(value, "smm_from_env")

    def test_falls_back_to_file(self):
        value = resolve_secret("HUBBCAP_API_KEY", env_file=self.path, environ={})
        self.assertEqual(value, "smm_from_file")

    def test_missing_everywhere(self):
        self.assertIsNone(
            resolve_secret("OTHER_KEY", env_file=self.path, environ={})
        )

    def test_blank_environment_value_falls_through(self):
        value = resolve_secret(
            "HUBBCAP_API_KEY", env_file=self.path, environ={"HUBBCAP_API_KEY": "  "}
        )
        self.assertEqual(value, "smm_from_file")


if __name__ == "__main__":
    unittest.main()
