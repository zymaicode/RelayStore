"""Coverage comparison across ManifestHub snapshots (M1-T08, answers Q1)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class RepoStats:
    name: str
    path: str
    files: int
    lua_files: int
    json_files: int
    tokens: int
    depot_keys: int
    bytes_total: int

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "files": self.files,
            "lua_files": self.lua_files,
            "json_files": self.json_files,
            "tokens": self.tokens,
            "depot_keys": self.depot_keys,
            "bytes_total": self.bytes_total,
        }


def _count_entries(path: Path, max_bytes: int) -> int:
    try:
        if path.stat().st_size > max_bytes:
            return -1
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return -1
    return len(payload) if isinstance(payload, dict) else -1


def scan_repo(
    path: str | Path,
    name: str | None = None,
    *,
    max_json_bytes: int = 64 * 1024 * 1024,
) -> RepoStats:
    """Walk one snapshot tree and count what a hub actually carries."""
    root = Path(path)
    if not root.is_dir():
        raise FileNotFoundError("repo path is not a directory: " + str(root))

    files = lua_files = json_files = 0
    tokens = depot_keys = 0
    bytes_total = 0
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        try:
            size = item.stat().st_size
        except OSError:
            continue
        files += 1
        bytes_total += size
        suffix = item.suffix.lower()
        if suffix == ".lua":
            lua_files += 1
        elif suffix == ".json":
            json_files += 1
            lowered = item.name.lower()
            if lowered.startswith("appaccesstokens"):
                counted = _count_entries(item, max_json_bytes)
                tokens += max(counted, 0)
            elif lowered.startswith("depotkeys"):
                counted = _count_entries(item, max_json_bytes)
                depot_keys += max(counted, 0)

    return RepoStats(
        name=name or root.name,
        path=str(root),
        files=files,
        lua_files=lua_files,
        json_files=json_files,
        tokens=tokens,
        depot_keys=depot_keys,
        bytes_total=bytes_total,
    )


def collect(roots: "Iterable[tuple[str, str | Path]]") -> list[RepoStats]:
    return [scan_repo(path, name) for name, path in roots]


def _human_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return (str(int(size)) if unit == "B" else f"{size:.1f}") + " " + unit
        size /= 1024
    return str(value)


def render_markdown(rows: "Iterable[RepoStats]", *, generated_at: str | None = None) -> str:
    items = list(rows)
    stamp = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# ManifestHub coverage report",
        "",
        "- generated: " + stamp,
        "- repos: " + str(len(items)),
        "",
        "| repo | files | .lua | .json | app tokens | depot keys | size |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in items:
        lines.append(
            "| " + row.name
            + " | " + str(row.files)
            + " | " + str(row.lua_files)
            + " | " + str(row.json_files)
            + " | " + str(row.tokens)
            + " | " + str(row.depot_keys)
            + " | " + _human_bytes(row.bytes_total)
            + " |"
        )
    if items:
        lines.append(
            "| **total** | " + str(sum(r.files for r in items))
            + " | " + str(sum(r.lua_files for r in items))
            + " | " + str(sum(r.json_files for r in items))
            + " | " + str(sum(r.tokens for r in items))
            + " | " + str(sum(r.depot_keys for r in items))
            + " | " + _human_bytes(sum(r.bytes_total for r in items))
            + " |"
        )
    lines += [
        "",
        "> -1 in a count column means the JSON was unreadable or above the size guard.",
        "> Token / key counts come from `appaccesstokens*.json` and `depotkeys*.json` first-level keys.",
        "",
    ]
    return "\n".join(lines)
