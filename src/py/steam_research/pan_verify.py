"""Batch verification for external packages (pan shares), with hard-delete guards.

Rules baked in:
- only the requested files are downloaded (body only, never mods/extras)
- nothing is ever executed: we hash and sniff magic bytes instead
- each batch lives in its own directory and is removed when the batch is done,
  permanently (no Recycle Bin), and only after three independent checks pass
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MAGIC = (
    (b"MZ", "pe-executable", "high"),
    (b"\x7fELF", "elf-executable", "high"),
    (b"PK\x03\x04", "zip-container", "medium"),
    (b"Rar!\x1a\x07", "rar-archive", "medium"),
    (b"7z\xbc\xaf\x27\x1c", "7z-archive", "medium"),
    (b"\xff\xd8\xff", "jpeg-image", "low"),
    (b"\x89PNG", "png-image", "low"),
    (b"%PDF", "pdf-document", "low"),
    (b"\x1f\x8b", "gzip-archive", "low"),
    (b"VZa", "steam-vzip", "low"),
)


class VerifyError(ValueError):
    """Raised when a batch cannot be verified or deleted safely."""


@dataclass
class FileRecord:
    name: str
    path: str
    size: int
    sha256: str
    md5: str
    magic: str = "unknown"
    risk: str = "unknown"

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256,
            "md5": self.md5,
            "magic": self.magic,
            "risk": self.risk,
        }


@dataclass
class BatchReport:
    batch_id: str
    dir: str
    files: list[FileRecord] = field(default_factory=list)
    deleted: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def bytes_total(self) -> int:
        return sum(record.size for record in self.files)

    def as_dict(self) -> dict:
        return {
            "batch_id": self.batch_id,
            "dir": self.dir,
            "files": [record.as_dict() for record in self.files],
            "files_total": len(self.files),
            "bytes_total": self.bytes_total,
            "deleted": self.deleted,
            "errors": self.errors,
        }


def sniff(path: Path) -> "tuple[str, str]":
    with path.open("rb") as handle:
        head = handle.read(8)
    for magic, kind, risk in MAGIC:
        if head.startswith(magic):
            return kind, risk
    return "unknown", "low"


def hash_file(path: Path, chunk: int = 4 * 1024 * 1024) -> "tuple[int, str, str]":
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    size = 0
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            size += len(block)
            sha.update(block)
            md5.update(block)
    return size, sha.hexdigest(), md5.hexdigest()


def safe_target(batch_dir: Path, name: str) -> Path:
    """Flatten the share path into a single filename and refuse traversal."""
    flat = name.replace("\\", "/").split("/")[-1]
    if not flat or flat in (".", "..") or "/" in flat:
        raise VerifyError("unsafe file name: " + repr(name))
    target = (batch_dir / flat).resolve()
    if batch_dir.resolve() not in target.parents:
        raise VerifyError("target escapes batch dir: " + flat)
    return target


def three_round_check(batch_dir: Path, records: "list[FileRecord]", root: Path) -> "list[str]":
    """Return a list of problems; empty means safe to delete."""
    problems: list[str] = []
    batch_dir = batch_dir.resolve()
    root = root.resolve()

    # round 1: structural guard — the directory must be a direct child of root
    if root not in batch_dir.parents:
        problems.append("batch dir is outside the verify root")
    if batch_dir.name != batch_dir.name.strip() or batch_dir == root:
        problems.append("batch dir name is suspicious")
    if any(".." in record.path.split("/") for record in records):
        problems.append("record path contains ..")

    # round 2: presence + size must match the record exactly
    for record in records:
        target = batch_dir / Path(record.path).name
        if not target.is_file():
            problems.append("missing file: " + record.name)
            continue
        if target.stat().st_size != record.size:
            problems.append("size mismatch: " + record.name)

    # round 3: recompute hashes and compare
    for record in records:
        target = batch_dir / Path(record.path).name
        if not target.is_file():
            continue
        size, sha256, md5 = hash_file(target)
        if size != record.size:
            problems.append("rehash size mismatch: " + record.name)
        if sha256 != record.sha256:
            problems.append("sha256 mismatch: " + record.name)
        if md5 != record.md5:
            problems.append("md5 mismatch: " + record.name)

    # extra: nothing in the directory may be unknown to the record
    known = {Path(record.path).name for record in records}
    known.add("batch-record.json")  # our own bookkeeping file
    for child in batch_dir.iterdir():
        if child.name not in known:
            problems.append("unexpected entry: " + child.name)
    return problems


def hard_delete(batch_dir: Path, root: Path) -> None:
    """Permanently remove a batch directory (no Recycle Bin) after guard checks."""
    batch_dir = batch_dir.resolve()
    root = root.resolve()
    if root not in batch_dir.parents or batch_dir == root:
        raise VerifyError("refusing to delete outside verify root: " + str(batch_dir))
    if not batch_dir.is_dir():
        raise VerifyError("batch dir does not exist: " + str(batch_dir))
    shutil.rmtree(batch_dir, ignore_errors=False)
    if batch_dir.exists():
        raise VerifyError("batch dir still present after delete: " + str(batch_dir))


def verify_batch(
    batch_id: str,
    source: "list[tuple[str, int]]",
    root: str | Path,
    download: Callable[[str, Path], None],
    *,
    delete: bool = True,
    log_path: str | Path | None = None,
) -> BatchReport:
    """Download one batch, hash it, optionally delete it after triple checks."""
    root_path = Path(root).resolve()
    root_path.mkdir(parents=True, exist_ok=True)
    batch_dir = (root_path / batch_id).resolve()
    if batch_dir.exists():
        raise VerifyError("batch dir already exists: " + str(batch_dir))
    batch_dir.mkdir(parents=True)
    report = BatchReport(batch_id=batch_id, dir=str(batch_dir))

    for name, expected_size in source:
        target = safe_target(batch_dir, name)
        download(name, target)
        if not target.is_file():
            report.errors.append("download produced no file: " + name)
            continue
        size, sha256, md5 = hash_file(target)
        if expected_size and size != expected_size:
            report.errors.append("size mismatch on download: " + name)
        magic, risk = sniff(target)
        if risk == "high":
            report.errors.append("executable payload (never run): " + name)
        report.files.append(
            FileRecord(
                name=name,
                path=str(target),
                size=size,
                sha256=sha256,
                md5=md5,
                magic=magic,
                risk=risk,
            )
        )

    record_path = batch_dir / "batch-record.json"
    record_path.write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    if delete:
        problems = three_round_check(batch_dir, report.files, root_path)
        if problems:
            report.errors.extend(problems)
        else:
            hard_delete(batch_dir, root_path)
            report.deleted = True

    if log_path is not None:
        log = Path(log_path)
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(report.as_dict(), ensure_ascii=False) + "\n")
    return report
