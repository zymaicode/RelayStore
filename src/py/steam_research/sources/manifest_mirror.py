"""Manifest mirror: try several raw/CDN endpoints for <depot>_<gid>.manifest."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..manifest import DepotManifest, parse_manifest

DEFAULT_REPOS = ("qwe213312/k25FCdfEOoEJ42S6",)

# {repo} {branch} {depot} {gid} are substituted; order matters (fastest/most reliable first)
DEFAULT_TEMPLATES = (
    "https://raw.githubusercontent.com/{repo}/{branch}/{depot}_{gid}.manifest",
    "https://cdn.jsdelivr.net/gh/{repo}@{branch}/{depot}_{gid}.manifest",
    "https://raw.githack.com/{repo}/{branch}/{depot}_{gid}.manifest",
)


class MirrorError(ValueError):
    """Raised when no configured mirror has the manifest."""


@dataclass
class MirrorAttempt:
    repo: str
    url: str
    status: int | str

    def as_dict(self) -> dict:
        return {"repo": self.repo, "url": self.url, "status": self.status}


@dataclass
class ManifestMirror:
    """Fetch <depot>_<gid>.manifest from several repos and endpoint flavours."""

    repos: tuple[str, ...] = DEFAULT_REPOS
    branch: str = "main"
    templates: tuple[str, ...] = DEFAULT_TEMPLATES
    fetch: object = None  # callable(url) -> bytes, injected in tests
    attempts: list[MirrorAttempt] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.fetch is None:
            from ..directlink import _http_get

            self.fetch = _http_get

    def url_for(self, repo: str, depot_id: int, gid: str, template: str | None = None) -> str:
        pattern = template or self.templates[0]
        return pattern.format(
            repo=repo,
            branch=self.branch,
            depot=str(int(depot_id)),
            gid=str(gid),
        )

    def candidates(self, depot_id: int, gid: str) -> "list[tuple[str, str]]":
        out: list[tuple[str, str]] = []
        for repo in self.repos:
            for template in self.templates:
                out.append((repo, self.url_for(repo, depot_id, gid, template)))
        return out

    def get_with_fallback(self, depot_id: int, gid: str, index) -> "tuple[DepotManifest, str, str]":
        """Try the current gid first, then any build the mirror actually has."""
        candidates = index.candidates(depot_id, gid) if index is not None else [str(gid)]
        last_error: Exception | None = None
        for candidate in candidates:
            known = index.repos_for(depot_id, candidate) if index is not None else []
            ordered = tuple(repo for repo in known if repo in self.repos) + tuple(
                repo for repo in self.repos if repo not in known
            )
            saved = self.repos
            self.repos = ordered or saved
            try:
                manifest, url = self.get(depot_id, candidate)
            except MirrorError as exc:
                last_error = exc
                continue
            finally:
                self.repos = saved
            return manifest, url, candidate
        raise last_error or MirrorError("no manifest for depot " + str(depot_id))

    def get(self, depot_id: int, gid: str) -> "tuple[DepotManifest, str]":
        for repo, url in self.candidates(depot_id, gid):
            try:
                payload = self.fetch(url)  # type: ignore[misc]
            except Exception as exc:  # noqa: BLE001 - try the next mirror
                self.attempts.append(MirrorAttempt(repo, url, type(exc).__name__))
                continue
            if not payload:
                self.attempts.append(MirrorAttempt(repo, url, "empty"))
                continue
            self.attempts.append(MirrorAttempt(repo, url, 200))
            return parse_manifest(payload), url
        raise MirrorError(
            "no mirror served manifest for depot " + str(depot_id) + " gid " + str(gid)
        )
