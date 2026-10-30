import atexit
import contextlib
import json
import os
import subprocess
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from typing import Any

from ...core.config import DATA_DIR
from ...core.logging import get_logger
from ...core.strings import get_string
from ...models.profile import Profile
from . import extensions, launch_opts, warmup, wireguard
from .control import TOKEN_HEADER
from .process import spawn_browser, terminate, wait_for_exit

logger = get_logger("browser.launcher")

_NOISY_PREFIXES = (
    "- [pid=",
    "console.error:",
    "Crash Annotation",
    "JavaScript error:",
    "WARNING: At least one completion condition",
)


class _LaunchResult:
    """Outcome of one launch, settled once the browser is ready or has failed."""

    def __init__(self) -> None:
        self.settled = threading.Event()
        self.ok = False
        self.error: str | None = None
        self._lock = threading.Lock()

    def settle(self, ok: bool, error: str | None = None) -> None:
        with self._lock:
            if self.settled.is_set():
                return
            self.ok = ok
            self.error = error
            self.settled.set()


class ProfileBusyError(Exception):
    """The profile's browser is running or another operation holds its data dir."""


class BrowserControlError(Exception):
    """A page action failed or the profile has no controllable browser."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


class BrowserLauncher:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_sessions: dict[str, subprocess.Popen] = {}
        self._stop_notifiers: dict[str, threading.Event] = {}
        self._launch_results: dict[str, _LaunchResult] = {}
        self._busy: set[str] = set()
        self._controls: dict[str, tuple[int, str]] = {}
        # WireGuard tunnels of running profiles (Check IP reuses them).
        self._tunnels: dict[str, wireguard.Tunnel] = {}
        # Called with (name, {"ip", "country"}) when a launch is ready.
        self.on_launched: Callable[[str, dict], None] | None = None
        # Unpacks encrypted profiles for a launch or a cookie operation (ProfileData).
        self.data: Any = None
        # Per running launch: gives its data back exactly once, however it ends.
        self._releasers: dict[str, Callable[[], None]] = {}
        # Called with the profile name once its browser has ended, however it ended.
        self.on_ended: Callable[[str], None] | None = None
        # App-wide launch options (e.g. {"geo_guard": True}) read at each launch.
        self.launch_options: Callable[[], dict] | None = None
        # Called with (name, sites done, total) as a cookie warm-up goes on.
        self.on_warmup: Callable[[str, int, int], None] | None = None
        # Called with (name, action, params, ok, error) after every page action.
        self.on_control: Callable[[str, str, dict, bool, str | None], None] | None = None
        atexit.register(self.shutdown_all)

    @contextlib.contextmanager
    def exclusive(self, profile_name: str) -> Iterator[str | None]:
        """Hold a stopped profile's data dir; launches are refused meanwhile.

        Yields the directory to work in (an encrypted profile is unpacked for the
        duration), or None when no ProfileData is attached.
        """
        with self._lock:
            if profile_name in self._busy:
                raise ProfileBusyError(profile_name)
            proc = self._active_sessions.get(profile_name)
            if proc is not None and proc.poll() is None:
                raise ProfileBusyError(profile_name)
            self._busy.add(profile_name)
        try:
            if self.data is None:
                yield None
            else:
                with self.data.opened(profile_name) as path:
                    yield str(path)
        finally:
            with self._lock:
                self._busy.discard(profile_name)

    @staticmethod
    def _profile_dir(name: str, data_dir: str | None) -> str:
        return data_dir or os.path.join(os.getcwd(), DATA_DIR, name)

    def _open_tunnel(
        self, name: str, data_dir: str | None, log: Callable[[str], None]
    ) -> wireguard.Tunnel:
        """Start the profile's WireGuard tunnel; its proxy replaces the profile's."""
        conf = wireguard.load(self._profile_dir(name, data_dir))
        if conf is None:
            raise wireguard.WireGuardError(f"{name} has no {wireguard.CONF_NAME}")
        tunnel = wireguard.Tunnel(conf)
        tunnel.start(log)
        with self._lock:
            self._tunnels[name] = tunnel
        log(get_string("wireguard_up", name=name))
        return tunnel

    @contextlib.contextmanager
    def wireguard_proxy(self, profile_name: str) -> Iterator[str]:
        """The proxy URL of the profile's tunnel: the running one, or a short-lived
        one for a stopped profile (Check IP). Raises WireGuardError without a config."""
        with self._lock:
            running = self._tunnels.get(profile_name)
        if running is not None and running.proxy:
            yield running.proxy
            return
        with self.exclusive(profile_name) as data_dir:
            conf = wireguard.load(self._profile_dir(profile_name, data_dir))
            if conf is None:
                raise wireguard.WireGuardError(f"{profile_name} has no {wireguard.CONF_NAME}")
            with wireguard.tunnel(conf) as proxy:
                yield proxy

    def wait_for_launch(self, profile_name: str, timeout: float) -> tuple[bool, str | None]:
        """Block until the latest launch of a profile is ready or has failed.

        Returns (ok, error). A launch still pending after `timeout` reports
        (False, "timeout") while the browser keeps starting in the background.
        """
        with self._lock:
            result = self._launch_results.get(profile_name)
        if result is None:
            return False, "No launch in progress"
        if not result.settled.wait(timeout):
            return False, "timeout"
        return result.ok, result.error

    def shutdown_all(self) -> None:
        with self._lock:
            for name, proc in list(self._active_sessions.items()):
                notifier = self._stop_notifiers.pop(name, None)
                if notifier:
                    notifier.set()
                terminate(proc, name, ask_to_close=self._closer(name))
            self._active_sessions.clear()
            releasers = list(self._releasers.values())
        # Pack encrypted profiles now: the exit-watcher threads die with the process.
        for release in releasers:
            release()
        logger.info("All browser sessions terminated")

    def _data_releaser(
        self, name: str, data_dir: str | None, tunnels: list | None = None
    ) -> Callable[[], None]:
        done = threading.Event()

        def release() -> None:
            with self._lock:
                if done.is_set():
                    return
                done.set()
                if self._releasers.get(name) is release:
                    del self._releasers[name]
                for tunnel in tunnels or []:
                    if self._tunnels.get(name) is tunnel:
                        del self._tunnels[name]
            for tunnel in tunnels or []:
                tunnel.stop()
            if data_dir is not None:
                try:
                    self.data.release(name)
                except Exception as e:
                    logger.exception("Could not pack the data of %s: %s", name, e)
            if self.on_ended:
                try:
                    self.on_ended(name)
                except Exception as e:
                    logger.warning("on_ended failed for %s: %s", name, e)

        return release

    def start_thread(
        self,
        profile: Profile,
        log_callback: Callable[[str], None],
        on_start: Callable[[], None] | None = None,
        on_ready: Callable[[], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        extra: dict | None = None,
    ) -> bool:
        """Launch a profile's browser in the background.

        Returns False, without calling any callback, when the profile already
        has a browser. Otherwise returns True and later calls on_ready or
        on_stop, also when spawning fails. Raises ProfileBusyError while
        another launch or a stopped-profile operation holds the profile.
        `extra` adds launch options for this launch only (a warm-up).
        """
        with self._lock:
            if profile.name in self._active_sessions:
                return False
            if profile.name in self._busy:
                raise ProfileBusyError(profile.name)
            # Reserve the profile until the process is registered, so two
            # concurrent launches cannot both spawn a browser.
            self._busy.add(profile.name)

        data_dir: str | None = None
        if self.data is not None:
            try:
                data_dir = str(self.data.acquire(profile.name))
            except BaseException:
                with self._lock:
                    self._busy.discard(profile.name)
                raise
        tunnels: list[wireguard.Tunnel] = []
        release_data = self._data_releaser(profile.name, data_dir, tunnels)
        with self._lock:
            self._releasers[profile.name] = release_data
        stop_event = threading.Event()
        notify_lock = threading.Lock()
        result = _LaunchResult()

        def notify_stopped() -> None:
            with notify_lock:
                if stop_event.is_set():
                    return
                stop_event.set()
                result.settle(False, "Browser exited before it was ready")
                with self._lock:
                    # A newer launch may already own this name; leave it alone.
                    if self._stop_notifiers.get(profile.name) is stop_event:
                        self._controls.pop(profile.name, None)
                        self._active_sessions.pop(profile.name, None)
                        self._stop_notifiers.pop(profile.name, None)
                release_data()
                log_callback(get_string("session_ended", name=profile.name))
                logger.info(f"Session ended for profile: {profile.name}")
                if on_stop:
                    on_stop()

        registered = False
        try:
            with self._lock:
                self._launch_results[profile.name] = result
            log_callback(get_string("starting_profile", name=profile.name, os=profile.os_type))
            for ext_id in extensions.mismatched(profile.extensions, profile.engine):
                log_callback(get_string("extension_skipped", name=profile.name, ext=ext_id))
            logger.info(f"Starting browser for profile: {profile.name}")
            if on_start:
                on_start()

            try:
                opts = {**(self.launch_options() if self.launch_options else {}), **(extra or {})}
                if urls := warmup.urls_from(opts):
                    self._report_warmup(profile.name, 0, len(urls))
                proxy = None
                if profile.wireguard:
                    tunnel = self._open_tunnel(profile.name, data_dir, log_callback)
                    tunnels.append(tunnel)
                    proxy = tunnel.proxy
                    if tunnel.internal:
                        opts = {**opts, "internal_tunnel": True}
                proc = spawn_browser(profile, data_dir, proxy=proxy, **opts)
                with self._lock:
                    self._active_sessions[profile.name] = proc
                    self._stop_notifiers[profile.name] = stop_event
                    self._busy.discard(profile.name)
                    registered = True

                threading.Thread(
                    target=self._monitor_process,
                    args=(proc, profile.name, log_callback, on_ready, notify_stopped, result),
                    daemon=True,
                ).start()
                threading.Thread(
                    target=wait_for_exit,
                    args=(proc, profile.name, notify_stopped),
                    daemon=True,
                ).start()
            except Exception as e:
                logger.exception(f"Error starting browser for {profile.name}: {e}")
                result.settle(False, str(e))
                with self._lock:
                    self._busy.discard(profile.name)
                release_data()
                log_callback(get_string("error_starting", error=e))
                if on_stop:
                    on_stop()
        finally:
            # Never keep the reservation when a callback raised before the
            # process was registered; the profile would stay busy for good.
            if not registered:
                with self._lock:
                    self._busy.discard(profile.name)
        return True

    def stop_profile(self, profile_name: str, timeout: int = 2) -> bool:
        with self._lock:
            if profile_name not in self._active_sessions:
                return False
            proc = self._active_sessions.pop(profile_name)
            notifier = self._stop_notifiers.pop(profile_name, None)
            ask_to_close = self._closer(profile_name)
            self._controls.pop(profile_name, None)
            release = self._releasers.get(profile_name)
        if notifier:
            notifier.set()
        terminate(proc, profile_name, timeout, ask_to_close)
        if release:
            release()
        logger.info("Stopped browser for profile: %s", profile_name)
        return True

    def control(
        self,
        profile_name: str,
        action: str,
        params: dict[str, Any] | None = None,
        timeout: float = 60,
        record: bool = True,
    ) -> Any:
        """Run a page action in a running profile's browser and return its result.

        record=False keeps the app's own actions out of the agent activity log.
        """
        with self._lock:
            endpoint = self._controls.get(profile_name)
        if not self.is_running(profile_name):
            raise BrowserControlError("Browser is not running", status=409)
        if endpoint is None:
            # Process is up but has not announced its control channel yet.
            raise BrowserControlError("Browser is still starting", status=503)
        port, token = endpoint
        try:
            result = self._call_control(port, token, action, params, timeout)
        except BrowserControlError as e:
            if record:
                self._report_control(profile_name, action, params, False, str(e))
            raise
        if record:
            self._report_control(profile_name, action, params, True, None)
        return result

    def _report_warmup(self, name: str, done: int, total: int) -> None:
        if self.on_warmup:
            try:
                self.on_warmup(name, done, total)
            except Exception as e:
                logger.warning("on_warmup failed for %s: %s", name, e)

    def _report_control(
        self, name: str, action: str, params: dict | None, ok: bool, error: str | None
    ) -> None:
        if self.on_control:
            try:
                self.on_control(name, action, params or {}, ok, error)
            except Exception as e:
                logger.debug("on_control failed: %s", e)

    def _closer(self, name: str) -> Callable[[], None] | None:
        """Asks a runner to close its browser, as a signal does (call under the lock)."""
        endpoint = self._controls.get(name)
        if endpoint is None:
            return None
        port, token = endpoint

        def close() -> None:
            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/shutdown",
                data=b"",
                headers={TOKEN_HEADER: token},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=2):
                pass

        return close

    @staticmethod
    def _call_control(
        port: int, token: str, action: str, params: dict | None, timeout: float
    ) -> Any:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/action",
            data=json.dumps({"action": action, "params": params or {}}).encode(),
            headers={"Content-Type": "application/json", TOKEN_HEADER: token},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read())
        except urllib.error.HTTPError as e:
            body = json.loads(e.read() or b"{}")
            raise BrowserControlError(body.get("error", f"HTTP {e.code}"), status=e.code) from e
        except (urllib.error.URLError, TimeoutError) as e:
            raise BrowserControlError(f"Browser did not respond: {e}", status=504) from e
        return body["result"]

    def running_profile_names(self) -> set[str]:
        with self._lock:
            stale = [n for n, p in self._active_sessions.items() if p.poll() is not None]
            for n in stale:
                self._active_sessions.pop(n, None)
                self._stop_notifiers.pop(n, None)
                self._controls.pop(n, None)
            return set(self._active_sessions.keys())

    def running_count(self) -> int:
        return len(self.running_profile_names())

    def is_running(self, profile_name: str) -> bool:
        with self._lock:
            if profile_name not in self._active_sessions:
                return False
            if self._active_sessions[profile_name].poll() is None:
                return True
            del self._active_sessions[profile_name]
            self._stop_notifiers.pop(profile_name, None)
            self._controls.pop(profile_name, None)
            return False

    def _monitor_process(
        self,
        proc: subprocess.Popen,
        name: str,
        log_callback: Callable[[str], None],
        on_ready: Callable[[], None] | None,
        notify_stopped: Callable[[], None],
        result: _LaunchResult,
    ) -> None:
        ready_notified = False
        geo: dict = {}
        try:
            if proc.stdout is None:
                return
            for line in iter(proc.stdout.readline, ""):
                msg = line.strip()
                if not msg:
                    continue
                if msg.startswith("CONTROL:"):
                    # Holds the control token: never log this line.
                    _, port, token = msg.split(":", 2)
                    with self._lock:
                        self._controls[name] = (int(port), token)
                    continue
                if msg.startswith(warmup.PREFIX):
                    if step := warmup.parse_line(msg):
                        done, total, url = step
                        self._report_warmup(name, done, total)
                        log_callback(
                            get_string("warmup_step", name=name, done=done, total=total, site=url)
                        )
                    continue
                if msg.startswith(launch_opts.GEO_PREFIX):
                    geo = launch_opts.parse_geo_line(msg) or {}
                    continue
                if msg == "BROWSER_STARTED":
                    result.settle(True)
                    if not ready_notified:
                        ready_notified = True
                        if self.on_launched:
                            try:
                                self.on_launched(name, geo)
                            except Exception as e:
                                logger.warning("on_launched failed for %s: %s", name, e)
                        if on_ready:
                            on_ready()
                    log_callback(get_string("browser_started"))
                    logger.info("Browser started for profile: %s", name)
                    continue
                if msg == "BROWSER_CLOSED":
                    logger.info("Browser close detected for profile: %s", name)
                    notify_stopped()
                    terminate(proc, name, timeout=1)
                    continue
                if msg.startswith("LAUNCH_FAILED:") or msg == "LAUNCH_CANCELLED":
                    result.settle(False, msg.removeprefix("LAUNCH_FAILED:").strip())
                    log_callback(f"[{name}] {msg}")
                    logger.warning("Launch failed for profile %s: %s", name, msg)
                    notify_stopped()
                    terminate(proc, name, timeout=1)
                    break
                if msg.startswith(_NOISY_PREFIXES):
                    logger.debug("[%s] %s", name, msg)
                    continue
                if len(msg) > 400:
                    msg = msg[:400] + "..."
                log_callback(f"[{name}] {msg}")
                logger.debug("[%s] %s", name, msg)
        except Exception as e:
            logger.exception("Monitor error for profile %s: %s", name, e)
            log_callback(f"[{name}] Monitor error: {e}")
        finally:
            if proc.stdout is not None:
                with contextlib.suppress(Exception):
                    proc.stdout.close()
