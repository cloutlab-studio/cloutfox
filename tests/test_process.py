import asyncio
import sys

import pytest

from src.models.profile import Profile
from src.services.browser import process, runner

# --- runner: launch failures -----------------------------------------------------------


def _patch_launch(monkeypatch, tmp_path, headless):
    seen = {"config": {}}

    def failing_camoufox(**config):
        seen["config"].update(config)
        raise RuntimeError("bad launch options")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner, "HEADLESS", headless)
    monkeypatch.setattr(runner, "AsyncCamoufox", failing_camoufox)
    monkeypatch.setattr(runner, "load_or_create", lambda *_: {})
    # No network: the exit-IP lookup (when present) is not under test here.
    monkeypatch.setattr(runner, "exit_ip", lambda *_: "5.6.7.8", raising=False)
    return seen


def test_launch_error_reports_launch_failed(monkeypatch, tmp_path, capsys):
    seen = _patch_launch(monkeypatch, tmp_path, True)
    assert asyncio.run(runner.run_browser("p", "None", "windows")) == 1

    assert "LAUNCH_FAILED: RuntimeError: bad launch options" in capsys.readouterr().out
    assert seen["config"]["headless"] is True


def test_dead_proxy_fails_before_the_browser_starts(monkeypatch, tmp_path, capsys):
    seen = _patch_launch(monkeypatch, tmp_path, False)

    def dead_proxy(*_):
        raise RuntimeError("Failed to get IP address")

    monkeypatch.setattr(runner, "exit_ip", dead_proxy)
    assert asyncio.run(runner.run_browser("p", "socks5://1.2.3.4:1080", "windows")) == 1
    assert "LAUNCH_FAILED: RuntimeError: Failed to get IP address" in capsys.readouterr().out
    assert seen["config"] == {}


def test_runners_share_the_launcher_session(monkeypatch):
    # A separate session would detach runners from the terminal: no Ctrl+C,
    # and closing the terminal would orphan their browsers.
    captured = {}
    monkeypatch.setattr(process.subprocess, "Popen", lambda args, **kw: captured.update(kw))
    process.spawn_browser(Profile(name="p"))
    assert not captured.get("start_new_session")


def test_proxy_stays_off_the_command_line(monkeypatch):
    import json

    from src.services.browser import launch_opts

    captured = {}
    monkeypatch.setattr(
        process.subprocess, "Popen", lambda args, **kw: captured.update(args=args, **kw)
    )
    profile = Profile(name="p", proxy="socks5://user:s3cret@192.0.2.1:1080")
    process.spawn_browser(profile)
    assert not any("s3cret" in a for a in captured["args"])
    assert json.loads(captured["env"][launch_opts.ENV])["proxy"] == profile.proxy
    process.spawn_browser(profile, proxy="http://u:p@127.0.0.1:40000")
    assert json.loads(captured["env"][launch_opts.ENV])["proxy"] == "http://u:p@127.0.0.1:40000"


class StubbornProc:
    """A runner that exits only once `exit()` is called (or it is killed)."""

    pid = 4242

    def __init__(self):
        self.calls = []
        self.code = None

    def poll(self):
        return self.code

    def terminate(self):
        self.calls.append("terminate")

    def kill(self):
        self.calls.append("kill")
        self.code = -9

    def exit(self):
        self.code = 0

    def wait(self, timeout=None):
        if self.code is None:
            raise process.subprocess.TimeoutExpired("runner", timeout)
        return self.code


def test_windows_asks_the_runner_to_close_instead_of_killing_it(monkeypatch):
    monkeypatch.setattr(process, "_WINDOWS", True)
    proc = StubbornProc()
    process.terminate(proc, "p", timeout=1, ask_to_close=proc.exit)
    assert proc.calls == [] and proc.code == 0


def test_windows_kills_the_whole_tree_when_the_runner_hangs(monkeypatch):
    monkeypatch.setattr(process, "_WINDOWS", True)
    monkeypatch.setattr(process.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    ran = []

    def taskkill(args, **kw):
        ran.append(args)
        proc.code = 1
        return process.subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(process.subprocess, "run", taskkill)
    proc = StubbornProc()

    def refuse():
        raise OSError("connection refused")

    process.terminate(proc, "p", timeout=0, ask_to_close=refuse)
    assert ran == [["taskkill", "/PID", "4242", "/T", "/F"]]
    assert proc.calls == []


def test_posix_signals_the_runner(monkeypatch):
    monkeypatch.setattr(process, "_WINDOWS", False)
    proc = StubbornProc()
    process.terminate(proc, "p", timeout=0, ask_to_close=proc.exit)
    assert proc.calls == ["terminate", "kill"]


def test_no_console_window_opens_for_the_runner(monkeypatch):
    """The installed app has no console, so a child console program would show one."""
    captured = {}
    monkeypatch.setattr(process.subprocess, "Popen", lambda args, **kw: captured.update(kw))
    process.spawn_browser(Profile(name="p"))
    expected = getattr(process.subprocess, "CREATE_NO_WINDOW", 0)
    assert captured["creationflags"] == expected


def test_kill_tree_hides_the_taskkill_window(monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured.update(args=args, **kwargs)

        class Done:
            returncode = 0

        return Done()

    monkeypatch.setattr(process, "_WINDOWS", True)
    monkeypatch.setattr(process.subprocess, "run", fake_run)
    process.kill_tree(type("P", (), {"pid": 42})())
    assert captured["args"][:2] == ["taskkill", "/PID"]
    assert captured["creationflags"] == getattr(process.subprocess, "CREATE_NO_WINDOW", 0)


@pytest.mark.skipif(sys.platform == "win32", reason="reads /proc")
def test_kill_tree_takes_the_browser_with_it():
    """A runner that dies must not leave its browser holding the profile: the next
    launch then fails with an opaque error and the profile looks broken."""
    import pathlib
    import subprocess as sp
    import sys
    import time

    code = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "print(child.pid, flush=True)\n"
        "time.sleep(30)\n"
    )
    runner = sp.Popen([sys.executable, "-c", code], stdout=sp.PIPE, text=True)
    try:
        child = int(runner.stdout.readline())
        assert process._descendants(runner.pid)
        process.kill_tree(runner)
        runner.wait(timeout=5)
        time.sleep(0.5)
        assert not pathlib.Path(f"/proc/{child}").exists(), "the browser survived its runner"
    finally:
        if runner.poll() is None:
            runner.kill()
