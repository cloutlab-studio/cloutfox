"""The panel's only way into Python: pywebview exposes every public method of
`Bridge` to the page as `window.pywebview.api.<method>`.

Each call runs in its own thread, so a slow one (a cookie export, a backup) just
blocks until it is done and the page awaits its Promise. Methods return plain
JSON: data, or `{"error": message}` for something the person should read.

The page shows text written by agents and websites (profile names, notes, the
agent activity log) and this object can unlock the vault, so keep every
attribute private (`_name`): pywebview walks public attributes too.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import sys
import threading
import urllib.request
import webbrowser
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from ..core.config import API_PORT, API_TOKEN, DATA_DIR
from ..core.container import Container
from ..core.logging import get_logger
from ..core.strings import STRINGS, current_language, get_string, set_language
from ..models.profile import META_FIELDS, STATUSES, Profile
from ..services import mcp_setup
from ..services.browser import (
    camoufox_fetch,
    chrome_prefetch,
    cookies,
    extensions,
    fingerprint,
    warmup,
    wireguard,
)
from ..services.browser.launcher import ProfileBusyError
from ..services.profile import bulk
from ..services.proxy.geo_check import GeoCheckResult, check_geo
from ..services.proxy.rotate import rotate_ip
from ..services.security.profile_data import ProfileDataError, work_in_ram
from ..services.security.vault import VaultError
from ..utils.proxy_parser import mask_proxy
from ..utils.validation import (
    normalize_tags,
    validate_http_url,
    validate_locale,
    validate_profile_name,
    validate_proxy_format,
    validate_timezone,
    validate_urls,
)
from . import attention
from .runtime import Runtime, launch_or_stop

logger = get_logger("ui.bridge")

API_URL = f"http://127.0.0.1:{API_PORT}"
MCP_URL = f"{API_URL}/mcp"

WARMUP_COUNTS = (3, 5, 10, 15, 20, 30)
BACKUP_HOURS = (0, 6, 12, 24, 72, 168)
BACKUP_KEEP = (3, 7, 14, 30)
MOTIONS = ("system", "full", "reduced")
# Settings the page may change, with their types; the rest go through their own methods.
_UI_SETTINGS = {
    "geo_guard": bool,
    "warmup_sites": list,
    "warmup_count": int,
    "backup_hours": int,
    "backup_keep": int,
    "language": str,
    "sound": bool,
    "sound_volume": int,
    "motion": str,
    "cursor": bool,
}
_COOKIE_EXT = {"json": "json", "netscape": "txt"}


def strings_table() -> dict[str, str]:
    """The active language over English, as the page's dictionary."""
    return {**STRINGS["en"], **STRINGS[current_language()]}


def _error(message: object) -> dict:
    return {"error": str(message)}


def _geo_report(result: GeoCheckResult) -> dict:
    return {
        "exit_ip": result.exit_ip,
        "country": result.country,
        "timezone": result.timezone,
        "timezone_pinned": result.timezone_pinned,
        "locale": result.locale,
        "locale_pinned": result.locale_pinned,
        "suggested_locale": result.suggested_locale,
        "sources": [asdict(s) for s in result.sources],
        "warnings": [w.message for w in result.warnings],
        "error": result.error,
    }


class Bridge:
    def __init__(self, container: Container, on_unlocked: Callable[[], None]) -> None:
        self._c = container
        self._on_unlocked = on_unlocked
        self._opened = False
        self._open_lock = threading.Lock()
        self._rt = Runtime(on_change=self._changed)
        self._window: Any = None
        self._pump: Any = None
        # fingerprint.json path -> (mtime, label)
        self._devices: dict[str, tuple[float, str]] = {}
        if language := container.settings.current.language:
            set_language(language)

    # --- wiring (not exposed: private names) -------------------------------------

    def _attach(self, window: Any, pump: Any) -> None:
        self._window = window
        self._pump = pump

    def _changed(self) -> None:
        if self._pump is not None:
            self._pump.changed()

    def _log(self, message: str) -> None:
        logger.info(message)
        line = self._rt.add_log(message)
        if self._pump is not None:
            self._pump.log(line)

    def _open(self) -> None:
        """Profiles are readable: build the services and start the API (once)."""
        with self._open_lock:
            if self._opened:
                return
            c = self._c
            c.profile_manager  # noqa: B018 - builds it; raises while locked
            bl = c.browser_launcher
            self._rt.track(set(c.profile_manager.profiles), bl.running_profile_names())
            self._opened = True
        self._on_unlocked()
        if self._pump is not None:
            self._pump.start()
        camoufox_fetch.start(self._log)

    def _dialog(self, kind: int, **kwargs: Any) -> list[str]:
        if self._window is None:
            return []
        try:
            picked = self._window.create_file_dialog(kind, **kwargs)
        except Exception as e:
            logger.warning("File dialog failed: %s", e)
            return []
        if not picked:
            return []
        return [picked] if isinstance(picked, str) else list(picked)

    def _pick_open(self, types: tuple[str, ...], multiple: bool = False) -> list[str]:
        import webview

        return self._dialog(webview.FileDialog.OPEN, allow_multiple=multiple, file_types=types)

    def _pick_folder(self) -> str | None:
        import webview

        picked = self._dialog(webview.FileDialog.FOLDER)
        return picked[0] if picked else None

    def _pick_save(self, filename: str, types: tuple[str, ...]) -> str | None:
        import webview

        picked = self._dialog(webview.FileDialog.SAVE, save_filename=filename, file_types=types)
        return picked[0] if picked else None

    def _device(self, name: str) -> str:
        path = self._c.profile_data.path(name)
        if path is None:
            return ""
        fp = pathlib.Path(fingerprint.fingerprint_path(str(path)))
        try:
            mtime = fp.stat().st_mtime
        except OSError:
            mtime = -1.0
        cached = self._devices.get(str(fp))
        if cached and cached[0] == mtime:
            return cached[1]
        info = fingerprint.summary(str(path))
        label = ""
        if info:
            cpu = f"{info['hardware_concurrency']} CPU"
            label = f"{info['screen']} · {cpu}" if info.get("screen") else cpu
        self._devices[str(fp)] = (mtime, label)
        return label

    def _row(self, p: Profile, running: set[str]) -> dict:
        c = self._c
        data = c.profile_data
        last = p.last_launch or {}
        scheme, _, host = mask_proxy(p.proxy).partition("://")
        warm = c.warmup.running(p.name)
        encrypted = data.is_encrypted(p.name)
        return {
            "name": p.name,
            "os": p.os_type,
            "engine": p.engine,
            "proxy": host,
            "scheme": scheme,
            "wireguard": p.wireguard,
            "timezone": p.timezone,
            "locale": p.locale,
            "tags": p.tags,
            "notes": p.notes,
            "status": p.status,
            "temporary": p.temporary,
            "rotate": bool(p.proxy_rotate_url),
            "last": {"at": last.get("at"), "ip": last.get("ip"), "country": last.get("country")},
            "running": p.name in running,
            "loading": self._rt.is_loading(p.name),
            "failed": p.name in self._rt.failed,
            "since": self._rt.since(p.name),
            "warmup": {"done": warm["done"], "total": warm["total"]} if warm else None,
            "device": self._device(p.name),
            "encrypted": encrypted,
            # Encrypted and not open: its files cannot be read right now.
            "sealed": data.path(p.name) is None,
            "locked": data.needs_password(p.name),
        }

    def _validate_profile(self, form: dict) -> dict | None:
        checks = (
            ("name", validate_profile_name, form.get("name", "")),
            ("proxy", validate_proxy_format, form.get("proxy", "")),
            ("geo", validate_timezone, form.get("timezone", "")),
            ("geo", validate_locale, form.get("locale", "")),
            ("extra", validate_urls, form.get("start_urls", "")),
            ("extra", validate_http_url, form.get("proxy_rotate_url", "")),
        )
        for field, validate, value in checks:
            ok, message = validate(value)
            if not ok:
                return {"field": field, "error": message}
        return None

    # --- session ------------------------------------------------------------------

    def boot(self) -> dict:
        from ..api.app import VERSION

        return {
            "locked": self._c.security.locked,
            "language": current_language(),
            "strings": strings_table(),
            "settings": self.settings(),
            "version": VERSION,
            "platform": sys.platform,
        }

    def unlock(self, password: str) -> dict:
        if self._c.security.unlock(password) == "wrong":
            return _error(get_string("password_wrong"))
        # A self-destruct password wiped everything and opens an empty app: the
        # page cannot tell the two apart, which is the point.
        self._open()
        return {}

    def unlock_recovery(self, key: str) -> dict:
        if not self._c.security.unlock_with_recovery(key.strip()):
            return _error(get_string("recovery_wrong"))
        self._open()
        return {}

    def start(self) -> dict:
        """Called by the page when no master password is set."""
        if self._c.security.locked:
            return _error(get_string("password_wrong"))
        self._open()
        return {}

    def set_language(self, code: str) -> dict:
        if code not in STRINGS:
            return _error(code)
        set_language(code)
        self._c.settings.update(language=code)
        return {"language": code, "strings": strings_table()}

    # --- reading ------------------------------------------------------------------

    def snapshot(self) -> dict:
        c = self._c
        pm, bl = c.profile_manager, c.browser_launcher
        running = bl.running_profile_names()
        self._rt.track(set(pm.profiles), running)
        return {
            "profiles": [self._row(p, running) for p in pm.list_profiles()],
            "help": [r.public() for r in c.human_requests.pending()],
            "master": c.vault.enabled,
        }

    def log_history(self) -> list[dict]:
        return self._rt.log_lines()

    def profile_detail(self, name: str) -> dict | None:
        p = self._c.profile_manager.profiles.get(name)
        if p is None:
            return None
        return {
            "name": p.name,
            "proxy": p.proxy or "",
            "os": p.os_type,
            "engine": p.engine,
            "timezone": p.timezone or "",
            "locale": p.locale or "",
            "tags": ", ".join(p.tags),
            "notes": p.notes,
            "status": p.status,
            "start_urls": "\n".join(p.start_urls),
            "proxy_rotate_url": p.proxy_rotate_url or "",
            "extensions": p.extensions,
            "wireguard": p.wireguard,
            "running": self._c.browser_launcher.is_running(name),
        }

    def options(self) -> dict:
        """Choices for the forms: engines, statuses, installed extensions, limits."""
        return {
            "statuses": list(STATUSES),
            "extensions": extensions.available(),
            "max_bulk": bulk.MAX_BULK,
            "warmup_counts": list(WARMUP_COUNTS),
            "backup_hours": list(BACKUP_HOURS),
            "backup_keep": list(BACKUP_KEEP),
        }

    def activity(self, name: str) -> list[dict]:
        return list(reversed(self._c.activity.entries(name)))

    # --- profiles -----------------------------------------------------------------

    def profile_save(self, original: str | None, form: dict) -> dict | None:
        """Create (original is None) or edit a profile; None when saved."""
        form = {k: (v.strip() if isinstance(v, str) else v) for k, v in form.items()}
        if problem := self._validate_profile(form):
            return problem
        pm, bl = self._c.profile_manager, self._c.browser_launcher
        meta = {k: form.get(k, "") for k in META_FIELDS}
        meta["extensions"] = list(form.get("extensions") or [])
        name = form["name"]
        if original is None:
            engine = form.get("engine", "camoufox")
            if engine == "chrome" and (reason := chrome_prefetch.unsupported_reason()):
                return {
                    "field": "name",
                    "error": get_string("chrome_engine_unsupported", reason=reason),
                }
            if not pm.add_profile(
                name,
                form.get("proxy", ""),
                form.get("os_type", "windows"),
                form.get("timezone", ""),
                form.get("locale", ""),
                engine,
                **meta,
            ):
                return {"field": "name", "error": get_string("profile_exists")}
            self._log(get_string("created_profile", name=name))
            if engine == "chrome":
                chrome_prefetch.start(self._log)
        else:
            if name != original and bl.is_running(original):
                return {"field": "name", "error": get_string("stop_before_rename")}
            if not pm.update_profile(
                original,
                name,
                form.get("proxy", ""),
                form.get("os_type", "windows"),
                form.get("timezone", ""),
                form.get("locale", ""),
            ):
                return {"field": "name", "error": get_string("update_failed")}
            # Extensions that are not installed any more are kept as they were.
            installed = {e["id"] for e in extensions.available()}
            old = pm.profiles[name].extensions
            meta["extensions"] += [e for e in old if e not in installed]
            pm.set_meta(name, **meta)
            self._log(get_string("updated_profile", old=original, new=name))
        self._changed()
        return None

    def profile_delete(self, names: list[str]) -> dict:
        """Delete stopped profiles; a running one is never deleted (like the API)."""
        pm, bl = self._c.profile_manager, self._c.browser_launcher
        running = [n for n in names if bl.is_running(n)]
        if running:
            self._log(get_string("bulk_skip_running", count=len(running)))
        deleted = 0
        for name in names:
            if name not in running and pm.delete_profile(name):
                deleted += 1
                self._log(get_string("deleted_profile", name=name))
        self._changed()
        return {"deleted": deleted, "skipped": len(running)}

    def profile_clone(self, name: str, new_name: str) -> dict | None:
        new_name = new_name.strip()
        ok, message = validate_profile_name(new_name)
        if not ok:
            return _error(message)
        if not self._c.profile_manager.clone_profile(name, new_name):
            return _error(get_string("profile_exists"))
        self._log(get_string("cloned_profile", name=name, new=new_name))
        self._changed()
        return None

    def bulk_create(self, form: dict) -> dict:
        engine = form.get("engine", "camoufox")
        if engine == "chrome" and (reason := chrome_prefetch.unsupported_reason()):
            return _error(get_string("chrome_engine_unsupported", reason=reason))
        tz, loc = (form.get("timezone") or "").strip(), (form.get("locale") or "").strip()
        try:
            if form.get("mode") == "list":
                rows = bulk.parse_profile_list(form.get("text", ""))
            else:
                for validate, value in ((validate_timezone, tz), (validate_locale, loc)):
                    ok, message = validate(value)
                    if not ok:
                        return _error(message)
                try:
                    count, start = int(form.get("count") or 0), int(form.get("start") or 1)
                except (TypeError, ValueError):
                    return _error(get_string("bulk_count_range", max=bulk.MAX_BULK))
                names = bulk.expand_names(form.get("pattern", ""), count, start)
                proxies = bulk.assign_proxies(
                    len(names),
                    bulk.parse_lines(form.get("proxies", "")),
                    form.get("proxy_mode", "order"),
                )
                rows = [
                    {"name": n, "proxy": p, "tags": form.get("tags", ""), "notes": ""}
                    for n, p in zip(names, proxies, strict=True)
                ]
        except bulk.BulkError as e:
            return _error(e)
        if not rows:
            return _error(get_string("bulk_nothing"))
        pm = self._c.profile_manager
        created = skipped = 0
        pattern = form.get("mode") != "list"
        for row in rows:
            ok = pm.add_profile(
                row["name"],
                row["proxy"],
                form.get("os_type", "windows"),
                tz if pattern else None,
                loc if pattern else None,
                engine,
                tags=row["tags"],
                notes=row["notes"],
                status=form.get("status", "") if pattern else "",
            )
            created += ok
            skipped += not ok
        message = get_string("bulk_created", created=created, skipped=skipped)
        self._log(message)
        if created and engine == "chrome":
            chrome_prefetch.start(self._log)
        self._changed()
        return {"message": message, "created": created}

    def bulk_edit(self, names: list[str], form: dict) -> dict:
        pm = self._c.profile_manager
        profiles = [p for n in names if (p := pm.profiles.get(n))]
        if form.get("direct"):
            proxy_lines: list[str] | None = []
        else:
            proxy_lines = bulk.parse_lines(form.get("proxies", "")) or None
        if proxy_lines is not None:
            try:
                proxies = bulk.assign_proxies(
                    len(profiles), proxy_lines, form.get("proxy_mode", "order")
                )
            except bulk.BulkError as e:
                return _error(e)
            for p, proxy in zip(profiles, proxies, strict=True):
                pm.update_profile(p.name, p.name, proxy, p.os_type, p.timezone, p.locale)
        add = normalize_tags(form.get("add_tags", ""))
        remove = set(normalize_tags(form.get("remove_tags", "")))
        status = form.get("status")
        for p in profiles:
            meta: dict = {}
            if add or remove:
                meta["tags"] = [t for t in p.tags if t not in remove] + [
                    t for t in add if t not in p.tags
                ]
            if status is not None:
                meta["status"] = status
            if meta:
                pm.set_meta(p.name, **meta)
        message = get_string("bulk_edited", count=len(profiles))
        self._log(message)
        self._changed()
        return {"message": message}

    def import_profiles(self) -> dict:
        files = self._pick_open(("ZIP (*.zip)",), multiple=True)
        ok_count = 0
        for path in files:
            success, result = self._c.profile_manager.import_profile(path)
            if success:
                ok_count += 1
                self._log(get_string("import_success") + f": {result}")
            else:
                self._log(get_string("import_error", error=result))
        if ok_count:
            self._changed()
        return {"picked": len(files), "imported": ok_count}

    def export_profiles(self, names: list[str], include_data: bool) -> dict:
        folder = self._pick_folder()
        if not folder:
            return {"cancelled": True}
        done = 0
        for name in names:
            success, result = self._c.profile_manager.export_profile(name, folder, include_data)
            if success:
                done += 1
                self._log(get_string("export_success") + f": {result}")
            else:
                self._log(get_string("export_error", error=result))
        return {"exported": done, "folder": folder}

    # --- browsers -----------------------------------------------------------------

    def launch(self, name: str) -> dict:
        """Start or stop; a profile that needs its password says so first."""
        c = self._c
        bl = c.browser_launcher
        if not bl.is_running(name) and c.profile_data.needs_password(name):
            return {"needs_password": True}
        launch_or_stop(name, c.profile_manager, bl, self._rt, self._log)
        return {}

    def launch_many(self, names: list[str]) -> dict:
        c = self._c
        bl, data = c.browser_launcher, c.profile_data
        # A password prompt per profile would interrupt the whole batch.
        locked = [n for n in names if data.needs_password(n)]
        if locked:
            self._log(get_string("bulk_skip_locked", count=len(locked)))
        started = 0
        for name in names:
            if name in locked or bl.is_running(name) or self._rt.is_loading(name):
                continue
            launch_or_stop(name, c.profile_manager, bl, self._rt, self._log)
            started += 1
        return {"started": started, "skipped": len(locked)}

    def stop_many(self, names: list[str]) -> dict:
        bl = self._c.browser_launcher
        stopped = 0
        for name in names:
            if bl.is_running(name):
                launch_or_stop(name, self._c.profile_manager, bl, self._rt, self._log)
                stopped += 1
        return {"stopped": stopped}

    def warmup_info(self) -> dict:
        s = self._c.settings.current
        return {"count": s.warmup_count, "shared": len(s.warmup_sites)}

    def warmup(self, names: list[str], own: str, count: int) -> dict:
        """Launch each stopped profile with its own random sample of sites."""
        c = self._c
        lines = [line.strip() for line in (own or "").splitlines() if line.strip()]
        if bad := [line for line in lines if warmup.normalize(line) is None]:
            return _error(get_string("warmup_bad_site", site=bad[0][:80]))
        if not lines and not c.settings.current.warmup_sites:
            return _error(get_string("warmup_no_sites"))
        bl, data = c.browser_launcher, c.profile_data
        todo = []
        for name in names:
            if bl.is_running(name):
                self._log(get_string("warmup_skip_running", name=name))
            else:
                todo.append(name)
        if len(todo) > 1 and (locked := [n for n in todo if data.needs_password(n)]):
            self._log(get_string("bulk_skip_locked", count=len(locked)))
            todo = [n for n in todo if n not in locked]
        if len(todo) == 1 and data.needs_password(todo[0]):
            return {"needs_password": todo[0]}
        for name in todo:
            urls = c.warmup_sites(lines or None, int(count))
            if not urls:
                return _error(get_string("warmup_no_sites"))
            self._log(get_string("warmup_started", name=name, count=len(urls)))
            launch_or_stop(
                name,
                c.profile_manager,
                bl,
                self._rt,
                self._log,
                extra=warmup.options(urls),
            )
        return {"started": len(todo)}

    def rotate(self, name: str) -> dict:
        profile = self._c.profile_manager.profiles.get(name)
        if not profile or not profile.proxy_rotate_url:
            return _error(name)
        self._log(get_string("rotating_ip", name=name))
        ok, reply = rotate_ip(profile.proxy_rotate_url)
        message = get_string("rotate_ok" if ok else "rotate_failed", name=name, reply=reply)
        self._log(message)
        return {"message": message} if ok else _error(message)

    def show_browser(self, name: str) -> dict:
        try:
            self._c.browser_launcher.control(name, "bring_to_front", record=False)
        except Exception as e:
            message = get_string("help_show_failed", name=name, error=e)
            self._log(message)
            return _error(message)
        return {}

    def answer_help(self, request_id: str, done: bool) -> dict:
        human = self._c.human_requests
        request = human.get(request_id)
        if request is None:
            return {}
        human.answer(request_id, done)
        key = "help_answered_done" if done else "help_answered_declined"
        self._log(get_string(key, name=request.profile))
        if not human.pending() and self._window is not None:
            attention.release_window(self._window)
        self._changed()
        return {}

    # --- checks -------------------------------------------------------------------

    def check_proxy(self, proxy: str) -> dict:
        proxy = proxy.strip()
        if not proxy:
            return _error(get_string("enter_proxy_to_check"))
        ok, message = self._c.proxy_service.check_proxy_sync(proxy)
        return {"ok": ok, "message": message}

    def check_geo(self, proxy: str, timezone: str, locale: str) -> dict:
        proxy, timezone, locale = proxy.strip(), timezone.strip(), locale.strip()
        for validate, value in (
            (validate_proxy_format, proxy),
            (validate_timezone, timezone),
            (validate_locale, locale),
        ):
            ok, message = validate(value)
            if not ok:
                return _error(message)
        try:
            return _geo_report(check_geo(proxy or None, timezone or None, locale or None))
        except Exception as e:
            return _error(get_string("geo_check_failed", error=e))

    # --- cookies and fingerprint ----------------------------------------------------

    def _stopped_profile(self, name: str, stop_key: str) -> Profile | dict:
        profile = self._c.profile_manager.profiles.get(name)
        if profile is None:
            return _error(name)
        if self._c.browser_launcher.is_running(name):
            message = get_string(stop_key, name=name)
            self._log(message)
            return _error(message)
        return profile

    def cookies_info(self, name: str) -> dict:
        path = self._c.profile_data.path(name)
        if path is None:
            return {"fingerprint": get_string("encrypted_short")}
        info = fingerprint.summary(str(path))
        line = (
            get_string(
                "fingerprint_current",
                platform=info["platform"],
                screen=info["screen"],
                cores=info["hardware_concurrency"],
            )
            if info
            else get_string("fingerprint_none")
        )
        return {"fingerprint": line}

    def _cookie_work(self, profile: Profile, fn: Callable, arg: object) -> Any:
        bl = self._c.browser_launcher
        with bl.exclusive(profile.name) as path:
            return fn(profile.name, profile.os_type, arg, engine=profile.engine, profile_dir=path)

    def cookies_export(self, name: str, fmt: str) -> dict:
        profile = self._stopped_profile(name, "cookie_stop_first")
        if isinstance(profile, dict):
            return profile
        ext = _COOKIE_EXT.get(fmt, "json")
        path = self._pick_save(f"{name}_cookies.{ext}", (f"{ext.upper()} (*.{ext})",))
        if not path:
            return {"cancelled": True}
        self._log(get_string("cookie_working", name=name))
        try:
            text, count = self._cookie_work(profile, cookies.export_cookies, fmt)
            pathlib.Path(path).write_text(text, encoding="utf-8")
        except (cookies.CookieError, OSError, ProfileBusyError) as e:
            message = get_string("cookie_error", name=name, error=e)
            self._log(message)
            return _error(message)
        message = get_string("cookie_exported", name=name, count=count, path=path)
        self._log(message)
        return {"message": message}

    def cookies_import(self, name: str) -> dict:
        profile = self._stopped_profile(name, "cookie_stop_first")
        if isinstance(profile, dict):
            return profile
        files = self._pick_open(("Cookies (*.json *.txt)",))
        if not files:
            return {"cancelled": True}
        self._log(get_string("cookie_working", name=name))
        try:
            text = pathlib.Path(files[0]).read_text(encoding="utf-8-sig")
            count = self._cookie_work(profile, cookies.import_cookies, text)
        except (cookies.CookieError, OSError, UnicodeDecodeError, ProfileBusyError) as e:
            message = get_string("cookie_error", name=name, error=e)
            self._log(message)
            return _error(message)
        message = get_string("cookie_imported", name=name, count=count)
        self._log(message)
        return {"message": message}

    def fingerprint_reset(self, name: str) -> dict:
        profile = self._stopped_profile(name, "cookie_stop_first")
        if isinstance(profile, dict):
            return profile
        try:
            with self._c.browser_launcher.exclusive(name) as path:
                fingerprint.reset(path or os.path.join(DATA_DIR, name))
        except ProfileBusyError as e:
            message = get_string("cookie_error", name=name, error=e)
            self._log(message)
            return _error(message)
        message = get_string("fingerprint_was_reset", name=name)
        self._log(message)
        self._changed()
        return {"message": message}

    # --- WireGuard ----------------------------------------------------------------

    def wireguard_load(self) -> dict:
        files = self._pick_open(("WireGuard (*.conf *.txt)",))
        if not files:
            return {"cancelled": True}
        path = pathlib.Path(files[0])
        try:
            if path.stat().st_size > wireguard.MAX_CONF_BYTES:
                raise wireguard.WireGuardError(get_string("wireguard_too_big"))
            return {"text": path.read_text(encoding="utf-8-sig")}
        except (OSError, UnicodeDecodeError, wireguard.WireGuardError) as e:
            return _error(get_string("wireguard_error", error=e))

    def wireguard_check(self, name: str, text: str) -> dict:
        profile = self._c.profile_manager.profiles.get(name)
        if profile is None:
            return _error(name)
        text = text.strip()
        try:
            if text:
                wireguard.parse(text)
        except wireguard.WireGuardError as e:
            return _error(get_string("wireguard_error", error=e))
        if not text and not profile.wireguard:
            return _error(get_string("wireguard_none"))
        bl = self._c.browser_launcher
        try:
            source = wireguard.tunnel(text, self._log) if text else bl.wireguard_proxy(name)
            with source as proxy:
                return _geo_report(check_geo(proxy, profile.timezone, profile.locale))
        except Exception as e:
            return _error(get_string("geo_check_failed", error=e))

    def wireguard_save(self, name: str, text: str | None) -> dict:
        profile = self._stopped_profile(name, "wireguard_stop_first")
        if isinstance(profile, dict):
            return profile
        if text is not None:
            text = text.strip()
            if not text:
                return {}
            try:
                wireguard.parse(text)
            except wireguard.WireGuardError as e:
                return _error(get_string("wireguard_error", error=e))
        c = self._c
        try:
            endpoint = wireguard.configure(
                c.browser_launcher, c.profile_manager, name, text, self._log
            )
        except Exception as e:
            message = get_string("wireguard_error", error=e)
            self._log(message)
            return _error(message)
        key = "wireguard_saved" if endpoint else "wireguard_removed"
        message = get_string(key, name=name, endpoint=endpoint or "")
        self._log(message)
        self._changed()
        return {"message": message}

    # --- encryption -----------------------------------------------------------------

    def encryption_info(self, name: str) -> dict:
        data = self._c.profile_data
        return {
            "encrypted": data.is_encrypted(name),
            "key_by": data.key_by(name) if data.is_encrypted(name) else [],
            "needs_password": data.needs_password(name),
            "master": self._c.vault.enabled,
            "ram": work_in_ram(),
            "running": self._c.browser_launcher.is_running(name),
        }

    def profile_unlock(self, name: str, password: str) -> dict:
        if not self._c.profile_data.unlock(name, password):
            return _error(get_string("password_wrong"))
        self._changed()
        return {}

    def _security_work(self, name: str, work: Callable[[], None], done_key: str) -> dict:
        if self._c.browser_launcher.is_running(name):
            return _error(get_string("encryption_stop_first", name=name))
        try:
            work()
        except Exception as e:
            message = get_string("security_error", error=e)
            self._log(message)
            return _error(message)
        finally:
            self._changed()
        message = get_string(done_key, name=name)
        self._log(message)
        return {"message": message}

    def encrypt(self, name: str, password: str) -> dict:
        if not password and not self._c.vault.enabled:
            return _error(get_string("password_required"))
        self._log(get_string("encrypting", name=name))
        data = self._c.profile_data
        return self._security_work(
            name, lambda: data.encrypt(name, password or None), "encrypted_done"
        )

    def decrypt(self, name: str) -> dict:
        self._log(get_string("decrypting", name=name))
        data = self._c.profile_data
        return self._security_work(name, lambda: data.decrypt(name), "decrypted_done")

    def set_profile_password(self, name: str, password: str) -> dict:
        if not password and not self._c.vault.enabled:
            return _error(get_string("password_required"))
        data = self._c.profile_data
        return self._security_work(
            name, lambda: data.set_password(name, password or None), "profile_password_changed"
        )

    # --- master password and self-destruct ---------------------------------------------

    def security_info(self) -> dict:
        vault = self._c.vault
        return {"master": vault.enabled, "duress": vault.enabled and vault.has_duress}

    def enable_master(self, password: str) -> dict:
        try:
            key = self._c.security.enable_master(password)
        except (VaultError, ProfileDataError) as e:
            return _error(e)
        self._log(get_string("master_enabled"))
        self._changed()
        return {"key": key}

    def change_master(self, password: str) -> dict:
        try:
            self._c.security.change_master(password)
        except VaultError as e:
            return _error(e)
        self._log(get_string("master_changed"))
        return {}

    def new_recovery_key(self) -> dict:
        return {"key": self._c.vault.new_recovery_key()}

    def disable_master(self) -> dict:
        try:
            self._c.security.disable_master()
        except (VaultError, ProfileDataError) as e:
            message = get_string("security_error", error=e)
            self._log(message)
            return _error(message)
        self._log(get_string("master_disabled"))
        self._changed()
        return {}

    def set_duress(self, password: str | None) -> dict:
        try:
            self._c.security.set_duress(password or None)
        except VaultError as e:
            return _error(e)
        self._log(get_string("duress_set" if password else "duress_cleared"))
        return {}

    # --- settings -------------------------------------------------------------------

    def settings(self) -> dict:
        s = asdict(self._c.settings.current)
        s["language"] = s["language"] or current_language()
        return s

    def settings_update(self, changes: dict) -> dict:
        clean: dict[str, Any] = {}
        for key, value in changes.items():
            kind = _UI_SETTINGS.get(key)
            if (
                kind is None
                or not isinstance(value, kind)
                or (kind is int and isinstance(value, bool))
            ):
                return _error(key)
            clean[key] = value
        if "warmup_sites" in clean:
            clean["warmup_sites"] = [
                s.strip()
                for s in clean["warmup_sites"]
                if isinstance(s, str) and warmup.normalize(s.strip())
            ]
        if "motion" in clean and clean["motion"] not in MOTIONS:
            return _error("motion")
        if "sound_volume" in clean:
            clean["sound_volume"] = max(0, min(100, clean["sound_volume"]))
        if "language" in clean:
            if clean["language"] not in STRINGS:
                return _error("language")
            set_language(clean["language"])
        before = self._c.settings.current.geo_guard
        self._c.settings.update(**clean)
        if "geo_guard" in clean and clean["geo_guard"] != before:
            self._log(get_string("geo_guard_on" if clean["geo_guard"] else "geo_guard_off"))
        if "warmup_sites" in clean:
            self._log(get_string("warmup_sites_saved", count=len(clean["warmup_sites"])))
        return self.settings()

    def extension_add(self, folder: bool) -> dict:
        if folder:
            source = self._pick_folder()
        else:
            picked = self._pick_open(("Extensions (*.xpi *.zip *.crx)",))
            source = picked[0] if picked else None
        if not source:
            return {"cancelled": True}
        try:
            ext_id = extensions.install(source)
        except extensions.ExtensionError as e:
            message = get_string("extension_failed", error=e)
            self._log(message)
            return _error(message)
        message = get_string("extension_added", name=ext_id)
        self._log(message)
        return {"message": message}

    def extension_remove(self, ext_id: str) -> dict:
        extensions.remove(ext_id)
        message = get_string("extension_removed", name=ext_id)
        self._log(message)
        return {"message": message}

    def backup_dir(self) -> dict:
        folder = self._pick_folder()
        if not folder:
            return {"cancelled": True}
        self._c.settings.update(backup_dir=folder)
        return self.settings()

    def backup_now(self) -> dict:
        self._log(get_string("backup_running"))
        try:
            path = self._c.backups.run_now()
        except Exception as e:
            message = get_string("backup_failed", error=e)
            self._log(message)
            return _error(message)
        message = get_string("backup_done", path=path)
        self._log(message)
        return {"message": message}

    # --- agents (MCP) ---------------------------------------------------------------

    def mcp_info(self, real_token: bool) -> dict:
        token = None
        if API_TOKEN:
            token = API_TOKEN if real_token else mcp_setup.TOKEN_PLACEHOLDER
        configs = mcp_setup.build_configs(MCP_URL, token, local=True, api_url=API_URL)
        return {
            "url": MCP_URL,
            "has_token": bool(API_TOKEN),
            "configs": mcp_setup.as_dicts(configs),
        }

    def mcp_health(self) -> dict:
        try:
            with urllib.request.urlopen(f"{API_URL}/api/v1/health", timeout=3):
                return {"ok": True}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    # --- misc -----------------------------------------------------------------------

    def open_external(self, url: str) -> dict:
        if not url.startswith(("https://", "http://")):
            return _error(url)
        with contextlib.suppress(Exception):
            webbrowser.open(url)
        return {}
