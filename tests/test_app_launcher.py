import pathlib
import subprocess
import sys
import types

import pytest

import cloutfox_app

ROOT = pathlib.Path(__file__).resolve().parent.parent


def test_home_fills_only_unset_paths(tmp_path):
    env = {"CLOUTFOX_HOME": str(tmp_path), "CLOUTFOX_LOG_DIR": "/elsewhere/logs"}
    assert cloutfox_app.apply_home(env) == tmp_path
    assert env["CLOUTFOX_PROFILES_FILE"] == str(tmp_path / "profiles.json")
    assert env["CLOUTFOX_BIN_DIR"] == str(tmp_path / "bin")
    assert env["CLOUTFOX_LOG_DIR"] == "/elsewhere/logs"


def test_default_home_on_windows(monkeypatch):
    monkeypatch.setattr(cloutfox_app.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "C:/Users/u/AppData/Local")
    assert cloutfox_app.default_home() == pathlib.Path("C:/Users/u/AppData/Local/CloutFox")


def test_run_sh_starts_the_launcher():
    assert "exec .venv/bin/python cloutfox_app.py" in (ROOT / "run.sh").read_text()


def test_dotenv_paths_win_over_the_home(tmp_path, monkeypatch):
    env = {"CLOUTFOX_HOME": str(tmp_path), "CLOUTFOX_DATA_DIR": str(tmp_path / "elsewhere")}
    cloutfox_app.apply_home(env)
    assert env["CLOUTFOX_DATA_DIR"] == str(tmp_path / "elsewhere")


@pytest.mark.skipif(not (ROOT / ".git").exists(), reason="not a git checkout")
def test_windows_scripts_keep_crlf():
    attrs = subprocess.run(
        ["git", "check-attr", "eol", "run_cloutfox.bat", "packaging/test_package.sh"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout
    assert "run_cloutfox.bat: eol: crlf" in attrs
    assert "packaging/test_package.sh: eol: lf" in attrs


def test_failed_start_lands_in_the_log(tmp_path, monkeypatch):
    def boom():
        raise RuntimeError("no Qt")

    monkeypatch.setitem(sys.modules, "src.main", types.SimpleNamespace(main=boom))
    monkeypatch.setattr(cloutfox_app.os, "environ", {"CLOUTFOX_HOME": str(tmp_path)})
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError):
        cloutfox_app.main()
    assert "RuntimeError: no Qt" in (tmp_path / "logs" / "crash.log").read_text()
