"""What the panel knows about launches beyond the launcher: which profiles are
starting, which failed, since when each one is live, and the activity log."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from ..core.strings import get_string
from ..interfaces.protocols import IBrowserLauncher, IProfileManager
from ..services.browser.launcher import ProfileBusyError

# Lines kept for the Log page; older ones are in the log file.
LOG_LIMIT = 2000


class Runtime:
    def __init__(self, on_change: Callable[[], None] = lambda: None) -> None:
        self._lock = threading.Lock()
        self._loading: set[str] = set()
        # Profiles whose last launch exited before it was ready.
        self.failed: set[str] = set()
        self._live_since: dict[str, str] = {}
        self._log: list[dict] = []
        self._log_seq = 0
        self.on_change = on_change

    def is_loading(self, name: str) -> bool:
        with self._lock:
            return name in self._loading

    def set_loading(self, name: str, value: bool) -> None:
        with self._lock:
            if value:
                self._loading.add(name)
            else:
                self._loading.discard(name)

    def changed(self) -> None:
        self.on_change()

    def track(self, names: set[str], running: set[str]) -> None:
        """Forget marks of profiles that are gone; note when each running one came up."""
        with self._lock:
            # A failure mark lasts until the profile runs again or is gone.
            self.failed.intersection_update(names - running)
            for name in running - set(self._live_since):
                self._live_since[name] = time.strftime("%H:%M")
            for name in set(self._live_since) - running:
                del self._live_since[name]

    def since(self, name: str) -> str:
        with self._lock:
            return self._live_since.get(name, "")

    def add_log(self, message: str) -> dict:
        with self._lock:
            self._log_seq += 1
            line = {"id": self._log_seq, "at": time.strftime("%H:%M:%S"), "text": message}
            self._log.append(line)
            del self._log[:-LOG_LIMIT]
            return line

    def log_lines(self) -> list[dict]:
        with self._lock:
            return list(self._log)


def launch_or_stop(
    name: str,
    pm: IProfileManager,
    bl: IBrowserLauncher,
    state: Runtime,
    log: Callable[[str], None],
    extra: dict | None = None,
) -> None:
    """Start a stopped profile (with launch options `extra`, e.g. a warm-up) or stop it."""
    profile = pm.profiles.get(name)
    if not profile:
        return

    if bl.is_running(name):
        log(get_string("stopping_profile", name=name))
        state.set_loading(name, True)
        state.changed()

        def do_stop() -> None:
            try:
                bl.stop_profile(name)
            finally:
                state.set_loading(name, False)
                state.changed()

        threading.Thread(target=do_stop, daemon=True).start()
        return

    state.set_loading(name, True)
    state.failed.discard(name)
    log(get_string("launching_profile", name=name))
    state.changed()
    ready = threading.Event()

    def _on_ready() -> None:
        ready.set()
        state.set_loading(name, False)
        state.changed()

    def _on_stop() -> None:
        if not ready.is_set():
            state.failed.add(name)
        state.set_loading(name, False)
        state.changed()

    try:
        started = bl.start_thread(
            profile,
            log,
            None,
            on_ready=_on_ready,
            on_stop=_on_stop,
            extra=extra,
        )
    except ProfileBusyError:
        state.set_loading(name, False)
        log(get_string("profile_busy", name=name))
        state.changed()
        return
    if not started:
        # Launched elsewhere (API, MCP) since the check above; none of the
        # callbacks will fire for this click.
        state.set_loading(name, False)
        state.changed()
