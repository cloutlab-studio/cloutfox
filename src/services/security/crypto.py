"""Primitives: Argon2id key derivation, AES-256-GCM wrapping, a chunked stream format.

Everything at rest is AES-256-GCM. Keys from passwords go through Argon2id;
random keys come from os.urandom. Large data (a profile's browser directory)
is encrypted as a stream of 1 MiB chunks, each sealed with its index and an
end marker in the associated data, so chunks cannot be reordered, dropped or
the stream cut short without detection.
"""

from __future__ import annotations

import base64
import io
import json
import os
import struct
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

KEY_LEN = 32
NONCE_LEN = 12
CHUNK = 1 << 20

# RFC 9106 second recommendation (64 MiB, 3 passes): about 0.2-0.5 s on a laptop.
DEFAULT_KDF = {"alg": "argon2id", "t": 3, "m": 65536, "p": 4}


class DecryptError(Exception):
    """Wrong key or password, or the data was changed or cut."""


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def unb64(text: str) -> bytes:
    return base64.b64decode(text)


def new_key() -> bytes:
    return os.urandom(KEY_LEN)


def new_kdf() -> dict:
    return {**DEFAULT_KDF, "salt": b64(os.urandom(16))}


def derive(secret: str | bytes, kdf: dict) -> bytes:
    """A 32-byte key from a password (or any secret) with the stored Argon2id parameters."""
    if kdf.get("alg") != "argon2id":
        raise DecryptError(f"unknown key derivation: {kdf.get('alg')}")
    raw = secret.encode() if isinstance(secret, str) else secret
    return Argon2id(
        salt=unb64(kdf["salt"]),
        length=KEY_LEN,
        iterations=int(kdf["t"]),
        lanes=int(kdf["p"]),
        memory_cost=int(kdf["m"]),
    ).derive(raw)


def seal(key: bytes, data: bytes, aad: bytes = b"") -> bytes:
    nonce = os.urandom(NONCE_LEN)
    return nonce + AESGCM(key).encrypt(nonce, data, aad)


def unseal(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    try:
        return AESGCM(key).decrypt(blob[:NONCE_LEN], blob[NONCE_LEN:], aad)
    except (InvalidTag, ValueError) as e:
        raise DecryptError("wrong key or damaged data") from e


# --- stream: MAGIC | u32 header length | header JSON | chunks ---------------------------
# chunk: u32 length | AES-GCM(nonce = prefix(8) | u32 index, aad = magic | prefix | index | last)


def _aad(magic: bytes, prefix: bytes, index: int, last: bool) -> bytes:
    return magic + prefix + struct.pack(">I?", index, last)


class StreamWriter(io.RawIOBase):
    """A write-only file object that encrypts what is written to `out` in chunks."""

    def __init__(self, out: BinaryIO, key: bytes, magic: bytes, header: dict) -> None:
        super().__init__()
        self._out, self._aes, self._magic = out, AESGCM(key), magic
        self._prefix = os.urandom(8)
        self._header = json.dumps({**header, "prefix": b64(self._prefix)}).encode()
        self._buf = bytearray()
        self._index = 0
        out.write(magic + struct.pack(">I", len(self._header)) + self._header)

    def writable(self) -> bool:
        return True

    def write(self, data) -> int:  # type: ignore[override]
        self._buf += data
        while len(self._buf) > CHUNK:
            self._flush_chunk(bytes(self._buf[:CHUNK]), last=False)
            del self._buf[:CHUNK]
        return len(data)

    def _flush_chunk(self, data: bytes, last: bool) -> None:
        nonce = self._prefix + struct.pack(">I", self._index)
        sealed = self._aes.encrypt(nonce, data, _aad(self._magic, self._prefix, self._index, last))
        self._out.write(struct.pack(">I", len(sealed)) + sealed)
        self._index += 1

    def close(self) -> None:
        if not self.closed:
            self._flush_chunk(bytes(self._buf), last=True)
            self._buf.clear()
        super().close()


def read_header(src: BinaryIO, magic: bytes) -> dict:
    """The stream's header; `src` is left at the first chunk."""
    if src.read(len(magic)) != magic:
        raise DecryptError("not an encrypted CloutFox file")
    (length,) = struct.unpack(">I", src.read(4))
    if length > 1 << 16:
        raise DecryptError("damaged header")
    raw = src.read(length)
    try:
        return json.loads(raw)
    except ValueError as e:
        raise DecryptError("damaged header") from e


class StreamReader(io.RawIOBase):
    """A read-only file object that decrypts a stream positioned after its header."""

    def __init__(self, src: BinaryIO, key: bytes, magic: bytes, header: dict) -> None:
        super().__init__()
        self._src, self._aes, self._magic = src, AESGCM(key), magic
        self._prefix = unb64(header["prefix"])
        self._buf = b""
        self._index = 0
        self._done = False

    def readable(self) -> bool:
        return True

    def _next_chunk(self) -> None:
        size = self._src.read(4)
        if len(size) < 4:
            raise DecryptError("encrypted data is cut short")
        (length,) = struct.unpack(">I", size)
        sealed = self._src.read(length)
        nonce = self._prefix + struct.pack(">I", self._index)
        for last in (False, True):
            try:
                self._buf = self._aes.decrypt(
                    nonce, sealed, _aad(self._magic, self._prefix, self._index, last)
                )
            except InvalidTag:
                continue
            self._done = last
            self._index += 1
            return
        raise DecryptError("wrong key or damaged data")

    def readinto(self, b) -> int:  # type: ignore[override]
        while not self._buf and not self._done:
            self._next_chunk()
        n = min(len(b), len(self._buf))
        b[:n] = self._buf[:n]
        self._buf = self._buf[n:]
        return n
