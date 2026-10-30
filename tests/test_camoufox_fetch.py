import os
import subprocess

import pytest

from src.services.browser import camoufox_fetch
from tests.conftest import REAL_ENSURE, REAL_START


@pytest.fixture
def fetch(monkeypatch, tmp_path):
    monkeypatch.setattr(camoufox_fetch, "lock_path", lambda: tmp_path / "fetch.lock")
    monkeypatch.setattr(camoufox_fetch, "_POLL_SECONDS", 0)
    state = {"installed": [False], "ran": []}

    def installed():
        values = state["installed"]
        return values.pop(0) if len(values) > 1 else values[0]

    monkeypatch.setattr(camoufox_fetch, "is_installed", installed)
    return state


class FakeFetch:
    def __init__(self, args, **kw):
        FakeFetch.args = args
        self.stdout = iter(
            [
                "Fetching Camoufox 150.0\n",
                "Downloading: 12.5%| 30MB 4.2MB/s\r 55%|\r",
                "Extracting...\n",
                "\n",
            ]
        )

    def wait(self):
        return 0


def test_installed_means_nothing_to_do(fetch, monkeypatch):
    fetch["installed"] = [True]
    monkeypatch.setattr(subprocess, "Popen", None)
    REAL_ENSURE(print)


def test_downloads_once_and_keeps_only_step_lines(fetch, monkeypatch, tmp_path):
    fetch["installed"] = [False, False, True]
    monkeypatch.setattr(subprocess, "Popen", FakeFetch)
    said = []
    REAL_ENSURE(said.append)
    assert FakeFetch.args[1:] == ["-m", "camoufox", "fetch"]
    assert "Fetching Camoufox 150.0" in said and "Extracting..." in said
    assert not any("%" in line for line in said)
    assert said[-1] == camoufox_fetch.get_string("camoufox_ready")
    assert not (tmp_path / "fetch.lock").exists()


def test_waits_for_a_live_download_elsewhere(fetch, monkeypatch, tmp_path):
    (tmp_path / "fetch.lock").write_text(str(os.getpid()))
    fetch["installed"] = [False, False, False, True]
    monkeypatch.setattr(subprocess, "Popen", None)
    said = []
    REAL_ENSURE(said.append)
    assert said == [camoufox_fetch.get_string("camoufox_waiting")]


def test_a_failed_download_raises_and_frees_the_lock(fetch, monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "Popen", FakeFetch)
    with pytest.raises(camoufox_fetch.CamoufoxMissing):
        REAL_ENSURE(lambda line: None)
    assert not (tmp_path / "fetch.lock").exists()


def test_start_runs_in_the_background_only_when_missing(fetch, monkeypatch):
    fetch["installed"] = [True]
    assert REAL_START() is False
    fetch["installed"] = [False]
    done = []
    monkeypatch.setattr(camoufox_fetch, "ensure", lambda say: done.append(1))
    assert REAL_START() is True
    camoufox_fetch._thread.join(5)
    assert done == [1]
