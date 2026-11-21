"""The panel window's guards against Qt WebEngine and pywebview growing without bound."""

from src.ui import window


def test_expose_gc_adds_the_v8_flag(monkeypatch):
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")
    window._expose_gc()
    assert window.os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] == "--no-sandbox --js-flags=--expose-gc"


def test_expose_gc_without_other_flags(monkeypatch):
    monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)
    window._expose_gc()
    assert window.os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] == "--js-flags=--expose-gc"


def test_expose_gc_keeps_own_v8_flags(monkeypatch):
    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", "--js-flags=--max-old-space-size=512")
    window._expose_gc()
    assert window.os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] == "--js-flags=--max-old-space-size=512"


def test_callbacks_keep_only_real_callbacks():
    callbacks = window._Callbacks({"old": print})
    callbacks["empty"] = None
    callbacks["async"] = len
    assert callbacks == {"old": print, "async": len}
    del callbacks["async"]
    assert "async" not in callbacks


def test_before_show_handlers_receive_the_window(monkeypatch):
    """pywebview passes the window only to a parameter named `window`; a handler
    with any other name raised TypeError and was skipped, which in 3.1 left the
    panel without its crash reload and its start watchdog."""
    from webview.event import Event

    seen = []
    monkeypatch.setattr(window, "_allow_sound", lambda w: seen.append(("sound", w)))
    monkeypatch.setattr(window, "_reload_on_crash", lambda w, b: seen.append(("crash", w, b)))
    monkeypatch.setattr(window, "_watch_panel", lambda w, b: seen.append(("watch", w, b)))

    class Sender:
        def attach(self, w):
            seen.append(("attach", w))

    event = Event("the-window", should_lock=True)
    for handler in window._before_show("the-bridge", Sender()):
        event += handler
    event.set()
    assert seen == [
        ("sound", "the-window"),
        ("crash", "the-window", "the-bridge"),
        ("watch", "the-window", "the-bridge"),
        ("attach", "the-window"),
    ]


class _Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)


class _Bridge:
    _panel_restarts = 0


def _crash_harness(monkeypatch):
    import sys
    import types

    reloads = []
    view_signal = _Signal()
    view = types.SimpleNamespace(
        reload=lambda: None, page=lambda: types.SimpleNamespace(renderProcessTerminated=view_signal)
    )
    fake = types.SimpleNamespace(native=types.SimpleNamespace(webview=view))
    qtcore = types.ModuleType("qtpy.QtCore")
    qtcore.QTimer = types.SimpleNamespace(singleShot=lambda ms, fn: reloads.append(ms))
    monkeypatch.setitem(sys.modules, "qtpy.QtCore", qtcore)
    clock = {"now": 1000.0}
    monkeypatch.setattr(window.time, "monotonic", lambda: clock["now"])
    window._reload_on_crash(fake, _Bridge())
    return view_signal.slots[0], reloads, clock


def test_crash_reload_backs_off_and_gives_up(monkeypatch):
    crashed, reloads, clock = _crash_harness(monkeypatch)
    for _ in range(7):
        clock["now"] += 1
        crashed("killed", 9)
    assert reloads == [2000, 4000, 8000, 16000, 30000]


def test_crash_reload_starts_over_after_a_quiet_spell(monkeypatch):
    crashed, reloads, clock = _crash_harness(monkeypatch)
    for _ in range(6):
        clock["now"] += 1
        crashed("killed", 9)
    clock["now"] += window.QUIET_RESET + 1
    crashed("killed", 9)
    assert reloads[-1] == 2000 and len(reloads) == 6


def test_qt_app_outlives_the_call(monkeypatch):
    import pytest

    pytest.importorskip("qtpy.QtWidgets")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from qtpy.QtWidgets import QApplication

    window._qt_app()
    app = QApplication.instance()
    assert app is not None
    assert app.desktopFileName() == window.APP_ID
