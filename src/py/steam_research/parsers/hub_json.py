"""Normalise ManifestHub-style JSON payloads (M1-T02).

Observed shapes (verified against the open-source snapshots, 2026-11-06):

* tokens          - appaccesstokens.json: flat map {appid: "digits"}
* depot_keys      - depotkeys.json: flat map {depot_id: "40-hex"}
* manifest_map    - {appid: {depot_id: manifest_gid}} (optionally nested)
* manifest_record - {appid, name, depots: [...]} (API style)

Shape detection is value-based on purpose: the token and key maps are both
flat numeric-key maps, only the value format tells them apart.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..model import AccessToken, AppRecord, DepotKey, ManifestRef

TOKEN_SOURCE = "manifesthub.tokens"
KEY_SOURCE = "manifesthub.depotkeys"
MANIFEST_SOURCE = "manifesthub"

_HEX = set("0123456789abcdefABCDEF")


class HubJsonError(ValueError):
    """Raised when a hub JSON payload does not match a known shape."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _is_hex(value: str) -> bool:
    return len(value) >= 16 and len(value) % 2 == 0 and all(ch in _HEX for ch in value)


def _is_gid(value: str) -> bool:
    return value.isdigit() and 10 <= len(value) <= 20


def detect_json_shape(payload: Any) -> str:
    """Return one of: tokens | depot_keys | manifest_map | manifest_record."""
    if not isinstance(payload, Mapping):
        raise HubJsonError("payload is not a JSON object")
    if not payload:
        raise HubJsonError("payload is an empty JSON object")

    lowered = {str(key).lower() for key in payload}
    if "appid" in lowered or "app_id" in lowered:
        return "manifest_record"

    values = list(payload.values())
    if any(isinstance(value, Mapping) for value in values):
        return "manifest_map"
    if all(isinstance(value, str) and _is_hex(value.strip()) for value in values):
        return "depot_keys"
    if all(isinstance(value, str) and value.strip().isdigit() for value in values):
        return "tokens"
    raise HubJsonError("unrecognised JSON shape")


def parse_access_tokens(
    payload: Any,
    *,
    source: str = TOKEN_SOURCE,
    fetched_at: str | None = None,
) -> tuple[AccessToken, ...]:
    """Parse a flat {appid: token} map."""
    if not isinstance(payload, Mapping):
        raise HubJsonError("app access tokens payload is not a JSON object")
    stamp = fetched_at or _now()
    tokens: list[AccessToken] = []
    for raw_appid, raw_token in payload.items():
        key = str(raw_appid).strip()
        if not key.isdigit():
            raise HubJsonError("appid must be numeric, got " + repr(raw_appid))
        token = str(raw_token).strip()
        if not token or not token.isdigit():
            raise HubJsonError("invalid app access token for appid " + key)
        tokens.append(
            AccessToken(appid=int(key), token=token, source=source, fetched_at=stamp)
        )
    if not tokens:
        raise HubJsonError("no app access tokens found")
    return tuple(sorted(tokens, key=lambda item: item.appid))


def parse_depot_keys(
    payload: Any,
    *,
    source: str = KEY_SOURCE,
    fetched_at: str | None = None,
) -> tuple[DepotKey, ...]:
    """Parse a flat {depot_id: hex_key} map."""
    if not isinstance(payload, Mapping):
        raise HubJsonError("depot keys payload is not a JSON object")
    stamp = fetched_at or _now()
    keys: list[DepotKey] = []
    for raw_depot, raw_key in payload.items():
        key = str(raw_depot).strip()
        if not key.isdigit():
            raise HubJsonError("depot id must be numeric, got " + repr(raw_depot))
        hex_key = str(raw_key).strip()
        if not _is_hex(hex_key):
            raise HubJsonError("invalid depot key for depot " + key)
        keys.append(
            DepotKey(
                depot_id=int(key),
                key_hex=hex_key.lower(),
                source=source,
                fetched_at=stamp,
            )
        )
    if not keys:
        raise HubJsonError("no depot keys found")
    return tuple(sorted(keys, key=lambda item: item.depot_id))


def _depot_entries(body: Mapping[str, Any]) -> dict[int, tuple[str | None, int | None]]:
    entries: dict[int, tuple[str | None, int | None]] = {}
    for raw_depot, value in body.items():
        depot = str(raw_depot).strip()
        if not depot.isdigit():
            raise HubJsonError("depot id must be numeric, got " + repr(raw_depot))
        gid: Any = value
        size: Any = None
        if isinstance(value, Mapping):
            gid = value.get("manifest") or value.get("gid") or value.get("manifest_gid")
            size = value.get("size")
        if gid is None:
            entries[int(depot)] = (None, None)
            continue
        gid_text = str(gid).strip()
        if not _is_gid(gid_text):
            raise HubJsonError(
                "invalid manifest gid " + repr(gid) + " for depot " + depot
            )
        entries[int(depot)] = (gid_text, int(size) if size is not None else None)
    return entries


def parse_manifest_map(
    payload: Any,
    appid: int | None = None,
    *,
    source: str = MANIFEST_SOURCE,
    fetched_at: str | None = None,
) -> AppRecord:
    """Parse {appid: {depot_id: gid}} into an AppRecord."""
    if not isinstance(payload, Mapping):
        raise HubJsonError("manifest map payload is not a JSON object")
    if appid is None:
        if len(payload) != 1:
            raise HubJsonError(
                "payload holds " + str(len(payload)) + " apps; pass appid explicitly"
            )
        appid = int(str(next(iter(payload))).strip())
    body = None
    for key, value in payload.items():
        if str(key).strip() == str(appid):
            body = value
            break
    if not isinstance(body, Mapping):
        raise HubJsonError("no depot map for appid " + str(appid))

    stamp = fetched_at or _now()
    entries = _depot_entries(body)
    manifests = tuple(
        ManifestRef(
            appid=appid,
            depot_id=depot,
            gid=gid,
            size=size,
            source=source,
            fetched_at=stamp,
        )
        for depot, (gid, size) in sorted(entries.items())
        if gid
    )
    return AppRecord(appid=appid, depots=tuple(sorted(entries)), manifests=manifests)


def _first(mapping: Mapping[str, Any], names: tuple[str, ...]) -> Any:
    lowered = {str(key).lower(): value for key, value in mapping.items()}
    for name in names:
        if name in lowered:
            return lowered[name]
    return None


def parse_manifest_record(
    payload: Any,
    *,
    source: str = MANIFEST_SOURCE,
    fetched_at: str | None = None,
) -> AppRecord:
    """Parse a record payload: {appid, name, depots: [...]}."""
    if not isinstance(payload, Mapping):
        raise HubJsonError("manifest record payload is not a JSON object")
    appid_value = _first(payload, ("appid", "app_id", "app", "id"))
    if appid_value is None or not str(appid_value).strip().isdigit():
        raise HubJsonError("manifest record has no numeric appid")
    appid = int(str(appid_value).strip())
    name = _first(payload, ("name", "title"))

    raw_depots = _first(payload, ("depots", "manifests", "installed_depots")) or []
    stamp = fetched_at or _now()
    entries: dict[int, tuple[str | None, int | None]] = {}
    if isinstance(raw_depots, Mapping):
        entries = _depot_entries(raw_depots)
    elif isinstance(raw_depots, list):
        for item in raw_depots:
            if not isinstance(item, Mapping):
                raise HubJsonError("depot entry is not an object")
            depot_value = _first(item, ("depot_id", "depot", "id"))
            if depot_value is None or not str(depot_value).strip().isdigit():
                raise HubJsonError("depot entry has no numeric depot_id")
            depot = int(str(depot_value).strip())
            gid_value = _first(
                item, ("manifest", "manifest_gid", "gid", "manifestid")
            )
            size_value = _first(item, ("size", "bytes"))
            gid = None
            if gid_value is not None:
                gid = str(gid_value).strip()
                if not _is_gid(gid):
                    raise HubJsonError("invalid manifest gid " + repr(gid_value))
            entries[depot] = (gid, int(size_value) if size_value is not None else None)
    else:
        raise HubJsonError("depots must be an object or a list")

    manifests = tuple(
        ManifestRef(
            appid=appid,
            depot_id=depot,
            gid=gid,
            size=size,
            source=source,
            fetched_at=stamp,
        )
        for depot, (gid, size) in sorted(entries.items())
        if gid
    )
    return AppRecord(
        appid=appid,
        name=str(name) if name is not None else None,
        depots=tuple(sorted(entries)),
        manifests=manifests,
    )


def parse_hub_json(
    payload: Any,
    appid: int | None = None,
    *,
    source: str | None = None,
    fetched_at: str | None = None,
):
    """Detect the shape and parse it; returns AppRecord or a tuple of models."""
    shape = detect_json_shape(payload)
    if shape == "tokens":
        return parse_access_tokens(
            payload, source=source or TOKEN_SOURCE, fetched_at=fetched_at
        )
    if shape == "depot_keys":
        return parse_depot_keys(
            payload, source=source or KEY_SOURCE, fetched_at=fetched_at
        )
    if shape == "manifest_map":
        return parse_manifest_map(
            payload, appid, source=source or MANIFEST_SOURCE, fetched_at=fetched_at
        )
    return parse_manifest_record(
        payload, source=source or MANIFEST_SOURCE, fetched_at=fetched_at
    )


def parse_hub_json_file(
    path: str | Path,
    appid: int | None = None,
    *,
    source: str | None = None,
    fetched_at: str | None = None,
):
    """Read a JSON file (UTF-8 with BOM tolerated) and parse it."""
    resolved = Path(path)
    text = resolved.read_text(encoding="utf-8-sig")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise HubJsonError(
            "invalid JSON in " + str(resolved) + ": line " + str(exc.lineno)
        ) from exc
    return parse_hub_json(payload, appid, source=source, fetched_at=fetched_at)
