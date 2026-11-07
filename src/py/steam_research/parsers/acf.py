"""Parse Steam appmanifest files: steamapps/appmanifest_<appid>.acf (VDF text).

Grammar (Steam VDF text, enough for an AppState block):

    document := STRING "{" body "}"
    body     := entry*
    entry    := STRING value
    value    := STRING | "{" body "}"

Tolerated noise: UTF-8 BOM, CRLF, // line comments, /* block */ comments,
tabs / spaces, unquoted bare tokens (550), escaped quotes (\").

Every failure carries the line (and column) that caused it: that is the point of
a hand-written parser here, because "malformed input reports a line number" is an
M1-T01 acceptance item.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ..model import AppRecord, ManifestRef

SOURCE = "acf"

_BARE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:/-+")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'"}


class AcfParseError(ValueError):
    """Raised when an appmanifest is not valid VDF / not a usable AppState."""

    def __init__(
        self,
        message: str,
        *,
        line: int | None = None,
        column: int | None = None,
        path: str | None = None,
    ):
        self.line = line
        self.column = column
        self.path = path
        bits = []
        if line is not None:
            bits.append("line " + str(line))
        if column is not None:
            bits.append("column " + str(column))
        where = ", ".join(bits) if bits else "unknown position"
        prefix = (str(path) + ": ") if path else ""
        super().__init__(prefix + message + " (" + where + ")")


@dataclass(frozen=True)
class AcfDepot:
    """One entry of InstalledDepots: a depot plus its installed manifest."""

    depot_id: int
    manifest_gid: str | None = None
    size: int | None = None
    raw: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AcfAppState:
    """Parsed AppState block of an appmanifest."""

    appid: int
    name: str | None = None
    installdir: str | None = None
    buildid: str | None = None
    state_flags: int | None = None
    size_on_disk: int | None = None
    depots: tuple[AcfDepot, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict)
    source_path: str = ""
    fetched_at: str = ""

    def to_app_record(self) -> AppRecord:
        """Normalise into the shared model so the catalog can store it."""
        manifests = tuple(
            sorted(
                (
                    ManifestRef(
                        appid=self.appid,
                        depot_id=depot.depot_id,
                        gid=depot.manifest_gid,
                        size=depot.size,
                        source=SOURCE,
                        source_url=self.source_path,
                        fetched_at=self.fetched_at,
                    )
                    for depot in self.depots
                    if depot.manifest_gid
                ),
                key=lambda ref: ref.depot_id,
            )
        )
        return AppRecord(
            appid=self.appid,
            name=self.name,
            depots=tuple(sorted({depot.depot_id for depot in self.depots})),
            manifests=manifests,
        )


@dataclass(frozen=True)
class _Token:
    kind: str  # "string" | "{" | "}" | "eof"
    value: str
    line: int
    column: int


class _VdfDict(dict):
    """dict that remembers the source line of every key."""

    __slots__ = ("lines", "line")

    def __init__(self, line: int):
        super().__init__()
        self.lines: dict[str, int] = {}
        self.line = line

    def put(self, key: str, value: Any, line: int) -> None:
        self[key] = value
        self.lines[key.lower()] = line


def _lex(text: str, path: str = "") -> list[_Token]:
    tokens: list[_Token] = []
    i = 0
    line = 1
    column = 1
    n = len(text)

    def advance(count: int = 1) -> None:
        nonlocal i, line, column
        for _ in range(count):
            if i < n and text[i] == "\n":
                line += 1
                column = 1
            else:
                column += 1
            i += 1

    while i < n:
        ch = text[i]

        if ch in " \t\r\n\f\v\ufeff":
            advance()
            continue

        if text.startswith("//", i):
            while i < n and text[i] != "\n":
                advance()
            continue

        if text.startswith("/*", i):
            start_line, start_col = line, column
            advance(2)
            while i < n and not text.startswith("*/", i):
                advance()
            if i >= n:
                raise AcfParseError(
                    "unterminated block comment",
                    line=start_line,
                    column=start_col,
                    path=path,
                )
            advance(2)
            continue

        if ch == "{":
            tokens.append(_Token("{", "{", line, column))
            advance()
            continue

        if ch == "}":
            tokens.append(_Token("}", "}", line, column))
            advance()
            continue

        if ch == '"':
            start_line, start_col = line, column
            advance()
            buf: list[str] = []
            while True:
                if i >= n:
                    raise AcfParseError(
                        "unterminated string",
                        line=start_line,
                        column=start_col,
                        path=path,
                    )
                cur = text[i]
                if cur == '"':
                    advance()
                    break
                if cur == "\\":
                    nxt = text[i + 1] if i + 1 < n else ""
                    buf.append(_ESCAPES.get(nxt, "\\" + nxt))
                    advance(2 if nxt else 1)
                    continue
                buf.append(cur)
                advance()
            tokens.append(_Token("string", "".join(buf), start_line, start_col))
            continue

        if ch in _BARE_CHARS:
            start_line, start_col = line, column
            buf = []
            while i < n and text[i] in _BARE_CHARS:
                buf.append(text[i])
                advance()
            tokens.append(_Token("string", "".join(buf), start_line, start_col))
            continue

        raise AcfParseError(
            "unexpected character " + repr(ch), line=line, column=column, path=path
        )

    tokens.append(_Token("eof", "", line, column))
    return tokens


class _Parser:
    def __init__(self, tokens: list[_Token], path: str):
        self.tokens = tokens
        self.pos = 0
        self.path = path

    def peek(self) -> _Token:
        return self.tokens[self.pos]

    def next(self) -> _Token:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def error(self, message: str, token: _Token) -> AcfParseError:
        return AcfParseError(message, line=token.line, column=token.column, path=self.path)

    def parse(self) -> _VdfDict:
        key = self.peek()
        if key.kind == "eof":
            raise self.error("empty input: expected an AppState block", key)
        if key.kind != "string":
            raise self.error("expected a block name, got " + repr(key.value), key)
        self.next()

        brace = self.peek()
        if brace.kind != "{":
            raise self.error("expected '{' after " + repr(key.value), brace)
        self.next()

        block = self.block(brace)
        tail = self.peek()
        if tail.kind != "eof":
            raise self.error("trailing data after root block: " + repr(tail.value), tail)

        if key.value.strip().lower() != "appstate":
            raise self.error(
                "root block must be 'AppState', got " + repr(key.value), key
            )
        return block

    def block(self, opener: _Token) -> _VdfDict:
        result = _VdfDict(opener.line)
        while True:
            token = self.peek()
            if token.kind == "eof":
                raise AcfParseError(
                    "unclosed '{': block opened at line " + str(opener.line),
                    line=opener.line,
                    column=opener.column,
                    path=self.path,
                )
            if token.kind == "}":
                self.next()
                return result
            if token.kind != "string":
                raise self.error("expected a key, got " + repr(token.value), token)
            self.next()

            value = self.peek()
            if value.kind == "string":
                self.next()
                result.put(token.value, value.value, token.line)
            elif value.kind == "{":
                self.next()
                result.put(token.value, self.block(value), token.line)
            else:
                raise self.error("key " + repr(token.value) + " has no value", value)


def _lookup(block: Mapping[str, Any], key: str) -> Any:
    lowered = key.lower()
    for name, value in block.items():
        if name.lower() == lowered:
            return value
    return None


def _lookup_line(block: _VdfDict, key: str, fallback: int) -> int:
    return block.lines.get(key.lower(), fallback)


def _as_int(value: Any, field_name: str, line: int, path: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, dict):
        raise AcfParseError(field_name + " must be a number", line=line, path=path)
    text = str(value).strip()
    if text.lstrip("+-").isdigit():
        return int(text)
    raise AcfParseError(
        field_name + " must be a number, got " + repr(value), line=line, path=path
    )


def _as_str(value: Any) -> str | None:
    if value is None or isinstance(value, dict):
        return None
    return str(value)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    return value


def _parse_depots(
    block: Any, appid: int, path: str, parent_line: int
) -> tuple[AcfDepot, ...]:
    if block is None:
        return ()
    if not isinstance(block, _VdfDict):
        raise AcfParseError(
            "InstalledDepots must be a block", line=parent_line, path=path
        )

    depots: list[AcfDepot] = []
    for raw_id, body in block.items():
        depot_line = block.lines.get(raw_id.lower(), parent_line)
        if not raw_id.strip().isdigit():
            raise AcfParseError(
                "depot id must be numeric, got " + repr(raw_id) + " (appid=" + str(appid) + ")",
                line=depot_line,
                path=path,
            )
        if not isinstance(body, _VdfDict):
            raise AcfParseError(
                "depot " + raw_id + " must be a block", line=depot_line, path=path
            )

        gid = _as_str(_lookup(body, "manifest"))
        if gid is not None:
            gid = gid.strip()
            if not gid.isdigit() or not 10 <= len(gid) <= 20:
                raise AcfParseError(
                    "depot " + raw_id + " has an invalid manifest gid " + repr(gid),
                    line=_lookup_line(body, "manifest", depot_line),
                    path=path,
                )

        size = _as_int(
            _lookup(body, "size"),
            "depot " + raw_id + " size",
            _lookup_line(body, "size", depot_line),
            path,
        )
        depots.append(
            AcfDepot(
                depot_id=int(raw_id),
                manifest_gid=gid,
                size=size,
                raw=_plain(body),
            )
        )
    return tuple(depots)


def parse_acf(text: str, *, source_path: str = "") -> AcfAppState:
    """Parse appmanifest text into an AcfAppState."""
    if isinstance(text, bytes):
        raise TypeError("parse_acf() takes str; use parse_acf_file() for bytes")

    tokens = _lex(text, source_path)
    block = _Parser(tokens, source_path).parse()
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    appid_value = _lookup(block, "appid")
    if appid_value is None or isinstance(appid_value, dict):
        raise AcfParseError("AppState has no appid", line=block.line, path=source_path)
    appid = _as_int(
        appid_value, "appid", _lookup_line(block, "appid", block.line), source_path
    )
    if appid is None or appid <= 0:
        raise AcfParseError(
            "appid must be a positive number, got " + repr(appid_value),
            line=_lookup_line(block, "appid", block.line),
            path=source_path,
        )

    depots = _parse_depots(
        _lookup(block, "InstalledDepots"),
        appid,
        source_path,
        _lookup_line(block, "InstalledDepots", block.line),
    )

    return AcfAppState(
        appid=appid,
        name=_as_str(_lookup(block, "name")),
        installdir=_as_str(_lookup(block, "installdir")),
        buildid=_as_str(_lookup(block, "buildid")),
        state_flags=_as_int(
            _lookup(block, "StateFlags"),
            "StateFlags",
            _lookup_line(block, "StateFlags", block.line),
            source_path,
        ),
        size_on_disk=_as_int(
            _lookup(block, "SizeOnDisk"),
            "SizeOnDisk",
            _lookup_line(block, "SizeOnDisk", block.line),
            source_path,
        ),
        depots=depots,
        raw=_plain(block),
        source_path=source_path,
        fetched_at=fetched_at,
    )


def parse_acf_file(path: str | Path) -> AcfAppState:
    """Read and parse one appmanifest_*.acf file (UTF-8, cp1252 fallback)."""
    resolved = Path(path)
    data = resolved.read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    return parse_acf(text, source_path=str(resolved))
