"""Inventory a game body directory and dump JSON (L1 evidence helper).

Usage:
    python tools/scripts/body-report.py --appid 550 --dir "src/data/body/550"
    python tools/scripts/body-report.py --appid 550 --dir "D:\\Steam" --acf "D:\\Steam\\steamapps\\appmanifest_550.acf"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.parsers import AcfParseError, parse_acf_file  # noqa: E402


def find_appmanifest(body_dir: Path, appid: int) -> Path | None:
    candidates = [
        body_dir / "steamapps" / ("appmanifest_" + str(appid) + ".acf"),
        body_dir / ("appmanifest_" + str(appid) + ".acf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def inventory(body_dir: Path) -> dict:
    files = 0
    total = 0
    exes: list[str] = []
    for item in body_dir.rglob("*"):
        if not item.is_file():
            continue
        files += 1
        try:
            total += item.stat().st_size
        except OSError:
            continue
        if item.suffix.lower() == ".exe" and item.parent == body_dir:
            exes.append(item.name)
    return {"files": files, "bytes": total, "root_exes": sorted(exes)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory a game body directory.")
    parser.add_argument("--appid", type=int, required=True)
    parser.add_argument("--dir", required=True, dest="body_dir")
    parser.add_argument("--acf", default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    body_dir = Path(args.body_dir)
    payload: dict = {"appid": args.appid, "dir": str(body_dir.resolve()), "exists": body_dir.is_dir()}
    if not body_dir.is_dir():
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    payload.update(inventory(body_dir))

    acf_path = Path(args.acf) if args.acf else find_appmanifest(body_dir, args.appid)
    payload["acf"] = str(acf_path) if acf_path else None
    if acf_path is not None and acf_path.is_file():
        try:
            state = parse_acf_file(acf_path)
        except AcfParseError as exc:
            payload["acf_error"] = str(exc)
        else:
            payload["appmanifest"] = {
                "name": state.name,
                "buildid": state.buildid,
                "state_flags": state.state_flags,
                "size_on_disk": state.size_on_disk,
                "depots": [
                    {"depot_id": depot.depot_id, "gid": depot.manifest_gid, "size": depot.size}
                    for depot in state.depots
                ],
            }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")
        print("written: " + str(out_path), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
