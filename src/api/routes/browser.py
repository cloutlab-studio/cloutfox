from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from ...core.config import HEADLESS, LAUNCH_WAIT_TIMEOUT
from ...core.logging import get_logger
from ...models.profile import ENGINES
from ...services.browser.control import PageController
from ...services.browser.launcher import BrowserControlError, ProfileBusyError
from ...services.security.profile_data import ProfileLocked
from ...utils.validation import (
    validate_locale,
    validate_proxy_format,
    validate_timezone,
    validate_urls,
)
from ..dependencies import (
    get_activity,
    get_browser_launcher,
    get_container,
    get_event_bus,
    get_human_requests,
    get_profile_manager,
)
from ..helpers import require_profile
from ..schemas.browser import (
    ActivityResponse,
    BroadcastRequest,
    BroadcastResponse,
    BrowserStatusResponse,
    HumanRequestBody,
    HumanRequestResponse,
    LaunchResponse,
    RunningBrowsersResponse,
    TempLaunchRequest,
    TempLaunchResponse,
    WarmupRequest,
    WarmupStatusResponse,
)
from ..schemas.common import ErrorResponse, SuccessResponse

if TYPE_CHECKING:
    from ...core.container import Container
    from ...core.events import EventBus
    from ...interfaces import IBrowserLauncher, IProfileManager

logger = get_logger("api.browser")

router = APIRouter(prefix="/browser", tags=["browser"])


def _api_log(msg: str) -> None:
    logger.info("[browser] %s", msg)


@router.get("", response_model=RunningBrowsersResponse)
def list_running(
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> RunningBrowsersResponse:
    names = sorted(bl.running_profile_names())
    return RunningBrowsersResponse(running=names, count=len(names))


@router.get(
    "/{name}/status",
    response_model=BrowserStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
def browser_status(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> BrowserStatusResponse:
    require_profile(name, pm)
    return BrowserStatusResponse(name=name, is_running=bl.is_running(name))


@router.post(
    "/{name}/launch",
    response_model=LaunchResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        502: {"model": LaunchResponse},
    },
)
def launch_browser(
    name: str,
    response: Response,
    wait: bool = Query(
        True,
        description=(
            "If true (default), block until the browser is ready or has failed, "
            f"up to {LAUNCH_WAIT_TIMEOUT}s (CLOUTFOX_LAUNCH_TIMEOUT). "
            "Pass wait=false to return 202 immediately and poll GET /{name}/status."
        ),
    ),
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    bus: EventBus = Depends(get_event_bus),
) -> LaunchResponse:
    profile = require_profile(name, pm)
    if bl.is_running(name):
        raise HTTPException(status_code=409, detail="Browser already running")
    return _launch(profile, response, wait, bl, bus)


def _launch(
    profile, response: Response, wait: bool, bl, bus, extra: dict | None = None
) -> LaunchResponse:
    """Start the browser and, with `wait`, report how the launch went."""
    name = profile.name

    def _on_ready() -> None:
        bus.emit()

    def _on_stop() -> None:
        bus.emit()

    try:
        started = bl.start_thread(
            profile, _api_log, on_ready=_on_ready, on_stop=_on_stop, extra=extra
        )
    except ProfileBusyError as e:
        raise HTTPException(status_code=409, detail="Profile is busy") from e
    except ProfileLocked as e:
        raise HTTPException(
            status_code=423,
            detail="Profile is encrypted with a password: enter it in the CloutFox app",
        ) from e
    if not started:
        raise HTTPException(status_code=409, detail="Browser already running")
    logger.info("API launched browser for: %s", name)
    bus.emit()

    if not wait:
        response.status_code = 202
        return LaunchResponse(success=True, message=f"Browser launching for '{name}'")

    ok, error = bl.wait_for_launch(name, LAUNCH_WAIT_TIMEOUT)
    if ok:
        return LaunchResponse(success=True, message=f"Browser started for '{name}'")
    if error == "timeout":
        response.status_code = 202
        return LaunchResponse(
            success=True,
            message=f"Browser for '{name}' is still starting",
        )
    response.status_code = 502
    return LaunchResponse(success=False, message=f"Launch failed: {error}")


@router.post(
    "/{name}/stop",
    response_model=SuccessResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def stop_browser(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    bus: EventBus = Depends(get_event_bus),
) -> SuccessResponse:
    require_profile(name, pm)
    if not bl.is_running(name):
        raise HTTPException(status_code=409, detail="Browser is not running")

    bl.stop_profile(name)
    logger.info("API stopped browser for: %s", name)
    bus.emit()
    return SuccessResponse(message=f"Browser stopped for '{name}'")


_WAIT = Query(True, description="Block until the browser is ready or has failed")


@router.post(
    "/{name}/warmup",
    response_model=LaunchResponse,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        502: {"model": LaunchResponse},
    },
)
def warm_up(
    name: str,
    body: WarmupRequest,
    response: Response,
    wait: bool = Query(True, description="Block until the browser is up, as for /launch"),
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    bus: EventBus = Depends(get_event_bus),
    container: Container = Depends(get_container),
) -> LaunchResponse:
    """Launch a stopped profile to collect cookies: it visits `count` sites like a person
    (accepts the cookie banner, scrolls, follows 1-3 links, 20-60 s each), then closes.
    Follow it with GET /{name}/warmup."""
    profile = require_profile(name, pm)
    if bl.is_running(name):
        raise HTTPException(status_code=409, detail="Browser already running")
    from ...services.browser.warmup import normalize, options

    bad = [u for u in body.urls or [] if normalize(u) is None]
    if bad:
        raise HTTPException(status_code=400, detail=f"not a site: {bad[0][:100]}")

    urls = container.warmup_sites(body.urls, body.count)
    if not urls:
        raise HTTPException(status_code=400, detail="No sites to visit")
    result = _launch(profile, response, wait, bl, bus, extra=options(urls))
    result.message += f" (warm-up: {len(urls)} sites)"
    return result


@router.get(
    "/{name}/warmup",
    response_model=WarmupStatusResponse,
    responses={404: {"model": ErrorResponse}},
)
def warm_up_status(
    name: str,
    pm: IProfileManager = Depends(get_profile_manager),
    container: Container = Depends(get_container),
) -> WarmupStatusResponse:
    """The profile's last cookie warm-up: sites done of total, and whether it still runs."""
    require_profile(name, pm)
    state = container.warmup.get(name) or {"done": 0, "total": 0, "running": False}
    return WarmupStatusResponse(name=name, **state)


@router.post(
    "/temp",
    response_model=TempLaunchResponse,
    status_code=201,
    responses={400: {"model": ErrorResponse}, 502: {"model": TempLaunchResponse}},
)
def launch_temp(
    body: TempLaunchRequest,
    response: Response,
    wait: bool = _WAIT,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    bus: EventBus = Depends(get_event_bus),
) -> TempLaunchResponse:
    """A one-time profile: fresh fingerprint, nothing saved, deleted when its browser ends."""
    if body.os_type not in ("windows", "macos", "linux") or body.engine not in ENGINES:
        raise HTTPException(status_code=400, detail="bad os_type or engine")
    checks = (
        (validate_proxy_format, body.proxy or ""),
        (validate_timezone, body.timezone or ""),
        (validate_locale, body.locale or ""),
        (validate_urls, body.start_urls),
    )
    for validate, value in checks:
        ok, msg = validate(value)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
    name = pm.add_temporary(
        body.proxy or "", body.os_type, body.engine, body.timezone, body.locale, body.start_urls
    )
    result = _launch(pm.profiles[name], response, wait, bl, bus)
    if not result.success:
        pm.delete_profile(name)
        bus.emit()
    if response.status_code in (None, 200):
        response.status_code = 201
    return TempLaunchResponse(name=name, success=result.success, message=result.message)


@router.get("/{name}/activity", response_model=ActivityResponse)
def agent_activity(
    name: str,
    limit: int = Query(200, ge=1, le=500),
    pm: IProfileManager = Depends(get_profile_manager),
    activity=Depends(get_activity),
) -> ActivityResponse:
    """The page actions agents ran in this profile (typed text is not kept)."""
    require_profile(name, pm)
    return ActivityResponse(name=name, entries=activity.entries(name, limit))


def _human_response(request) -> HumanRequestResponse:
    return HumanRequestResponse(**request.public(), headless=bool(HEADLESS))


@router.post(
    "/{name}/human",
    response_model=HumanRequestResponse,
    status_code=201,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def ask_human(
    name: str,
    body: HumanRequestBody,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
    human=Depends(get_human_requests),
) -> HumanRequestResponse:
    """Ask the person at the desktop app to do something in this browser."""
    require_profile(name, pm)
    if not bl.is_running(name):
        raise HTTPException(status_code=409, detail="Browser is not running")
    return _human_response(human.ask(name, body.reason))


@router.get(
    "/{name}/human/{request_id}",
    response_model=HumanRequestResponse,
    responses={404: {"model": ErrorResponse}},
)
def human_answer(
    name: str,
    request_id: str,
    wait: int = Query(0, ge=0, le=120, description="Seconds to wait for an answer"),
    human=Depends(get_human_requests),
) -> HumanRequestResponse:
    request = human.wait(request_id, wait)
    if request is None or request.profile != name:
        raise HTTPException(status_code=404, detail="No such request")
    return _human_response(request)


@router.post(
    "/broadcast", response_model=BroadcastResponse, responses={400: {"model": ErrorResponse}}
)
def broadcast(
    body: BroadcastRequest,
    pm: IProfileManager = Depends(get_profile_manager),
    bl: IBrowserLauncher = Depends(get_browser_launcher),
) -> BroadcastResponse:
    """Run one page action in several running profiles at once."""
    if body.action not in PageController.ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unknown action '{body.action}'")
    names = list(dict.fromkeys(body.profiles))
    for name in names:
        require_profile(name, pm)

    def one(name: str) -> dict:
        try:
            return {"ok": True, "result": bl.control(name, body.action, body.params, body.timeout)}
        except BrowserControlError as e:
            return {"ok": False, "error": str(e)}

    with ThreadPoolExecutor(max_workers=min(16, max(1, len(names)))) as pool:
        results = dict(zip(names, pool.map(one, names), strict=True))
    return BroadcastResponse(results=results)
