"""One running CloutFox per data folder: a second start wakes the first one."""

import pytest

from src.ui import instance

QtNetwork = pytest.importorskip("qtpy.QtNetwork")


@pytest.fixture
def qt_app(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from src.ui import window

    window._qt_app()
    return window._APP


def _pump(app, until, rounds=200):
    import time

    for _ in range(rounds):
        app.processEvents()
        if until():
            return True
        time.sleep(0.01)
    return False


def test_server_name_depends_on_the_data_folder(tmp_path):
    a = instance.server_name(str(tmp_path / "a" / "profiles.json"))
    b = instance.server_name(str(tmp_path / "b" / "profiles.json"))
    assert a != b
    assert a == instance.server_name(str(tmp_path / "a" / "profiles.json"))
    assert a.startswith("cloutfox-")


def test_second_start_wakes_the_first_and_steps_back(qt_app, tmp_path):
    import threading

    name = instance.server_name(str(tmp_path / "profiles.json"))
    first = instance.claim(name)
    assert first is not None
    shown = []
    first.on_show(lambda: shown.append(True))

    result = {}

    def second():
        result["claim"] = instance.claim(name)

    thread = threading.Thread(target=second)
    thread.start()
    assert _pump(qt_app, lambda: not thread.is_alive() and shown)
    assert result["claim"] is None
    assert shown == [True]
    first._server.close()


def test_a_stale_socket_is_taken_over(qt_app, tmp_path):
    name = instance.server_name(str(tmp_path / "stale" / "profiles.json"))
    first = instance.claim(name)
    assert first is not None
    # A crashed app never closes its server: on Linux its socket file stays.
    first._server.close()
    again = instance.claim(name)
    assert again is not None
    again._server.close()
