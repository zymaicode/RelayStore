"""App-level pipeline: appid -> depots -> manifests -> keys -> restore -> report."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable

from .directlink import DirectLink
from .keys import Keyring
from .manifest import DepotManifest, parse_manifest
from .restore import RestoreError, restore_depot
from .sources.appinfo import DepotInfo, AppInfoError, public_depots
from .sources.manifest_mirror import ManifestMirror, MirrorError
from .sources.manifest_index import ManifestIndex


@dataclass
class DepotResult:
    depot_id: int
    gid: str
    status: str = "pending"  # ok | missing_key | missing_manifest | failed | skipped
    files_ok: int = 0
    files_total: int = 0
    directories: int = 0
    bytes: int = 0
    expected_bytes: int | None = None
    seconds: float = 0.0
    error: str = ""
    source_url: str = ""
    gid_used: str = ""

    def as_dict(self) -> dict:
        return {
            "depot_id": self.depot_id,
            "gid": self.gid,
            "status": self.status,
            "files_ok": self.files_ok,
            "files_total": self.files_total,
            "directories": self.directories,
            "bytes": self.bytes,
            "expected_bytes": self.expected_bytes,
            "bytes_delta": (self.bytes - self.expected_bytes) if self.expected_bytes is not None else None,
            "seconds": round(self.seconds, 2),
            "error": self.error,
            "gid_used": self.gid_used,
            "source_url": self.source_url,
        }


@dataclass
class AppRestoreReport:
    appid: int
    out_dir: str
    depots: list[DepotResult] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return bool(self.depots) and all(
            depot.status in ("ok", "skipped", "cancelled") for depot in self.depots
        )

    @property
    def restored(self) -> int:
        return sum(1 for depot in self.depots if depot.status == "ok")

    def as_dict(self) -> dict:
        return {
            "appid": self.appid,
            "out_dir": self.out_dir,
            "ok": self.ok,
            "restored": self.restored,
            "depots_total": len(self.depots),
            "files_ok": sum(depot.files_ok for depot in self.depots),
            "files_total": sum(depot.files_total for depot in self.depots),
            "bytes": sum(depot.bytes for depot in self.depots),
            "seconds": round(self.seconds, 2),
            "depots": [depot.as_dict() for depot in self.depots],
        }


def restore_app(
    appid: int,
    out_dir: str | Path,
    *,
    keys: Keyring,
    depots: Iterable[DepotInfo] | None = None,
    mirror: ManifestMirror | None = None,
    index: ManifestIndex | None = None,
    hubcap: object | None = None,
    link: DirectLink | None = None,
    steamcmd: str | Path = "tools/bin/steamcmd.exe",
    workers: int = 6,
    only: Iterable[int] | None = None,
    max_depot_bytes: int | None = None,
    state_path: str | Path | None = None,
    depot_workers: int = 1,
    on_progress=None,
    should_stop=None,
) -> AppRestoreReport:
    """Restore every depot of an app, reporting per-depot status."""
    started = time.perf_counter()
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    report = AppRestoreReport(appid=int(appid), out_dir=str(root))

    selected = list(depots) if depots is not None else list(public_depots(appid, steamcmd=steamcmd))
    only_set = {int(item) for item in only} if only else None
    state: dict = {}
    if state_path is not None and Path(state_path).is_file():
        import json as _json_state

        try:
            state = _json_state.loads(Path(state_path).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a corrupt state file must not block a restore
            state = {}
    done = {int(k) for k, v in state.items() if v == "ok"}

    def save_state() -> None:
        if state_path is None:
            return
        Path(state_path).parent.mkdir(parents=True, exist_ok=True)
        Path(state_path).write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

    mirror = mirror or ManifestMirror()
    link = link or DirectLink()

    state_lock = threading.Lock()

    def process(info) -> DepotResult:
        result = DepotResult(depot_id=info.depot_id, gid=str(info.gid), expected_bytes=info.size)
        if should_stop is not None and should_stop():
            result.status = "cancelled"
            result.error = "cancelled by client"
            return result
        if info.depot_id in done:
            result.status = "skipped"
            result.error = "resumed: already ok"
            return result
        if only_set is not None and info.depot_id not in only_set:
            result.status = "skipped"
            return result
        if max_depot_bytes is not None and info.size is not None and info.size > max_depot_bytes:
            result.status = "skipped"
            result.error = "depot size " + str(info.size) + " > limit " + str(max_depot_bytes)
            return result

        key = keys.get(info.depot_id)
        if key is None:
            result.status = "missing_key"
            result.error = "no depot key for " + str(info.depot_id)
            return result

        started_depot = time.perf_counter()
        try:
            if index is not None:
                manifest, url, gid_used = mirror.get_with_fallback(info.depot_id, str(info.gid), index)
            else:
                manifest, url = mirror.get(info.depot_id, str(info.gid))
                gid_used = str(info.gid)
            result.source_url = url
            result.gid_used = gid_used
        except MirrorError as exc:
            if hubcap is not None:
                try:
                    target = hubcap.fetch_manifest(info.depot_id, str(info.gid))
                    manifest = parse_manifest(target.read_bytes())
                    url = "hubcap:" + str(target)
                    gid_used = str(info.gid)
                    result.error = ""
                except Exception as hub_exc:  # noqa: BLE001
                    result.status = "missing_manifest"
                    result.error = str(exc) + " | hubcap: " + type(hub_exc).__name__
                    result.seconds = time.perf_counter() - started_depot
                    return result
            else:
                result.status = "missing_manifest"
                result.error = str(exc)
                result.seconds = time.perf_counter() - started_depot
                return result
        result.source_url = url
        result.gid_used = gid_used

        try:
            depot_dir = root / str(info.depot_id)
            restore = restore_depot(
                info.depot_id,
                str(info.gid),
                key,
                depot_dir,
                link=link,
                workers=workers,
                manifest=manifest,
            )
            result.files_ok = restore.files_ok
            result.files_total = restore.files_total
            result.directories = restore.directories
            result.bytes = restore.bytes_written
            result.status = "ok" if restore.ok else "failed"
            if restore.errors:
                result.error = "; ".join(restore.errors[:3])
        except (RestoreError, Exception) as exc:  # noqa: BLE001 - per-depot isolation
            result.status = "failed"
            result.error = type(exc).__name__ + ": " + str(exc)
        result.seconds = time.perf_counter() - started_depot
        with state_lock:
            state[str(info.depot_id)] = result.status
            save_state()
        if on_progress:
            on_progress(str(info.depot_id) + " " + result.status)
        return result

    if depot_workers and depot_workers > 1:
        with ThreadPoolExecutor(max_workers=depot_workers) as pool:
            report.depots = list(pool.map(process, selected))
    else:
        report.depots = [process(info) for info in selected]

    report.seconds = time.perf_counter() - started
    return report
