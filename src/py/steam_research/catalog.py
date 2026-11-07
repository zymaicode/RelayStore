"""SQLite catalog: manifests, tokens and depot keys (M1-T04)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .model import AccessToken, AppRecord, DepotKey, ManifestRef

SCHEMA = """
CREATE TABLE IF NOT EXISTS apps (
    appid INTEGER PRIMARY KEY,
    name TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS manifests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    appid INTEGER NOT NULL,
    depot_id INTEGER NOT NULL,
    gid TEXT NOT NULL,
    size INTEGER,
    sha1 TEXT,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL,
    UNIQUE (appid, depot_id, gid)
);
CREATE INDEX IF NOT EXISTS idx_manifests_app ON manifests (appid, depot_id);
CREATE TABLE IF NOT EXISTS tokens (
    appid INTEGER PRIMARY KEY,
    token TEXT NOT NULL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS depot_keys (
    depot_id INTEGER PRIMARY KEY,
    key_hex TEXT NOT NULL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Catalog:
    """Thin, idempotent wrapper over a SQLite file (history friendly)."""

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # -- lifecycle -----------------------------------------------------
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Catalog":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- writes --------------------------------------------------------
    def upsert(self, record: AppRecord) -> int:
        """Insert/refresh one AppRecord. Returns the number of manifest rows touched."""
        stamp = _now()
        self._conn.execute(
            "INSERT INTO apps (appid, name, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(appid) DO UPDATE SET "
            "name = COALESCE(excluded.name, apps.name), updated_at = excluded.updated_at",
            (record.appid, record.name, stamp),
        )
        for ref in record.manifests:
            self._conn.execute(
                "INSERT INTO manifests "
                "(appid, depot_id, gid, size, sha1, source, source_url, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(appid, depot_id, gid) DO UPDATE SET "
                "size = excluded.size, sha1 = excluded.sha1, source = excluded.source, "
                "source_url = excluded.source_url, fetched_at = excluded.fetched_at",
                (
                    ref.appid,
                    ref.depot_id,
                    ref.gid,
                    ref.size,
                    ref.sha1,
                    ref.source,
                    ref.source_url,
                    ref.fetched_at or stamp,
                ),
            )
        self._conn.commit()
        return len(record.manifests)

    def upsert_tokens(self, tokens: Iterable[AccessToken]) -> int:
        rows = list(tokens)
        for token in rows:
            self._conn.execute(
                "INSERT INTO tokens (appid, token, source, fetched_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(appid) DO UPDATE SET token = excluded.token, "
                "source = excluded.source, fetched_at = excluded.fetched_at",
                (token.appid, token.token, token.source, token.fetched_at or _now()),
            )
        self._conn.commit()
        return len(rows)

    def upsert_depot_keys(self, keys: Iterable[DepotKey]) -> int:
        rows = list(keys)
        for key in rows:
            self._conn.execute(
                "INSERT INTO depot_keys (depot_id, key_hex, source, fetched_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(depot_id) DO UPDATE SET key_hex = excluded.key_hex, "
                "source = excluded.source, fetched_at = excluded.fetched_at",
                (key.depot_id, key.key_hex, key.source, key.fetched_at or _now()),
            )
        self._conn.commit()
        return len(rows)

    # -- reads ---------------------------------------------------------
    def query(self, appid: int) -> AppRecord | None:
        app = self._conn.execute(
            "SELECT appid, name FROM apps WHERE appid = ?", (int(appid),)
        ).fetchone()
        rows = self._conn.execute(
            "SELECT * FROM manifests WHERE id IN ("
            "  SELECT MAX(id) FROM manifests WHERE appid = ? GROUP BY depot_id"
            ") ORDER BY depot_id",
            (int(appid),),
        ).fetchall()
        if app is None and not rows:
            return None
        manifests = tuple(
            ManifestRef(
                appid=row["appid"],
                depot_id=row["depot_id"],
                gid=row["gid"],
                size=row["size"],
                sha1=row["sha1"],
                source=row["source"],
                source_url=row["source_url"],
                fetched_at=row["fetched_at"],
            )
            for row in rows
        )
        return AppRecord(
            appid=int(appid),
            name=app["name"] if app is not None else None,
            depots=tuple(sorted({ref.depot_id for ref in manifests})),
            manifests=manifests,
        )

    def history(self, appid: int, depot_id: int | None = None) -> list[dict]:
        if depot_id is None:
            rows = self._conn.execute(
                "SELECT * FROM manifests WHERE appid = ? ORDER BY id", (int(appid),)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM manifests WHERE appid = ? AND depot_id = ? ORDER BY id",
                (int(appid), int(depot_id)),
            ).fetchall()
        return [dict(row) for row in rows]

    def token_for(self, appid: int) -> str | None:
        row = self._conn.execute(
            "SELECT token FROM tokens WHERE appid = ?", (int(appid),)
        ).fetchone()
        return row["token"] if row else None

    def depot_key(self, depot_id: int) -> str | None:
        row = self._conn.execute(
            "SELECT key_hex FROM depot_keys WHERE depot_id = ?", (int(depot_id),)
        ).fetchone()
        return row["key_hex"] if row else None

    def stats(self) -> dict:
        result = {}
        for table in ("apps", "manifests", "tokens", "depot_keys"):
            row = self._conn.execute("SELECT COUNT(*) AS n FROM " + table).fetchone()
            result[table] = int(row["n"])
        return result

    def sources(self) -> dict:
        rows = self._conn.execute(
            "SELECT source, COUNT(*) AS n FROM manifests GROUP BY source ORDER BY source"
        ).fetchall()
        return {row["source"]: int(row["n"]) for row in rows}
