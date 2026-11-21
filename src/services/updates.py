"""Is there a newer CloutFox, and how does this copy get it?

The check is opt-in: one HTTPS GET of `latest.json` on software.cloutlab.studio
(GitHub Pages, written by the Packages workflow when a release is published),
with the GitHub releases API as the fallback. No identifier, no telemetry,
nothing about the machine. The static file matters: the API allows 60 requests
an hour per address, and behind a provider's shared address that runs out.

Installing happens only when the person presses the button. How depends on how
this copy was installed (`plan`): the Windows setup or the MSI run after the app
has closed, then start it again; the deb or rpm goes through the system package
manager behind the password prompt; an AppImage replaces itself. A zip or a
source checkout gets the release page instead. Every file is checked against
the release's SHA-256 before it runs.
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
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from ..core.logging import get_logger

logger = get_logger("updates")

MANIFEST = "https://software.cloutlab.studio/latest.json"
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
    # File name -> sha256 when the answer carried them (latest.json does).
    sums: dict[str, str] | None = None


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
        raise UpdateError(f"{urllib.parse.urlsplit(url).hostname} answered {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError(str(getattr(e, "reason", e))) from e


def _from_manifest(payload: object) -> Release:
    if not isinstance(payload, dict):
        raise UpdateError("unreadable latest.json")
    version, url, assets = payload.get("version"), payload.get("url"), payload.get("assets")
    if not isinstance(version, str) or not isinstance(url, str):
        raise UpdateError("no version in latest.json")
    sums = None
    if isinstance(assets, dict):
        sums = {
            str(name): str(digest).lower()
            for name, digest in assets.items()
            if isinstance(digest, str) and len(digest) == 64
        }
    return _checked(version, url, sums)


def _from_github(payload: object) -> Release:
    if not isinstance(payload, dict):
        raise UpdateError("unreadable answer from GitHub")
    tag = payload.get("tag_name")
    url = payload.get("html_url")
    if not isinstance(tag, str) or not isinstance(url, str):
        raise UpdateError("no version in the answer from GitHub")
    return _checked(tag, url, None)


def _checked(tag: str, url: str, sums: dict[str, str] | None) -> Release:
    version = tag.strip().lstrip("vV")
    if parse_version(version) is None:
        raise UpdateError(f"unexpected version {tag!r}")
    # The page comes from the answer, so keep it on our own releases.
    if not url.startswith(PAGE_PREFIX):
        raise UpdateError("the answer points away from our releases")
    return Release(version=version, url=url, sums=sums or None)


def latest(fetch=None) -> Release:
    """The newest published release: latest.json first, the GitHub API if that fails."""
    fetch = fetch or _fetch
    errors = []
    for url, read in ((MANIFEST, _from_manifest), (API, _from_github)):
        try:
            return read(json.loads(fetch(url)))
        except json.JSONDecodeError:
            errors.append(f"{url}: unreadable answer")
        except UpdateError as e:
            errors.append(str(e))
    logger.debug("Update check failed: %s", errors)
    raise UpdateError(errors[-1])


# --- installing ------------------------------------------------------------------------

SUMS = "SHA256SUMS"
DOWNLOAD = "https://github.com/cloutlab-studio/cloutfox/releases/download"
CHUNK = 1024 * 256
APP = pathlib.Path(__file__).resolve().parents[2]
LINUX_PREFIX = pathlib.Path("/opt/cloutfox")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NEW_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


@dataclass(frozen=True)
class Plan:
    """How this copy of CloutFox would be replaced: what to download and how to run it."""

    kind: str  # inno, msi, appimage, deb, rpm
    asset: str
    root: str = ""  # the installed folder (Windows) or the AppImage file
    scope: str = ""  # Windows setup: "user" or "machine"


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


def _windows_plan(version: str, root: pathlib.Path, environ) -> Plan | None:
    if (root / "unins000.exe").exists():
        local = environ.get("LOCALAPPDATA", "")
        mine = bool(local) and _inside(root, pathlib.Path(local))
        return Plan(
            "inno", f"CloutFox-{version}-setup-x64.exe", str(root), "user" if mine else "machine"
        )
    for key in ("ProgramFiles", "ProgramW6432"):
        folder = environ.get(key)
        if folder and _inside(root, pathlib.Path(folder)):
            return Plan("msi", f"CloutFox-{version}-x64.msi", str(root), "machine")
    # The zip: a folder the person unpacked anywhere, no installer to run.
    return None


def _inside(path: pathlib.Path, folder: pathlib.Path) -> bool:
    try:
        return path.resolve().is_relative_to(folder.resolve())
    except (OSError, ValueError):
        return False


def plan(
    version: str,
    environ=None,
    platform: str | None = None,
    app: pathlib.Path | None = None,
) -> Plan | None:
    """The file that would replace this copy, or None when no installer put it there."""
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    app = APP if app is None else app
    if platform == "win32":
        # cloutfox_app.py lives in <install>\app.
        return _windows_plan(version, app.parent, environ)
    if environ.get("APPIMAGE"):
        return Plan("appimage", f"CloutFox-{version}-x86_64.AppImage", environ["APPIMAGE"])
    if _inside(app, LINUX_PREFIX):
        kind = distro_kind()
        asset = (
            f"cloutfox_{version}_amd64.deb" if kind == "deb" else f"cloutfox-{version}-1.x86_64.rpm"
        )
        return Plan(kind, asset, str(LINUX_PREFIX))
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
        step = 0
        while chunk := response.read(CHUNK):
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if say and total and done * 10 // total > step:
                step = done * 10 // total
                say(f"{step * 10}%")
    return digest.hexdigest()


def download(target: Plan, release: Release, say=lambda message: None) -> pathlib.Path:
    """Fetch the release file for `target` and return it once its SHA-256 matches."""
    expected = (release.sums or {}).get(target.asset)
    base = f"{DOWNLOAD}/v{release.version}"
    if not expected:
        expected = checksum_for(_fetch_text(f"{base}/{SUMS}"), target.asset)
    if not expected:
        raise UpdateError(f"{SUMS} has no {target.asset}")
    folder = pathlib.Path(tempfile.mkdtemp(prefix="cloutfox-update-"))
    file = folder / target.asset
    say(target.asset)
    try:
        actual = _download(f"{base}/{target.asset}", file, say)
    except (urllib.error.URLError, OSError) as e:
        shutil.rmtree(folder, ignore_errors=True)
        raise UpdateError(str(getattr(e, "reason", e))) from e
    if actual != expected:
        shutil.rmtree(folder, ignore_errors=True)
        raise UpdateError("the downloaded file does not match its checksum")
    return file


# --- after the download -------------------------------------------------------------------
#
# Windows cannot replace files a running program holds, and a setup that runs
# while CloutFox and its browsers are open either fails half way or kills them.
# So the app starts a small hidden PowerShell that waits for it to exit, runs
# the installer and starts CloutFox again, and then closes itself the normal way
# (browsers stop and save their tabs). Linux replaces files under a running
# program without trouble, so the package manager runs first and the app then
# restarts into the new version.


def _ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def windows_script(target: Plan, file: pathlib.Path, pid: int) -> str:
    """The PowerShell that installs once the app with `pid` has exited."""
    root = pathlib.Path(target.root)
    exe = root / "CloutFox.exe"
    if target.kind == "inno":
        scope = "/CURRENTUSER" if target.scope == "user" else "/ALLUSERS"
        args = f'/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS {scope} /DIR="{root}"'
        install = (
            f"Start-Process -FilePath {_ps_quote(str(file))} -ArgumentList {_ps_quote(args)} -Wait"
        )
    else:
        args = f'/i "{file}" /passive /norestart'
        install = (
            f"Start-Process -FilePath 'msiexec.exe' -ArgumentList {_ps_quote(args)} "
            "-Verb RunAs -Wait"
        )
    return "; ".join(
        [
            "$ErrorActionPreference = 'Continue'",
            f"Wait-Process -Id {int(pid)} -Timeout 300 -ErrorAction SilentlyContinue",
            f"try {{ {install} }} catch {{ }}",
            f"Start-Process -FilePath {_ps_quote(str(exe))}",
            f"Remove-Item -LiteralPath {_ps_quote(str(file.parent))} -Recurse -Force "
            "-ErrorAction SilentlyContinue",
        ]
    )


def relaunch_command(target: Plan | None, pid: int) -> list[str]:
    """A detached shell that waits for `pid` to exit and starts CloutFox again (Linux)."""
    if target is not None and target.kind == "appimage":
        program = [target.root]
    elif pathlib.Path("/usr/bin/cloutfox").exists() and _inside(APP, LINUX_PREFIX):
        program = ["/usr/bin/cloutfox"]
    elif (APP.parent / "cloutfox").is_file():
        # The tar.gz: its launcher sits next to the app folder.
        program = [str(APP.parent / "cloutfox")]
    else:
        program = [sys.executable, str(APP / "cloutfox_app.py")]
    return [
        "/bin/sh",
        "-c",
        'pid="$1"; shift; while kill -0 "$pid" 2>/dev/null; do sleep 0.3; done; exec "$@"',
        "cloutfox-relaunch",
        str(int(pid)),
        *program,
    ]


def package_command(target: Plan, file: pathlib.Path) -> list[str]:
    """The package manager call behind the system password prompt."""
    if target.kind == "deb":
        command = ["apt-get", "install", "-y", "--allow-downgrades", str(file)]
    else:
        command = ["dnf", "install", "-y", str(file)]
        if not shutil.which("dnf") and shutil.which("zypper"):
            command = ["zypper", "--non-interactive", "install", "--allow-unsigned-rpm", str(file)]
    return ["pkexec", *command] if shutil.which("pkexec") else command


def spawn_detached(command: list[str]) -> None:
    """Start a helper that outlives this process."""
    if sys.platform == "win32":
        subprocess.Popen(
            command,
            creationflags=NO_WINDOW | NEW_GROUP,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    subprocess.Popen(
        command,
        start_new_session=True,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def install(target: Plan, file: pathlib.Path, pid: int, say=lambda message: None) -> None:
    """Put the downloaded file in place. Afterwards the caller closes the app.

    Windows: hands over to a PowerShell that waits for the exit. Linux: the
    package manager (or the AppImage swap) runs now, then a relaunch helper waits
    for the exit. Raises UpdateError when nothing was installed, so the app stays.
    """
    if target.kind in ("inno", "msi"):
        script = windows_script(target, file, pid)
        spawn_detached(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-Command",
                script,
            ]
        )
        return
    if target.kind == "appimage":
        current = pathlib.Path(target.root)
        if not current.is_file():
            raise UpdateError("cannot find the running AppImage")
        file.chmod(0o755)
        try:
            os.replace(file, current)
        except OSError:
            # Another file system (the download sits in /tmp): copy, then swap.
            staged = current.with_name(current.name + ".new")
            shutil.copy2(file, staged)
            staged.chmod(0o755)
            os.replace(staged, current)
        spawn_detached(relaunch_command(target, pid))
        return
    if target.kind in ("deb", "rpm"):
        command = package_command(target, file)
        say(" ".join(command[:3]))
        done = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
        shutil.rmtree(file.parent, ignore_errors=True)
        if done.returncode != 0:
            # 126/127: the password prompt was closed or refused.
            if done.returncode in (126, 127):
                raise UpdateError("the password prompt was closed")
            tail = (done.stdout or "").strip().splitlines()[-1:] or [f"exit {done.returncode}"]
            raise UpdateError(tail[0])
        spawn_detached(relaunch_command(target, pid))
        return
    raise UpdateError(f"cannot update a {target.kind} install")


def installed_version(app: pathlib.Path | None = None) -> str | None:
    """The version on disk, which a system update may have replaced under the running app."""
    path = (APP if app is None else app) / "src" / "api" / "app.py"
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.startswith("VERSION = "):
                    return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        return None
    return None


def _fetch_text(url: str) -> str:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"User-Agent": "CloutFox"}), timeout=TIMEOUT
        ) as response:
            return response.read(MAX_BYTES).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError(str(getattr(e, "reason", e))) from e
