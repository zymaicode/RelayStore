"""Parse payloads from https://api.steamcmd.net/v1/info/<appid>.

Shape (verified 2026-11-05):
    {"status": "success", "data": {"550": {"common": {...}, "depots": {
        "551": {"manifests": {"public": {"gid": "314878501352141828",
                                         "size": "11329675570"}}},
        "branches": {...}  # non-numeric keys must be ignored
    }}}}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..model import AppRecord, ManifestRef

SOURCE = "steamcmd"


class ParseError(ValueError):
    """Raised when a payload does not look like a steamcmd appinfo response."""

    def __init__(self, message: str, *, appid: int | None = None, path: str | None = None):
        self.appid = appid
        self.path = path
        super().__init__(f"{message} (appid={appid}, path={path})")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _to_int(value: object, field_name: str, *, appid: int, depot_id: int | None = None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ParseError(f"invalid {field_name}: {value!r}", appid=appid)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise ParseError(
        f"invalid {field_name}: {value!r} (depot={depot_id})", appid=appid
    )


def parse_appinfo(
    payload: dict,
    appid: int | None = None,
    *,
    source_url: str | None = None,
    fetched_at: str | None = None,
    path: str | None = None,
) -> AppRecord:
    """Turn one steamcmd appinfo payload into an AppRecord."""
    if not isinstance(payload, dict):
        raise ParseError("payload is not an object", appid=appid, path=path)

    data = payload.get("data")
    if not isinstance(data, dict) or not data:
        raise ParseError("payload has no data object", appid=appid, path=path)

    if appid is None:
        keys = list(data.keys())
        if len(keys) != 1:
            raise ParseError(f"ambiguous payload: {len(keys)} apps", path=None)
        appid = _to_int(keys[0], "appid", appid=0)
    if appid is None:
        raise ParseError("appid is required", appid=appid)

    entry = data.get(str(appid))
    if not isinstance(entry, dict):
        raise ParseError("app not present in payload", appid=appid, path=path)
    if entry.get("_missing_token"):
        raise ParseError("steamcmd reports _missing_token for this app", appid=appid)

    common = entry.get("common") if isinstance(entry.get("common"), dict) else {}
    name = common.get("name") if isinstance(common.get("name"), str) else None

    depots_obj = entry.get("depots")
    if not isinstance(depots_obj, dict):
        raise ParseError("app has no depots object", appid=appid)

    stamp = fetched_at or _now()
    url = source_url or f"https://api.steamcmd.net/v1/info/{appid}"
    depot_ids: list[int] = []
    refs: list[ManifestRef] = []

    for key, depot in depots_obj.items():
        if not isinstance(key, str) or not key.isdigit():
            continue
        if not isinstance(depot, dict):
            continue
        depot_id = int(key)
        depot_ids.append(depot_id)

        manifests = depot.get("manifests")
        public = manifests.get("public") if isinstance(manifests, dict) else None
        if not isinstance(public, dict):
            continue

        gid = public.get("gid")
        if not isinstance(gid, str) or not gid.isdigit():
            raise ParseError(
                f"invalid manifest gid: {gid!r} (depot={depot_id})", appid=appid
            )
        refs.append(
            ManifestRef(
                appid=appid,
                depot_id=depot_id,
                gid=gid,
                size=_to_int(public.get("size"), "size", appid=appid, depot_id=depot_id),
                sha1=public.get("sha") if isinstance(public.get("sha"), str) else None,
                source=SOURCE,
                source_url=url,
                fetched_at=stamp,
            )
        )

    if not depot_ids:
        raise ParseError("app has no numeric depots", appid=appid)

    return AppRecord(
        appid=appid,
        name=name,
        depots=tuple(sorted(depot_ids)),
        manifests=tuple(sorted(refs, key=lambda r: r.depot_id)),
    )


def parse_appinfo_file(path: str | Path, appid: int | None = None, **kwargs) -> AppRecord:
    """Load an appinfo JSON file (fixture or cached response) and parse it."""
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ParseError("fixture not found", appid=appid, path=str(p)) from exc
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc.msg}", appid=appid, path=str(p)) from exc
    return parse_appinfo(payload, appid, path=str(p), **kwargs)