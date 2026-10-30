from typing import Any

from pydantic import BaseModel, Field


class BrowserStatusResponse(BaseModel):
    name: str
    is_running: bool


class RunningBrowsersResponse(BaseModel):
    running: list[str]
    count: int


class LaunchResponse(BaseModel):
    success: bool
    message: str


class WarmupRequest(BaseModel):
    urls: list[str] | None = Field(
        None,
        max_length=100,
        description="Sites to visit; default: the list in CloutFox's settings",
    )
    count: int | None = Field(
        None, ge=1, le=100, description="How many of them, in random order; default: settings"
    )


class WarmupStatusResponse(BaseModel):
    name: str
    running: bool
    done: int
    total: int


class TempLaunchRequest(BaseModel):
    os_type: str = "windows"
    engine: str = "camoufox"
    proxy: str | None = None
    timezone: str | None = None
    locale: str | None = None
    start_urls: list[str] = Field(default_factory=list)


class TempLaunchResponse(LaunchResponse):
    name: str


class ActivityResponse(BaseModel):
    name: str
    entries: list[dict]


class HumanRequestBody(BaseModel):
    reason: str = Field(description="What the person should do, e.g. 'solve the captcha'")


class HumanRequestResponse(BaseModel):
    id: str
    profile: str
    reason: str
    status: str = Field(description="pending, done or declined")
    note: str = ""
    headless: bool = Field(False, description="The browser has no window a person can see")


class BroadcastRequest(BaseModel):
    profiles: list[str]
    action: str = Field(description="A page action, e.g. navigate, click, scroll, screenshot")
    params: dict[str, Any] = Field(default_factory=dict)
    timeout: float = Field(60, gt=0, le=300)


class BroadcastResponse(BaseModel):
    results: dict[str, dict]
