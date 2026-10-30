import logging
import threading
from collections.abc import Callable

from ..interfaces.protocols import IBrowserLauncher, IProfileManager, IProxyService
from .config import (
    BIN_DIR,
    DATA_DIR,
    ENCRYPTED_DIR,
    EXTENSIONS_DIR,
    KEYS_FILE,
    LOG_DIR,
    LOG_LEVEL,
    PROFILES_FILE,
    SETTINGS_FILE,
    VAULT_FILE,
)
from .events import EventBus
from .logging import setup_logging


class Container:
    def __init__(self) -> None:
        setup_logging(LOG_DIR, getattr(logging, LOG_LEVEL, logging.INFO))
        self._instances: dict = {}
        # The first API requests arrive on several worker threads at once; each
        # service must be built exactly once or they would hold separate state.
        self._lock = threading.RLock()

    def _get(self, key: str, build: Callable[[], object]):
        instance = self._instances.get(key)
        if instance is None:
            with self._lock:
                instance = self._instances.get(key)
                if instance is None:
                    instance = self._instances[key] = build()
        return instance

    @property
    def event_bus(self) -> EventBus:
        return self._get("eb", EventBus)

    @property
    def vault(self):
        from ..services.security.vault import Vault

        return self._get("vault", lambda: Vault(VAULT_FILE))

    @property
    def profile_data(self):
        from ..services.security.profile_data import ProfileData

        return self._get(
            "data", lambda: ProfileData(DATA_DIR, ENCRYPTED_DIR, KEYS_FILE, self.vault)
        )

    @property
    def security(self):
        from ..services.security.service import SecurityService

        return self._get(
            "security",
            lambda: SecurityService(
                self.vault, self.profile_data, lambda: self.profile_manager, self.wipe_paths
            ),
        )

    def wipe_paths(self) -> list[str]:
        """Everything self-destruct removes after the keys: data, logs, settings,
        extensions and this app's backups (only those files in the backup folder).

        A backup in progress is cancelled first: one finished after the listing
        would survive and still open with the master password in its header."""
        from ..services.backup import existing

        self.backups.stop()
        backups = [str(p) for p in existing(self.settings.current.backup_dir, partial=True)]
        # The app opens empty right after; it must not show or reuse the old folder.
        self.settings.reset()
        return [
            PROFILES_FILE, DATA_DIR, LOG_DIR, EXTENSIONS_DIR, BIN_DIR, *backups, SETTINGS_FILE
        ]  # fmt: skip

    @property
    def backups(self):
        from ..services.backup import BackupScheduler

        return self._get(
            "backups",
            lambda: BackupScheduler(self.settings, self.vault, lambda _: self.event_bus.emit()),
        )

    @property
    def profile_manager(self) -> IProfileManager:
        """Built on first use; with a master password set, only after it was entered."""
        from ..services.profile.manager import ProfileManager

        def build() -> IProfileManager:
            if self.security.locked:
                raise RuntimeError("profiles are locked by the master password")
            return ProfileManager(self.vault, self.profile_data)

        return self._get("pm", build)

    @property
    def browser_launcher(self) -> IBrowserLauncher:
        return self._get("bl", self._build_launcher)

    def _build_launcher(self) -> IBrowserLauncher:
        from ..services.browser.launcher import BrowserLauncher

        launcher = BrowserLauncher()
        launcher.data = self.profile_data

        def launched(name: str, geo: dict) -> None:
            self.profile_manager.record_launch(name, geo.get("ip"), geo.get("country"))
            self.event_bus.emit()

        def warmed(name: str, done: int, total: int) -> None:
            self.warmup.update(name, done, total)
            self.event_bus.emit()

        def ended(name: str) -> None:
            self.warmup.finish(name)
            self.human_requests.drop_profile(name)
            profile = self.profile_manager.profiles.get(name)
            if profile is not None and profile.temporary:
                self.profile_manager.delete_profile(name)
                self.activity.forget(name)
            self.event_bus.emit()

        launcher.launch_options = lambda: {"geo_guard": self.settings.current.geo_guard}
        launcher.on_launched = launched
        launcher.on_ended = ended
        launcher.on_warmup = warmed
        launcher.on_control = self.activity.record
        return launcher

    @property
    def settings(self):
        from .settings import SettingsStore

        return self._get("settings", SettingsStore)

    @property
    def activity(self):
        from ..services.agent.activity import ActivityLog

        return self._get("activity", lambda: ActivityLog(self.profile_data.path))

    @property
    def warmup(self):
        """Progress of cookie warm-ups (services/browser/warmup.py)."""
        from ..services.browser.warmup import Progress

        return self._get("warmup", Progress)

    def warmup_sites(self, urls: list[str] | None, count: int | None) -> list[str]:
        """The sites for one warm-up: the given list or the one in Settings, sampled."""
        from ..services.browser.warmup import pick

        current = self.settings.current
        return pick(urls or current.warmup_sites, count or current.warmup_count)

    @property
    def human_requests(self):
        from ..services.agent.human import HumanRequests

        return self._get("human", lambda: HumanRequests(self.event_bus.emit))

    @property
    def proxy_service(self) -> IProxyService:
        from ..services.proxy.service import ProxyService

        return self._get("ps", ProxyService)
