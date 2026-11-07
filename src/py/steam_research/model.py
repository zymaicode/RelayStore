"""Domain model shared by parsers, sources and the catalog."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ManifestRef:
    """One depot -> manifest reference (a single gid)."""

    appid: int
    depot_id: int
    gid: str
    size: int | None = None
    sha1: str | None = None
    source: str = "unknown"
    source_url: str = ""
    fetched_at: str = ""

    def as_dict(self) -> dict:
        return {
            "appid": self.appid,
            "depot_id": self.depot_id,
            "gid": self.gid,
            "size": self.size,
            "sha1": self.sha1,
            "source": self.source,
            "source_url": self.source_url,
            "fetched_at": self.fetched_at,
        }


@dataclass(frozen=True)
class AppRecord:
    """An app plus every depot/manifest we could resolve for it."""

    appid: int
    name: str | None = None
    depots: tuple[int, ...] = field(default_factory=tuple)
    manifests: tuple[ManifestRef, ...] = field(default_factory=tuple)

    def manifest_for(self, depot_id: int) -> ManifestRef | None:
        for ref in self.manifests:
            if ref.depot_id == depot_id:
                return ref
        return None

@dataclass(frozen=True)
class AccessToken:
    """App access token: ManifestHub appaccesstokens.json maps appid -> token."""

    appid: int
    token: str
    source: str = "unknown"
    fetched_at: str = ""

    def as_dict(self) -> dict:
        return {
            "appid": self.appid,
            "token": self.token,
            "source": self.source,
            "fetched_at": self.fetched_at,
        }


@dataclass(frozen=True)
class DepotKey:
    """Depot decryption key: ManifestHub depotkeys.json maps depot_id -> hex key."""

    depot_id: int
    key_hex: str
    source: str = "unknown"
    fetched_at: str = ""

    def as_dict(self) -> dict:
        return {
            "depot_id": self.depot_id,
            "key_hex": self.key_hex,
            "source": self.source,
            "fetched_at": self.fetched_at,
        }
