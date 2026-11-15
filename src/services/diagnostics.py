"""A ZIP with what the app can tell about itself, sent with a bug report.

The archive holds no secrets: proxy credentials, the rotate link, WireGuard
configs, the API token, cookies and profile keys never go in. It does hold
paths, profile names and settings, because that is what makes a report useful;
the person picks the file themselves and is told so in the panel.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import pathlib
import platform
import subprocess
import sys
import time
import zipfile
from typing import Any

from ..core import config
from ..core.logging import get_logger
from ..models.profile import Profile

logger = get_logger("diagnostics")

# Caps so a runaway log or a thousand profiles cannot make the archive huge.
MAX_LOG_BYTES = 512 * 1024
MAX_PROCESS_BYTES = 128 * 1024
MAX_TEXT = 300
PANEL_KEYS = (
    "user_agent",
    "device_pixel_ratio",
    "screen",
    "window",
    "heap_used",
    "heap_limit",
    "dom_nodes",
    "body_text",
    "boot_ms",
    "uptime_s",
    "renderer",
)
LIBS = (
    "camoufox",
    "pywebview",
    "qtpy",
    "PyQt6",
    "PyQt6-WebEngine",
    "PySide6",
    "aiohttp",
    "fastapi",
    "uvicorn",
    "playwright",
    "cryptography",
    "argon2-cffi",
    "python-dotenv",
)


def clean_panel(panel: dict | None) -> dict[str, Any]:
    """The page's own numbers, accepted only as short scalars (untrusted input)."""
    if not isinstance(panel, dict):
        return {}
    clean: dict[str, Any] = {}
    for key in PANEL_KEYS:
        value = panel.get(key)
        if isinstance(value, (bool, int, float)):
            clean[key] = value
        elif isinstance(value, str):
            clean[key] = value[:MAX_TEXT]
    return clean


def library_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in LIBS:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        except Exception:  # a broken distribution must not stop the report
            continue
    return versions


def _profile_row(container: Any, profile: Profile, running: set[str]) -> dict[str, Any]:
    data = container.profile_data
    try:
        encrypted = data.is_encrypted(profile.name)
    except Exception:
        encrypted = False
    return {
        "name": profile.name,
        "engine": profile.engine,
        "os": profile.os_type,
        "tags": list(profile.tags),
        "status": profile.status,
        # Only the fact, never the value: a proxy carries a password.
        "has_proxy": bool(profile.proxy),
        "proxy_scheme": (profile.proxy or "").split("://", 1)[0]
        if "://" in (profile.proxy or "")
        else "",
        "has_wireguard": bool(profile.wireguard),
        "has_rotate_link": bool(profile.proxy_rotate_url),
        "extensions": len(profile.extensions),
        "pinned_geo": bool(profile.timezone or profile.locale),
        "encrypted": encrypted,
        "temporary": profile.temporary,
        "running": profile.name in running,
        "last_launch": {
            "at": (profile.last_launch or {}).get("at"),
            "country": (profile.last_launch or {}).get("country"),
        },
    }


def profiles_report(container: Any) -> dict[str, Any]:
    try:
        manager = container.profile_manager
    except Exception as e:
        return {"locked": True, "error": type(e).__name__}
    try:
        running = set(container.browser_launcher.running_profile_names())
    except Exception:
        running = set()
    rows = [_profile_row(container, p, running) for p in manager.profiles.values()]
    rows.sort(key=lambda r: r["name"].lower())
    return {"count": len(rows), "running": len(running), "profiles": rows}


def environment(container: Any, panel: dict | None = None) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    try:
        from dataclasses import asdict

        settings = asdict(container.settings.current)
    except Exception:
        settings = {}
    try:
        from ..services.security.profile_data import work_in_ram

        in_ram = work_in_ram()
    except Exception:
        in_ram = False
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "app": {"version": _version(), "frozen": bool(getattr(sys, "frozen", False))},
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "encoding": {
                "stdout": getattr(sys.stdout, "encoding", None),
                "filesystem": sys.getfilesystemencoding(),
            },
        },
        "system": {
            "platform": sys.platform,
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "language": config.LANGUAGE,
        },
        "paths": {
            "cwd": os.getcwd(),
            "data_dir": config.DATA_DIR,
            "profiles_file": config.PROFILES_FILE,
            "encrypted_dir": config.ENCRYPTED_DIR,
            "keys_file": config.KEYS_FILE,
            "vault_file": config.VAULT_FILE,
            "settings_file": config.SETTINGS_FILE,
            "extensions_dir": config.EXTENSIONS_DIR,
            "bin_dir": config.BIN_DIR,
            "log_dir": config.LOG_DIR,
            "work_dir_in_ram": in_ram,
        },
        "runtime": {
            "headless": config.HEADLESS,
            "restore_tabs": config.RESTORE_TABS,
            "api_port": config.API_PORT,
            "api_token_set": bool(config.API_TOKEN),
            "upload_dirs": list(config.UPLOAD_DIRS),
        },
        "settings": settings,
        "libraries": library_versions(),
        "panel": clean_panel(panel),
    }


def _version() -> str:
    try:
        from ..api.app import VERSION

        return VERSION
    except Exception:
        return "unknown"


def _tail(path: pathlib.Path, limit: int) -> str:
    try:
        size = path.stat().st_size
        with path.open("rb") as f:
            if size > limit:
                f.seek(size - limit)
                head = f"[... first {size - limit} bytes skipped]\n"
            else:
                head = ""
            body = f.read().decode("utf-8", errors="replace")
        return head + body
    except FileNotFoundError:
        return ""
    except OSError as e:
        return f"[could not read {path.name}: {e}]"


def logs_report() -> dict[str, str]:
    log_dir = pathlib.Path(config.LOG_DIR)
    files: dict[str, str] = {}
    try:
        candidates = sorted(log_dir.glob("*.log"))
    except OSError:
        candidates = []
    for path in candidates[-3:]:
        files[f"logs/{path.name}"] = _tail(path, MAX_LOG_BYTES)
    return files


def process_list() -> str:
    """Processes that belong to CloutFox: the app, its runners and the browsers."""
    if sys.platform == "win32":
        query = (
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -match 'python|firefox|camoufox|wireproxy|chrom|CloutFox' } | "
            "Select-Object ProcessId,ParentProcessId,Name,@{n='MB';e={[int]($_.WorkingSetSize/1MB)}} | "
            "Format-Table -AutoSize | Out-String -Width 200"
        )
        command = ["powershell", "-NoProfile", "-NonInteractive", "-Command", query]
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    else:
        command = ["ps", "-eo", "pid,ppid,rss,comm,args"]
        flags = 0
    try:
        done = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=20,
            creationflags=flags,
        )
    except (OSError, subprocess.SubprocessError) as e:
        return f"[could not list processes: {e}]"
    out = done.stdout or done.stderr or ""
    if sys.platform != "win32":
        lines = [
            line
            for line in out.splitlines()
            if any(
                k in line.lower()
                for k in ("python", "firefox", "camoufox", "wireproxy", "chrom", "cloutfox")
            )
        ]
        lines = [out.splitlines()[0], *lines] if out.splitlines() else lines
        out = "\n".join(lines)
    return out[:MAX_PROCESS_BYTES]


def build(container: Any, panel: dict | None = None) -> bytes:
    """The archive as bytes; the caller writes it where the person chose."""
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "environment.json",
            json.dumps(environment(container, panel), indent=2, ensure_ascii=False, default=str),
        )
        archive.writestr(
            "profiles.json",
            json.dumps(profiles_report(container), indent=2, ensure_ascii=False, default=str),
        )
        archive.writestr("processes.txt", process_list())
        for name, text in logs_report().items():
            archive.writestr(name, text)
        archive.writestr(
            "README.txt",
            "CloutFox diagnostics. No passwords, proxy credentials, cookies, "
            "WireGuard configs or API tokens are included. Paths, profile names "
            "and settings are.\n",
        )
    return buffer.getvalue()


def export(container: Any, dest: pathlib.Path, panel: dict | None = None) -> pathlib.Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_bytes(build(container, panel))
    os.replace(tmp, dest)
    logger.info("Diagnostics written to %s", dest)
    return dest
