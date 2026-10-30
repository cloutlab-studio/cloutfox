import os
import pathlib
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
    )


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill a process and, on Windows, everything it started (the browser too)."""
    if _WINDOWS:
        done = subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
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
