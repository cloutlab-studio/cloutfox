"""Turning encryption on and off, unlocking, and self-destruct."""

from __future__ import annotations

import contextlib
import logging
import os
import pathlib
import shutil
from collections.abc import Callable

from ...core.logging import get_logger
from .profile_data import ProfileData
from .vault import Vault, VaultError

logger = get_logger("security")

MIN_PASSWORD = 8


class SecurityService:
    def __init__(
        self,
        vault: Vault,
        data: ProfileData,
        get_profile_manager: Callable[[], object],
        wipe_paths: Callable[[], list[str]],
    ) -> None:
        """`wipe_paths` lists what self-destruct removes after the keys (profiles.json,
        data and log folders, backups); it is read at that moment."""
        self.vault = vault
        self.data = data
        self._pm = get_profile_manager
        self._wipe_paths = wipe_paths

    @property
    def locked(self) -> bool:
        """A master password is set and was not entered yet."""
        return self.vault.enabled and not self.vault.unlocked

    def unlock(self, password: str) -> str:
        """'ok', 'wrong', or 'wiped' (the self-destruct password was entered)."""
        if self.vault.is_duress(password):
            self.self_destruct()
            return "wiped"
        return "ok" if self.vault.unlock(password) else "wrong"

    def unlock_with_recovery(self, key: str) -> bool:
        return self.vault.unlock_with_recovery(key)

    def enable_master(self, password: str) -> str:
        """Turn the master password on; returns the recovery key (shown once)."""
        _check_password(password)
        recovery = self.vault.enable(password)
        self.data.rewrap_all(master=True)
        self._pm().save_profiles()
        return recovery

    def change_master(self, password: str) -> None:
        _check_password(password)
        self.vault.change(password)

    def disable_master(self) -> None:
        """Back to no master password: master-only encrypted profiles are decrypted."""
        self.data.rewrap_all(master=False)
        self.vault.disable()
        self._pm().save_profiles()

    def set_duress(self, password: str | None) -> None:
        if password is not None:
            _check_password(password)
        self.vault.set_duress(password)

    def self_destruct(self) -> None:
        """Keys first (the data is unreadable from that moment), then the files."""
        logger.warning("Self-destruct")
        self.vault.forget()
        self.data.wipe_all()
        for handler in list(logging.getLogger().handlers) + list(
            logging.getLogger("cloutfox").handlers
        ):
            if isinstance(handler, logging.FileHandler):
                handler.close()
        for raw in self._wipe_paths():
            path = pathlib.Path(raw)
            with contextlib.suppress(OSError):
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                elif path.exists():
                    shred(path)


def shred(path: pathlib.Path) -> None:
    """Overwrite a file with random bytes in 1 MiB steps (backups run to gigabytes), then delete it."""
    size = path.stat().st_size
    with path.open("r+b") as f:
        while f.tell() < size:
            f.write(os.urandom(min(1 << 20, size - f.tell())))
        f.flush()
        os.fsync(f.fileno())
    path.unlink()


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise VaultError(f"at least {MIN_PASSWORD} characters")
