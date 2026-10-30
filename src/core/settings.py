"""Settings changed from the app (not secrets): settings.json next to profiles.json.

Environment variables stay the way to configure paths and the API; this file
holds what a person toggles in the Settings dialog.
"""

from __future__ import annotations

import json
import os
import pathlib
import threading
from dataclasses import asdict, dataclass, field, fields

from .config import SETTINGS_FILE
from .logging import get_logger

logger = get_logger("settings")


# Where a cookie warm-up goes unless the person changes the list: big sites from
# many countries that set cookies on a first visit.
DEFAULT_WARMUP_SITES = (
    "google.com",
    "youtube.com",
    "wikipedia.org",
    "amazon.com",
    "ebay.com",
    "reddit.com",
    "bbc.com",
    "cnn.com",
    "nytimes.com",
    "theguardian.com",
    "imdb.com",
    "booking.com",
    "tripadvisor.com",
    "weather.com",
    "accuweather.com",
    "stackoverflow.com",
    "github.com",
    "bing.com",
    "yahoo.com",
    "msn.com",
    "aliexpress.com",
    "walmart.com",
    "espn.com",
    "cnet.com",
    "forbes.com",
    "nationalgeographic.com",
    "allrecipes.com",
    "pinterest.com",
    "twitch.tv",
    "medium.com",
)


@dataclass
class Settings:
    # Refuse a launch when the exit IP's geo does not match what the browser shows.
    geo_guard: bool = False
    # Scheduled backups: folder, every N hours (0 = off), how many to keep.
    backup_dir: str = ""
    backup_hours: int = 0
    backup_keep: int = 7
    last_backup: str = ""
    # Cookie warm-up: the shared list of sites and how many one warm-up visits.
    warmup_sites: list = field(default_factory=lambda: list(DEFAULT_WARMUP_SITES))
    warmup_count: int = 10
    # The panel: language ("" = CLOUTFOX_LANG), sounds, motion and the cursor.
    language: str = ""
    sound: bool = True
    sound_volume: int = 60
    motion: str = "system"
    cursor: bool = True


class SettingsStore:
    def __init__(self, path: str | os.PathLike = SETTINGS_FILE) -> None:
        self.path = pathlib.Path(path)
        self._lock = threading.Lock()
        self.current = self._load()

    def _load(self) -> Settings:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return Settings()
        except ValueError as e:
            logger.warning("Ignoring unreadable %s: %s", self.path, e)
            return Settings()
        known = {f.name for f in fields(Settings)}
        values = {}
        for key, value in raw.items() if isinstance(raw, dict) else []:
            default = getattr(Settings(), key, None)
            if key in known and isinstance(value, type(default)):
                if isinstance(value, list):
                    value = [v for v in value if isinstance(v, str)]
                values[key] = value
        return Settings(**values)

    def reset(self) -> None:
        """Back to the defaults in memory only (self-destruct deletes the file)."""
        with self._lock:
            self.current = Settings()

    def update(self, **changes: object) -> Settings:
        with self._lock:
            for key, value in changes.items():
                if not hasattr(self.current, key):
                    raise TypeError(f"unknown setting: {key}")
                setattr(self.current, key, value)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(asdict(self.current), indent=2), encoding="utf-8")
            os.replace(tmp, self.path)
            return self.current
