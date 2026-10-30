"""The master key: optional master password, recovery key and self-destruct password.

vault.json (next to profiles.json) holds no secret in the clear:

    {"version": 1,
     "master":   {"kdf": {...}, "dek": seal(KEK(master password), DEK)},
     "recovery": {"kdf": {...}, "dek": seal(KEK(recovery key), DEK)},
     "duress":   {"kdf": {...}, "check": KEK(self-destruct password)}}

The data key (DEK) encrypts profiles.json, backups and the keys of encrypted
profiles. Without a master password there is no vault.json and no DEK.
"""

from __future__ import annotations

import base64
import hmac
import json
import os
import pathlib
import threading

from ...core.logging import get_logger
from . import crypto

logger = get_logger("security.vault")

FILE_MAGIC = b"CFXF1\n"
_AAD_DEK = b"cloutfox-dek"


class VaultError(Exception):
    pass


def format_recovery_key(raw: bytes) -> str:
    text = base64.b32encode(raw).decode().rstrip("=")
    return "-".join(text[i : i + 4] for i in range(0, len(text), 4))


def parse_recovery_key(text: str) -> bytes:
    clean = "".join(ch for ch in text.upper() if ch.isalnum())
    try:
        return base64.b32decode(clean + "=" * (-len(clean) % 8))
    except ValueError as e:
        raise VaultError("not a recovery key") from e


def _write_atomic(path: pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class Vault:
    def __init__(self, path: str | os.PathLike) -> None:
        self.path = pathlib.Path(path)
        self._lock = threading.RLock()
        self._dek: bytes | None = None
        self._state: dict = {}
        self._load()

    def _load(self) -> None:
        try:
            self._state = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self._state = {}
        except ValueError as e:
            # A damaged vault must not silently turn encryption off.
            raise VaultError(f"{self.path} is damaged: {e}") from e

    def _save(self) -> None:
        if self._state.get("master"):
            _write_atomic(self.path, json.dumps({"version": 1, **self._state}, indent=2).encode())
        else:
            self.path.unlink(missing_ok=True)

    @classmethod
    def from_wrapped(cls, wrapped: dict) -> Vault:
        """A locked in-memory vault from wrapped_keys() (to open a backup)."""
        vault = cls.__new__(cls)
        vault.path = pathlib.Path(os.devnull)
        vault._lock = threading.RLock()
        vault._dek = None
        vault._state = dict(wrapped)
        return vault

    def wrapped_keys(self) -> dict:
        """The master and recovery blocks (no secret in the clear), for a backup header."""
        return {k: v for k, v in self._state.items() if k in ("master", "recovery")}

    # --- state ---------------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """A master password is set."""
        return bool(self._state.get("master"))

    @property
    def unlocked(self) -> bool:
        return self._dek is not None

    @property
    def has_duress(self) -> bool:
        return bool(self._state.get("duress"))

    @property
    def dek(self) -> bytes:
        if self._dek is None:
            raise VaultError("vault is locked")
        return self._dek

    # --- unlocking -----------------------------------------------------------------------

    def is_duress(self, password: str) -> bool:
        duress = self._state.get("duress")
        if not duress or not password:
            return False
        check = crypto.derive(password, duress["kdf"])
        return hmac.compare_digest(check, crypto.unb64(duress["check"]))

    def unlock(self, password: str) -> bool:
        with self._lock:
            master = self._state.get("master")
            if not master:
                return True
            try:
                kek = crypto.derive(password, master["kdf"])
                self._dek = crypto.unseal(kek, crypto.unb64(master["dek"]), _AAD_DEK)
            except crypto.DecryptError:
                return False
            return True

    def unlock_with_recovery(self, recovery_key: str) -> bool:
        with self._lock:
            recovery = self._state.get("recovery")
            if not recovery:
                return False
            try:
                kek = crypto.derive(parse_recovery_key(recovery_key), recovery["kdf"])
                self._dek = crypto.unseal(kek, crypto.unb64(recovery["dek"]), _AAD_DEK)
            except (crypto.DecryptError, VaultError):
                return False
            return True

    # --- changing ------------------------------------------------------------------------

    def _wrap(self, secret: str | bytes) -> dict:
        kdf = crypto.new_kdf()
        return {
            "kdf": kdf,
            "dek": crypto.b64(crypto.seal(crypto.derive(secret, kdf), self.dek, _AAD_DEK)),
        }

    def enable(self, password: str) -> str:
        """Turn the master password on; returns the recovery key to show once."""
        with self._lock:
            if self.enabled:
                raise VaultError("master password is already set")
            self._dek = crypto.new_key()
            recovery = os.urandom(20)
            self._state = {"master": self._wrap(password), "recovery": self._wrap(recovery)}
            self._save()
            logger.info("Master password enabled")
            return format_recovery_key(recovery)

    def change(self, password: str) -> None:
        """New master password for the same data key (unlock first)."""
        with self._lock:
            if self.is_duress(password):
                raise VaultError("same as the self-destruct password")
            self._state["master"] = self._wrap(password)
            self._save()

    def new_recovery_key(self) -> str:
        with self._lock:
            recovery = os.urandom(20)
            self._state["recovery"] = self._wrap(recovery)
            self._save()
            return format_recovery_key(recovery)

    def set_duress(self, password: str | None) -> None:
        """Set (or with None remove) the self-destruct password; needs the master on."""
        with self._lock:
            if not self.enabled:
                raise VaultError("self-destruct needs a master password")
            if password is None:
                self._state.pop("duress", None)
            else:
                if self._verifies_master(password):
                    raise VaultError("same as the master password")
                kdf = crypto.new_kdf()
                self._state["duress"] = {
                    "kdf": kdf,
                    "check": crypto.b64(crypto.derive(password, kdf)),
                }
            self._save()

    def _verifies_master(self, password: str) -> bool:
        master = self._state["master"]
        try:
            crypto.unseal(
                crypto.derive(password, master["kdf"]), crypto.unb64(master["dek"]), _AAD_DEK
            )
        except crypto.DecryptError:
            return False
        return True

    def disable(self) -> None:
        """Forget the master password, recovery key and self-destruct password.

        Callers first rewrite everything the data key protected.
        """
        with self._lock:
            self._state = {}
            self._dek = None
            self._save()
            logger.info("Master password disabled")

    def forget(self) -> None:
        """Self-destruct: overwrite and remove vault.json, drop the key from memory."""
        with self._lock:
            self._dek = None
            self._state = {}
            try:
                size = self.path.stat().st_size
                with self.path.open("r+b") as f:
                    f.write(os.urandom(size))
                    f.flush()
                    os.fsync(f.fileno())
            except OSError:
                pass
            self.path.unlink(missing_ok=True)

    # --- small files (profiles.json, backups) --------------------------------------------

    def seal_file_bytes(self, data: bytes) -> bytes:
        return FILE_MAGIC + crypto.seal(self.dek, data, FILE_MAGIC)

    def open_file_bytes(self, blob: bytes) -> bytes:
        if not blob.startswith(FILE_MAGIC):
            return blob
        return crypto.unseal(self.dek, blob[len(FILE_MAGIC) :], FILE_MAGIC)


def is_sealed(blob: bytes) -> bool:
    return blob.startswith(FILE_MAGIC)
