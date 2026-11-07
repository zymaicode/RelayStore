"""Parse and update SteamTools / LMU style Lua manifest configs (M1-T03).

Only two calls carry manifest state; everything else (comments, addtoken,
unknown user code) is preserved byte for byte so an update produces a diff
limited to the gid / size that actually changed.

    addappid(550)                              -- appid declaration
    addappid(551, 1, "314878501352141828")     -- depot + manifest gid
    setManifestid(551, "314878501352141828", 11329675570)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_ADDAPPID = re.compile(
    r'^(?P<indent>\s*)addappid\s*\(\s*(?P<depot>\d+)\s*'
    r'(?:,\s*(?P<flag>\d+)\s*(?:,\s*"(?P<gid>[^"]*)"\s*)?)?\)\s*(?P<tail>--.*)?$'
)
_SETMANIFEST = re.compile(
    r'^(?P<indent>\s*)setManifestid\s*\(\s*(?P<depot>\d+)\s*,\s*"(?P<gid>[^"]*)"'
    r'\s*(?:,\s*(?P<size>\d+)\s*)?\)\s*(?P<tail>--.*)?$'
)


class LuaError(ValueError):
    """Raised when a Lua manifest config cannot be parsed or updated."""


@dataclass(frozen=True)
class LuaEntry:
    gid: str | None = None
    size: int | None = None


def _valid_gid(gid: str) -> bool:
    return gid.isdigit() and 10 <= len(gid) <= 20


@dataclass
class LuaConfig:
    appid: int | None
    lines: list[str] = field(default_factory=list)
    entries: dict[int, LuaEntry] = field(default_factory=dict)
    trailing_newline: bool = True

    @classmethod
    def parse(cls, text: str) -> "LuaConfig":
        raw_lines = text.splitlines()
        config = cls(
            appid=None,
            lines=list(raw_lines),
            entries={},
            trailing_newline=text.endswith("\n"),
        )
        for line in raw_lines:
            setmatch = _SETMANIFEST.match(line)
            if setmatch:
                depot = int(setmatch.group("depot"))
                gid = setmatch.group("gid")
                size = setmatch.group("size")
                config.entries[depot] = LuaEntry(
                    gid=gid or None,
                    size=int(size) if size else None,
                )
                continue
            addmatch = _ADDAPPID.match(line)
            if addmatch:
                depot = int(addmatch.group("depot"))
                gid = addmatch.group("gid")
                if gid:
                    previous = config.entries.get(depot)
                    config.entries[depot] = LuaEntry(
                        gid=gid,
                        size=previous.size if previous else None,
                    )
                elif config.appid is None:
                    config.appid = depot
        return config

    def render(self) -> str:
        text = "\n".join(self.lines)
        return text + ("\n" if self.trailing_newline else "")

    def apply(
        self,
        manifests: "dict[int, str]",
        sizes: "dict[int, int | None] | None" = None,
    ) -> str:
        """Return new config text where only gid / size lines changed."""
        updates: dict[int, str] = {}
        for raw_depot, raw_gid in manifests.items():
            depot = int(raw_depot)
            gid = str(raw_gid).strip()
            if not _valid_gid(gid):
                raise LuaError("invalid manifest gid " + repr(raw_gid) + " for depot " + str(depot))
            updates[depot] = gid
        new_sizes = {int(k): v for k, v in (sizes or {}).items()}

        handled: set[int] = set()
        new_lines = list(self.lines)
        for index, line in enumerate(new_lines):
            setmatch = _SETMANIFEST.match(line)
            if setmatch:
                depot = int(setmatch.group("depot"))
                if depot in updates:
                    size = new_sizes.get(depot, setmatch.group("size"))
                    size_part = ", " + str(size) if size is not None else ""
                    tail = (" " + setmatch.group("tail")) if setmatch.group("tail") else ""
                    new_lines[index] = (
                        setmatch.group("indent")
                        + 'setManifestid('
                        + str(depot)
                        + ', "'
                        + updates[depot]
                        + '"'
                        + size_part
                        + ")"
                        + tail
                    )
                    handled.add(depot)
                continue
            addmatch = _ADDAPPID.match(line)
            if addmatch and addmatch.group("gid"):
                depot = int(addmatch.group("depot"))
                if depot in updates:
                    tail = (" " + addmatch.group("tail")) if addmatch.group("tail") else ""
                    new_lines[index] = (
                        addmatch.group("indent")
                        + 'addappid('
                        + str(depot)
                        + ", "
                        + (addmatch.group("flag") or "1")
                        + ', "'
                        + updates[depot]
                        + '")'
                        + tail
                    )
                    handled.add(depot)

        for depot in sorted(updates):
            if depot in handled:
                continue
            size = new_sizes.get(depot)
            size_part = ", " + str(size) if size is not None else ""
            new_lines.append(
                'setManifestid(' + str(depot) + ', "' + updates[depot] + '"' + size_part + ")"
            )

        text = "\n".join(new_lines)
        return text + ("\n" if self.trailing_newline else "")


def parse_lua(text: str) -> LuaConfig:
    return LuaConfig.parse(text)


def parse_lua_file(path) -> LuaConfig:
    from pathlib import Path

    resolved = Path(path)
    return parse_lua(resolved.read_text(encoding="utf-8-sig"))
