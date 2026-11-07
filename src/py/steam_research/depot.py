"""Steam depot chunk decoding: AES-256 (ECB-then-CBC) + VZip/Zip decompression.

Reference implementation (read-only snapshot):
    opensource/SteamKit2-SteamRE/SteamKit2/SteamKit2/Steam/CDN/DepotChunk.cs

Layout per SteamKit:
    key    = 32-byte depot key
    iv     = AES-256-ECB-decrypt(first 16 bytes of ciphertext, no padding)
    plain  = AES-256-CBC-decrypt(rest, iv, PKCS7)
    magic  = "VSZa" (zstd) | "VZa" (LZMA/VZip) | "PK\\x03\\x04" (zip)

Pure standard library on purpose: the project core must not depend on pycryptodome.
"""

from __future__ import annotations

import io
import lzma
import zipfile
import zlib


class DepotError(ValueError):
    """Raised when a chunk cannot be decrypted or decoded."""


# ---------------------------------------------------------------------------
# Minimal AES-256 (decrypt only) - FIPS-197 inverse cipher
# ---------------------------------------------------------------------------

def _xtime(a: int) -> int:
    a <<= 1
    if a & 0x100:
        a ^= 0x11B
    return a & 0xFF


def _gmul(a: int, b: int) -> int:
    result = 0
    for _ in range(8):
        if b & 1:
            result ^= a
        b >>= 1
        a = _xtime(a)
    return result


def _rotl8(value: int, shift: int) -> int:
    return ((value << shift) | (value >> (8 - shift))) & 0xFF


def _build_sboxes() -> tuple[list[int], list[int]]:
    sbox = [0] * 256
    for x in range(256):
        inv = 0 if x == 0 else _gmul(x, 1)  # placeholder, fixed below
        sbox[x] = x  # overwritten below
    # multiplicative inverse via exponentiation, then affine transform
    for x in range(256):
        if x == 0:
            inv = 0
        else:
            inv = 1
            base = x
            exp = 254
            while exp:
                if exp & 1:
                    inv = _gmul(inv, base)
                base = _gmul(base, base)
                exp >>= 1
        s = (
            inv
            ^ _rotl8(inv, 1)
            ^ _rotl8(inv, 2)
            ^ _rotl8(inv, 3)
            ^ _rotl8(inv, 4)
            ^ 0x63
        )
        sbox[x] = s
    inv_sbox = [0] * 256
    for x in range(256):
        inv_sbox[sbox[x]] = x
    return sbox, inv_sbox


SBOX, INV_SBOX = _build_sboxes()


def _expand_key(key: bytes) -> list[list[int]]:
    if len(key) != 32:
        raise DepotError("AES-256 needs a 32-byte key")
    nk, nr = 8, 14
    words = [list(key[i * 4:(i + 1) * 4]) for i in range(nk)]
    rcon = 1
    for i in range(nk, 4 * (nr + 1)):
        temp = list(words[i - 1])
        if i % nk == 0:
            temp = temp[1:] + temp[:1]
            temp = [SBOX[b] for b in temp]
            temp[0] ^= rcon
            rcon = _xtime(rcon)
        elif i % nk == 4:
            temp = [SBOX[b] for b in temp]
        words.append([words[i - nk][j] ^ temp[j] for j in range(4)])
    return words


def _add_round_key(state: list[int], words: list[list[int]], rnd: int) -> None:
    for col in range(4):
        word = words[rnd * 4 + col]
        for row in range(4):
            state[col * 4 + row] ^= word[row]


def _inv_shift_rows(state: list[int]) -> None:
    for row in range(1, 4):
        row_values = [state[col * 4 + row] for col in range(4)]
        row_values = row_values[-row:] + row_values[:-row]
        for col in range(4):
            state[col * 4 + row] = row_values[col]


def _inv_sub_bytes(state: list[int]) -> None:
    for i in range(16):
        state[i] = INV_SBOX[state[i]]


def _inv_mix_columns(state: list[int]) -> None:
    for col in range(4):
        a = state[col * 4:(col + 1) * 4]
        state[col * 4 + 0] = _gmul(a[0], 14) ^ _gmul(a[1], 11) ^ _gmul(a[2], 13) ^ _gmul(a[3], 9)
        state[col * 4 + 1] = _gmul(a[0], 9) ^ _gmul(a[1], 14) ^ _gmul(a[2], 11) ^ _gmul(a[3], 13)
        state[col * 4 + 2] = _gmul(a[0], 13) ^ _gmul(a[1], 9) ^ _gmul(a[2], 14) ^ _gmul(a[3], 11)
        state[col * 4 + 3] = _gmul(a[0], 11) ^ _gmul(a[1], 13) ^ _gmul(a[2], 9) ^ _gmul(a[3], 14)


def aes256_decrypt_block(key: bytes, block: bytes) -> bytes:
    """Decrypt one 16-byte block with AES-256 (ECB primitive)."""
    if len(block) != 16:
        raise DepotError("AES block must be 16 bytes")
    words = _expand_key(key)
    state = list(block)
    _add_round_key(state, words, 14)
    for rnd in range(13, 0, -1):
        _inv_shift_rows(state)
        _inv_sub_bytes(state)
        _add_round_key(state, words, rnd)
        _inv_mix_columns(state)
    _inv_shift_rows(state)
    _inv_sub_bytes(state)
    _add_round_key(state, words, 0)
    return bytes(state)


def aes256_ecb_decrypt(key: bytes, data: bytes) -> bytes:
    if len(data) % 16:
        raise DepotError("ECB data length must be a multiple of 16")
    return b"".join(aes256_decrypt_block(key, data[i:i + 16]) for i in range(0, len(data), 16))


FAST_PATH_MIN_BYTES = 64 * 1024


def _openssl_executable() -> str | None:
    import shutil

    return shutil.which("openssl")


def _openssl_cbc_decrypt(key: bytes, iv: bytes, data: bytes) -> bytes | None:
    """Bulk AES-256-CBC via openssl (100x faster than the pure-python path)."""
    executable = _openssl_executable()
    if executable is None:
        return None
    import subprocess

    command = [
        executable,
        "enc",
        "-d",
        "-aes-256-cbc",
        "-K",
        key.hex(),
        "-iv",
        iv.hex(),
        "-nopad",
    ]
    completed = subprocess.run(command, input=data, capture_output=True, check=False)
    if completed.returncode != 0:
        raise DepotError("openssl failed: " + completed.stderr.decode("utf-8", "replace")[:200])
    return completed.stdout


def _unpad(data: bytes) -> bytes:
    if not data:
        raise DepotError("empty CBC payload")
    pad = data[-1]
    if pad < 1 or pad > 16 or data[-pad:] != bytes([pad]) * pad:
        raise DepotError("invalid PKCS7 padding")
    return data[:-pad]


def aes256_cbc_decrypt(key: bytes, iv: bytes, data: bytes, *, unpad: bool = True) -> bytes:
    if len(iv) != 16:
        raise DepotError("AES IV must be 16 bytes")
    if len(data) % 16:
        raise DepotError("CBC data length must be a multiple of 16")

    bulk = _openssl_cbc_decrypt(key, iv, data) if len(data) >= FAST_PATH_MIN_BYTES else None
    if bulk is not None:
        return _unpad(bulk) if unpad else bulk

    out = bytearray()
    prev = iv
    for offset in range(0, len(data), 16):
        block = data[offset:offset + 16]
        plain = aes256_decrypt_block(key, block)
        out.extend(a ^ b for a, b in zip(plain, prev))
        prev = block
    result = bytes(out)
    return _unpad(result) if unpad else result


# ---------------------------------------------------------------------------
# Chunk codecs
# ---------------------------------------------------------------------------

VZIP_HEADER = 7
VZIP_PROPS = 5
VZIP_FOOTER = 10


def _lzma1_filters(props: bytes) -> "list[dict]":
    if len(props) != 5:
        raise DepotError("LZMA properties must be 5 bytes")
    first = props[0]
    lc = first % 9
    rest = first // 9
    lp = rest % 5
    pb = rest // 5
    dict_size = int.from_bytes(props[1:5], "little")
    if dict_size < 4096:
        dict_size = 4096
    return [{"id": lzma.FILTER_LZMA1, "dict_size": dict_size, "lc": lc, "lp": lp, "pb": pb}]


def vzip_decompress(payload: bytes) -> bytes:
    """VZip = 7-byte header + 5 LZMA props + raw LZMA stream + 10-byte footer.

    The stream carries no end-of-stream marker: the footer holds the decompressed
    size, so we decompress with max_length (SteamKit VZipUtil does the same).
    """
    if not payload.startswith(b"VZ"):
        raise DepotError("not a VZip payload")
    if payload[2:3] != b"a":
        raise DepotError("unsupported VZip version " + repr(payload[2:3]))
    if len(payload) < VZIP_HEADER + VZIP_PROPS + VZIP_FOOTER:
        raise DepotError("VZip payload too short")
    props = payload[VZIP_HEADER:VZIP_HEADER + VZIP_PROPS]
    stream = payload[VZIP_HEADER + VZIP_PROPS:len(payload) - VZIP_FOOTER]
    footer = payload[len(payload) - VZIP_FOOTER:]
    output_crc = int.from_bytes(footer[0:4], "little")
    size = int.from_bytes(footer[4:8], "little", signed=True)
    if size < 0:
        raise DepotError("VZip footer declares a negative size")
    decompressor = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=_lzma1_filters(props))
    try:
        out = decompressor.decompress(stream, max_length=size)
    except lzma.LZMAError as exc:
        raise DepotError("VZip LZMA decode failed: " + str(exc)) from exc
    if len(out) != size:
        raise DepotError("VZip decoded " + str(len(out)) + " bytes, footer says " + str(size))
    if output_crc and (zlib.crc32(out) & 0xFFFFFFFF) != output_crc:
        raise DepotError("VZip CRC mismatch")
    return out


def zip_decompress(payload: bytes) -> bytes:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = archive.namelist()
            if not names:
                raise DepotError("zip payload has no members")
            return archive.read(names[0])
    except zipfile.BadZipFile as exc:
        raise DepotError("bad zip payload") from exc


VZSTD_HEADER = 8
VZSTD_FOOTER = 15


def vzstd_decompress(payload: bytes, *, runner=None) -> bytes:
    """VZstd = 8-byte header + zstd frame + 15-byte footer; needs an external zstd."""
    if not payload.startswith(b"VSZa"):
        raise DepotError("not a VZstd payload")
    if len(payload) < VZSTD_HEADER + VZSTD_FOOTER:
        raise DepotError("VZstd payload too short")
    frame = payload[VZSTD_HEADER:len(payload) - VZSTD_FOOTER]
    if runner is None:
        import shutil
        import subprocess

        executable = shutil.which("zstd")
        if executable is None:
            raise DepotError("zstd chunks need the zstd executable on PATH")

        def runner(blob: bytes) -> bytes:  # type: ignore[misc]
            completed = subprocess.run(
                [executable, "-d", "-c", "-q"], input=blob, capture_output=True, check=False
            )
            if completed.returncode != 0:
                raise DepotError("zstd failed: " + completed.stderr.decode("utf-8", "replace")[:200])
            return completed.stdout

    return runner(frame)


def decode_chunk(ciphertext: bytes, depot_key: bytes) -> bytes:
    """Decrypt + decompress one depot chunk (AES-256 ECB-IV + CBC, then VZip/Zip)."""
    if len(depot_key) != 32:
        raise DepotError("depot key must be 32 bytes")
    if len(ciphertext) < 32 or len(ciphertext) % 16:
        raise DepotError("chunk length must be a multiple of 16 and at least 32 bytes")
    iv = aes256_ecb_decrypt(depot_key, ciphertext[:16])
    plain = aes256_cbc_decrypt(depot_key, iv, ciphertext[16:])
    if plain.startswith(b"VZa"):
        return vzip_decompress(plain)
    if plain.startswith(b"PK\x03\x04"):
        return zip_decompress(plain)
    if plain.startswith(b"VSZa"):
        return vzstd_decompress(plain)
    raise DepotError("unexpected chunk compression: " + plain[:4].hex())
