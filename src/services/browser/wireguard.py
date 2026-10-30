"""WireGuard per profile through wireproxy, a userspace WireGuard client.

A profile's tunnel config is `wireguard.conf` in its data directory, so an
encrypted profile keeps its private key encrypted. At launch `Tunnel` starts
wireproxy with that config and a local HTTP proxy on a random loopback port;
the browser uses that proxy instead of the profile's own. The proxy has no
login: Camoufox (Firefox) never completes wireproxy's 407 challenge, and
Playwright's Firefox refuses SOCKS5 with a password. Profiles.json keeps only
the endpoint, for display.

Only [Interface] and [Peer] keys WireGuard itself uses are kept: wireproxy also
reads sections such as [Socks5] or [TCPServerTunnel], and an imported file must
not open listeners of its own.

wireproxy is downloaded on first use from its GitHub releases, pinned to one
version and checked against SHA-256 sums recorded here.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import hashlib
import io
import ipaddress
import os
import pathlib
import platform
import secrets
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.request
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from ...core.config import BIN_DIR
from ...core.logging import get_logger
from ...core.strings import get_string

logger = get_logger("browser.wireguard")

CONF_NAME = "wireguard.conf"
MAX_CONF_BYTES = 16 * 1024

VERSION = "1.1.3"
_URL = "https://github.com/windtf/wireproxy/releases/download/v{version}/{asset}"
# (sys.platform prefix, machine) -> (release asset, its SHA-256)
_ASSETS = {
    ("linux", "x86_64"): (
        "wireproxy_linux_amd64.tar.gz",
        "e88c1d090740373fc606c1bafd81d9a5eadc642cce5667616e20e9d7a444f51c",
    ),
    ("linux", "aarch64"): (
        "wireproxy_linux_arm64.tar.gz",
        "370e00bd2167960d1ecd1c3c1439715bbaa94a0a110a2040468670c9af6021b6",
    ),
    ("win", "amd64"): (
        "wireproxy_windows_amd64.tar.gz",
        "bce041ea9fe0f8a3351301dcbe29cdf6a523bb25cf9c62f17ebb5699a8051d0f",
    ),
}
_ALIASES = {"amd64": "x86_64", "arm64": "aarch64"}

_KEPT = {
    "interface": ("PrivateKey", "Address", "DNS", "MTU"),
    "peer": ("PublicKey", "PresharedKey", "Endpoint", "AllowedIPs", "PersistentKeepalive"),
}
_KEYS = ("PrivateKey", "PublicKey", "PresharedKey")

START_TIMEOUT = 15.0


class WireGuardError(Exception):
    pass


# --- config ----------------------------------------------------------------------------


@dataclass
class Config:
    text: str  # the normalised file: only the kept keys
    endpoint: str  # first peer's Endpoint, shown in the app
    allowed_ips: tuple[str, ...] = ()  # every peer's AllowedIPs

    @property
    def routes_everything(self) -> bool:
        """Whether AllowedIPs covers all IPv4 or all IPv6 addresses (0.0.0.0/0, ::/0,
        or halves like 0.0.0.0/1 + 128.0.0.0/1), as a VPN with an internet exit does.

        A tunnel into a private network (a studio's panel) routes only that network:
        sites and the exit-IP lookup cannot go through it.
        """
        nets = [ipaddress.ip_network(n, strict=False) for n in self.allowed_ips]
        for version in (4, 6):
            same = [n for n in nets if n.version == version]
            if [n.prefixlen for n in ipaddress.collapse_addresses(same)] == [0]:
                return True
        return False


def _valid_key(value: str) -> bool:
    try:
        return len(base64.b64decode(value, validate=True)) == 32
    except (binascii.Error, ValueError):
        return False


def _check_value(section: str, key: str, value: str) -> None:
    if key in _KEYS:
        if not _valid_key(value):
            raise WireGuardError(f"{key} is not a WireGuard key")
    elif key in ("Address", "AllowedIPs"):
        for part in value.split(","):
            try:
                ipaddress.ip_interface(part.strip())
            except ValueError as e:
                raise WireGuardError(f"{key}: {part.strip()!r} is not an address") from e
    elif key == "DNS":
        for part in value.split(","):
            try:
                ipaddress.ip_address(part.strip())
            except ValueError as e:
                raise WireGuardError(f"DNS: {part.strip()!r} is not an IP address") from e
    elif key in ("MTU", "PersistentKeepalive"):
        if not value.isdigit() or not 0 <= int(value) <= 65535:
            raise WireGuardError(f"{key} must be a number")
    elif key == "Endpoint":
        host, sep, port = value.rpartition(":")
        if not (sep and host and port.isdigit() and 0 < int(port) < 65536) or any(
            c.isspace() for c in value
        ):
            raise WireGuardError("Endpoint must be host:port")


def parse(text: str) -> Config:
    """Validate a wg-quick style file and keep only what WireGuard needs."""
    if len(text.encode("utf-8", "replace")) > MAX_CONF_BYTES:
        raise WireGuardError("the file is too large for a WireGuard config")
    sections: list[tuple[str, dict[str, str]]] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            sections.append((line[1:-1].strip().lower(), {}))
            continue
        key, sep, value = line.partition("=")
        if not sep or not sections:
            raise WireGuardError(f"cannot read line: {raw.strip()[:40]}")
        section, values = sections[-1]
        key, value = key.strip(), value.strip()
        kept = {k.lower(): k for k in _KEPT.get(section, ())}
        if key.lower() in kept:
            name = kept[key.lower()]
            _check_value(section, name, value)
            values[name] = value
    interfaces = [v for s, v in sections if s == "interface"]
    peers = [v for s, v in sections if s == "peer"]
    if len(interfaces) != 1:
        raise WireGuardError("the config needs exactly one [Interface]")
    if not peers:
        raise WireGuardError("the config has no [Peer]")
    interface = interfaces[0]
    for key in ("PrivateKey", "Address"):
        if key not in interface:
            raise WireGuardError(f"[Interface] has no {key}")
    for peer in peers:
        for key in ("PublicKey", "Endpoint"):
            if key not in peer:
                raise WireGuardError(f"[Peer] has no {key}")
    blocks = [("Interface", interface)] + [("Peer", p) for p in peers]
    out = "\n".join(
        f"[{name}]\n" + "".join(f"{k} = {v}\n" for k, v in values.items())
        for name, values in blocks
    )
    allowed = tuple(
        part.strip() for p in peers for part in p.get("AllowedIPs", "").split(",") if part.strip()
    )
    return Config(out, peers[0]["Endpoint"], allowed)


def load(profile_dir: str) -> str | None:
    path = pathlib.Path(profile_dir) / CONF_NAME
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def save(profile_dir: str, text: str) -> str:
    """Write the profile's normalised config (owner-only); returns the endpoint."""
    config = parse(text)
    folder = pathlib.Path(profile_dir)
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / (CONF_NAME + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(config.text)
    os.replace(tmp, folder / CONF_NAME)
    return config.endpoint


def remove(profile_dir: str) -> None:
    from ..security.service import shred

    path = pathlib.Path(profile_dir) / CONF_NAME
    if path.exists():
        shred(path)


# --- wireproxy binary ------------------------------------------------------------------


def _asset() -> tuple[str, str]:
    system = "win" if sys.platform.startswith("win") else sys.platform
    machine = platform.machine().lower()
    for (prefix, arch), asset in _ASSETS.items():
        if system.startswith(prefix) and _ALIASES.get(machine, machine) == _ALIASES.get(arch, arch):
            return asset
    raise WireGuardError(f"WireGuard is not available on {sys.platform} {machine}")


def binary_path() -> pathlib.Path:
    name = "wireproxy.exe" if sys.platform.startswith("win") else "wireproxy"
    return pathlib.Path(BIN_DIR).resolve() / f"wireproxy-{VERSION}" / name


def is_installed() -> bool:
    return binary_path().is_file()


_install_lock = threading.Lock()


def install(log: Callable[[str], None] | None = None) -> pathlib.Path:
    """Download, verify and unpack the pinned wireproxy (no-op when present)."""
    with _install_lock:
        target = binary_path()
        if target.is_file():
            return target
        asset, sha256 = _asset()
        url = _URL.format(version=VERSION, asset=asset)
        if log:
            log(get_string("wireproxy_downloading", version=VERSION))
        logger.info("Downloading %s", url)
        with urllib.request.urlopen(url, timeout=60) as response:
            blob = response.read(64 << 20)
        digest = hashlib.sha256(blob).hexdigest()
        if digest != sha256:
            raise WireGuardError(f"wireproxy download does not match its checksum ({digest})")
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
            member = next(
                (m for m in archive.getmembers() if m.isfile() and m.name == target.name), None
            )
            if member is None:
                raise WireGuardError(f"{target.name} is missing from {asset}")
            data = archive.extractfile(member).read()
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.{os.getpid()}.part")
        tmp.write_bytes(data)
        tmp.chmod(0o755)
        os.replace(tmp, target)
        if log:
            log(get_string("wireproxy_ready"))
        return target


_prefetch_lock = threading.Lock()
_prefetch: threading.Thread | None = None


def prefetch(log: Callable[[str], None] | None = None) -> bool:
    """Download wireproxy in the background unless it is present or on its way."""
    global _prefetch
    with _prefetch_lock:
        if is_installed() or (_prefetch is not None and _prefetch.is_alive()):
            return False

        def run() -> None:
            try:
                install(log)
            except Exception as e:
                logger.warning("wireproxy download failed: %s", e)
                if log:
                    log(get_string("wireproxy_failed", error=e))

        _prefetch = threading.Thread(target=run, daemon=True, name="wireproxy-prefetch")
        _prefetch.start()
        return True


# --- tunnel ----------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


class Tunnel:
    """One wireproxy process exposing the tunnel as an HTTP proxy on loopback."""

    def __init__(self, conf_text: str) -> None:
        self._conf = parse(conf_text)
        self._proc: subprocess.Popen | None = None
        self._output: deque[str] = deque(maxlen=20)
        self.proxy: str | None = None
        # No route to the internet: the runner launches without an exit IP.
        self.internal = not self._conf.routes_everything

    def start(self, log: Callable[[str], None] | None = None) -> str:
        """Start wireproxy and return the proxy URL for the browser."""
        binary = install(log)
        port = _free_port()
        # A fresh login per tunnel: other OS users can reach a loopback port. The
        # browser cannot answer wireproxy's 407, so its runner puts the bridge
        # (proxy_bridge.ProxyBridge, same-user only) in front and logs in for it.
        user, password = secrets.token_hex(8), secrets.token_urlsafe(24)
        rendered = self._conf.text + (
            f"\n[http]\nBindAddress = 127.0.0.1:{port}\nUsername = {user}\nPassword = {password}\n"
        )
        # The rendered file holds the private key: in RAM where possible, and
        # deleted as soon as wireproxy has read it.
        from ..security.profile_data import work_root

        fd, path = tempfile.mkstemp(prefix="wireproxy-", suffix=".conf", dir=work_root())
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(rendered)
            flags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
            self._proc = subprocess.Popen(
                [str(binary), "-s", "-c", path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                creationflags=flags,
            )
            threading.Thread(target=self._read, daemon=True, name="wireproxy-out").start()
            deadline = time.monotonic() + START_TIMEOUT
            while not _listening(port):
                if self._proc.poll() is not None:
                    raise WireGuardError(self._failure())
                if time.monotonic() > deadline:
                    raise WireGuardError("wireproxy did not open its proxy in time")
                time.sleep(0.1)
        except BaseException:
            self.stop()
            raise
        finally:
            with contextlib.suppress(OSError):
                os.unlink(path)
        logger.info("WireGuard tunnel to %s on 127.0.0.1:%d", self._conf.endpoint, port)
        # Holds the login: never log it or pass it on a command line.
        self.proxy = f"http://{user}:{password}@127.0.0.1:{port}"
        return self.proxy

    def _read(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.strip()
            if line:
                self._output.append(line)
                logger.info("wireproxy: %s", line[:300])

    def _failure(self) -> str:
        time.sleep(0.2)  # let the reader catch the last lines
        detail = " / ".join(self._output) or f"exit code {self._proc.returncode}"
        return f"wireproxy stopped: {detail[:300]}"

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(3)


@contextlib.contextmanager
def tunnel(conf_text: str, log: Callable[[str], None] | None = None) -> Iterator[str]:
    """A short-lived tunnel (Check IP of a stopped profile); yields the proxy URL."""
    t = Tunnel(conf_text)
    try:
        yield t.start(log)
    finally:
        t.stop()


def configure(bl, pm, name: str, text: str | None, log=None) -> str | None:
    """Store (or with None remove) a stopped profile's tunnel config; returns the endpoint.

    Raises WireGuardError for a bad config and ProfileBusyError while it runs.
    """
    from ...core.config import DATA_DIR

    endpoint = parse(text).endpoint if text is not None else None
    with bl.exclusive(name) as data_dir:
        folder = data_dir or os.path.join(os.getcwd(), DATA_DIR, name)
        if text is None:
            remove(folder)
        else:
            save(folder, text)
    pm.set_wireguard(name, endpoint)
    if endpoint:
        prefetch(log)
    return endpoint
