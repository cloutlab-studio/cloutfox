"""Backups of everything CloutFox keeps, to a folder of the user's choice.

A backup is one ZIP of profiles.json, the key files, settings, extensions and
every profile's data (plain folders and encrypted containers). While a master
password is set the ZIP is itself encrypted with the data key (.cfxbak), and
its header carries the wrapped key, so it opens with the master password (or
recovery key) that was current when it was made:

    python -m src.services.backup restore <backup> <empty folder>
"""

from __future__ import annotations

import contextlib
import getpass
import io
import os
import pathlib
import shutil
import sys
import tempfile
import threading
import zipfile
from datetime import datetime

from ..core.config import (
    DATA_DIR,
    ENCRYPTED_DIR,
    EXTENSIONS_DIR,
    KEYS_FILE,
    PROFILES_FILE,
    SETTINGS_FILE,
    VAULT_FILE,
)
from ..core.logging import get_logger
from .profile.manager import TEMP_PREFIX
from .security import crypto
from .security.service import shred
from .security.vault import Vault

logger = get_logger("backup")

PREFIX = "cloutfox-backup-"
MAGIC = b"CFXB1\n"
_FILES = {
    "profiles.json": PROFILES_FILE,
    "vault.json": VAULT_FILE,
    "profile_keys.json": KEYS_FILE,
    "settings.json": SETTINGS_FILE,
}
_DIRS = {"camoufox_data": DATA_DIR, "encrypted_data": ENCRYPTED_DIR, "extensions": EXTENSIONS_DIR}


class BackupError(Exception):
    pass


def _write_zip(out: io.RawIOBase | io.BufferedIOBase, cancel: threading.Event | None = None) -> int:
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for arc, path in _FILES.items():
            if os.path.isfile(path):
                archive.write(path, arc)
                count += 1
        for arc, root in _DIRS.items():
            for folder, dirs, files in os.walk(root):
                rel = os.path.relpath(folder, root)
                if arc == "camoufox_data" and rel.split(os.sep)[0].startswith(TEMP_PREFIX):
                    dirs.clear()
                    continue
                for name in files:
                    if cancel is not None and cancel.is_set():
                        raise BackupError("backup cancelled")
                    path = os.path.join(folder, name)
                    if os.path.islink(path):
                        continue  # Firefox's "lock" and similar runtime links
                    try:
                        archive.write(path, os.path.normpath(os.path.join(arc, rel, name)))
                        count += 1
                    except OSError as e:
                        logger.info("Backup skipped %s: %s", path, e)
    return count


def backup_now(
    dest_dir: str, keep: int, vault: Vault, cancel: threading.Event | None = None
) -> pathlib.Path:
    """Write a backup into `dest_dir` and keep only the newest `keep` there.

    Setting `cancel` stops it between files and leaves nothing behind."""
    dest = pathlib.Path(dest_dir).expanduser()
    if not dest.is_dir():
        raise BackupError(f"{dest} is not a folder")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    sealed = vault.enabled
    target = dest / f"{PREFIX}{stamp}{'.cfxbak' if sealed else '.zip'}"
    tmp = target.with_name(target.name + ".part")
    try:
        with tmp.open("wb") as raw:
            if sealed:
                header = {"v": 1, "vault": vault.wrapped_keys()}
                writer = crypto.StreamWriter(raw, vault.dek, MAGIC, header)
                buffered = io.BufferedWriter(writer, crypto.CHUNK)
                count = _write_zip(buffered, cancel)
                buffered.flush()
                writer.close()
            else:
                count = _write_zip(raw, cancel)
        os.replace(tmp, target)
    except BaseException:
        # A cancelled backup (self-destruct) must not leave readable pieces on disk.
        with contextlib.suppress(OSError):
            shred(tmp)
        tmp.unlink(missing_ok=True)
        raise
    logger.info("Backup %s: %d files", target.name, count)
    prune(dest, keep)
    return target


def existing(dest_dir: str, partial: bool = False) -> list[pathlib.Path]:
    """This folder's CloutFox backups, oldest first; `partial` adds unfinished .part files."""
    dest = pathlib.Path(dest_dir).expanduser()
    if not dest_dir or not dest.is_dir():
        return []
    suffixes = (".zip", ".cfxbak", ".part") if partial else (".zip", ".cfxbak")
    found = [p for p in dest.iterdir() if p.name.startswith(PREFIX) and p.suffix in suffixes]
    return sorted(found, key=lambda p: p.name)


def prune(dest: pathlib.Path, keep: int) -> None:
    for old in existing(str(dest))[: -max(1, keep)]:
        old.unlink(missing_ok=True)


def restore(backup: str, target_dir: str, secret: str | None = None) -> int:
    """Unpack a backup into an empty folder; `secret` is the master password or recovery key."""
    target = pathlib.Path(target_dir)
    if target.exists() and any(target.iterdir()):
        raise BackupError(f"{target} is not empty")
    target.mkdir(parents=True, exist_ok=True)
    with open(backup, "rb") as src, tempfile.TemporaryFile(dir=target) as plain:
        if src.read(len(MAGIC)) == MAGIC:
            src.seek(0)
            header = crypto.read_header(src, MAGIC)
            if secret is None:
                raise BackupError("this backup is encrypted: give the master password")
            vault = Vault.from_wrapped(header["vault"])
            if not (vault.unlock(secret) or vault.unlock_with_recovery(secret)):
                raise BackupError("wrong master password or recovery key")
            shutil.copyfileobj(crypto.StreamReader(src, vault.dek, MAGIC, header), plain)
        else:
            src.seek(0)
            shutil.copyfileobj(src, plain)
        plain.seek(0)
        with zipfile.ZipFile(plain) as archive:
            base = target.resolve()
            for member in archive.infolist():
                if not (target / member.filename).resolve().is_relative_to(base):
                    raise BackupError(f"unsafe path in backup: {member.filename}")
            archive.extractall(target)
            return len(archive.infolist())


def due(settings: object, now: datetime | None = None) -> bool:
    """A scheduled backup is on and the last one is older than its interval."""
    hours = getattr(settings, "backup_hours", 0)
    if hours <= 0 or not getattr(settings, "backup_dir", ""):
        return False
    try:
        last = datetime.fromisoformat(settings.last_backup)
    except (TypeError, ValueError):
        return True
    return ((now or datetime.now()) - last).total_seconds() >= hours * 3600


class BackupScheduler:
    """Checks every few minutes whether a scheduled backup is due and makes it."""

    CHECK_SECONDS = 300

    def __init__(self, store, vault: Vault, on_done=None) -> None:
        self._store, self._vault, self._on_done = store, vault, on_done
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def run_now(self) -> pathlib.Path:
        """Make a backup with the current settings (raises BackupError)."""
        settings = self._store.current
        if not settings.backup_dir:
            raise BackupError("choose a backup folder first")
        with self._lock:
            if self._stop.is_set():
                raise BackupError("backups are stopped")
            path = backup_now(settings.backup_dir, settings.backup_keep, self._vault, self._stop)
            self._store.update(last_backup=datetime.now().isoformat(timespec="seconds"))
        if self._on_done:
            self._on_done(path)
        return path

    def stop(self) -> None:
        """Cancel a running backup, wait until it has cleaned up, and refuse new ones."""
        self._stop.set()
        with self._lock:
            pass

    def start(self) -> None:
        if self._thread is not None or self._stop.is_set():
            return

        def loop() -> None:
            while not self._stop.wait(self.CHECK_SECONDS):
                if due(self._store.current):
                    try:
                        self.run_now()
                    except Exception as e:
                        logger.warning("Scheduled backup failed: %s", e)

        self._thread = threading.Thread(target=loop, daemon=True, name="cloutfox-backup")
        self._thread.start()


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] != "restore":
        print("usage: python -m src.services.backup restore <backup> <empty folder>")
        return 2
    secret = None
    if argv[1].endswith(".cfxbak"):
        secret = getpass.getpass("Master password or recovery key: ")
    try:
        count = restore(argv[1], argv[2], secret)
    except (BackupError, crypto.DecryptError, OSError, zipfile.BadZipFile) as e:
        print(f"Restore failed: {e}")
        return 1
    print(f"Restored {count} files into {argv[2]}. Start CloutFox with CLOUTFOX_HOME={argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
