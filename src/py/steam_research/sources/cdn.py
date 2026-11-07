"""Steam content CDN client: manifest + chunk URLs with host fallback (M3 preview).

Why this exists: the direct-link chain for an app the account does NOT own needs
    gid (steamcmd.net) + app/depot auth + depot key + a reachable CDN host.
Raw HTTP against the CDN needs the *client session* credential, not just a scraped
app token - that is why unauthenticated probes return 401. This module keeps the
transport pluggable so the auth path can be solved separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

DEFAULT_HOSTS = (
    "https://steampipe.akamaized.net",
    "https://st.dl.eccdnx.com",
    "https://cdn.steamcontent.com",
)

USER_AGENT = "Valve/Steam HTTP Client 1.0"


class CdnError(ValueError):
    """Raised when no configured CDN host could serve the request."""

    def __init__(self, message: str, *, attempts: Sequence["CdnAttempt"] = ()):
        self.attempts = tuple(attempts)
        detail = "; ".join(
            attempt.host + "=" + str(attempt.status) for attempt in self.attempts
        )
        super().__init__(message + (" (" + detail + ")" if detail else ""))


@dataclass(frozen=True)
class CdnAttempt:
    host: str
    status: int | str
    bytes: int

    def as_dict(self) -> dict:
        return {"host": self.host, "status": self.status, "bytes": self.bytes}


def _strip(host: str) -> str:
    return host.rstrip("/")


class CdnClient:
    """Builds SteamPipe URLs and walks hosts until one answers."""

    def __init__(
        self,
        *,
        hosts: Iterable[str] = DEFAULT_HOSTS,
        fetch: Callable[[str, dict], "tuple[int, bytes]"] | None = None,
        timeout: float = 30.0,
        user_agent: str = USER_AGENT,
    ):
        self.hosts = tuple(_strip(host) for host in hosts)
        if not self.hosts:
            raise CdnError("at least one CDN host is required")
        self.timeout = timeout
        self.user_agent = user_agent
        self._fetch = fetch or self._http_fetch

    def _http_fetch(self, url: str, headers: dict) -> "tuple[int, bytes]":
        import ssl
        import urllib.error
        import urllib.request

        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return int(response.status), response.read()
        except urllib.error.HTTPError as exc:
            return int(exc.code), exc.read() or b""
        except Exception:  # noqa: BLE001 - MSYS python ships without a CA bundle
            context = ssl._create_unverified_context()  # noqa: SLF001
            try:
                with urllib.request.urlopen(request, timeout=self.timeout, context=context) as response:
                    return int(response.status), response.read()
            except urllib.error.HTTPError as exc:
                return int(exc.code), exc.read() or b""

    def manifest_path(self, depot_id: int, gid: str, version: int = 5) -> str:
        if int(depot_id) <= 0:
            raise CdnError("depot_id must be positive")
        manifest = str(gid).strip()
        if not manifest.isdigit():
            raise CdnError("manifest gid must be numeric: " + repr(gid))
        return "/depot/" + str(int(depot_id)) + "/manifest/" + manifest + "/" + str(int(version))

    def chunk_path(self, depot_id: int, chunk_sha1: str) -> str:
        if int(depot_id) <= 0:
            raise CdnError("depot_id must be positive")
        sha = str(chunk_sha1).strip().lower()
        if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
            raise CdnError("chunk sha1 must be 40 hex chars: " + repr(chunk_sha1))
        return "/depot/" + str(int(depot_id)) + "/chunk/" + sha

    def manifest_url(self, depot_id: int, gid: str, version: int = 5, host: str | None = None) -> str:
        base = _strip(host) if host else self.hosts[0]
        return base + self.manifest_path(depot_id, gid, version)

    def chunk_url(self, depot_id: int, chunk_sha1: str, host: str | None = None) -> str:
        base = _strip(host) if host else self.hosts[0]
        return base + self.chunk_path(depot_id, chunk_sha1)

    def _walk(self, path: str, token: str | None) -> "tuple[str, bytes]":
        headers = {"User-Agent": self.user_agent}
        if token:
            headers["Authorization"] = "Bearer " + str(token).strip()
        attempts: list[CdnAttempt] = []
        last_error: Exception | None = None
        for host in self.hosts:
            url = host + path
            try:
                status, payload = self._fetch(url, dict(headers))
            except Exception as exc:  # noqa: BLE001 - transport failure is an attempt
                attempts.append(CdnAttempt(host, type(exc).__name__, 0))
                last_error = exc
                continue
            attempts.append(CdnAttempt(host, status, len(payload)))
            if status == 200 and payload:
                return url, payload
            last_error = None
        raise CdnError(
            "no CDN host served " + path + " (last transport error: " + type(last_error).__name__ + ")"
            if last_error
            else "no CDN host served " + path,
            attempts=attempts,
        )

    def fetch_manifest(
        self, depot_id: int, gid: str, *, token: str | None = None, version: int = 5
    ) -> "tuple[str, bytes]":
        return self._walk(self.manifest_path(depot_id, gid, version), token)

    def fetch_chunk(self, depot_id: int, chunk_sha1: str, *, token: str | None = None) -> "tuple[str, bytes]":
        return self._walk(self.chunk_path(depot_id, chunk_sha1), token)
