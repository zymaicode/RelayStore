"""Read-only coverage check: can an app be restored, without downloading it."""

from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from .keys import Keyring
from .sources.appinfo import DepotInfo, public_depots
from .sources.manifest_index import ManifestIndex

DEFAULT_REPO = "qwe213312/k25FCdfEOoEJ42S6"


def _head(url: str, timeout: float = 25.0) -> int | str:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "steam-research/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except Exception:  # noqa: BLE001 - msys python has no CA bundle; retry unverified
        try:
            context = ssl._create_unverified_context()  # noqa: SLF001
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                return int(response.status)
        except urllib.error.HTTPError as exc:
            return int(exc.code)
        except Exception as exc:  # noqa: BLE001
            return type(exc).__name__


@dataclass
class DepotCoverage:
    depot_id: int
    gid: str
    size: int = 0
    has_key: bool = False
    index_gids: int = 0
    manifest_status: int | str | None = None
    hubcap_manifest: str = ""
    hubcap_error: str = ""

    def as_dict(self) -> dict:
        return {
            "depot_id": self.depot_id,
            "gid": self.gid,
            "size": self.size,
            "has_key": self.has_key,
            "index_gids": self.index_gids,
            "manifest_status": self.manifest_status,
            "hubcap_manifest": self.hubcap_manifest,
            "hubcap_error": self.hubcap_error,
        }


@dataclass
class CoverageReport:
    appid: int
    depots: list[DepotCoverage] = field(default_factory=list)
    steamtools: dict | None = None

    @property
    def total_bytes(self) -> int:
        return sum(depot.size for depot in self.depots)

    @property
    def keys_ok(self) -> int:
        return sum(1 for depot in self.depots if depot.has_key)

    @property
    def manifests_current(self) -> int:
        return sum(1 for depot in self.depots if depot.manifest_status == 200)

    @property
    def manifests_any(self) -> int:
        return sum(1 for depot in self.depots if depot.index_gids > 0)

    @property
    def downloadable_depots(self) -> int:
        return sum(
            1
            for depot in self.depots
            if depot.has_key
            and (
                depot.manifest_status == 200
                or str(depot.manifest_status).startswith("hubcap:")
                or depot.index_gids > 0
            )
        )

    def as_dict(self) -> dict:
        return {
            "appid": self.appid,
            "depots_total": len(self.depots),
            "size_bytes": self.total_bytes,
            "keys_ok": self.keys_ok,
            "manifests_current": self.manifests_current,
            "manifests_any_build": self.manifests_any,
            "downloadable_depots": self.downloadable_depots,
            "downloadable": bool(self.depots) and self.downloadable_depots == len(self.depots),
            "steamtools": self.steamtools,
            "depots": [depot.as_dict() for depot in self.depots],
        }


def check_coverage(
    appid: int,
    *,
    keys: Keyring | None = None,
    index: ManifestIndex | None = None,
    depots: "list[DepotInfo] | None" = None,
    steamcmd: str = "tools/bin/steamcmd.exe",
    repo: str = DEFAULT_REPO,
    branch: str = "main",
    head: Callable[[str], int | str] | None = None,
    steamtools_probe: Callable[[int], object] | None = None,
    hubcap: object | None = None,
    appinfo_cache: str | None = None,
) -> CoverageReport:
    """Never downloads content: appinfo + local index + HEAD on the manifest URL."""
    head = head or _head
    selected = (
        depots
        if depots is not None
        else list(public_depots(appid, steamcmd=steamcmd, cache_dir=appinfo_cache))
    )
    report = CoverageReport(appid=int(appid))
    for info in selected:
        item = DepotCoverage(depot_id=info.depot_id, gid=str(info.gid), size=info.size or 0)
        if keys is not None:
            item.has_key = keys.has(info.depot_id)
        if index is not None:
            item.index_gids = len(index.gids.get(int(info.depot_id), []))
        url = (
            "https://raw.githubusercontent.com/"
            + repo
            + "/"
            + branch
            + "/"
            + str(info.depot_id)
            + "_"
            + str(info.gid)
            + ".manifest"
        )
        item.manifest_status = head(url)
        if item.manifest_status != 200 and item.index_gids == 0 and hubcap is not None:
            try:
                target = hubcap.fetch_manifest(info.depot_id, str(info.gid))
                item.manifest_status = "hubcap:" + str(target.stat().st_size)
                item.hubcap_manifest = str(target)
            except Exception as exc:  # noqa: BLE001 - hubcap is best effort
                item.hubcap_error = type(exc).__name__
        report.depots.append(item)
    if steamtools_probe is not None:
        try:
            probe = steamtools_probe(int(appid))
            report.steamtools = probe.as_dict() if hasattr(probe, "as_dict") else dict(probe)
        except Exception as exc:  # noqa: BLE001
            report.steamtools = {"appid": int(appid), "in_db": None, "message": type(exc).__name__}
    return report
