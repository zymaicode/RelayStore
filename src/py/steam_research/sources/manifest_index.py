"""Local index of mirror manifests: depot_id -> gid -> repos that have it."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_NAME = re.compile(r"^(\d+)_(\d+)\.manifest$")


class ManifestIndex:
    """depot -> {gid -> [repos]}; a repo-less gid simply has an empty list."""

    def __init__(
        self,
        entries: "dict[int, dict[str, list[str]]] | None" = None,
        repos: "list[str] | None" = None,
        gids: "dict[int, list[str]] | None" = None,
    ) -> None:
        self.entries: dict[int, dict[str, list[str]]] = dict(entries or {})
        self.repos: list[str] = list(repos or [])
        if gids:  # v1 compatibility: depot -> [gid]
            for depot, values in gids.items():
                for gid in values:
                    self.add(int(depot), str(gid))

    # -- backward compatible view -------------------------------------------
    @property
    def gids(self) -> "dict[int, list[str]]":
        return {depot: list(bucket) for depot, bucket in self.entries.items()}

    def add(self, depot_id: int, gid: str, repo: str = "") -> None:
        bucket = self.entries.setdefault(int(depot_id), {})
        repos = bucket.setdefault(str(gid), [])
        if repo and repo not in repos:
            repos.append(repo)
        if repo and repo not in self.repos:
            self.repos.append(repo)

    def has(self, depot_id: int) -> bool:
        return bool(self.entries.get(int(depot_id)))

    def repos_for(self, depot_id: int, gid: str) -> "list[str]":
        return list(self.entries.get(int(depot_id), {}).get(str(gid), []))

    def candidates(self, depot_id: int, current: str | None = None) -> "list[str]":
        """Current gid first (if known), then other builds newest-first."""
        bucket = list(self.entries.get(int(depot_id), {}))
        bucket.sort(key=lambda value: int(value), reverse=True)
        if current is not None:
            text = str(current)
            if text in bucket:
                bucket.remove(text)
            bucket.insert(0, text)
        return bucket

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def manifest_count(self) -> int:
        return sum(len(bucket) for bucket in self.entries.values())

    # -- io -----------------------------------------------------------------
    @classmethod
    def from_filelist(cls, path: str | Path, repo: str = "") -> "ManifestIndex":
        index = cls()
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            match = _NAME.match(line.strip())
            if match:
                index.add(int(match.group(1)), match.group(2), repo)
        return index

    @classmethod
    def load(cls, path: str | Path) -> "ManifestIndex":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        index = cls()
        if "depots" in payload:  # v2
            for depot, bucket in payload["depots"].items():
                for gid, repos in bucket.items():
                    index.entries[int(depot)] = index.entries.get(int(depot), {})
                    index.entries[int(depot)][str(gid)] = [str(r) for r in repos]
            index.repos = [str(r) for r in payload.get("repos", [])]
            return index
        for depot, gids in payload.items():  # v1: depot -> [gid]
            for gid in gids:
                index.add(int(depot), str(gid))
        return index

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 2,
            "repos": list(self.repos),
            "depots": {
                str(depot): {gid: list(repos) for gid, repos in sorted(bucket.items(), key=lambda kv: int(kv[0]), reverse=True)}
                for depot, bucket in sorted(self.entries.items())
            },
        }
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return target
