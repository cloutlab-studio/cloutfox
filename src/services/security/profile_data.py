"""Where a profile's browser data lives, and its optional encryption at rest.

A plain profile keeps its data in DATA_DIR/<name>. An encrypted one keeps a
single stream ENCRYPTED_DIR/<name>.cfx (a tar of the directory, see
crypto.StreamWriter) and its key in KEYS_FILE. To use it (launch, cookies,
export) the data is unpacked into a private work directory, in RAM where
the OS has one (/dev/shm on Linux), and packed back when the last user
releases it. Windows has no RAM disk: the work directory is a temp folder on
disk for as long as the profile is open.

A profile key is a random AES key wrapped by the master data key, by a key
from the profile's own password, or by both (password inside, master outside).
"""

from __future__ import annotations

import contextlib
import getpass
import hashlib
import json
import os
import pathlib
import shutil
import sys
import tarfile
import tempfile
import threading
from collections.abc import Iterator

from ...core.logging import get_logger
from . import crypto
from .vault import Vault

logger = get_logger("security.profile_data")

STREAM_MAGIC = b"CFXP1\n"
_AAD_PW = b"cloutfox-profile-password"
_AAD_MASTER = b"cloutfox-profile-master"
# Inside an unpacked work directory while it is in use; left behind only by a crash.
_OPEN_MARKER = ".cloutfox-open"
# How often open encrypted profiles are packed while running (RAM is lost on power cut).
CHECKPOINT_SECONDS = 600


class ProfileLocked(Exception):
    """The profile is encrypted with its own password, which was not entered yet."""


class ProfileDataError(Exception):
    pass


def work_root() -> pathlib.Path:
    """Private parent of the work directories: in RAM on Linux, a temp dir elsewhere."""
    shm = pathlib.Path("/dev/shm")
    owner = os.getuid() if hasattr(os, "getuid") else getpass.getuser()
    in_ram = sys.platform.startswith("linux") and shm.is_dir()
    root = (shm if in_ram else pathlib.Path(tempfile.gettempdir())) / f"cloutfox-{owner}"
    root.mkdir(mode=0o700, exist_ok=True)
    if hasattr(os, "getuid"):
        # /dev/shm and /tmp are shared: never unpack into a folder someone else made.
        if root.is_symlink() or root.stat().st_uid != os.getuid():
            raise ProfileDataError(f"{root} belongs to another user")
        root.chmod(0o700)
    return root


def work_in_ram() -> bool:
    return work_root().parent == pathlib.Path("/dev/shm")


def _regular_only(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Files and folders only: Firefox's "lock" symlink and sockets are runtime state."""
    if info.name == _OPEN_MARKER:
        return None
    if info.isfile() or info.isdir():
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        return info
    return None


def _safe_members(tar: tarfile.TarFile) -> Iterator[tarfile.TarInfo]:
    for member in tar:
        name = pathlib.PurePosixPath(member.name)
        if name.is_absolute() or ".." in name.parts or not (member.isfile() or member.isdir()):
            raise ProfileDataError(f"unsafe entry in encrypted profile: {member.name}")
        yield member


class ProfileData:
    def __init__(self, data_dir: str, encrypted_dir: str, keys_file: str, vault: Vault) -> None:
        self.data_dir = pathlib.Path(data_dir)
        self.encrypted_dir = pathlib.Path(encrypted_dir)
        self.keys_file = pathlib.Path(keys_file)
        self.vault = vault
        self._lock = threading.RLock()
        self._keys: dict[str, bytes] = {}
        self._open: dict[str, list] = {}  # name -> [work dir, users]
        self._checkpointer: threading.Thread | None = None
        self._stop = threading.Event()

    # --- where ---------------------------------------------------------------------------

    def plain_dir(self, name: str) -> pathlib.Path:
        return self.data_dir / name

    def work_dir(self, name: str) -> pathlib.Path:
        """Where `name` is unpacked; one folder per data home, so two installs never mix."""
        home = hashlib.sha256(str(self.encrypted_dir.resolve()).encode()).hexdigest()[:12]
        return work_root() / home / name

    def container(self, name: str) -> pathlib.Path:
        return self.encrypted_dir / f"{name}.cfx"

    def is_encrypted(self, name: str) -> bool:
        return self.container(name).exists()

    def path(self, name: str) -> pathlib.Path | None:
        """The directory holding the data right now, or None while it is encrypted and closed."""
        with self._lock:
            if name in self._open:
                return pathlib.Path(self._open[name][0])
        return None if self.is_encrypted(name) else self.plain_dir(name)

    # --- keys ----------------------------------------------------------------------------

    def _key_table(self) -> dict:
        try:
            return json.loads(self.keys_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def _save_key_table(self, table: dict) -> None:
        self.keys_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.keys_file.with_name(self.keys_file.name + ".tmp")
        tmp.write_text(json.dumps(table, indent=2), encoding="utf-8")
        os.replace(tmp, self.keys_file)

    def key_by(self, name: str) -> list[str]:
        """How the profile's key is protected: ["master"], ["password"] or both."""
        return list(self._key_table().get(name, {}).get("key_by", []))

    def has_password(self, name: str) -> bool:
        return "password" in self.key_by(name)

    def needs_password(self, name: str) -> bool:
        """Encrypted with its own password that was not entered in this session."""
        with self._lock:
            return self.is_encrypted(name) and self.has_password(name) and name not in self._keys

    def _wrap(self, key: bytes, password: str | None, master: bool) -> dict:
        entry: dict = {"key_by": []}
        wrapped = key
        if password:
            entry["pw_kdf"] = crypto.new_kdf()
            wrapped = crypto.seal(crypto.derive(password, entry["pw_kdf"]), wrapped, _AAD_PW)
            entry["key_by"].append("password")
        if master:
            wrapped = crypto.seal(self.vault.dek, wrapped, _AAD_MASTER)
            entry["key_by"].append("master")
        if not entry["key_by"]:
            raise ProfileDataError("an encrypted profile needs a password or the master password")
        entry["wrapped"] = crypto.b64(wrapped)
        return entry

    def _unwrap(self, entry: dict, password: str | None) -> bytes:
        blob = crypto.unb64(entry["wrapped"])
        if "master" in entry["key_by"]:
            if not self.vault.unlocked:
                raise ProfileLocked("master password not entered")
            blob = crypto.unseal(self.vault.dek, blob, _AAD_MASTER)
        if "password" in entry["key_by"]:
            if password is None:
                raise ProfileLocked("profile password needed")
            blob = crypto.unseal(crypto.derive(password, entry["pw_kdf"]), blob, _AAD_PW)
        return blob

    def unlock(self, name: str, password: str) -> bool:
        """Check the profile password and keep its key for this session."""
        entry = self._key_table().get(name)
        if entry is None:
            return False
        try:
            key = self._unwrap(entry, password)
        except (crypto.DecryptError, ProfileLocked):
            return False
        with self._lock:
            self._keys[name] = key
        return True

    def _key(self, name: str) -> bytes:
        with self._lock:
            if name in self._keys:
                return self._keys[name]
        entry = self._key_table().get(name)
        if entry is None:
            raise ProfileDataError(f"no key for encrypted profile {name}")
        key = self._unwrap(entry, None)
        with self._lock:
            self._keys[name] = key
        return key

    # --- packing -------------------------------------------------------------------------

    def _pack(self, name: str, src: pathlib.Path, key: bytes) -> None:
        """Encrypt directory `src` into the profile's container (atomic replace)."""
        self.encrypted_dir.mkdir(parents=True, exist_ok=True)
        target = self.container(name)
        tmp = target.with_name(target.name + ".tmp")
        with tmp.open("wb") as out:
            writer = crypto.StreamWriter(out, key, STREAM_MAGIC, {"v": 1})
            with tarfile.open(fileobj=writer, mode="w|") as tar:
                for child in sorted(src.iterdir()) if src.exists() else []:
                    tar.add(child, arcname=child.name, filter=_regular_only)
            writer.close()
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, target)

    def _unpack(self, name: str, dest: pathlib.Path, key: bytes) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        with self.container(name).open("rb") as src:
            header = crypto.read_header(src, STREAM_MAGIC)
            reader = crypto.StreamReader(src, key, STREAM_MAGIC, header)
            with tarfile.open(fileobj=reader, mode="r|") as tar:
                for member in _safe_members(tar):
                    tar.extract(member, dest, set_attrs=False)

    # --- open / close --------------------------------------------------------------------

    def acquire(self, name: str) -> pathlib.Path:
        """The profile's data directory for use; release() it afterwards.

        Raises ProfileLocked when its password is needed first.
        """
        with self._lock:
            if name in self._open:
                self._open[name][1] += 1
                return pathlib.Path(self._open[name][0])
            if not self.is_encrypted(name):
                self._open[name] = [str(self.plain_dir(name)), 1]
                return self.plain_dir(name)
            key = self._key(name)
            work = self.work_dir(name)
            if work.exists() and (work / _OPEN_MARKER).exists():
                # Left by a crash with the data still in it: newer than the container.
                logger.warning("Reusing the unpacked data of %s left by an earlier run", name)
            else:
                shutil.rmtree(work, ignore_errors=True)
                self._unpack(name, work, key)
                (work / _OPEN_MARKER).touch()
            self._open[name] = [str(work), 1]
            return work

    def release(self, name: str) -> None:
        with self._lock:
            entry = self._open.get(name)
            if entry is None:
                return
            entry[1] -= 1
            if entry[1] > 0:
                return
            del self._open[name]
            if not self.is_encrypted(name):
                return
            work = pathlib.Path(entry[0])
            # On failure the unpacked copy (and its marker) stays, so the next
            # acquire() picks it up instead of the older container.
            self._pack(name, work, self._key(name))
            shutil.rmtree(work, ignore_errors=True)

    @contextlib.contextmanager
    def opened(self, name: str) -> Iterator[pathlib.Path]:
        path = self.acquire(name)
        try:
            yield path
        finally:
            self.release(name)

    def checkpoint(self) -> None:
        """Pack every open encrypted profile so a power loss loses little (RAM is gone)."""
        with self._lock:
            names = [n for n in self._open if self.is_encrypted(n)]
        for name in names:
            try:
                with self._lock:
                    if name not in self._open:
                        continue
                    self._pack(name, pathlib.Path(self._open[name][0]), self._key(name))
            except Exception as e:
                logger.warning("Checkpoint of %s failed: %s", name, e)

    def start_checkpoints(self, interval: float = CHECKPOINT_SECONDS) -> None:
        """Checkpoint open encrypted profiles every `interval` seconds, in the background."""
        if self._checkpointer is not None:
            return

        def loop() -> None:
            while not self._stop.wait(interval):
                self.checkpoint()

        self._checkpointer = threading.Thread(target=loop, daemon=True, name="cloutfox-pack")
        self._checkpointer.start()

    def is_open(self, name: str) -> bool:
        with self._lock:
            return name in self._open

    # --- changing protection (profile closed) --------------------------------------------

    def _require_closed(self, name: str) -> None:
        if self.is_open(name):
            raise ProfileDataError("stop the profile first")

    def encrypt(self, name: str, password: str | None) -> None:
        """Encrypt a plain profile with its password, the master key, or both."""
        with self._lock:
            self._require_closed(name)
            if self.is_encrypted(name):
                raise ProfileDataError("already encrypted")
            key = crypto.new_key()
            entry = self._wrap(key, password, self.vault.enabled)
            self._pack(name, self.plain_dir(name), key)
            table = self._key_table()
            table[name] = entry
            self._save_key_table(table)
            self._keys[name] = key
            shutil.rmtree(self.plain_dir(name), ignore_errors=True)

    def decrypt(self, name: str) -> None:
        """Back to a plain directory under DATA_DIR."""
        with self._lock:
            self._require_closed(name)
            key = self._key(name)
            tmp = self.data_dir / f".{name}.decrypting"
            shutil.rmtree(tmp, ignore_errors=True)
            self._unpack(name, tmp, key)
            shutil.rmtree(self.plain_dir(name), ignore_errors=True)
            os.replace(tmp, self.plain_dir(name))
            self._forget(name)

    def set_password(self, name: str, password: str | None) -> None:
        """New (or with None no) profile password; the data is not re-encrypted."""
        with self._lock:
            key = self._key(name)
            table = self._key_table()
            table[name] = self._wrap(key, password, self.vault.enabled)
            self._save_key_table(table)

    def rewrap_all(self, master: bool) -> None:
        """Re-protect every key after the master password was turned on (True), or
        before it is turned off (False). Only the outer master layer changes, so no
        profile password is needed. Without a master, a key with no password of its
        own cannot stay encrypted: those profiles are decrypted to plain directories.
        """
        with self._lock:
            table = self._key_table()
            if busy := [n for n in table if self.is_open(n)]:
                raise ProfileDataError(f"stop {', '.join(busy)} first")
            to_decrypt = []
            for name, entry in table.items():
                has_master = "master" in entry["key_by"]
                blob = crypto.unb64(entry["wrapped"])
                if master and not has_master:
                    entry["wrapped"] = crypto.b64(crypto.seal(self.vault.dek, blob, _AAD_MASTER))
                    entry["key_by"] = [*entry["key_by"], "master"]
                elif not master and has_master:
                    if "password" in entry["key_by"]:
                        inner = crypto.unseal(self.vault.dek, blob, _AAD_MASTER)
                        entry["wrapped"] = crypto.b64(inner)
                        entry["key_by"] = ["password"]
                    else:
                        to_decrypt.append(name)
            for name in to_decrypt:
                self.decrypt(name)
                table.pop(name, None)
            self._save_key_table(table)

    # --- names ---------------------------------------------------------------------------

    def rename(self, old: str, new: str) -> None:
        with self._lock:
            if not self.is_encrypted(old):
                return
            os.replace(self.container(old), self.container(new))
            table = self._key_table()
            if old in table:
                table[new] = table.pop(old)
                self._save_key_table(table)
            if old in self._keys:
                self._keys[new] = self._keys.pop(old)

    def _forget(self, name: str) -> None:
        self.container(name).unlink(missing_ok=True)
        table = self._key_table()
        if table.pop(name, None) is not None:
            self._save_key_table(table)
        self._keys.pop(name, None)

    def remove(self, name: str) -> None:
        with self._lock:
            self._forget(name)
            shutil.rmtree(self.work_dir(name), ignore_errors=True)

    def lock_all(self) -> None:
        """Drop every profile key from memory."""
        with self._lock:
            self._keys.clear()

    def wipe_all(self) -> None:
        """Self-destruct: keys first, then containers and every work directory."""
        with self._lock:
            self._keys.clear()
            self._open.clear()
            with contextlib.suppress(OSError):
                size = self.keys_file.stat().st_size
                with self.keys_file.open("r+b") as f:
                    f.write(os.urandom(size))
                    f.flush()
                    os.fsync(f.fileno())
            self.keys_file.unlink(missing_ok=True)
            shutil.rmtree(self.encrypted_dir, ignore_errors=True)
            shutil.rmtree(self.work_dir(""), ignore_errors=True)
