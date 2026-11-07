"""Fetch .manifest files through the hubcapmanifest (Morrenus) API (M1-T10)."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

DEFAULT_BASE = "https://hubcapmanifest.com/api/v1/generate/manifest"


class HubcapError(ValueError):
    """Raised when the hubcap API cannot deliver a manifest file."""


class HubcapClient:
    """Thin HTTP client with a content cache; injectable fetch for tests."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE,
        fetch: Callable[[str], bytes] | None = None,
        cache_dir: str | Path | None = None,
        timeout: float = 30.0,
        max_bytes: int | None = None,
        user_agent: str = "steam-research/0.1",
    ):
        if not api_key or not str(api_key).strip():
            raise HubcapError("api_key is required")
        self.api_key = str(api_key).strip()
        self.base_url = base_url
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.user_agent = user_agent
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._fetch = fetch or self._http_fetch
        self.calls = 0

    def _http_fetch(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read()

    def url_for(self, depot_id: int, manifest_id: str) -> str:
        if int(depot_id) <= 0:
            raise HubcapError("depot_id must be positive")
        gid = str(manifest_id).strip()
        if not gid.isdigit():
            raise HubcapError("manifest_id must be numeric: " + repr(manifest_id))
        query = urllib.parse.urlencode(
            {
                "depot_id": int(depot_id),
                "manifest_id": gid,
                "api_key": self.api_key,
            }
        )
        return self.base_url + "?" + query

    def cache_path(self, depot_id: int, manifest_id: str) -> Path | None:
        if self.cache_dir is None:
            return None
        digest = hashlib.sha256(
            (str(int(depot_id)) + ":" + str(manifest_id)).encode("utf-8")
        ).hexdigest()[:12]
        return self.cache_dir / ("hubcap-" + str(int(depot_id)) + "-" + str(manifest_id) + "-" + digest + ".manifest")

    def fetch_manifest(self, depot_id: int, manifest_id: str) -> Path:
        """Download (or reuse) one manifest file; returns its local path."""
        url = self.url_for(depot_id, manifest_id)
        target = self.cache_path(depot_id, manifest_id)
        if target is not None and target.is_file() and target.stat().st_size > 0:
            return target

        self.calls += 1
        try:
            payload = self._fetch(url)
        except Exception as exc:  # noqa: BLE001 - surfaced as HubcapError
            raise HubcapError(
                "fetch failed for depot " + str(depot_id) + ": " + type(exc).__name__
            ) from exc
        if not payload:
            raise HubcapError("empty manifest response for depot " + str(depot_id))
        if self.max_bytes is not None and len(payload) > self.max_bytes:
            raise HubcapError(
                "manifest larger than max_bytes (" + str(len(payload)) + " > " + str(self.max_bytes) + ")"
            )

        if target is None:
            raise HubcapError("no cache_dir configured: refusing to drop bytes on the floor")
        tmp = target.with_suffix(".part")
        tmp.write_bytes(payload)
        tmp.replace(target)
        return target

KEY_RE = re.compile(r"^smm_[0-9a-f]{96}$")


def is_valid_key(key: str | None) -> bool:
    """Local format check: smm_ + 96 lowercase hex chars (100 total)."""
    return bool(key) and bool(KEY_RE.match(str(key).strip()))


def stats_url(api_key: str) -> str:
    return (
        "https://hubcapmanifest.com/api/v1/user/stats?api_key="
        + urllib.parse.quote(str(api_key).strip(), safe="")
    )


def _default_get(url: str, timeout: float, user_agent: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def hubcap_stats(
    api_key: str,
    *,
    fetch: Callable[[str], bytes] | None = None,
    timeout: float = 20.0,
    user_agent: str = "steam-research/0.1",
) -> dict:
    """Validate the key format, then read quota / expiry from /api/v1/user/stats."""
    key = str(api_key).strip()
    if not is_valid_key(key):
        raise HubcapError("invalid key format: expected smm_ + 96 lowercase hex chars")
    getter = fetch or (lambda url: _default_get(url, timeout, user_agent))
    try:
        raw = getter(stats_url(key))
    except Exception as exc:  # noqa: BLE001 - surfaced as HubcapError
        raise HubcapError("stats request failed: " + type(exc).__name__) from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise HubcapError("stats response is not JSON") from exc
    if not isinstance(payload, dict):
        raise HubcapError("stats response is not a JSON object")
    return {
        "username": payload.get("username"),
        "daily_usage": int(payload.get("daily_usage") or 0),
        "daily_limit": int(payload.get("daily_limit") or 0),
        "can_make_requests": bool(payload.get("can_make_requests")),
        "expires_at": payload.get("api_key_expires_at"),
        "raw": payload,
    }
