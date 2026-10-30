from typing import Literal

from pydantic import BaseModel, Field


class NavigateRequest(BaseModel):
    url: str
    wait_until: Literal["load", "domcontentloaded", "networkidle", "commit"] = "load"


class ClickRequest(BaseModel):
    selector: str = Field(
        description="Playwright selector: CSS, text=..., or role=button[name='...']"
    )
    timeout: int = Field(10_000, ge=100, le=120_000)


class TypeRequest(BaseModel):
    selector: str
    text: str = Field(max_length=20_000)
    submit: bool = Field(False, description="Press Enter after typing")
    clear: bool = Field(True, description="Replace the field's value instead of appending")
    timeout: int = Field(10_000, ge=100, le=120_000)
    delay: float = Field(0, ge=0, le=300, description="Milliseconds between key presses")


class PressRequest(BaseModel):
    key: str = Field(description="Key name such as Enter, Tab, Escape, Control+A")
    selector: str | None = None


class ClickAtRequest(BaseModel):
    x: float = Field(ge=0, description="Viewport X in CSS pixels, as on a screenshot")
    y: float = Field(ge=0, description="Viewport Y in CSS pixels, as on a screenshot")


class KeyboardTypeRequest(BaseModel):
    text: str = Field(max_length=20_000)
    delay: float = Field(0, ge=0, le=300, description="Milliseconds between key presses")


class HoverRequest(BaseModel):
    selector: str
    timeout: int = Field(10_000, ge=100, le=120_000)


class ScrollRequest(BaseModel):
    dy: float = Field(600, ge=-20_000, le=20_000, description="Pixels down (negative: up)")
    dx: float = Field(0, ge=-20_000, le=20_000, description="Pixels right (negative: left)")
    selector: str | None = Field(None, description="Scroll this element into view instead")
    timeout: int = Field(10_000, ge=100, le=120_000)


class SelectRequest(BaseModel):
    selector: str
    values: list[str] = Field(min_length=1, max_length=50, description="Option values or labels")
    timeout: int = Field(10_000, ge=100, le=120_000)


class DragRequest(BaseModel):
    source: str
    target: str
    timeout: int = Field(10_000, ge=100, le=120_000)


class UploadRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=20, description="Local file paths")
    selector: str = Field(
        "input[type=file]",
        description="A file input, or a button that opens the file picker",
    )
    timeout: int = Field(15_000, ge=100, le=120_000)


class PauseRequest(BaseModel):
    ms: int = Field(ge=1, le=60_000)


class DialogsRequest(BaseModel):
    accept: bool | None = Field(None, description="Accept (true) or dismiss (false) future dialogs")
    prompt_text: str | None = Field(None, max_length=2_000)


class WaitRequest(BaseModel):
    selector: str
    timeout: int = Field(15_000, ge=100, le=120_000)


class EvaluateRequest(BaseModel):
    script: str = Field(
        max_length=200_000,
        description="JavaScript expression or function body, e.g. document.title",
    )


class TabNewRequest(BaseModel):
    url: str | None = None
