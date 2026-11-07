
import re, pathlib
root = pathlib.Path(r"E:\vibe coding\steam\tools\steamcore")
core = root / "core"
core.mkdir(exist_ok=True)
files = ["manifest.go","chunk.go","vdf.go","appinfo.go","keys_index.go","mirror.go","coverage.go","restore.go","apprestore.go"]
renames = [
    ("func decryptChunk(", "func DecryptChunk("),
    ("func decodeAuto(", "func DecodeAuto("),
    ("func decompress(", "func Decompress("),
    ("func hexKey(", "func HexKey("),
    ("decryptChunk(", "DecryptChunk("),
    ("decodeAuto(", "DecodeAuto("),
    ("decompress(", "Decompress("),
    ("hexKey(", "HexKey("),
]
for name in files:
    src = (root / name).read_text(encoding="utf-8")
    src = src.replace("package main", "package core", 1)
    for a, b in renames:
        src = src.replace(a, b)
    (core / name).write_text(src, encoding="utf-8")
    (root / name).unlink()
print("moved", len(files))
