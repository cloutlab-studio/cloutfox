"""Telling the page that something changed.

The EventBus carries no data, and launches end without an event, so one loop
watches the bus flag, the set of running browsers and warm-up progress, and
sends the page a single `changed` signal; the page then asks for a snapshot.
New log lines are batched into the same tick. An agent's request for help also
raises the window here, so it comes up even while the page is busy.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import Any

from ..core.container import Container
from ..core.logging import get_logger
from . import attention

logger = get_logger("ui.push")

TICK = 0.25


class Pump:
    def __init__(self, container: Container, send: Callable[[str], Any], window: Any = None):
        self._c = container
        self._send = send
        self._window = window
        self._dirty = threading.Event()
        self._lock = threading.Lock()
        self._lines: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: tuple = ()
        self._help_seen: set[str] = set()
        # Called with each new request for help (the bridge logs it).
        self.on_help: Callable[[Any], None] = lambda request: None
        container.event_bus.subscribe(self.changed)

    def changed(self) -> None:
        self._dirty.set()

    def log(self, line: dict) -> None:
        with self._lock:
            self._lines.append(line)

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="ui-push", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _state(self) -> tuple:
        bl = self._c.browser_launcher
        running = frozenset(bl.running_profile_names())
        warm = tuple(sorted((n, str(self._c.warmup.running(n))) for n in running))
        return running, warm

    def _emit(self, message: dict) -> None:
        # json.dumps escapes everything the page did not write itself (profile
        # names, log text), so it can only arrive as data.
        self._send(f"window.__cf && window.__cf.push({json.dumps(message)})")

    def tick(self) -> None:
        state = self._state()
        dirty = self._dirty.is_set() or state != self._last
        self._dirty.clear()
        self._last = state
        with self._lock:
            lines, self._lines = self._lines, []
        if lines:
            self._emit({"type": "log", "lines": lines})
        if dirty:
            self._emit({"type": "changed"})
        requests = self._c.human_requests.pending()
        new = [r for r in requests if r.id not in self._help_seen]
        for request in new:
            self.on_help(request)
        if new and self._window is not None:
            attention.raise_window(self._window)
        self._help_seen = {r.id for r in requests}

    def _run(self) -> None:
        while not self._stop.wait(TICK):
            try:
                self.tick()
            except Exception as e:
                logger.error("UI push failed: %s", e)
