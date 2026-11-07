"""Byte-level comparison of two game trees (L2 evidence when .manifest is missing).

Compares every shared relative path by streaming SHA-1; reports missing/extra files.
Usage:
    python tools/scripts/compare-trees.py --left <dir> --right <dir> --out report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

CHUNK = 4 * 1024 * 1024


def sha1_of(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def walk(root: Path, exclude_parts: tuple[str, ...]) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(root)
        if exclude_parts and any(part in rel.parts for part in exclude_parts):
            continue
        files[str(rel).lower()] = item
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two game trees by SHA-1.")
    parser.add_argument("--left", required=True)
    parser.add_argument("--right", required=True)
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--out", default=None)
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args(argv)

    left = Path(args.left)
    right = Path(args.right)
    exclude = tuple(args.exclude)
    left_files = walk(left, exclude)
    right_files = walk(right, exclude)

    shared = sorted(set(left_files) & set(right_files))
    only_left = sorted(set(left_files) - set(right_files))
    only_right = sorted(set(right_files) - set(left_files))

    mismatches = []
    compared = 0
    for rel in shared:
        compared += 1
        if sha1_of(left_files[rel]) != sha1_of(right_files[rel]):
            mismatches.append(rel)
            if len(mismatches) >= args.limit:
                break

    payload = {
        "left": str(left),
        "right": str(right),
        "shared_files": len(shared),
        "compared": compared,
        "mismatches": len(mismatches),
        "mismatch_samples": mismatches[: args.limit],
        "only_left": len(only_left),
        "only_left_samples": only_left[: args.limit],
        "only_right": len(only_right),
        "only_right_samples": only_right[: args.limit],
        "ok": not mismatches and not only_left,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
