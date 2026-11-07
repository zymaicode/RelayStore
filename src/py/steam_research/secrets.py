"""Resolve secrets from the environment or backup/private/.env (never tracked)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

DEFAULT_ENV_FILE = Path("backup/private/.env")


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE file; comments, blanks and noise are ignored."""
    resolved = Path(path)
    if not resolved.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in resolved.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.lower().startswith("export "):
            key = key[7:].strip()
        if not key:
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


def resolve_secret(
    name: str,
    *,
    env_file: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    """Environment first, then the private .env file. Blank values fall through."""
    env = os.environ if environ is None else environ
    from_env = (env.get(name) or "").strip()
    if from_env:
        return from_env
    source = DEFAULT_ENV_FILE if env_file is None else Path(env_file)
    from_file = (parse_env_file(source).get(name) or "").strip()
    return from_file or None
