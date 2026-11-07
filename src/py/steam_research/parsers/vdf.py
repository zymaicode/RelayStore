"""Generic VDF (Valve Data Format) text parser, returns nested dicts."""

from __future__ import annotations

from dataclasses import dataclass


class VdfError(ValueError):
    """Raised on malformed VDF text; carries the line number."""

    def __init__(self, message: str, *, line: int | None = None):
        self.line = line
        super().__init__(message + ((" (line " + str(line) + ")") if line else ""))


@dataclass(frozen=True)
class _Tok:
    kind: str
    value: str
    line: int


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'"}


def _lex(text: str):
    tokens: list[_Tok] = []
    i = 0
    line = 1
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in " \t\r\n\ufeff":
            if ch == "\n":
                line += 1
            i += 1
            continue
        if text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "{":
            tokens.append(_Tok("{", "{", line))
            i += 1
            continue
        if ch == "}":
            tokens.append(_Tok("}", "}", line))
            i += 1
            continue
        if ch == '"':
            start = line
            i += 1
            buf: list[str] = []
            while True:
                if i >= n:
                    raise VdfError("unterminated string", line=start)
                cur = text[i]
                if cur == '"':
                    i += 1
                    break
                if cur == "\\":
                    nxt = text[i + 1] if i + 1 < n else ""
                    buf.append(_ESCAPES.get(nxt, "\\" + nxt))
                    i += 2 if nxt else 1
                    continue
                if cur == "\n":
                    line += 1
                buf.append(cur)
                i += 1
            tokens.append(_Tok("string", "".join(buf), start))
            continue
        # bare token
        start = line
        buf = []
        while i < n and text[i] not in ' \t\r\n{}"':
            buf.append(text[i])
            i += 1
        if not buf:
            raise VdfError("unexpected character " + repr(ch), line=line)
        tokens.append(_Tok("string", "".join(buf), start))
    tokens.append(_Tok("eof", "", line))
    return tokens


def parse_vdf(text: str) -> dict:
    """Parse one root block or a flat key/value body into a dict."""
    tokens = _lex(text)
    pos = 0

    def parse_body(opener_line: int) -> dict:
        nonlocal pos
        result: dict = {}
        while True:
            tok = tokens[pos]
            if tok.kind == "eof":
                raise VdfError("unclosed block", line=opener_line)
            if tok.kind == "}":
                pos += 1
                return result
            if tok.kind != "string":
                raise VdfError("expected a key", line=tok.line)
            key = tok.value
            pos += 1
            nxt = tokens[pos]
            if nxt.kind == "string":
                result[key] = nxt.value
                pos += 1
            elif nxt.kind == "{":
                pos += 1
                result[key] = parse_body(nxt.line)
            else:
                raise VdfError("key " + repr(key) + " has no value", line=nxt.line)

    first = tokens[pos]
    if first.kind == "string" and tokens[pos + 1].kind == "{":
        root = first.value
        pos += 2
        body = parse_body(tokens[pos - 1].line)
        return {root: body}
    return parse_body(1)
