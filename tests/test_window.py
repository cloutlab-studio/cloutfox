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
