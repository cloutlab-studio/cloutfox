"""An agent asks a person for help (captcha, 2FA, a login) and waits for the answer."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class HelpRequest:
    id: str
    profile: str
    reason: str
    created: float = field(default_factory=time.time)
    status: str = "pending"  # pending | done | declined
    note: str = ""
    _event: threading.Event = field(default_factory=threading.Event, repr=False)

    def public(self) -> dict:
        return {
            "id": self.id,
            "profile": self.profile,
            "reason": self.reason,
            "status": self.status,
            "note": self.note,
        }


class HumanRequests:
    def __init__(self, on_change: Callable[[], None] | None = None) -> None:
        self._lock = threading.Lock()
        self._requests: dict[str, HelpRequest] = {}
        self._on_change = on_change

    def _changed(self) -> None:
        if self._on_change:
            self._on_change()

    def ask(self, profile: str, reason: str) -> HelpRequest:
        request = HelpRequest(uuid.uuid4().hex[:12], profile, reason.strip()[:500])
        with self._lock:
            self._requests[request.id] = request
        self._changed()
        return request

    def get(self, request_id: str) -> HelpRequest | None:
        with self._lock:
            return self._requests.get(request_id)

    def pending(self) -> list[HelpRequest]:
        with self._lock:
            return [r for r in self._requests.values() if r.status == "pending"]

    def answer(self, request_id: str, done: bool, note: str = "") -> None:
        with self._lock:
            request = self._requests.get(request_id)
            if request is None or request.status != "pending":
                return
            request.status = "done" if done else "declined"
            request.note = note[:500]
        request._event.set()
        self._changed()

    def wait(self, request_id: str, timeout: float) -> HelpRequest | None:
        request = self.get(request_id)
        if request is not None and request.status == "pending":
            request._event.wait(timeout)
        return request

    def drop_profile(self, profile: str) -> None:
        """The profile's browser ended: its open requests can no longer be served."""
        with self._lock:
            ended = [
                r for r in self._requests.values() if r.profile == profile and r.status == "pending"
            ]
            for r in ended:
                r.status = "declined"
                r.note = "browser closed"
        for r in ended:
            r._event.set()
        if ended:
            self._changed()
