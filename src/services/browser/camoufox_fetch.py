"""Download Camoufox on first use: the installers ship without the browser.

The app starts the download in the background once the profiles are open, and a
Camoufox runner that finds no browser waits for it (or downloads it itself when
nothing else is). One process downloads at a time, under a lock file next to
Camoufox's cache. The download is `python -m camoufox fetch`, the command people
run by hand, in its own process.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from ...core.logging import get_logger
from ...core.strings import get_string

logger = get_logger("browser.camoufox_fetch")

_POLL_SECONDS = 1.0
# Progress bars and download speeds: one line per step is enough for the log.
_NOISE = re.compile(r"\d+(\.\d+)?%|\d+(\.\d+)?\s*[kMG]i?B/s")

_lock = threading.Lock()
_thread: threading.Thread | None = None


class CamoufoxMissing(Exception):
    pass


def is_installed() -> bool:
    try:
        from camoufox.geolocation import get_mmdb_path
        from camoufox.pkgman import camoufox_path

        camoufox_path(download_if_missing=False)
        return get_mmdb_path().exists()
    except Exception:
        return False


def lock_path() -> Path:
    from camoufox.pkgman import INSTALL_DIR

    return Path(INSTALL_DIR).parent / "cloutfox-camoufox.lock"


def _download(say: Callable[[str], None]) -> None:
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    proc = subprocess.Popen(
        [sys.executable, "-m", "camoufox", "fetch"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
        # Wide enough that its console output does not wrap paths and URLs.
        env={**os.environ, "COLUMNS": "400"},
    )
    assert proc.stdout is not None
    for raw in proc.stdout:
        for line in raw.replace("\r", "\n").splitlines():
            line = line.strip()
            if line and not _NOISE.search(line):
                say(line)
    proc.wait()


def ensure(say: Callable[[str], None]) -> None:
    """Return once Camoufox is installed, downloading it if no one else is.

    Raises CamoufoxMissing when the download did not install it."""
    from chrome_engine.fetch import _lock_owner, _try_lock

    if is_installed():
        return
    lock = lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    told = False
    while not _try_lock(lock):
        if _lock_owner(lock) is not None:
            if not told:
                say(get_string("camoufox_waiting"))
                told = True
            time.sleep(_POLL_SECONDS)
        if is_installed():
            return
    try:
        if is_installed():
            return
        say(get_string("camoufox_downloading"))
        _download(say)
    finally:
        with contextlib.suppress(OSError):
            lock.unlink()
    if not is_installed():
        raise CamoufoxMissing(get_string("camoufox_download_failed"))
    say(get_string("camoufox_ready"))


def start(log: Callable[[str], None] | None = None) -> bool:
    """Download Camoufox in the background unless it is installed or downloading.

    Returns True if a download thread was started."""
    global _thread

    def say(message: str) -> None:
        logger.info(message)
        if log:
            log(message)

    def run() -> None:
        try:
            ensure(say)
        except Exception as e:
            logger.warning("Camoufox download failed: %s", e)
            say(str(e))

    with _lock:
        if (_thread is not None and _thread.is_alive()) or is_installed():
            return False
        _thread = threading.Thread(target=run, daemon=True, name="camoufox-fetch")
        _thread.start()
        return True
