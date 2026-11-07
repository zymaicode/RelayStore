"""Depot key sources: JSON corpora, the local Steam client, and ad-hoc hex."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .parsers.vdf import VdfError, parse_vdf


class KeyError_(ValueError):
    """Raised when a depot key cannot be loaded."""


@dataclass
class Keyring:
    """depot_id -> 32-byte key, from any number of sources."""

    keys: dict[int, bytes] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    invalid: int = 0

    def add_hex(self, depot_id: int, hex_key: str, *, source: str = "inline") -> None:
        text = str(hex_key).strip().lower()
        if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
            raise KeyError_("depot " + str(depot_id) + ": key must be 64 hex chars")
        self.keys[int(depot_id)] = bytes.fromhex(text)
        if source not in self.sources:
            self.sources.append(source)

    def get(self, depot_id: int) -> bytes | None:
        return self.keys.get(int(depot_id))

    def has(self, depot_id: int) -> bool:
        return int(depot_id) in self.keys

    def __len__(self) -> int:
        return len(self.keys)

    def merge(self, other: "Keyring") -> "Keyring":
        self.keys.update(other.keys)
        for source in other.sources:
            if source not in self.sources:
                self.sources.append(source)
        self.invalid += other.invalid
        return self

    def save_json(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {str(depot): key.hex() for depot, key in sorted(self.keys.items())}
        target.write_text(json.dumps(payload), encoding="utf-8")
        return target

    @classmethod
    def from_json_text(cls, text: str, *, source: str = "text") -> "Keyring":
        ring = cls()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise KeyError_("cannot parse " + source + ": " + str(exc)) from exc
        if not isinstance(payload, dict):
            raise KeyError_(source + " is not a JSON object")
        for raw_depot, raw_key in payload.items():
            if not str(raw_depot).strip().isdigit():
                continue
            try:
                ring.add_hex(int(raw_depot), str(raw_key), source=source)
            except KeyError_:
                ring.invalid += 1
        return ring

    @classmethod
    def from_json_files(cls, paths) -> "Keyring":
        ring = cls()
        for path in paths:
            resolved = Path(path)
            if not resolved.is_file():
                continue
            payload = json.loads(resolved.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict):
                continue
            for raw_depot, raw_key in payload.items():
                if not str(raw_depot).strip().isdigit():
                    continue
                try:
                    ring.add_hex(int(raw_depot), str(raw_key), source=resolved.name)
                except KeyError_:
                    ring.invalid += 1  # corpus files carry junk keys; skip them
                    continue
        return ring

    @classmethod
    def from_vdf_text(cls, text: str, *, source: str = "key.vdf") -> "Keyring":
        """Collect every depots.<id>.DecryptionKey found anywhere in a VDF tree."""
        ring = cls()
        try:
            parsed = parse_vdf(text)
        except VdfError as exc:
            raise KeyError_("cannot parse " + source + ": " + str(exc)) from exc

        def collect(node) -> None:
            if not isinstance(node, dict):
                return
            for key, value in node.items():
                if key == "depots" and isinstance(value, dict):
                    for raw_depot, body in value.items():
                        if not str(raw_depot).strip().isdigit() or not isinstance(body, dict):
                            continue
                        hex_key = body.get("DecryptionKey")
                        if hex_key:
                            try:
                                ring.add_hex(int(raw_depot), str(hex_key), source=source)
                            except KeyError_:
                                continue
                collect(value)

        collect(parsed)
        return ring

    @classmethod
    def from_config_vdf(cls, path: str | Path) -> "Keyring":
        """Read depots.<id>.DecryptionKey out of a Steam client config.vdf."""
        resolved = Path(path)
        if not resolved.is_file():
            raise KeyError_("config.vdf not found: " + str(resolved))
        try:
            text = resolved.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise KeyError_("cannot read config.vdf: " + str(exc)) from exc
        return cls.from_vdf_text(text, source=resolved.name)

    @classmethod
    def from_vdf_files(cls, paths) -> "Keyring":
        ring = cls()
        for path in paths:
            resolved = Path(path)
            if resolved.is_file():
                ring.merge(cls.from_config_vdf(resolved))
        return ring
