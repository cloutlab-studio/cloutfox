"""What agents did in each profile: every page action that went through the API or MCP.

Only an allow-list of parameters is kept (selectors, keys, coordinates...);
typed text, prompt answers and scripts become their length, URLs lose their
query string, file paths keep only the file name.
"""

from __future__ import annotations

import json
import pathlib
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ...core.logging import get_logger

logger = get_logger("agent.activity")

LOG_FILE = "agent_actions.jsonl"
KEEP = 500
# Parameters kept as they are; everything else (typed text, prompt answers,
# scripts, values) is reduced to its length, so secrets never reach the log.
_KEEP_PARAMS = {
    "selector",
    "source",
    "target",
    "key",
    "x",
    "y",
    "dx",
    "dy",
    "index",
    "ms",
    "timeout",
    "wait_until",
    "max_chars",
    "full_page",
    "submit",
    "clear",
    "delay",
    "accept",
}


def _url(value: str) -> str:
    """scheme://host/path: query strings and fragments often carry tokens."""
    parts = urlsplit(value)
    if not parts.scheme:
        return f"<{len(value)} chars>"
    return urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", ""))


def summarize(action: str, params: dict[str, Any]) -> dict[str, Any]:
    """Parameters safe to keep and show to anyone who can open the app."""
    out: dict[str, Any] = {}
    for key, value in params.items():
        if key == "url" and isinstance(value, str):
            out[key] = _url(value)
        elif key == "paths" and isinstance(value, list):
            out[key] = [pathlib.PurePath(str(p)).name for p in value]
        elif key in _KEEP_PARAMS and (value is None or isinstance(value, bool | int | float)):
            out[key] = value
        elif key in _KEEP_PARAMS and isinstance(value, str):
            out[key] = value[:200] + ("..." if len(value) > 200 else "")
        elif isinstance(value, str | list | dict):
            out[key] = (
                f"<{len(value)} chars>" if isinstance(value, str) else f"<{len(value)} items>"
            )
        else:
            out[key] = f"<{type(value).__name__}>"
    return out


class ActivityLog:
    def __init__(self, path_of: Callable[[str], pathlib.Path | None]) -> None:
        """`path_of(name)` is the profile's data directory right now (None: unavailable);
        entries are appended there too, so an encrypted profile's log stays encrypted."""
        self._path_of = path_of
        self._lock = threading.Lock()
        self._recent: dict[str, deque] = {}

    def record(
        self, name: str, action: str, params: dict[str, Any], ok: bool, error: str | None
    ) -> None:
        entry = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "action": action,
            "params": summarize(action, params),
            "ok": ok,
            **({"error": error[:300]} if error else {}),
        }
        with self._lock:
            self._recent.setdefault(name, deque(maxlen=KEEP)).append(entry)
        path = self._path_of(name)
        if path is None:
            return
        try:
            with (pathlib.Path(path) / LOG_FILE).open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.debug("Could not append agent log for %s: %s", name, e)

    def entries(self, name: str, limit: int = 200) -> list[dict]:
        """The latest entries, oldest first: this session's, or else the saved file."""
        with self._lock:
            recent = list(self._recent.get(name, ()))
        if recent:
            return recent[-limit:]
        path = self._path_of(name)
        if path is None:
            return []
        try:
            lines = (pathlib.Path(path) / LOG_FILE).read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in lines[-limit:]:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out

    def forget(self, name: str) -> None:
        with self._lock:
            self._recent.pop(name, None)
