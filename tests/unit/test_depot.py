"""Unit tests for depot chunk decoding (AES-256 + VZip/Zip)."""

from __future__ import annotations

import io
import lzma
import os
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "py"))

from steam_research.depot import (
    DepotError,
    aes256_cbc_decrypt,
    aes256_decrypt_block,
    aes256_ecb_decrypt,
    decode_chunk,
    vzip_decompress,
    zip_decompress,
)

# FIPS-197 C.3 AES-256 vector
FIPS_KEY = bytes.fromhex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
FIPS_CT = bytes.fromhex("8ea2b7ca516745bfeafc49904b496089")
FIPS_PT = bytes.fromhex("00112233445566778899aabbccddeeff")
# NIST SP800-38A F.1.5 (ECB-AES256) first block
SP_KEY = bytes.fromhex("603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4")
SP_CT = bytes.fromhex("f3eed1bdb5d2a03c064b5a7e3db181f8")
SP_PT = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")


class AesTest(unittest.TestCase):
    def test_fips197_ecb_vector(self):
        self.assertEqual(aes256_decrypt_block(FIPS_KEY, FIPS_CT), FIPS_PT)

    def test_ecb_roundtrip_of_two_blocks(self):
        data = SP_CT * 2
        out = aes256_ecb_decrypt(SP_KEY, data)
        self.assertEqual(out, SP_PT * 2)

    def test_sp800_38a_ecb_vector(self):
        self.assertEqual(aes256_decrypt_block(SP_KEY, SP_CT), SP_PT)

    def test_bad_key_length(self):
        with self.assertRaises(DepotError):
            aes256_decrypt_block(b"short", FIPS_CT)

    def test_bad_block_length(self):
        with self.assertRaises(DepotError):
            aes256_decrypt_block(FIPS_KEY, b"short")

    def test_cbc_known_vector(self):
        # NIST SP800-38A F.2.6 CBC-AES256 decrypt (first block)
        key = bytes.fromhex("603deb1015ca71be2b73aef0857d77811f352c073b6108d72d9810a30914dff4")
        iv = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
        ct = bytes.fromhex("f58c4c04d6e5f1ba779eabfb5f7bfbd6")
        pt = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")
        self.assertEqual(aes256_cbc_decrypt(key, iv, ct, unpad=False), pt)

    def test_cbc_bad_padding(self):
        key = SP_KEY
        iv = b"\x00" * 16
        with self.assertRaises(DepotError):
            aes256_cbc_decrypt(key, iv, b"\x00" * 16)


def make_vzip(raw: bytes, *, crc: bool = True) -> bytes:
    import zlib

    alone = lzma.compress(raw, format=lzma.FORMAT_ALONE)
    props, stream = alone[:5], alone[13:]
    # strip a trailing end-of-stream marker if the encoder wrote one; footer carries size
    footer_crc = (zlib.crc32(raw) & 0xFFFFFFFF) if crc else 0
    footer = footer_crc.to_bytes(4, "little") + len(raw).to_bytes(4, "little") + b"zv"
    return b"VZa" + b"\x00" * 4 + props + stream + footer


class CodecTest(unittest.TestCase):
    def test_vzip_roundtrip(self):
        raw = b"hello depot chunk" * 100
        payload = make_vzip(raw)
        self.assertEqual(vzip_decompress(payload), raw)

    def test_vzip_rejects_short(self):
        with self.assertRaises(DepotError):
            vzip_decompress(b"VZa" + b"\x00" * 4)

    def test_zip_roundtrip(self):
        raw = b"zip content" * 50
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("data", raw)
        self.assertEqual(zip_decompress(buffer.getvalue()), raw)

    def test_zip_rejects_garbage(self):
        with self.assertRaises(DepotError):
            zip_decompress(b"not a zip")


class ZstdTest(unittest.TestCase):
    def test_vzstd_roundtrip_with_external_zstd(self):
        import shutil
        import subprocess
        from steam_research.depot import vzstd_decompress

        if shutil.which("zstd") is None:
            self.skipTest("zstd executable not available")
        raw = b"zstd chunk payload" * 200
        frame = subprocess.run(["zstd", "-q", "-c"], input=raw, capture_output=True, check=True).stdout
        payload = b"VSZa" + b"\x00" * 4 + frame + b"\x00" * 15
        self.assertEqual(vzstd_decompress(payload), raw)

    def test_vzstd_rejects_short(self):
        from steam_research.depot import vzstd_decompress

        with self.assertRaises(DepotError):
            vzstd_decompress(b"VSZa" + b"\x00" * 4)


class DecodeChunkTest(unittest.TestCase):
    def test_short_chunk_rejected(self):
        with self.assertRaises(DepotError):
            decode_chunk(b"\x00" * 16, FIPS_KEY)

    def test_bad_key(self):
        with self.assertRaises(DepotError):
            decode_chunk(b"\x00" * 32, b"short")

    def test_unknown_compression(self):
        # 32 bytes of random ciphertext almost never decodes to a known magic
        with self.assertRaises(DepotError):
            decode_chunk(os.urandom(64), SP_KEY)

