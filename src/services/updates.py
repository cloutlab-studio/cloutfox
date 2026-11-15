"""Is there a newer CloutFox on GitHub?

Only when a person presses "Check for updates": one HTTPS GET to the public
releases API, no identifier, no telemetry, nothing sent about the machine. The
answer is a version to compare and the release page to open; the app never
downloads or installs anything by itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from ..core.logging import get_logger

logger = get_logger("updates")

API = "https://api.github.com/repos/cloutlab-studio/cloutfox/releases/latest"
PAGE_PREFIX = "https://github.com/cloutlab-studio/cloutfox/releases/"
TIMEOUT = 8
MAX_BYTES = 64 * 1024


class UpdateError(Exception):
    """The check failed: offline, refused, or an answer we do not trust."""


@dataclass(frozen=True)
class Release:
    version: str
    url: str


def parse_version(text: str) -> tuple[int, ...] | None:
    """3.1.10 -> (3, 1, 10); a leading v and a -beta suffix are not part of it."""
    core = text.strip().lstrip("vV").split("-")[0].split("+")[0]
    parts = core.split(".")
    if not parts or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def is_newer(latest: str, current: str) -> bool:
    """True when `latest` is a higher version than `current`; garbage is never newer."""
    new, old = parse_version(latest), parse_version(current)
    if new is None or old is None:
        return False
    length = max(len(new), len(old))
    return new + (0,) * (length - len(new)) > old + (0,) * (length - len(old))


def due(last: str, hours: int = 24, now: datetime | None = None) -> bool:
    """True when the automatic check is due: never checked, or checked long ago."""
    if not last:
        return True
    try:
        at = datetime.fromisoformat(last)
    except ValueError:
        return True
    return ((now or datetime.now()) - at).total_seconds() >= hours * 3600


def _fetch(url: str) -> bytes:
    from ..api.app import VERSION

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"CloutFox/{VERSION} (+https://github.com/cloutlab-studio/cloutfox)",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read(MAX_BYTES)
    except urllib.error.HTTPError as e:
        raise UpdateError(f"GitHub answered {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError(str(getattr(e, "reason", e))) from e


def latest(fetch=None) -> Release:
    """The newest published release on GitHub, as a version and the page to open."""
    try:
        payload = json.loads((fetch or _fetch)(API))
    except json.JSONDecodeError as e:
        raise UpdateError("unreadable answer from GitHub") from e
    if not isinstance(payload, dict):
        raise UpdateError("unreadable answer from GitHub")
    tag = payload.get("tag_name")
    url = payload.get("html_url")
    if not isinstance(tag, str) or not isinstance(url, str):
        raise UpdateError("no version in the answer from GitHub")
    version = tag.strip().lstrip("vV")
    if parse_version(version) is None:
        raise UpdateError(f"unexpected version {tag!r}")
    # The page comes from the answer, so keep it on our own releases.
    if not url.startswith(PAGE_PREFIX):
        raise UpdateError("the answer points away from our releases")
    return Release(version=version, url=url)


# --- installing ------------------------------------------------------------------------

SUMS = "SHA256SUMS"
DOWNLOAD = "https://github.com/cloutlab-studio/cloutfox/releases/download"
CHUNK = 1024 * 256


@dataclass(frozen=True)
class Plan:
    """How this copy of CloutFox would be replaced: what to download and how to run it."""

    kind: str  # appimage, deb, rpm, windows
    asset: str


def distro_kind(os_release: str = "/etc/os-release") -> str:
    """deb or rpm, from /etc/os-release; dpkg presence decides when that is unclear."""
    try:
        text = pathlib.Path(os_release).read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    fields = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key.strip()] = value.strip().strip('"').lower()
    family = " ".join([fields.get("ID", ""), fields.get("ID_LIKE", "")])
    if any(
        name in family for name in ("fedora", "rhel", "centos", "suse", "opensuse", "rocky", "alma")
    ):
        return "rpm"
    if any(name in family for name in ("debian", "ubuntu", "mint", "pop")):
        return "deb"
    return "deb" if shutil.which("dpkg") else "rpm"


def plan(version: str, environ=None, platform: str | None = None) -> Plan | None:
    """The file that would replace this copy, or None when it was not installed by a package."""
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    if platform == "win32":
        return Plan("windows", f"CloutFox-{version}-setup-x64.exe")
    if environ.get("APPIMAGE"):
        return Plan("appimage", f"CloutFox-{version}-x86_64.AppImage")
    if pathlib.Path("/opt/cloutfox").is_dir():
        kind = distro_kind()
        return Plan(
            kind,
            f"cloutfox_{version}_amd64.deb"
            if kind == "deb"
            else f"cloutfox-{version}-1.x86_64.rpm",
        )
    return None


def checksum_for(sums: str, asset: str) -> str | None:
    """The sha256 of `asset` from a SHA256SUMS file (`<hash>  <name>` per line)."""
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == asset:
            digest = parts[0].lower()
            return digest if len(digest) == 64 else None
    return None


def _download(url: str, dest: pathlib.Path, say=None) -> str:
    """Stream a file to disk and return its sha256."""
    digest = hashlib.sha256()
    with (
        urllib.request.urlopen(urllib.request.Request(url), timeout=TIMEOUT) as response,
        dest.open("wb") as out,
    ):
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(CHUNK):
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if say and total and done % (CHUNK * 40) < CHUNK:
                say(f"{done * 100 // total}%")
    return digest.hexdigest()


def install(target: Plan, version: str, say=lambda message: None) -> str:
    """Download the release file, check its checksum and start the installer.

    Returns a key for the panel: "update_installing" (the app will be replaced) or
    "update_restart" (an AppImage now holds the new build). Raises UpdateError.
    """
    base = f"{DOWNLOAD}/v{version}"
    try:
        sums = _fetch_text(f"{base}/{SUMS}")
    except UpdateError:
        raise
    expected = checksum_for(sums, target.asset)
    if not expected:
        raise UpdateError(f"{SUMS} has no {target.asset}")
    folder = pathlib.Path(tempfile.mkdtemp(prefix="cloutfox-update-"))
    file = folder / target.asset
    say(f"download {target.asset}")
    if _download(f"{base}/{target.asset}", file, say) != expected:
        file.unlink(missing_ok=True)
        raise UpdateError("the downloaded file does not match its checksum")

    if target.kind == "appimage":
        current = pathlib.Path(os.environ.get("APPIMAGE", ""))
        if not current.is_file():
            raise UpdateError("cannot find the running AppImage")
        file.chmod(0o755)
        os.replace(file, current)
        return "update_restart"
    if target.kind == "windows":
        # Inno Setup: silent, per user, and it closes the running app by itself.
        subprocess.Popen(
            [
                str(file),
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/CURRENTUSER",
                "/NORESTART",
                "/CLOSEAPPLICATIONS",
            ],
            close_fds=True,
        )
        return "update_installing"
    if target.kind in ("deb", "rpm"):
        command = (
            ["apt-get", "install", "-y", str(file)]
            if target.kind == "deb"
            else ["dnf", "install", "-y", str(file)]
        )
        # pkexec asks for the system password in a desktop dialog; no terminal needed.
        if shutil.which("pkexec"):
            command = ["pkexec", *command]
        subprocess.Popen(command, close_fds=True)
        return "update_installing"
    raise UpdateError(f"cannot update a {target.kind} install")


def _fetch_text(url: str) -> str:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "CloutFox"}), timeout=TIMEOUT
        ) as response:
            return response.read(MAX_BYTES).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError(str(getattr(e, "reason", e))) from e
