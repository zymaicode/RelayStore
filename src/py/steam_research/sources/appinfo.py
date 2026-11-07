"""Public app info through steamcmd: works for apps the account does not own.

`steamcmd +login anonymous "+app_info_print <appid>"` prints the public VDF block,
which includes the depot list with manifest gids. This is the keyless replacement
for the token-gated appinfo APIs.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..parsers.vdf import VdfError, parse_vdf

DEFAULT_STEAMCMD = Path("tools/bin/steamcmd.exe")


class AppInfoError(ValueError):
    """Raised when app info cannot be fetched or parsed."""


@dataclass(frozen=True)
class DepotInfo:
    depot_id: int
    gid: str
    size: int | None = None
    name: str | None = None

    def as_dict(self) -> dict:
        return {"depot_id": self.depot_id, "gid": self.gid, "size": self.size, "name": self.name}


def extract_block(raw: str, appid: int) -> str:
    """Cut the output down to the quoted appid block steamcmd prints."""
    marker = '"' + str(appid) + '"'
    index = raw.find(marker)
    if index < 0:
        raise AppInfoError("appid " + str(appid) + " not found in steamcmd output")
    depth = 0
    started = False
    end = index
    for pos in range(index, len(raw)):
        ch = raw[pos]
        if ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
            if started and depth == 0:
                end = pos + 1
                break
    if not started or depth != 0:
        raise AppInfoError("unbalanced block for appid " + str(appid))
    return raw[index:end]


def parse_app_info(raw: str, appid: int) -> dict:
    block = extract_block(raw, appid)
    try:
        parsed = parse_vdf(block)
    except VdfError as exc:
        raise AppInfoError("cannot parse app info: " + str(exc)) from exc
    return parsed.get(str(appid), parsed)


def depots_from_app_info(info: dict) -> tuple[DepotInfo, ...]:
    depots = info.get("depots") if isinstance(info, dict) else None
    if not isinstance(depots, dict):
        return ()
    out: list[DepotInfo] = []
    for raw_id, body in depots.items():
        if not str(raw_id).isdigit() or not isinstance(body, dict):
            continue
        manifests = body.get("manifests")
        public = manifests.get("public") if isinstance(manifests, dict) else None
        gid = public.get("gid") if isinstance(public, dict) else None
        if not gid or not str(gid).isdigit():
            continue
        size = None
        if isinstance(public, dict) and str(public.get("size", "")).isdigit():
            size = int(public["size"])
        out.append(
            DepotInfo(
                depot_id=int(raw_id),
                gid=str(gid),
                size=size,
                name=body.get("name") if isinstance(body.get("name"), str) else None,
            )
        )
    return tuple(sorted(out, key=lambda depot: depot.depot_id))


def app_info_raw(appid: int, *, steamcmd: str | Path = DEFAULT_STEAMCMD, timeout: float = 180.0) -> str:
    executable = Path(steamcmd)
    if not executable.is_file():
        raise AppInfoError("steamcmd not found: " + str(executable))
    command = [str(executable), "+login", "anonymous", "+app_info_print", str(appid), "+quit"]
    try:
        completed = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise AppInfoError("steamcmd timed out for appid " + str(appid)) from exc
    raw = (completed.stdout or b"") + (completed.stderr or b"")
    try:
        output = raw.decode("utf-8")
    except UnicodeDecodeError:
        output = raw.decode("cp1252", "replace")
    if '"' + str(appid) + '"' not in output:
        raise AppInfoError("steamcmd returned no app info for appid " + str(appid))
    return output


def public_depots(appid: int, *, cache_dir: str | Path | None = None, **kwargs) -> tuple[DepotInfo, ...]:
    """Public depots for an appid; optional on-disk cache avoids repeated steamcmd runs."""
    cache_file = None
    if cache_dir is not None:
        import json

        folder = Path(cache_dir)
        folder.mkdir(parents=True, exist_ok=True)
        cache_file = folder / (str(int(appid)) + ".json")
        if cache_file.is_file():
            try:
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
                return tuple(
                    DepotInfo(
                        depot_id=int(item["depot_id"]),
                        gid=str(item["gid"]),
                        size=item.get("size"),
                        name=item.get("name"),
                    )
                    for item in payload
                )
            except Exception:  # noqa: BLE001 - a corrupt cache must not block a fetch
                pass

    depots = depots_from_app_info(parse_app_info(app_info_raw(appid, **kwargs), appid))
    if cache_file is not None:
        import json

        cache_file.write_text(
            json.dumps([depot.as_dict() for depot in depots], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    return depots
