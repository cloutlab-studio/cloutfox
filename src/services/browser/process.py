import contextlib
import os
import pathlib
import signal
import subprocess
import sys
from collections.abc import Callable

from ...core.logging import get_logger
from ...models.profile import Profile
from . import launch_opts

logger = get_logger("browser.process")


_PROJECT_ROOT = str(pathlib.Path(__file__).parents[3])


# Stands for the proxy on the runner's command line: other OS users can read
# command lines, so the real one (with its password) travels in the environment.
PROXY_IN_ENV = "-"

_WINDOWS = sys.platform == "win32"
# The installed app runs under pythonw.exe, which has no console: a console
# program started without this flag opens an empty black window of its own.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def runner_command(profile: Profile) -> list[str]:
    """The runner for the profile's engine; both speak the same stdout protocol."""
    if profile.engine == "chrome":
        runner = ["-m", "chrome_engine.runner"]
    else:
        runner = [os.path.join(pathlib.Path(__file__).parent, "runner.py")]
    return [
        sys.executable,
        *runner,
        profile.name,
        PROXY_IN_ENV,
        profile.os_type,
        profile.timezone or "",
        profile.locale or "",
    ]


def spawn_browser(
    profile: Profile, data_dir: str | None = None, proxy: str | None = None, **opts: object
) -> subprocess.Popen:
    """Spawn the browser subprocess for the given profile (data in `data_dir` if given).

    `proxy` overrides the profile's (a local WireGuard bridge); `opts` are app-wide
    launch options such as geo_guard.
    """
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = _PROJECT_ROOT + (
        os.pathsep + existing_pythonpath if existing_pythonpath else ""
    )
    env[launch_opts.ENV] = launch_opts.encode(profile, proxy=str(proxy or profile.proxy), **opts)
    if data_dir:
        env[launch_opts.PROFILE_DIR_ENV] = data_dir
    return subprocess.Popen(
        runner_command(profile),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=pathlib.Path.cwd(),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=_NO_WINDOW,
    )


def _descendants(pid: int) -> list[int]:
    """Every process started by `pid`, the browser among them (Linux /proc scan)."""
    parents: dict[int, int] = {}
    try:
        names = os.listdir("/proc")
    except OSError:
        return []
    for name in names:
        if not name.isdigit():
            continue
        try:
            stat = pathlib.Path(f"/proc/{name}/stat").read_text()
            ppid = int(stat.rsplit(")", 1)[1].split()[1])
        except (OSError, IndexError, ValueError):
            continue
        parents[int(name)] = ppid
    found, frontier = [], [pid]
    while frontier:
        current = frontier.pop()
        for child, parent in parents.items():
            if parent == current and child not in found:
                found.append(child)
                frontier.append(child)
    return found


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill a process and everything it started (the browser too)."""
    if not _WINDOWS:
        for child in _descendants(proc.pid):
            with contextlib.suppress(OSError):
                os.kill(child, signal.SIGKILL)
        proc.kill()
        return
    if _WINDOWS:
        done = subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            creationflags=_NO_WINDOW,
        )
        if done.returncode == 0:
            return
    proc.kill()


def terminate(
    proc: subprocess.Popen,
    name: str,
    timeout: int = 5,
    ask_to_close: Callable[[], None] | None = None,
) -> None:
    """Gracefully terminate a browser process, force-kill on timeout.

    Windows has no SIGTERM: there `proc.terminate()` would kill the runner at once,
    before it saves the tabs and closes the browser. So on Windows the runner is
    asked through `ask_to_close` (its control server), and on timeout the whole
    process tree is killed.
    """
    if proc.poll() is not None:
        return
    try:
        if not _WINDOWS:
            proc.terminate()
        elif ask_to_close is not None:
            try:
                ask_to_close()
            except Exception as e:
                logger.debug("Browser %s did not take the close request: %s", name, e)
        try:
            proc.wait(timeout=timeout)
            logger.info("Browser %s terminated gracefully", name)
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            proc.wait(timeout=1)
            logger.warning("Browser %s force killed after timeout", name)
    except Exception as e:
        logger.exception("Error terminating browser %s: %s", name, e)


def wait_for_exit(
    proc: subprocess.Popen,
    name: str,
    notify_stopped: Callable[[], None],
) -> None:
    """Block until the process exits, then fire the callback."""
    try:
        proc.wait()
    except Exception as e:
        logger.exception("Wait error for profile %s: %s", name, e)
    finally:
        notify_stopped()
