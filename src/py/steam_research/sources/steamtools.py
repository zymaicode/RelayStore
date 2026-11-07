"""steamtools.games public API: lua + key.vdf for any appid in their DB."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

DEFAULT_BASE = "https://steamtools.games"


class SteamToolsError(ValueError):
    """Raised when the steamtools.games API cannot be reached or parsed."""


@dataclass
class SteamToolsProbe:
    appid: int
    in_db: bool | None = None  # None = unknown (transport/HTTP error)
    message: str = ""
    lua_url: str = ""
    key_url: str = ""
    download_url: str = ""

    def as_dict(self) -> dict:
        return {
            "appid": self.appid,
            "in_db": self.in_db,
            "message": self.message,
            "lua_url": self.lua_url,
            "key_url": self.key_url,
            "download_url": self.download_url,
        }


def _default_post(url: str, payload: dict, timeout: float) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "steam-research/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        if exc.code not in (403, 429, 500, 502, 503):
            raise
        raise
    except Exception:  # noqa: BLE001 - msys python lacks a CA bundle: retry unverified
        context = ssl._create_unverified_context()  # noqa: SLF001
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return json.loads(response.read().decode("utf-8", "replace"))


def fetch_text(url: str, *, timeout: float = 30.0) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "steam-research/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001 - retry without CA verification
        context = ssl._create_unverified_context()  # noqa: SLF001
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return response.read().decode("utf-8", "replace")


def probe(
    appid: int,
    *,
    base: str = DEFAULT_BASE,
    post: Callable[[str, dict, float], dict] | None = None,
    timeout: float = 25.0,
) -> SteamToolsProbe:
    """Ask steamtools.games whether an appid is in their manifest database."""
    result = SteamToolsProbe(appid=int(appid))
    payload = (post or _default_post)(base + "/api/generate", {"appId": str(int(appid))}, timeout)
    if not isinstance(payload, dict):
        result.message = "unexpected payload"
        return result
    code = payload.get("code")
    message = str(payload.get("message") or "")
    result.message = message
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if code == 0 and data:
        result.in_db = True
        result.lua_url = str(data.get("luaUrl") or "")
        result.key_url = str(data.get("keyVdfUrl") or "")
        result.download_url = str(data.get("downloadUrl") or "")
    elif message.startswith("not_in_db"):
        result.in_db = False
    return result
