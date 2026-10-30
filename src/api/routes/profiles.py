from __future__ import annotations

import os
import pathlib
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ...core.config import DATA_DIR
from ...core.logging import get_logger
from ...models.profile import ENGINES, META_FIELDS, STATUSES
from ...services.browser import chrome_prefetch, cookies, extensions, fingerprint, wireguard
from ...services.browser.launcher import ProfileBusyError
from ...services.profile import bulk
from ...services.proxy.geo_check import check_geo
from ...services.proxy.rotate import rotate_ip
from ...services.security.profile_data import ProfileLocked
from ...utils.validation import (
    MAX_NOTES_LENGTH,
    validate_http_url,
    validate_locale,
    validate_profile_name,
    validate_proxy_format,
    validate_timezone,
    validate_urls,
)
from ..dependencies import get_browser_launcher, get_event_bus, get_profile_manager
from ..helpers import build_profile_response, data_dir, profile_response, require_profile
from ..schemas.common import ErrorResponse, SuccessResponse
from ..schemas.profiles import (
    BulkCreateRequest,
    BulkCreateResponse,
    CloneRequest,
    CookieImportRequest,
    CookieImportResponse,
    DataDirResponse,
    ExportRequest,
    ExportResponse,
    FingerprintResponse,
    ImportListRequest,
    ImportRequest,
    ImportResponse,
    ProfileCreate,
    ProfileListResponse,
    ProfileResponse,
    ProfileUpdate,
    RotateResponse,
    SetProxiesRequest,
    SetProxiesResponse,
    WireGuardRequest,
)
from ..schemas.proxy import GeoCheckResponse

if TYPE_CHECKING:
    from ...core.events import EventBus
    from ...interfaces import IBrowserLauncher, IProfileManager

logger = get_logger("api.profiles")

router = APIRouter(prefix="/profiles", tags=["profiles"])

_OS_TYPES = ("windows", "macos", "linux")


def _require_os(os_type: str) -> None:
    if os_type not in _OS_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"os_type must be one of: {', '.join(_OS_TYPES)}",
        )


def _require_engine(engine: str) -> None:
    if engine not in ENGINES:
        raise HTTPException(
            status_code=400,
            detail=f"engine must be one of: {', '.join(ENGINES)}",
        )
    if engine == "chrome" and (reason := chrome_prefetch.unsupported_reason()):
        raise HTTPException(status_code=400, detail=f"Chrome engine unavailable here: {reason}")


def _require_geo(timezone: str | None, locale: str | None) -> None:
    for validate, value in ((validate_timezone, timezone), (validate_locale, locale)):
        valid, msg = validate(value or "")
        if not valid:
            raise HTTPException(status_code=400, detail=msg)


def _require_meta(meta: dict, engine: str | None = None) -> None:
    """400 unless the supplied organisation fields are usable (extensions for `engine`)."""
    if meta.get("status") not in (None, *STATUSES):
        raise HTTPException(
            status_code=400, detail=f"status must be one of: {', '.join(s for s in STATUSES if s)}"
        )
    if len(meta.get("notes") or "") > MAX_NOTES_LENGTH:
        raise HTTPException(status_code=400, detail=f"notes: at most {MAX_NOTES_LENGTH} characters")
    checks = (
        (validate_urls, meta.get("start_urls") or []),
        (validate_http_url, meta.get("proxy_rotate_url") or ""),
    )
    for validate, value in checks:
        valid, msg = validate(value)
        if not valid:
            raise HTTPException(status_code=400, detail=msg)
    installed = {e["id"]: e["engine"] for e in extensions.available()}
    unknown = set(meta.get("extensions") or []) - set(installed)
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"extensions not installed: {', '.join(sorted(unknown))}"
        )
    other = sorted(e for e in meta.get("extensions") or [] if engine and installed[e] != engine)
    if other:
        raise HTTPException(
            status_code=400, detail=f"extensions not made for {engine}: {', '.join(other)}"
        )


def _bulk_error(e: bulk.BulkError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=ProfileListResponse)
def list_profiles(
    tag: str | None = Query(None, description="Only profiles with this tag"),
    status: str | None = Query(None, description="Only profiles with this status"),
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> ProfileListResponse:
    found = pm.list_profiles()
    if tag:
        found = [p for p in found if tag.strip().lower() in p.tags]
    if status is not None:
        found = [p for p in found if p.status == status]
    profiles = [profile_response(p, bl) for p in found]
    return ProfileListResponse(profiles=profiles, total=len(profiles))


@router.post(
    "/bulk",
    response_model=BulkCreateResponse,
    status_code=201,
    responses={400: {"model": ErrorResponse}},
)
def create_profiles_bulk(
    body: BulkCreateRequest,
    pm: IProfileManager = Depends(get_profile_manager),
    bus: EventBus = Depends(get_event_bus),
) -> BulkCreateResponse:
    """Create `count` profiles named from `pattern`, proxies taken from the pool."""
    _require_os(body.os_type)
    _require_engine(body.engine)
    _require_geo(body.timezone, body.locale)
    meta = {"tags": body.tags, "status": body.status, "start_urls": body.start_urls}
    _require_meta(meta)
    try:
        names = bulk.expand_names(body.pattern, body.count, body.start)
        proxies = bulk.assign_proxies(len(names), body.proxies, body.proxy_mode)
    except bulk.BulkError as e:
        raise _bulk_error(e) from e
    created, skipped = [], []
    for name, proxy in zip(names, proxies, strict=True):
        ok = pm.add_profile(
            name, proxy, body.os_type, body.timezone, body.locale, body.engine, **meta
        )
        (created if ok else skipped).append(name)
    logger.info("API bulk-created %d profiles (%d skipped)", len(created), len(skipped))
    if created and body.engine == "chrome":
        chrome_prefetch.start()
    bus.emit()
    return BulkCreateResponse(created=created, skipped=skipped)


@router.post(
    "/import-list",
    response_model=BulkCreateResponse,
    status_code=201,
    responses={400: {"model": ErrorResponse}},
)
def import_profile_list(
    body: ImportListRequest,
    pm: IProfileManager = Depends(get_profile_manager),
    bus: EventBus = Depends(get_event_bus),
) -> BulkCreateResponse:
    """Create profiles from lines of name;proxy;tags;notes (moving from another tool)."""
    _require_os(body.os_type)
    _require_engine(body.engine)
    try:
        rows = bulk.parse_profile_list(body.text)
    except bulk.BulkError as e:
        raise _bulk_error(e) from e
    created, skipped = [], []
    for row in rows:
        ok = pm.add_profile(
            row["name"],
            row["proxy"],
            body.os_type,
            engine=body.engine,
            tags=row["tags"],
            notes=row["notes"],
        )
        (created if ok else skipped).append(row["name"])
    if created and body.engine == "chrome":
        chrome_prefetch.start()
    bus.emit()
    return BulkCreateResponse(created=created, skipped=skipped)


@router.post(
    "/proxies",
    response_model=SetProxiesResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def set_proxies(
    body: SetProxiesRequest,
    pm: IProfileManager = Depends(get_profile_manager),
    bus: EventBus = Depends(get_event_bus),
) -> SetProxiesResponse:
    """Give several profiles new proxies; running browsers pick them up on their next launch."""
    profiles = [require_profile(name, pm) for name in body.names]
    try:
        proxies = bulk.assign_proxies(len(profiles), body.proxies, body.proxy_mode)
    except bulk.BulkError as e:
        raise _bulk_error(e) from e
    updated = []
    for profile, proxy in zip(profiles, proxies, strict=True):
        if pm.update_profile(
            profile.name, profile.name, proxy, profile.os_type, profile.timezone, profile.locale
        ):
            updated.append(profile.name)
    bus.emit()
    return SetProxiesResponse(updated=updated)


@router.post(
    "",
    response_model=ProfileResponse,
    status_code=201,
    responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def create_profile(
    body: ProfileCreate,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    bus: EventBus = Depends(get_event_bus),
) -> ProfileResponse:
    valid, msg = validate_profile_name(body.name)
    if not valid:
        raise HTTPException(status_code=400, detail=msg)
    _require_os(body.os_type)
    _require_engine(body.engine)
    _require_geo(body.timezone, body.locale)
    meta = body.model_dump(include=set(META_FIELDS))
    _require_meta(meta, body.engine)

    if body.proxy:
        valid, msg = validate_proxy_format(body.proxy)
        if not valid:
            raise HTTPException(status_code=400, detail=msg)

    if not pm.add_profile(
        body.name,
        body.proxy or "",
        body.os_type,
        body.timezone or None,
        body.locale or None,
        body.engine,
        **meta,
    ):
        raise HTTPException(status_code=409, detail="Profile already exists")

    logger.info("API created profile: %s", body.name)
    if body.engine == "chrome":
        chrome_prefetch.start()
    bus.emit()
    return build_profile_response(body.name, pm, bl)


@router.get(
    "/{name}",
    response_model=ProfileResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_profile(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> ProfileResponse:
    require_profile(name, pm)
    return build_profile_response(name, pm, bl)


@router.patch(
    "/{name}",
    response_model=ProfileResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def update_profile(
    name: str,
    body: ProfileUpdate,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    bus: EventBus = Depends(get_event_bus),
) -> ProfileResponse:
    profile = require_profile(name, pm)
    supplied = body.model_dump(exclude_unset=True)

    new_name = supplied.get("name", name)
    new_proxy = supplied.get("proxy", profile.proxy)
    new_os = supplied.get("os_type", profile.os_type)
    new_timezone = supplied.get("timezone", profile.timezone)
    new_locale = supplied.get("locale", profile.locale)

    if "name" in supplied:
        valid, msg = validate_profile_name(new_name)
        if not valid:
            raise HTTPException(status_code=400, detail=msg)
        if new_name != name and bl.is_running(name):
            raise HTTPException(
                status_code=409,
                detail="Stop the browser before renaming",
            )

    if supplied.get("engine") not in (None, profile.engine):
        raise HTTPException(
            status_code=400,
            detail="A profile's engine cannot be changed; create a new profile instead",
        )
    if "os_type" in supplied:
        _require_os(new_os)
    _require_geo(supplied.get("timezone"), supplied.get("locale"))

    if "proxy" in supplied and new_proxy:
        valid, msg = validate_proxy_format(new_proxy)
        if not valid:
            raise HTTPException(status_code=400, detail=msg)
    meta = {k: v for k, v in supplied.items() if k in META_FIELDS}
    _require_meta(meta, profile.engine)

    if not pm.update_profile(
        name, new_name, new_proxy or "", new_os, new_timezone or None, new_locale or None
    ):
        raise HTTPException(status_code=409, detail="Update failed (name conflict?)")
    if meta:
        pm.set_meta(new_name, **meta)

    logger.info("API updated profile: %s -> %s", name, new_name)
    bus.emit()
    return build_profile_response(new_name, pm, bl)


@router.post(
    "/{name}/clone",
    response_model=ProfileResponse,
    status_code=201,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def clone_profile(
    name: str,
    body: CloneRequest,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    bus: EventBus = Depends(get_event_bus),
) -> ProfileResponse:
    """A new profile with the same settings, no cookies and a new fingerprint."""
    require_profile(name, pm)
    valid, msg = validate_profile_name(body.name)
    if not valid:
        raise HTTPException(status_code=400, detail=msg)
    if not pm.clone_profile(name, body.name):
        raise HTTPException(status_code=409, detail="Profile already exists")
    bus.emit()
    return build_profile_response(body.name, pm, bl)


@router.post(
    "/{name}/rotate-ip",
    response_model=RotateResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def rotate_profile_ip(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
) -> RotateResponse:
    """Call the profile's mobile-proxy rotate link now."""
    profile = require_profile(name, pm)
    if not profile.proxy_rotate_url:
        raise HTTPException(status_code=400, detail="Profile has no rotate link")
    ok, message = rotate_ip(profile.proxy_rotate_url)
    return RotateResponse(success=ok, message=message)


@router.delete(
    "/{name}",
    response_model=SuccessResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def delete_profile(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    bus: EventBus = Depends(get_event_bus),
) -> SuccessResponse:
    require_profile(name, pm)
    if bl.is_running(name):
        raise HTTPException(
            status_code=409,
            detail="Stop the browser before deleting",
        )
    pm.delete_profile(name)
    logger.info("API deleted profile: %s", name)
    bus.emit()
    return SuccessResponse(message=f"Profile '{name}' deleted")


@router.get(
    "/{name}/data-dir",
    response_model=DataDirResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_data_dir(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> DataDirResponse:
    require_profile(name, pm)
    path = data_dir(name, bl)
    return DataDirResponse(name=name, data_dir=path, exists=pathlib.Path(path).exists())


@router.post(
    "/{name}/export",
    response_model=ExportResponse,
    responses={404: {"model": ErrorResponse}},
)
def export_profile(
    name: str,
    body: ExportRequest,
    pm: IProfileManager = Depends(get_profile_manager),
) -> ExportResponse:
    require_profile(name, pm)
    if not pathlib.Path(body.export_dir).is_dir():
        raise HTTPException(status_code=400, detail="export_dir is not a directory")

    success, result = pm.export_profile(name, body.export_dir, body.include_data)
    if success:
        logger.info("API exported profile: %s -> %s", name, result)
        return ExportResponse(success=True, zip_path=result)
    return ExportResponse(success=False, error=result)


@router.post(
    "/import",
    response_model=ImportResponse,
    responses={400: {"model": ErrorResponse}},
)
def import_profile(
    body: ImportRequest,
    pm: IProfileManager = Depends(get_profile_manager),
    bus: EventBus = Depends(get_event_bus),
) -> ImportResponse:
    if not pathlib.Path(body.zip_path).is_file():
        raise HTTPException(status_code=400, detail="zip_path is not a file")

    success, result = pm.import_profile(body.zip_path, body.overwrite)
    if success:
        logger.info("API imported profile: %s", result)
        bus.emit()
        return ImportResponse(success=True, profile_name=result)
    return ImportResponse(success=False, error=result)


def _require_stopped(name: str, bl: IBrowserLauncher, action: str) -> None:
    if bl.is_running(name):
        raise HTTPException(status_code=409, detail=f"Stop the browser before {action}")


_BUSY_DETAIL = "Profile is running or busy with another operation"


def _locked() -> HTTPException:
    return HTTPException(
        status_code=423, detail="Profile is encrypted with a password: enter it in the CloutFox app"
    )


@router.get(
    "/{name}/cookies",
    response_class=PlainTextResponse,
    responses={
        200: {"content": {"text/plain": {}, "application/json": {}}},
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def export_cookies(
    name: str,
    format: str = Query("json", pattern="^(json|netscape)$"),
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> PlainTextResponse:
    """Export cookies as Cookie-Editor JSON or Netscape cookies.txt."""
    profile = require_profile(name, pm)
    _require_stopped(name, bl, "exporting cookies")
    try:
        with bl.exclusive(name) as path:
            text, count = cookies.export_cookies(
                name, profile.os_type, format, profile.engine, profile_dir=path
            )
    except ProfileBusyError as e:
        raise HTTPException(status_code=409, detail=_BUSY_DETAIL) from e
    except ProfileLocked as e:
        raise _locked() from e
    except cookies.CookieError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    media = "application/json" if format == "json" else "text/plain"
    return PlainTextResponse(text, media_type=media, headers={"X-Cookie-Count": str(count)})


@router.post(
    "/{name}/cookies",
    response_model=CookieImportResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def import_cookies(
    name: str,
    body: CookieImportRequest,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> CookieImportResponse:
    """Import cookies from JSON or Netscape text into a stopped profile."""
    profile = require_profile(name, pm)
    _require_stopped(name, bl, "importing cookies")
    try:
        with bl.exclusive(name) as path:
            count = cookies.import_cookies(
                name, profile.os_type, body.content, profile.engine, profile_dir=path
            )
    except ProfileBusyError as e:
        raise HTTPException(status_code=409, detail=_BUSY_DETAIL) from e
    except ProfileLocked as e:
        raise _locked() from e
    except cookies.CookieError as e:
        return CookieImportResponse(success=False, error=str(e))
    logger.info("API imported %d cookies into %s", count, name)
    return CookieImportResponse(success=True, imported=count)


@router.get(
    "/{name}/fingerprint",
    response_model=FingerprintResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_fingerprint(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> FingerprintResponse:
    """Show the fingerprint the profile presents on every launch."""
    require_profile(name, pm)
    path = data_dir(name, bl)
    info = fingerprint.summary(path)
    if info is None and getattr(bl, "data", None) is not None and bl.data.is_encrypted(name):
        try:
            with bl.exclusive(name) as path:
                info = fingerprint.summary(path)
        except ProfileBusyError:
            info = None
        except ProfileLocked as e:
            raise _locked() from e
    if info is None:
        return FingerprintResponse(name=name, exists=False)
    return FingerprintResponse(name=name, exists=True, **info)


@router.delete(
    "/{name}/fingerprint",
    response_model=SuccessResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def reset_fingerprint(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> SuccessResponse:
    """Discard the saved fingerprint; the next launch generates a new device."""
    require_profile(name, pm)
    _require_stopped(name, bl, "resetting the fingerprint")
    try:
        with bl.exclusive(name) as path:
            removed = fingerprint.reset(path or os.path.join(DATA_DIR, name))
    except ProfileBusyError as e:
        raise HTTPException(status_code=409, detail=_BUSY_DETAIL) from e
    except ProfileLocked as e:
        raise _locked() from e
    logger.info("API reset fingerprint for %s (existed=%s)", name, removed)
    return SuccessResponse(message=f"Fingerprint reset for '{name}'")


@router.get(
    "/{name}/ip-check",
    response_model=GeoCheckResponse,
    responses={404: {"model": ErrorResponse}},
)
def check_profile_ip(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> GeoCheckResponse:
    """Where GeoIP sources place the profile's exit IP vs. the timezone/locale it presents.

    Goes out through the profile's proxy (or its WireGuard tunnel) to Cloudflare, ipinfo
    and ip-api (~10s).
    """
    profile = require_profile(name, pm)
    if not profile.wireguard:
        result = check_geo(profile.proxy, profile.timezone, profile.locale)
        return GeoCheckResponse.from_result(result)
    try:
        with bl.wireguard_proxy(name) as proxy:
            result = check_geo(proxy, profile.timezone, profile.locale)
    except ProfileBusyError as e:
        raise HTTPException(status_code=409, detail=_BUSY_DETAIL) from e
    except ProfileLocked as e:
        raise _locked() from e
    except wireguard.WireGuardError as e:
        raise HTTPException(status_code=502, detail=f"WireGuard: {e}") from e
    return GeoCheckResponse.from_result(result)


@router.put(
    "/{name}/wireguard",
    response_model=ProfileResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def set_wireguard(
    name: str,
    body: WireGuardRequest,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    bus: EventBus = Depends(get_event_bus),
) -> ProfileResponse:
    """Give a stopped profile a WireGuard tunnel; it replaces the proxy from the next launch.

    The config is kept in the profile's data folder and never returned.
    """
    return _configure_wireguard(name, body.config, pm, bl, bus)


@router.delete(
    "/{name}/wireguard",
    response_model=ProfileResponse,
    responses={404: {"model": ErrorResponse}},
)
def remove_wireguard(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    bus: EventBus = Depends(get_event_bus),
) -> ProfileResponse:
    """Remove a stopped profile's WireGuard tunnel; its proxy applies again."""
    return _configure_wireguard(name, None, pm, bl, bus)


def _configure_wireguard(
    name: str, text: str | None, pm: IProfileManager, bl: IBrowserLauncher, bus: EventBus
) -> ProfileResponse:
    require_profile(name, pm)
    _require_stopped(name, bl, "changing its WireGuard tunnel")
    try:
        wireguard.configure(bl, pm, name, text)
    except wireguard.WireGuardError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ProfileBusyError as e:
        raise HTTPException(status_code=409, detail=_BUSY_DETAIL) from e
    except ProfileLocked as e:
        raise _locked() from e
    logger.info("API %s WireGuard for %s", "set" if text else "removed", name)
    bus.emit()
    return build_profile_response(name, pm, bl)
