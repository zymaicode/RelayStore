"""Minimal Steam depot manifest reader (protobuf sections, per SteamKit2).

Container layout (SteamKit2/Types/DepotManifest.cs):
    [u32 magic][i32 length][blob]   repeated for PAYLOAD / METADATA / SIGNATURE
    [u32 ENDOFMANIFEST magic]

Payload protobuf:
    ContentManifestPayload { 1: repeated FileMapping mappings }
    FileMapping            { 1: repeated string filenames, 2: repeated ChunkData chunks }
    ChunkData              { 1: bytes sha, 2: fixed32 crc, 3: varint offset,
                             4: varint cb_original, 5: varint cb_compressed }
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PAYLOAD_MAGIC = 0x71F617D0
METADATA_MAGIC = 0x1F4812BE
SIGNATURE_MAGIC = 0x1B81B817
END_MAGIC = 0x32C415AB


class ManifestError(ValueError):
    """Raised when manifest bytes cannot be parsed."""


@dataclass(frozen=True)
class Chunk:
    sha: str
    crc: int
    offset: int
    cb_original: int
    cb_compressed: int


@dataclass(frozen=True)
class FileEntry:
    names: tuple[str, ...]
    chunks: tuple[Chunk, ...]
    sha_content: str = ""
    size_bytes: int = 0
    linktarget: str = ""

    @property
    def size(self) -> int:
        return sum(chunk.cb_original for chunk in self.chunks)


@dataclass(frozen=True)
class DepotManifest:
    files: tuple[FileEntry, ...] = ()
    metadata: dict | None = None
    has_signature: bool = False

    @property
    def chunk_count(self) -> int:
        return sum(len(entry.chunks) for entry in self.files)

    def chunks(self):
        for entry in self.files:
            for chunk in entry.chunks:
                yield chunk


def _read_varint(data: bytes, pos: int) -> "tuple[int, int]":
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise ManifestError("truncated varint")
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 63:
            raise ManifestError("varint too long")


def _fields(data: bytes, start: int = 0, end: int | None = None):
    end = len(data) if end is None else end
    pos = start
    while pos < end:
        key, pos = _read_varint(data, pos)
        field_no, wire = key >> 3, key & 0x07
        if wire == 0:
            value, pos = _read_varint(data, pos)
            yield field_no, wire, value
        elif wire == 1:
            yield field_no, wire, data[pos:pos + 8]
            pos += 8
        elif wire == 2:
            length, pos = _read_varint(data, pos)
            yield field_no, wire, data[pos:pos + length]
            pos += length
        elif wire == 5:
            yield field_no, wire, data[pos:pos + 4]
            pos += 4
        else:
            raise ManifestError("unsupported wire type " + str(wire))
        if pos > end:
            raise ManifestError("field overran buffer")


def _parse_chunk(blob: bytes) -> Chunk:
    sha = ""
    crc = 0
    offset = 0
    cb_original = 0
    cb_compressed = 0
    for field_no, wire, value in _fields(blob):
        if field_no == 1 and wire == 2:
            sha = bytes(value).hex()
        elif field_no == 2 and wire == 5:
            crc = int.from_bytes(value, "little")
        elif field_no == 3 and wire == 0:
            offset = int(value)
        elif field_no == 4 and wire == 0:
            cb_original = int(value)
        elif field_no == 5 and wire == 0:
            cb_compressed = int(value)
    if not sha:
        raise ManifestError("chunk without sha")
    return Chunk(sha=sha, crc=crc, offset=offset, cb_original=cb_original, cb_compressed=cb_compressed)


def _parse_file(blob: bytes) -> FileEntry:
    names: list[str] = []
    chunks: list[Chunk] = []
    sha_content = ""
    size_bytes = 0
    linktarget = ""
    for field_no, wire, value in _fields(blob):
        if field_no == 1 and wire == 2:
            names.append(bytes(value).decode("utf-8", "replace"))
        elif field_no == 2 and wire == 0:
            size_bytes = int(value)
        elif field_no == 5 and wire == 2:
            sha_content = bytes(value).hex()
        elif field_no == 6 and wire == 2:  # FileMapping.chunks
            chunks.append(_parse_chunk(value))
        elif field_no == 7 and wire == 2:
            linktarget = bytes(value).decode("utf-8", "replace")
    return FileEntry(
        names=tuple(names),
        chunks=tuple(chunks),
        sha_content=sha_content,
        size_bytes=size_bytes,
        linktarget=linktarget,
    )


def _parse_payload(blob: bytes) -> tuple[FileEntry, ...]:
    files: list[FileEntry] = []
    for field_no, wire, value in _fields(blob):
        if field_no == 1 and wire == 2:
            files.append(_parse_file(value))
    return tuple(files)


def _parse_metadata(blob: bytes) -> dict:
    metadata: dict = {}
    for field_no, wire, value in _fields(blob):
        if field_no == 1 and wire == 0:
            metadata["depot_id"] = int(value)
        elif field_no == 2 and wire == 0:
            metadata["gid_manifest"] = int(value)
        elif field_no == 3 and wire == 0:
            metadata["creation_time"] = int(value)
        elif field_no == 8 and wire == 0:
            metadata["unique_chunks"] = int(value)
        elif field_no == 10 and wire == 0:
            metadata["crc_clear"] = int(value)
    return metadata


def parse_manifest(data: bytes) -> DepotManifest:
    if len(data) < 8:
        raise ManifestError("manifest too short")
    pos = 0
    files: tuple[FileEntry, ...] = ()
    metadata: dict | None = None
    has_signature = False
    while pos + 4 <= len(data):
        magic = int.from_bytes(data[pos:pos + 4], "little")
        pos += 4
        if magic == END_MAGIC:
            return DepotManifest(files=files, metadata=metadata, has_signature=has_signature)
        if magic not in (PAYLOAD_MAGIC, METADATA_MAGIC, SIGNATURE_MAGIC):
            raise ManifestError("unrecognised section magic: " + hex(magic))
        if pos + 4 > len(data):
            raise ManifestError("truncated section length")
        length = int.from_bytes(data[pos:pos + 4], "little", signed=True)
        pos += 4
        if length < 0 or pos + length > len(data):
            raise ManifestError("truncated section body")
        blob = data[pos:pos + length]
        pos += length
        if magic == PAYLOAD_MAGIC:
            files = _parse_payload(blob)
        elif magic == METADATA_MAGIC:
            metadata = _parse_metadata(blob)
        else:
            has_signature = True
    raise ManifestError("missing end-of-manifest marker")


def parse_manifest_file(path: str | Path) -> DepotManifest:
    return parse_manifest(Path(path).read_bytes())
