"""The desktop window: Qt WebEngine through pywebview, showing the built panel
(`src/ui/dist`) and handing it the bridge."""

from __future__ import annotations

import contextlib
import os
import pathlib
import sys
import time
from collections.abc import Callable

from ..core.container import Container
from ..core.logging import get_logger
from ..core.strings import get_string
from . import instance as instance_mod
from .bridge import Bridge
from .push import Pump

logger = get_logger("ui.window")

DIST = pathlib.Path(__file__).parent / "dist"
ICON = pathlib.Path(__file__).parent.parent / "assets" / "icon.png"
# Wayland app id and X11 WM_CLASS; the packages' desktop file names it in StartupWMClass.
APP_ID = "cloutfox"
WINDOWS_APP_ID = "Cloutlab.CloutFox"
# Seconds without a renderer crash after which the reload backoff starts over.
QUIET_RESET = 600


def _expose_gc() -> None:
    """Let the panel call gc(): Qt WebEngine reads these flags when it starts.

    Every frame the panel draws on the main thread (a CSS animation of a
    non-composited property, the cursor, a new log line) leaves garbage in
    Blink's heap, and V8 schedules collections only by its own heap, which here
    stays at a few megabytes. Nothing ever collected it, and the renderer died
    at Chromium's 8 GiB data limit after about an hour of live profiles.
    """
    flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
    # Someone who sets their own V8 flags keeps them; the panel then skips gc().
    if "--js-flags" not in flags:
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{flags} --js-flags=--expose-gc".strip()


class _Callbacks(dict):
    """pywebview's table of evaluate_js callbacks, minus the empty ones.

    evaluate_js stores an entry for every call and deletes only those that had a
    callback, so each bridge call's reply would otherwise stay in it for good.
    """

    def __setitem__(self, key, value) -> None:
        if value is not None:
            super().__setitem__(key, value)


_APP = None


def _qt_app() -> None:
    """Create the Qt application first so the window gets CloutFox's name and app id."""
    if sys.platform == "win32":
        # Without its own id the taskbar button shows the Python icon.
        with contextlib.suppress(Exception):
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    # Qt WebEngine refuses to load once an application exists unless it was
    # imported first; pywebview imports it only later, in webview.start.
    import qtpy.QtWebEngineWidgets  # noqa: F401
    from qtpy.QtWidgets import QApplication

    global _APP
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName("CloutFox")
    app.setDesktopFileName(APP_ID)
    # PyQt destroys an application nobody references: without this the window
    # came up in a second one pywebview made, with no app id (no taskbar icon
    # grouping on Wayland) and with the single-instance server already dead.
    _APP = app


def _quit_on_sigterm() -> None:
    """Close like the window's X on SIGTERM (logout, `kill`, a package upgrade).

    Python's default handler ends the process at once, so atexit never ran:
    browsers were left running on their profiles, tabs were not saved and
    encrypted profiles stayed unpacked. Qt's loop is C code, so a timer lets
    Python run the handler.
    """
    if sys.platform == "win32":
        return
    with contextlib.suppress(Exception):
        import signal

        from qtpy.QtCore import QTimer
        from qtpy.QtWidgets import QApplication

        signal.signal(signal.SIGTERM, lambda *_: QApplication.quit())
        app = QApplication.instance()
        timer = QTimer(app)
        timer.timeout.connect(lambda: None)
        timer.start(500)


def _allow_sound(window) -> None:
    # The chime for an agent's request must play before anyone clicks the page.
    with contextlib.suppress(Exception):
        from qtpy.QtWebEngineCore import QWebEngineSettings

        window.native.webview.settings().setAttribute(
            QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
        )


def _reload_on_crash(window, bridge) -> None:
    # A renderer that runs out of memory or gets killed leaves a blank window
    # with the app still running behind it; load the panel again instead.
    # Backoff with a cap: a renderer that dies at once on every load would
    # otherwise turn into a reload storm, which looks like a flickering app.
    with contextlib.suppress(Exception):
        from qtpy.QtCore import QTimer

        view = window.native.webview
        quiet = {"count": 0, "last": 0.0}

        def terminated(status, code) -> None:
            bridge._panel_restarts += 1
            now = time.monotonic()
            # A crash after a long quiet spell starts the backoff over: a panel
            # left open for days must not stop reloading after its fifth crash.
            if now - quiet["last"] > QUIET_RESET:
                quiet["count"] = 0
            quiet["last"] = now
            quiet["count"] += 1
            delay = min(2 ** quiet["count"], 30)
            logger.warning(
                "The panel's renderer stopped (%s, code %s); reloading in %s s, %s time(s) so far",
                status,
                code,
                delay,
                bridge._panel_restarts,
            )
            if quiet["count"] > 5:
                logger.error("The panel's renderer keeps stopping; not reloading any more")
                return
            QTimer.singleShot(delay * 1000, view.reload)

        view.page().renderProcessTerminated.connect(terminated)


def _watch_panel(window, bridge) -> None:
    """Reload a panel that never says it is ready: a dead renderer leaves a blank window.

    A page that loads but fails in JavaScript shows the boot screen for good and
    never calls panel_ready, so silence is the only signal there is. Two reloads
    and a log line, so a real bug does not turn into an endless reload loop.
    """
    with contextlib.suppress(Exception):
        from qtpy.QtCore import QTimer

        view = window.native.webview
        tries = {"n": 0}

        def check() -> None:
            if bridge._panel_alive(within=120):
                return
            tries["n"] += 1
            if tries["n"] > 2:
                logger.error("The panel did not report ready after two reloads")
                return
            logger.warning("The panel did not report ready; reloading (%s of 2)", tries["n"])
            view.reload()
            QTimer.singleShot(20_000, check)

        QTimer.singleShot(15_000, check)


class _PageSender:
    """Runs the pump's scripts in the page without waiting for an answer.

    pywebview's evaluate_js blocks until the page replies, and a renderer that
    died mid-call never replies, which would stop every later update to the
    panel. The relay is made on the GUI thread (before_show), so a script sent
    from the pump's thread is queued to it.
    """

    def __init__(self) -> None:
        self._relay = None

    def attach(self, window) -> None:
        from qtpy.QtCore import QObject, Signal, Slot

        page = window.native.webview.page()

        class Relay(QObject):
            script = Signal(str)

            @Slot(str)
            def run(self, source: str) -> None:
                page.runJavaScript(source, 0)

        relay = Relay()
        relay.script.connect(relay.run)
        self._relay = relay

    def __call__(self, source: str) -> None:
        if self._relay is not None:
            self._relay.script.emit(source)


def _before_show(bridge, sender: _PageSender) -> list[Callable]:
    """What runs once the native window exists.

    pywebview hands the window only to a handler whose parameter is named
    `window` (it reads the signature), so every handler here takes exactly that.
    """

    def allow_sound(window) -> None:
        _allow_sound(window)

    def reload_on_crash(window) -> None:
        _reload_on_crash(window, bridge)

    def watch_panel(window) -> None:
        _watch_panel(window, bridge)

    def attach(window) -> None:
        sender.attach(window)

    return [allow_sound, reload_on_crash, watch_panel, attach]


def claim_instance() -> instance_mod.Instance | None:
    """The Qt application first, then the single-instance channel; None: already running."""
    _expose_gc()
    _qt_app()
    return instance_mod.claim()


def _show(window) -> None:
    """Bring the window forward for a second start of the app."""
    with contextlib.suppress(Exception):
        window.restore()
    with contextlib.suppress(Exception):
        window.show()
    with contextlib.suppress(Exception):
        native = window.native
        native.raise_()
        native.activateWindow()


class Window:
    def __init__(
        self,
        container: Container,
        on_unlocked: Callable[[], None],
        instance: instance_mod.Instance | None = None,
    ) -> None:
        self.c = container
        self.bridge = Bridge(container, on_unlocked)
        self.instance = instance

    def run(self) -> None:
        import webview

        index = DIST / "index.html"
        if not index.exists():
            raise SystemExit(
                f"The panel is not built: {index} is missing (cd frontend && npm run build)"
            )
        _expose_gc()
        _qt_app()
        _quit_on_sigterm()
        window = webview.create_window(
            get_string("window_title"),
            str(index),
            js_api=self.bridge,
            width=1400,
            height=860,
            min_size=(1180, 680),
            background_color="#F5F0E1",
            text_select=True,
        )
        window._callbacks = _Callbacks(window._callbacks)
        sender = _PageSender()
        pump = Pump(self.c, sender, window)
        pump.on_help = lambda r: self.bridge._log(get_string("help_requested", name=r.profile))
        self.bridge._attach(window, pump)
        for handler in _before_show(self.bridge, sender):
            window.events.before_show += handler
        if self.instance is not None:
            self.instance.on_show(lambda: _show(window))

        def stay_home() -> None:
            # Only the panel may run in this window: it holds the bridge.
            url = window.get_current_url() or ""
            if not url.startswith("http://127.0.0.1:") or "/index.html" not in url:
                logger.warning("The window left the panel (%s); going back", url)
                window.load_url(str(index))

        window.events.loaded += stay_home
        window.events.closed += pump.stop
        webview.start(gui="qt", http_server=True, icon=str(ICON), private_mode=True)
