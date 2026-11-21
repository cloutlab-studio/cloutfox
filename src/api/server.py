from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

import uvicorn

from ..core.config import API_HOST, API_PORT
from ..core.logging import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger("api.server")


class APIServer:
    """Runs the FastAPI app in a background daemon thread."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    def start(self, on_failed: Callable[[str], None] | None = None) -> None:
        """Serve in the background; `on_failed` hears why when the port cannot be bound."""
        config = uvicorn.Config(
            app=self._app,
            host=API_HOST,
            port=API_PORT,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        self._thread = threading.Thread(
            target=self._server.run,
            daemon=True,
            name="cloutfox-api",
        )
        self._thread.start()
        threading.Thread(
            target=self._watch_start, args=(on_failed,), daemon=True, name="cloutfox-api-watch"
        ).start()

    def _watch_start(self, on_failed: Callable[[str], None] | None, wait: float = 30.0) -> None:
        """uvicorn exits its thread when the port is taken: say so instead of claiming success."""
        server, thread = self._server, self._thread
        if server is None or thread is None:
            return
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline and thread.is_alive() and not server.started:
            time.sleep(0.05)
        if server.started:
            logger.info("API available at http://%s:%s/api/v1", API_HOST, API_PORT)
            return
        if thread.is_alive():
            return
        logger.error("The API could not start: port %s on %s is in use", API_PORT, API_HOST)
        if on_failed is not None:
            try:
                on_failed(f"{API_HOST}:{API_PORT}")
            except Exception as e:
                logger.warning("on_failed raised: %s", e)

    def stop(self) -> None:
        if self._server:
            self._server.should_exit = True
            logger.info("API server shutdown requested")

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
