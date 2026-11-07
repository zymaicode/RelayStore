"""SHA-1 / size verification and safe path joining (M1-T06)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

CHUNK_SIZE = 4 * 1024 * 1024


class VerifyError(ValueError):
    """Raised when a verification request is malformed or a file is missing."""


@dataclass(frozen=True)
class VerifyCheck:
    name: str
    expected: str
    actual: str
    status: str  # "OK" | "FAIL"

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "expected": self.expected,
            "actual": self.actual,
            "status": self.status,
        }


@dataclass(frozen=True)
class VerifyReport:
    ok: bool
    checks: tuple[VerifyCheck, ...]

    def as_dict(self) -> dict:
        return {"ok": self.ok, "checks": [check.as_dict() for check in self.checks]}


def _is_sha1(value: str) -> bool:
    return len(value) == 40 and all(ch in "0123456789abcdefABCDEF" for ch in value)


def sha1_file(path: str | Path, chunk_size: int = CHUNK_SIZE) -> str:
    """Stream a file and return its SHA-1 hex digest."""
    resolved = Path(path)
    if not resolved.is_file():
        raise VerifyError("file not found: " + str(resolved))
    if chunk_size <= 0:
        raise VerifyError("chunk_size must be positive")
    digest = hashlib.sha1()
    with resolved.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(
    path: str | Path,
    *,
    sha1: str | None = None,
    size: int | None = None,
    chunk_size: int = CHUNK_SIZE,
) -> VerifyReport:
    """Compare a file against an expected SHA-1 and/or size."""
    if sha1 is None and size is None:
        raise VerifyError("nothing to verify: pass sha1 and/or size")
    if sha1 is not None and not _is_sha1(sha1):
        raise VerifyError("invalid sha1: " + repr(sha1))
    resolved = Path(path)
    if not resolved.is_file():
        raise VerifyError("file not found: " + str(resolved))

    checks: list[VerifyCheck] = []
    actual_size = resolved.stat().st_size
    if sha1 is not None:
        actual_sha1 = sha1_file(resolved, chunk_size=chunk_size)
        checks.append(
            VerifyCheck(
                name="sha1",
                expected=sha1.lower(),
                actual=actual_sha1,
                status="OK" if actual_sha1 == sha1.lower() else "FAIL",
            )
        )
    if size is not None:
        checks.append(
            VerifyCheck(
                name="size",
                expected=str(int(size)),
                actual=str(actual_size),
                status="OK" if actual_size == int(size) else "FAIL",
            )
        )
    return VerifyReport(
        ok=all(check.status == "OK" for check in checks),
        checks=tuple(checks),
    )


def safe_join(root: str | Path, relative: str) -> Path:
    """Join a manifest-relative path under root, rejecting traversal tricks."""
    text = str(relative).strip()
    if not text:
        raise VerifyError("empty relative path")
    if ":" in text:
        raise VerifyError("absolute paths and drive/ADS colons are not allowed: " + text)
    candidate = Path(text)
    if candidate.is_absolute() or candidate.drive:
        raise VerifyError("absolute paths are not allowed: " + text)
    if any(part == ".." for part in candidate.parts):
        raise VerifyError("path traversal is not allowed: " + text)
    return Path(root) / candidate
