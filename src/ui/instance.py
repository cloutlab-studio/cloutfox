"""One CloutFox per data folder.

A second start (a double click on the shortcut while the first window is still
coming up, the menu entry clicked again) used to open a second window on the
same profiles: its API could not bind the port and died silently, both windows
wrote `profiles.json`, and the second one deleted the first one's one-time
profiles as leftovers. Now the second start asks the first one to show its
window and exits.

The channel is a QLocalServer (a named pipe on Windows, a socket only this user
may open on Linux) named after the data folder, so separate CLOUTFOX_HOME
folders still run side by side.
"""

from __future__ import annotations

import getpass
import hashlib
import os
from collections.abc import Callable
from typing import Any

from ..core.logging import get_logger

logger = get_logger("ui.instance")

SHOW = b"show\n"
CONNECT_MS = 1000


def server_name(home: str | None = None) -> str:
    """A name for this user's data folder: the same for every start that shares it."""
    folder = home or os.environ.get("CLOUTFOX_PROFILES_FILE") or os.path.abspath("profiles.json")
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    digest = hashlib.sha256(f"{user}\0{os.path.realpath(folder)}".encode()).hexdigest()[:16]
    return f"cloutfox-{digest}"


class Instance:
    """The running app's end of the channel: raises the window when asked."""

    def __init__(self, server: Any) -> None:
        self._server = server
        self._on_show: Callable[[], None] | None = None
        server.newConnection.connect(self._accept)

    def on_show(self, callback: Callable[[], None]) -> None:
        self._on_show = callback

    def _accept(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                return
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(socket.deleteLater)

    def _read(self, socket: Any) -> None:
        data = bytes(socket.readAll())
        if SHOW.strip() in data and self._on_show is not None:
            logger.info("Another start of CloutFox asked for this window")
            try:
                self._on_show()
            except Exception as e:
                logger.warning("Could not show the window: %s", e)
        socket.disconnectFromServer()


def claim(name: str | None = None) -> Instance | None:
    """Become the running instance, or wake the one already running and return None.

    Needs the QApplication to exist (window._qt_app).
    """
    from qtpy.QtNetwork import QLocalServer, QLocalSocket

    name = name or server_name()
    socket = QLocalSocket()
    socket.connectToServer(name)
    if socket.waitForConnected(CONNECT_MS):
        socket.write(SHOW)
        socket.flush()
        socket.waitForBytesWritten(CONNECT_MS)
        socket.disconnectFromServer()
        logger.info("CloutFox is already running with this data folder; showed its window")
        return None
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(name):
        # A socket file left by a crash: nobody answered on it, so it is stale.
        QLocalServer.removeServer(name)
        if not server.listen(name):
            logger.warning("Single-instance channel unavailable: %s", server.errorString())
            return Instance(server)
    return Instance(server)
