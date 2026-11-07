"""List (and optionally resolve) Xunlei Cloud Drive share links without a login.

Protocol reproduced from the Gopeed extension `cybdarlnig-png/gopeed-extension-xunlei`
(MIT): share listing needs only a locally generated device id + a short-lived
captcha token; transferring/downloading files needs the user own account.
"""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

API_BASE = "https://api-pan.xunlei.com/drive/v1"
CAPTCHA_API = "https://xluser-ssl.xunlei.com/v1/shield/captcha/init"
CLIENT_ID = "Xqp0kJBXWhwaTpB6"
CLIENT_VERSION = "1.92.89"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
PAGE_SIZE = 100
SALTS = (
    "q1FLg",
    "OECaw0higFYs7qCdOWvMEe",
    "1UQvF/CWht+RATnmBnyakvJFHL1jaAb8MRYvdVHQLZ",
    "OV+xWBsbnAehPNmDEUnjcVT",
    "bbuvyCYHdJwBOtJ8Cdeg",
    "9ROgxnyRfQInpATpkchBTZW",
    "vXA2EpRk8",
    "oEd",
    "QCBQwX/",
    "P5NlYzyVtGjJUI/dIzi+SOL+mf0Wl17",
    "7GRbxu7OmpasI841c66J",
    "PEVQN9w+A4wRbGoX",
    "CJ3yz0fu1kqhPDOyL438W",
    "tD75Q",
)


class XunleiError(ValueError):
    """Raised when the share API rejects the request."""


def new_device_id() -> str:
    return os.urandom(16).hex()


def captcha_sign(timestamp: str, device_id: str) -> str:
    current = CLIENT_ID + CLIENT_VERSION + "pan.xunlei.com" + device_id + str(timestamp)
    for salt in SALTS:
        current = hashlib.md5((current + salt).encode("utf-8")).hexdigest()
    return "1." + current


def _opener(request: urllib.request.Request, timeout: float) -> bytes:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except Exception:  # noqa: BLE001 - msys python has no CA bundle
        context = ssl._create_unverified_context()  # noqa: SLF001
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return response.read()


@dataclass
class PanSession:
    """Authenticated session (authorization token from the web client)."""

    device_id: str
    token: str
    authorization: str = ""
    cookie: str = ""
    timeout: float = 120.0

    def headers(self, json_body: bool = False) -> dict:
        headers = _headers(self.device_id, self.token)
        if json_body:
            headers["Content-Type"] = "application/json"
        if self.authorization:
            value = self.authorization.strip()
            headers["Authorization"] = value if value.lower().startswith("bearer ") else "Bearer " + value
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    def get(self, path: str, params: dict) -> dict:
        url = API_BASE + path + "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers=self.headers())
        return json.loads(_opener(request, self.timeout))

    def post(self, path: str, body: dict) -> dict:
        payload = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            API_BASE + path, data=payload, headers=self.headers(json_body=True), method="POST"
        )
        return json.loads(_opener(request, self.timeout))


def open_session(authorization: str = "", cookie: str = "", *, timeout: float = 120.0) -> PanSession:
    device_id = new_device_id()
    return PanSession(
        device_id=device_id,
        token=captcha_token(device_id, timeout=timeout),
        authorization=authorization,
        cookie=cookie,
        timeout=timeout,
    )


def restore_share(session: PanSession, share_id: str, pass_code_token: str, file_ids: "list[str]") -> dict:
    return session.post(
        "/share/restore",
        {
            "parent_id": "",
            "share_id": share_id,
            "pass_code_token": pass_code_token,
            "ancestor_ids": [],
            "file_ids": file_ids,
            "specify_parent_id": True,
        },
    )


def my_files(session: PanSession, parent_id: str = "") -> "list[dict]":
    payload = session.get("/files", {"parent_id": parent_id, "limit": 100, "space": ""})
    return _items(payload)


def file_link(session: PanSession, file_id: str) -> str:
    payload = session.get("/files/" + urllib.parse.quote(file_id), {"space": "", "usage": "CONSUME"})
    data = payload.get("file") if isinstance(payload.get("file"), dict) else payload
    return str(data.get("web_content_link") or "")


def delete_files(session: PanSession, file_ids: "list[str]") -> dict:
    return session.post("/files:batchDelete", {"ids": list(file_ids)})


def _headers(device_id: str, token: str = "") -> dict:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": USER_AGENT,
        "X-Client-Id": CLIENT_ID,
        "X-Client-Version": CLIENT_VERSION,
        "X-Device-Id": device_id,
        "Referer": "https://pan.xunlei.com/",
    }
    if token:
        headers["X-Captcha-Token"] = token
    return headers


def captcha_token(
    device_id: str,
    *,
    action: str = "get:/drive/v1/share",
    timeout: float = 25.0,
    transport: Callable | None = None,
) -> str:
    timestamp = str(int(time.time() * 1000))
    payload = {
        "client_id": CLIENT_ID,
        "action": action,
        "device_id": device_id,
        "meta": {
            "username": "",
            "phone_number": "",
            "email": "",
            "package_name": "pan.xunlei.com",
            "client_version": CLIENT_VERSION,
            "captcha_sign": captcha_sign(timestamp, device_id),
            "timestamp": timestamp,
            "user_id": "0",
        },
    }
    body = json.dumps(payload).encode("utf-8")
    headers = _headers(device_id)
    headers["Content-Type"] = "application/json"
    if transport is not None:
        data = transport(CAPTCHA_API, headers, body, timeout)
    else:
        request = urllib.request.Request(CAPTCHA_API, data=body, headers=headers, method="POST")
        data = json.loads(_opener(request, timeout))
    token = (data or {}).get("captcha_token")
    if not token:
        raise XunleiError("captcha token missing: " + str(data)[:200])
    return str(token)


@dataclass
class ShareEntry:
    file_id: str
    name: str
    size: int = 0
    kind: str = "file"  # file | folder
    inline_url: str = ""

    def as_dict(self) -> dict:
        return {
            "file_id": self.file_id,
            "name": self.name,
            "size": self.size,
            "kind": self.kind,
            "inline_url": self.inline_url,
        }


@dataclass
class ShareListing:
    share_id: str
    entries: list[ShareEntry] = field(default_factory=list)
    pass_code_token: str = ""

    @property
    def total_bytes(self) -> int:
        return sum(entry.size for entry in self.entries)

    def as_dict(self) -> dict:
        return {
            "share_id": self.share_id,
            "entries": [entry.as_dict() for entry in self.entries],
            "total_bytes": self.total_bytes,
        }


def parse_share_url(url: str) -> "tuple[str, str]":
    parsed = urllib.parse.urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    share_id = parts[-1] if parts else ""
    query = urllib.parse.parse_qs(parsed.query)
    pass_code = (query.get("pwd") or [""])[0]
    if not share_id:
        raise XunleiError("cannot parse share id from " + url)
    return share_id, pass_code


def _get(params: dict, device_id: str, token: str, path: str, timeout: float, transport) -> dict:
    url = API_BASE + path + "?" + urllib.parse.urlencode(params)
    headers = _headers(device_id, token)
    if transport is not None:
        return transport(url, headers, None, timeout)
    request = urllib.request.Request(url, headers=headers)
    return json.loads(_opener(request, timeout))


def _items(payload: dict) -> "list[dict]":
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    for key in ("files", "file_list", "list"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def list_folder(
    share_id: str,
    parent_id: str,
    pass_code_token: str,
    *,
    device_id: str,
    token: str,
    timeout: float = 25.0,
    transport: Callable | None = None,
) -> "list[ShareEntry]":
    params = {
        "share_id": share_id,
        "parent_id": parent_id,
        "pass_code_token": pass_code_token,
        "limit": PAGE_SIZE,
        "space": "",
        "thumbnail_size": "SIZE_MEDIUM",
        "scene": "NORMAL",
    }
    payload = _get(params, device_id, token, "/share/detail", timeout, transport)
    entries: list[ShareEntry] = []
    for item in _items(payload):
        entries.append(
            ShareEntry(
                file_id=str(item.get("id") or item.get("file_id") or ""),
                name=str(item.get("name") or item.get("file_name") or ""),
                size=int(item.get("size") or 0),
                kind="folder" if "folder" in str(item.get("kind") or "").lower() else "file",
                inline_url=str(item.get("web_content_link") or ""),
            )
        )
    return entries


def walk_share(
    share_id: str,
    pass_code: str = "",
    *,
    max_depth: int = 6,
    timeout: float = 25.0,
    transport: Callable | None = None,
) -> "list[ShareEntry]":
    """Recursively list every file in a share (folders carry a path prefix)."""
    device_id = new_device_id()
    token = captcha_token(device_id, timeout=timeout, transport=transport)
    listing = list_share(share_id, pass_code, device_id=device_id, timeout=timeout, transport=transport)
    out: list[ShareEntry] = []

    def walk(entries: "list[ShareEntry]", prefix: str, depth: int) -> None:
        for entry in entries:
            if entry.kind == "folder":
                if depth >= max_depth:
                    continue
                children = list_folder(
                    share_id,
                    entry.file_id,
                    listing.pass_code_token,
                    device_id=device_id,
                    token=token,
                    timeout=timeout,
                    transport=transport,
                )
                walk(children, prefix + entry.name + "/", depth + 1)
            else:
                entry.name = prefix + entry.name
                out.append(entry)

    walk(listing.entries, "", 0)
    return out


def list_share(
    share_id: str,
    pass_code: str = "",
    *,
    device_id: str | None = None,
    timeout: float = 25.0,
    transport: Callable | None = None,
    max_entries: int = 5000,
) -> ShareListing:
    """List a share root; folders are expanded one level deep is NOT done here."""
    device_id = device_id or new_device_id()
    token = captcha_token(device_id, timeout=timeout, transport=transport)
    params = {
        "share_id": share_id,
        "limit": PAGE_SIZE,
        "space": "",
        "thumbnail_size": "SIZE_MEDIUM",
        "scene": "NORMAL",
    }
    if pass_code:
        params["pass_code"] = pass_code
    payload = _get(params, device_id, token, "/share", timeout, transport)
    listing = ShareListing(share_id=share_id)
    listing.pass_code_token = str(payload.get("pass_code_token") or "")
    for item in _items(payload):
        if len(listing.entries) >= max_entries:
            break
        listing.entries.append(
            ShareEntry(
                file_id=str(item.get("id") or item.get("file_id") or ""),
                name=str(item.get("name") or item.get("file_name") or ""),
                size=int(item.get("size") or 0),
                kind="folder" if "folder" in str(item.get("kind") or "").lower() else "file",
                inline_url=str(item.get("web_content_link") or ""),
            )
        )
    return listing
