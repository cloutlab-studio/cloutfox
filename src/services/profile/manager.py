import contextlib
import copy
import json
import os
import pathlib
import secrets
import shutil
import threading
import time
from datetime import datetime
from typing import Any

from ...core.config import DATA_DIR, PROFILES_FILE
from ...core.logging import get_logger
from ...models.profile import META_FIELDS, Profile
from ...utils.validation import normalize_tags, normalize_urls, validate_profile_name
from .codec import profile_from_dict
from .transfer import export_to_zip, import_from_zip, read_profile_meta

logger = get_logger("profile.manager")

TEMP_PREFIX = "temp-"


def _replace(src: pathlib.Path, dst: pathlib.Path, attempts: int = 10) -> None:
    """os.replace, retried briefly: on Windows it fails with a sharing violation
    while another process (antivirus, indexer, a reader) has the target open."""
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.02 * (i + 1))


class ProfileManager:
    def __init__(self, vault: Any = None, data: Any = None) -> None:
        """`vault` (security.Vault) seals profiles.json while a master password is set;
        `data` (security.ProfileData) keeps encrypted profiles' containers in step."""
        self._lock = threading.RLock()
        self.profiles: dict[str, Profile] = {}
        self._vault = vault
        self._data = data
        # Set when profiles.json exists but could not be read: saving would replace
        # every profile with whatever is in memory, so saves are refused.
        self.load_error: str | None = None
        self._load_profiles()
        pathlib.Path(DATA_DIR).mkdir(exist_ok=True, parents=True)
        self._remove_stale_temporary()

    def _remove_stale_temporary(self) -> None:
        """Data of one-time profiles left by a crash (they are never saved)."""
        if self.load_error:
            return
        for path in pathlib.Path(DATA_DIR).glob(f"{TEMP_PREFIX}*"):
            if path.is_dir() and path.name not in self.profiles:
                shutil.rmtree(path, ignore_errors=True)

    def add_temporary(
        self,
        proxy: str = "",
        os_type: str = "windows",
        engine: str = "camoufox",
        timezone: str | None = None,
        locale: str | None = None,
        start_urls: list[str] | None = None,
    ) -> str:
        """A one-time profile with a fresh fingerprint; returns its generated name."""
        with self._lock:
            while True:
                name = f"{TEMP_PREFIX}{secrets.token_hex(4)}"
                if self._find_by_casefold(name) is None:
                    break
            if not self.add_profile(
                name, proxy, os_type, timezone, locale, engine, start_urls=start_urls or []
            ):
                raise OSError(f"could not create {name}")
            self.profiles[name].temporary = True
            self.save_profiles()
            return name

    def _find_by_casefold(self, name: str) -> str | None:
        """Return the existing profile key that case-folds to *name*, or None.

        Used to enforce case-insensitive uniqueness across all platforms so that
        a profiles.json exported on Linux (case-sensitive FS) can be imported on
        Windows/macOS (case-insensitive FS) without data-dir collisions.
        """
        lower = name.casefold()
        return next((k for k in self.profiles if k.casefold() == lower), None)

    def _data_path(self, name: str) -> str:
        return os.path.join(DATA_DIR, name)

    def _load_profiles(self) -> None:
        path = pathlib.Path(PROFILES_FILE)
        if not path.exists():
            return
        try:
            raw = path.read_bytes()
            if self._vault is not None and self._vault.unlocked:
                raw = self._vault.open_file_bytes(raw)
            data = json.loads(raw.decode("utf-8"))
            for name, p_data in data.items():
                if not validate_profile_name(name)[0] or p_data.get("name") != name:
                    logger.warning("Skipping profile with unsafe name: %r", name)
                    continue
                self.profiles[name] = profile_from_dict(p_data)
            logger.info("Loaded %d profiles", len(self.profiles))
        except Exception as e:
            self.load_error = f"{type(e).__name__}: {e}"
            logger.exception("Error loading profiles: %s", e)

    def _encode(self) -> bytes:
        data = json.dumps(
            {name: p.to_dict() for name, p in self.profiles.items() if not p.temporary},
            indent=4,
        )
        raw = data.encode("utf-8")
        if self._vault is not None and self._vault.enabled:
            raw = self._vault.seal_file_bytes(raw)
        return raw

    def save_profiles(self) -> None:
        """Atomic write: write to a temp file then os.replace.

        Sealed with the master key while one is set (see security.vault).
        """
        if self.load_error:
            logger.error("Not saving profiles: profiles.json could not be read")
            return
        path = pathlib.Path(PROFILES_FILE)
        tmp = path.with_suffix(".json.tmp")
        try:
            tmp.write_bytes(self._encode())
            _replace(tmp, path)
            logger.debug("Profiles saved")
        except Exception as e:
            logger.exception("Error saving profiles: %s", e)
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)

    def add_profile(
        self,
        name: str,
        proxy: str,
        os_type: str,
        timezone: str | None = None,
        locale: str | None = None,
        engine: str = "camoufox",
        **meta: object,
    ) -> bool:
        """Create a profile; `meta` takes any of META_FIELDS."""
        with self._lock:
            if self._find_by_casefold(name) is not None:
                return False
            # Create directory before touching profiles.json so a mkdir failure
            # does not leave an entry with no data dir on disk.
            try:
                pathlib.Path(self._data_path(name)).mkdir(exist_ok=True, parents=True)
            except OSError as e:
                logger.warning("Could not create data dir for %s: %s", name, e)
                return False
            self.profiles[name] = Profile(
                name=name,
                proxy=proxy or None,
                os_type=os_type,
                timezone=timezone or None,
                locale=locale or None,
                engine=engine,
            )
            self._apply_meta(self.profiles[name], meta)
            self.save_profiles()
            logger.info("Created profile: %s", name)
            return True

    @staticmethod
    def _apply_meta(profile: Profile, meta: dict) -> None:
        for key, value in meta.items():
            if key not in META_FIELDS:
                raise TypeError(f"not a meta field: {key}")
            if key == "tags":
                value = normalize_tags(value)
            elif key == "start_urls":
                value = normalize_urls(value)
            elif key == "proxy_rotate_url":
                value = value or None
            elif key == "extensions":
                value = [e for e in dict.fromkeys(value or []) if isinstance(e, str)]
            elif value is None:
                value = ""
            setattr(profile, key, value)

    def set_wireguard(self, name: str, endpoint: str | None) -> bool:
        """Record (or with None clear) that the profile has a WireGuard config."""
        with self._lock:
            profile = self.profiles.get(name)
            if profile is None:
                return False
            profile.wireguard = endpoint or None
            self.save_profiles()
            return True

    def set_meta(self, name: str, **meta: object) -> bool:
        """Change tags, notes, status, start URLs or the rotate link; False if not found.

        Callers validate the values; tags and URLs are normalised here.
        """
        with self._lock:
            profile = self.profiles.get(name)
            if profile is None:
                return False
            self._apply_meta(profile, meta)
            self.save_profiles()
            return True

    def record_launch(self, name: str, ip: str | None, country: str | None) -> None:
        """Remember when the profile last came up and through which exit IP."""
        with self._lock:
            profile = self.profiles.get(name)
            if profile is None:
                return
            profile.last_launch = {
                "at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "ip": ip,
                "country": country,
            }
            self.save_profiles()

    def clone_profile(self, source: str, new_name: str) -> bool:
        """A new profile with the same settings and an empty data dir (new device)."""
        with self._lock:
            original = self.profiles.get(source)
            if original is None:
                return False
            return self.add_profile(
                new_name,
                original.proxy or "",
                original.os_type,
                original.timezone,
                original.locale,
                original.engine,
                **{key: copy.deepcopy(getattr(original, key)) for key in META_FIELDS},
            )

    def update_profile(
        self,
        original_name: str,
        new_name: str,
        new_proxy: str,
        new_os: str,
        new_timezone: str | None = None,
        new_locale: str | None = None,
    ) -> bool:
        """Replace every field; a None/empty timezone or locale means automatic."""
        with self._lock:
            if original_name not in self.profiles:
                return False

            if new_name != original_name:
                # Case-insensitive uniqueness: a case-only rename of the profile
                # itself is allowed; renaming to another profile's casefold is not.
                conflicting = self._find_by_casefold(new_name)
                if conflicting is not None and conflicting != original_name:
                    return False

            # Rename the data directory BEFORE mutating in-memory state so that
            # an OSError leaves memory and JSON untouched.
            if new_name != original_name:
                old_dir = pathlib.Path(self._data_path(original_name))
                new_dir = pathlib.Path(self._data_path(new_name))
                if old_dir.exists():
                    if new_dir.exists():
                        # On case-insensitive filesystems (Windows/macOS) a
                        # case-only rename sees the target as existing because
                        # both paths point to the same directory entry.  Allow
                        # the rename only in that situation.
                        try:
                            same = old_dir.samefile(new_dir)
                        except OSError:
                            same = False
                        if not same:
                            # Refuse: do NOT delete potential user data.
                            logger.warning(
                                "Cannot rename %s -> %s: target data dir already exists",
                                original_name,
                                new_name,
                            )
                            return False
                    try:
                        old_dir.rename(new_dir)
                    except OSError as e:
                        logger.warning("Could not rename data dir for %s: %s", original_name, e)
                        return False

            if new_name != original_name and self._data is not None:
                try:
                    self._data.rename(original_name, new_name)
                except OSError as e:
                    logger.warning("Could not rename encrypted data of %s: %s", original_name, e)
                    return False

            profile = self.profiles[original_name]
            profile.name = new_name
            profile.proxy = new_proxy or None
            profile.os_type = new_os
            profile.timezone = new_timezone or None
            profile.locale = new_locale or None

            if new_name != original_name:
                del self.profiles[original_name]
                self.profiles[new_name] = profile

            self.save_profiles()
            logger.info("Updated profile: %s -> %s", original_name, new_name)
            return True

    def delete_profile(self, name: str) -> bool:
        with self._lock:
            if name not in self.profiles:
                return False
            del self.profiles[name]
            self.save_profiles()
            # Inside the lock: a profile re-created under the same (or, on a
            # case-insensitive file system, a case-variant) name must not have
            # its fresh data dir removed by this delete.
            shutil.rmtree(self._data_path(name), ignore_errors=True)
            if self._data is not None:
                self._data.remove(name)
        logger.info("Deleted profile: %s", name)
        return True

    def list_profiles(self) -> list[Profile]:
        with self._lock:
            return list(self.profiles.values())

    def export_profile(
        self,
        name: str,
        export_path: str,
        include_data: bool = True,
    ) -> tuple[bool, str]:
        with self._lock:
            if name not in self.profiles:
                return False, "Profile not found"
            profile = self.profiles[name]
        if self._data is None:
            return export_to_zip(profile, self._data_path(name), export_path, include_data)
        # An encrypted profile is unpacked for the export; the archive is plain.
        with self._data.opened(name) as data_path:
            return export_to_zip(profile, str(data_path), export_path, include_data)

    def import_profile(
        self,
        zip_path: str,
        overwrite: bool = False,
    ) -> tuple[bool, str]:
        # Decide before extracting: an archive must not write into an existing
        # profile's data unless overwriting, and an overwrite that changes the
        # engine starts from an empty directory (the engines' data do not mix).
        meta = read_profile_meta(zip_path) or {}
        name = meta.get("name")
        with self._lock:
            # Case-insensitive collision check: find any existing profile whose
            # name casefolds to the imported name so the check is consistent on
            # all platforms (Windows/macOS case-insensitive FS, Linux sensitive).
            existing_key = self._find_by_casefold(name) if name else None
            if existing_key is not None:
                if not overwrite:
                    return False, f"Profile '{name}' already exists"
                if (meta.get("engine") or "camoufox") != self.profiles[existing_key].engine:
                    shutil.rmtree(self._data_path(existing_key), ignore_errors=True)
                if self._data is not None and self._data.is_encrypted(existing_key):
                    # The archive brings plain data; the old encrypted copy goes.
                    self._data.remove(existing_key)

            success, result = import_from_zip(zip_path, DATA_DIR)
            if not success:
                return False, result

            profile = result

            # An overwrite under a different case replaces the old entry rather
            # than leaving two names for one data directory.
            if existing_key is not None and existing_key != profile.name:
                old_dir = pathlib.Path(self._data_path(existing_key))
                new_dir = pathlib.Path(self._data_path(profile.name))
                if old_dir.exists() and not (new_dir.exists() and old_dir.samefile(new_dir)):
                    shutil.rmtree(old_dir, ignore_errors=True)
                del self.profiles[existing_key]
            self.profiles[profile.name] = profile
            self.save_profiles()
            logger.info("Registered imported profile: %s", profile.name)
            return True, profile.name
