"""Restore a depot from direct links: chunk -> decode -> assemble -> verify (M3).

Flow (all keyless except the depot key):
    manifest (GitHub raw) -> unique chunks (CDN) -> AES+zstd/LZMA decode
    -> write each file at chunk offsets -> verify chunk sha1 + file sha1
"""

from __future__ import annotations

import hashlib
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .depot import DepotError, decode_chunk
from .directlink import DirectLink, DirectLinkError
from .manifest import Chunk, DepotManifest, FileEntry


class RestoreError(ValueError):
    """Raised when a depot cannot be restored."""


@dataclass
class RestoreReport:
    depot_id: int
    gid: str
    out_dir: str
    files_total: int = 0
    files_ok: int = 0
    files_failed: int = 0
    chunks_total: int = 0
    chunks_downloaded: int = 0
    bytes_written: int = 0
    directories: int = 0
    seconds: float = 0.0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.files_failed == 0 and self.files_ok == self.files_total > 0

    def as_dict(self) -> dict:
        return {
            "depot_id": self.depot_id,
            "gid": self.gid,
            "out_dir": self.out_dir,
            "files_total": self.files_total,
            "files_ok": self.files_ok,
            "files_failed": self.files_failed,
            "chunks_total": self.chunks_total,
            "chunks_downloaded": self.chunks_downloaded,
            "bytes_written": self.bytes_written,
            "directories": self.directories,
            "seconds": round(self.seconds, 2),
            "ok": self.ok,
            "errors": self.errors[:20],
        }


def _safe_target(root: Path, names: Iterable[str]) -> Path:
    """Pick the first filename, rejecting traversal / absolute paths."""
    for name in names:
        text = str(name).replace("\\", "/").lstrip("/")
        if not text:
            continue
        candidate = Path(text)
        if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
            raise RestoreError("unsafe path in manifest: " + str(name))
        return root / candidate
    raise RestoreError("manifest entry without filename")


def _decode_to_cache(
    link: DirectLink,
    depot_id: int,
    chunk: Chunk,
    depot_key: bytes,
    cache_dir: Path,
    retries: int = 3,
) -> "tuple[str, Path]":
    target = cache_dir / chunk.sha
    if target.is_file() and target.stat().st_size == chunk.cb_original:
        return chunk.sha, target
    cipher = b""
    last_error: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            cipher = link.get_chunk(depot_id, chunk.sha)
            last_error = None
            break
        except Exception as exc:  # noqa: BLE001 - transient CDN errors are expected
            last_error = exc
            time.sleep(0.4 * (attempt + 1))
    if last_error is not None:
        raise RestoreError(str(last_error))
    if len(cipher) != chunk.cb_compressed:
        raise RestoreError(
            "chunk " + chunk.sha[:12] + " size " + str(len(cipher)) + " != " + str(chunk.cb_compressed)
        )
    plain = decode_chunk(cipher, depot_key)
    if len(plain) != chunk.cb_original:
        raise RestoreError(
            "chunk " + chunk.sha[:12] + " decoded " + str(len(plain)) + " != " + str(chunk.cb_original)
        )
    digest = hashlib.sha1(plain).hexdigest()
    if digest != chunk.sha:
        raise RestoreError("chunk " + chunk.sha[:12] + " sha1 mismatch (" + digest[:12] + ")")
    tmp = target.with_suffix(".part")
    tmp.write_bytes(plain)
    tmp.replace(target)
    return chunk.sha, target


def restore_depot(
    depot_id: int,
    gid: str,
    depot_key: bytes,
    out_dir: str | Path,
    *,
    link: DirectLink | None = None,
    workers: int = 6,
    retries: int = 3,
    keep_cache: bool = True,
    manifest: DepotManifest | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> RestoreReport:
    """Download every chunk of a depot, rebuild the files, verify sha1."""
    link = link or DirectLink()
    root = Path(out_dir)
    cache_dir = root / ".chunks"
    cache_dir.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    if manifest is None:
        manifest = link.get_manifest(depot_id, gid)
    report = RestoreReport(depot_id=depot_id, gid=str(gid), out_dir=str(root))
    report.files_total = len([entry for entry in manifest.files if entry.chunks])

    unique: dict[str, Chunk] = {}
    for chunk in manifest.chunks():
        unique.setdefault(chunk.sha, chunk)
    report.chunks_total = len(unique)

    # 1) fetch + decode every unique chunk
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(_decode_to_cache, link, depot_id, chunk, depot_key, cache_dir, retries): chunk
            for chunk in unique.values()
        }
        for future in as_completed(futures):
            chunk = futures[future]
            try:
                future.result()
                report.chunks_downloaded += 1
            except Exception as exc:  # noqa: BLE001 - collected into the report
                report.errors.append("chunk " + chunk.sha[:12] + ": " + str(exc))
            if on_progress and report.chunks_downloaded % 25 == 0:
                on_progress(
                    "chunks "
                    + str(report.chunks_downloaded)
                    + "/"
                    + str(report.chunks_total)
                )

    if report.errors:
        report.seconds = time.perf_counter() - started
        report.files_failed = report.files_total
        return report

    # 2) assemble files by chunk offsets, then verify
    for entry in manifest.files:
        try:
            target = _safe_target(root, entry.names)
            if entry.linktarget or not entry.chunks:
                # symlink / directory marker: never materialise a zero-byte file that
                # would then collide with children entries
                target.mkdir(parents=True, exist_ok=True)
                report.directories += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as handle:
                for chunk in entry.chunks:
                    payload = (cache_dir / chunk.sha).read_bytes()
                    handle.seek(chunk.offset)
                    handle.write(payload)
                    report.bytes_written += len(payload)
            size = target.stat().st_size
            expected_size = entry.size_bytes or entry.size
            digest = hashlib.sha1(target.read_bytes()).hexdigest() if size <= 64 * 1024 * 1024 else _sha1_stream(target)
            if size != expected_size:
                raise RestoreError("size " + str(size) + " != " + str(expected_size))
            if entry.sha_content and digest != entry.sha_content:
                raise RestoreError("sha1 mismatch")
            report.files_ok += 1
        except Exception as exc:  # noqa: BLE001
            report.files_failed += 1
            report.errors.append((entry.names[0] if entry.names else "?") + ": " + str(exc))

    if not keep_cache:
        shutil.rmtree(cache_dir, ignore_errors=True)
    report.seconds = time.perf_counter() - started
    return report


def _sha1_stream(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()
