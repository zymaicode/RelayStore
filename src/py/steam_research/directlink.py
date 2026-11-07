"""End-to-end direct link: manifest (GitHub raw) -> chunk (CDN) -> verify (M3).

Chain verified 2026-11-06 against an unowned app (3DMark, depot 1276160):
    manifest  https://raw.githubusercontent.com/<repo>/<branch>/<depot>_<gid>.manifest
    chunk     https://<cdn>/depot/<depot>/chunk/<sha>
    decode    AES-256 (ECB IV + CBC) then VZip / Zip / VZstd
"""

from __future__ import annotations

import hashlib
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .depot import DepotError, decode_chunk
from .manifest import Chunk, DepotManifest, parse_manifest

DEFAULT_REPO = "qwe213312/k25FCdfEOoEJ42S6"
DEFAULT_BRANCH = "main"
DEFAULT_CDN = "https://steampipe.akamaized.net"


class DirectLinkError(ValueError):
    """Raised when a direct-link step fails."""


@dataclass(frozen=True)
class FetchResult:
    depot_id: int
    gid: str
    manifest_bytes: int
    files: int
    chunks: int
    chunk_sha: str
    cipher_bytes: int
    plain_bytes: int
    cb_original: int
    sha_ok: bool

    def as_dict(self) -> dict:
        return {
            "depot_id": self.depot_id,
            "gid": self.gid,
            "manifest_bytes": self.manifest_bytes,
            "files": self.files,
            "chunks": self.chunks,
            "chunk_sha": self.chunk_sha,
            "cipher_bytes": self.cipher_bytes,
            "plain_bytes": self.plain_bytes,
            "cb_original": self.cb_original,
            "sha_ok": self.sha_ok,
        }


def manifest_url(depot_id: int, gid: str, *, repo: str = DEFAULT_REPO, branch: str = DEFAULT_BRANCH) -> str:
    if int(depot_id) <= 0:
        raise DirectLinkError("depot_id must be positive")
    manifest = str(gid).strip()
    if not manifest.isdigit():
        raise DirectLinkError("manifest gid must be numeric")
    return (
        "https://raw.githubusercontent.com/"
        + repo
        + "/"
        + branch
        + "/"
        + str(int(depot_id))
        + "_"
        + manifest
        + ".manifest"
    )


def chunk_url(depot_id: int, sha: str, *, host: str = DEFAULT_CDN) -> str:
    digest = str(sha).strip().lower()
    if len(digest) != 40 or any(ch not in "0123456789abcdef" for ch in digest):
        raise DirectLinkError("chunk sha must be 40 hex chars")
    return host.rstrip("/") + "/depot/" + str(int(depot_id)) + "/chunk/" + digest


def _http_get(url: str, timeout: float = 45.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "steam-research/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, ssl.SSLError):
            # msys2 python ships no CA bundle; retry once without verification.
            context = ssl._create_unverified_context()  # noqa: SLF001
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                return response.read()
        raise DirectLinkError("GET failed for " + url + ": " + str(reason)) from exc


class DirectLink:
    """Fetch a manifest and one chunk for an app the account does not own."""

    def __init__(
        self,
        *,
        repo: str = DEFAULT_REPO,
        branch: str = DEFAULT_BRANCH,
        cdn: str = DEFAULT_CDN,
        fetch: Callable[[str], bytes] | None = None,
    ):
        self.repo = repo
        self.branch = branch
        self.cdn = cdn
        self.fetch = fetch or _http_get

    def get_manifest(self, depot_id: int, gid: str) -> DepotManifest:
        payload = self.fetch(manifest_url(depot_id, gid, repo=self.repo, branch=self.branch))
        self.manifest_bytes = len(payload)
        return parse_manifest(payload)

    def get_chunk(self, depot_id: int, sha: str) -> bytes:
        return self.fetch(chunk_url(depot_id, sha, host=self.cdn))

    def verify_first_chunk(self, depot_id: int, manifest: DepotManifest, depot_key: bytes) -> FetchResult:
        chunks = [chunk for chunk in manifest.chunks() if chunk.cb_compressed > 0]
        if not chunks:
            raise DirectLinkError("manifest has no chunks")
        chunk = chunks[0]
        cipher = self.get_chunk(depot_id, chunk.sha)
        if len(cipher) != chunk.cb_compressed:
            raise DirectLinkError(
                "chunk size mismatch: got " + str(len(cipher)) + ", want " + str(chunk.cb_compressed)
            )
        try:
            plain = decode_chunk(cipher, depot_key)
        except DepotError as exc:
            raise DirectLinkError(str(exc)) from exc
        sha_ok = hashlib.sha1(plain).hexdigest() == chunk.sha
        return FetchResult(
            depot_id=depot_id,
            gid="",
            manifest_bytes=getattr(self, "manifest_bytes", 0),
            files=len(manifest.files),
            chunks=manifest.chunk_count,
            chunk_sha=chunk.sha,
            cipher_bytes=len(cipher),
            plain_bytes=len(plain),
            cb_original=chunk.cb_original,
            sha_ok=sha_ok,
        )
