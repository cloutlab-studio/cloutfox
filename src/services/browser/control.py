"""Remote control of a running profile's pages.

runner.py starts `serve()` next to the browser. It listens on 127.0.0.1 on a
random port, requires a random per-launch token, and announces itself on
stdout as "CONTROL:<port>:<token>" so the launcher can forward API calls.
`POST /shutdown` with the same token asks the runner to close the browser the
way a signal does; the launcher uses it where there are no signals (Windows).
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
import secrets
from collections import deque
from collections.abc import Callable
from typing import Any
from urllib.parse import unquote, urlparse

from aiohttp import web

from ...core.config import UPLOAD_DIRS, UPLOAD_EXTENSIONS

ALLOWED_SCHEMES = ("http", "https", "about")
MAX_FULL_PAGE_HEIGHT = 16_384
MAX_TEXT = 40_000
MAX_UPLOAD_FILES = 20
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
MAX_PAUSE_MS = 60_000
# Never handed to a website even inside an allowed directory.
SECRET_SUFFIXES = (".kdbx", ".key", ".pem", ".p12", ".pfx", ".age", ".env", ".asc", ".gpg")
TOKEN_HEADER = "X-Control-Token"


class ControlError(Exception):
    pass


_SCHEME = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):(.*)$", re.S)


def _check_url(url: str) -> str:
    url = url.strip()
    # "%66ile:" or "java%73cript:" would miss _SCHEME and get https:// prepended;
    # decode a percent-encoded scheme and check it like any other.
    colon = url.find(":")
    slash = url.find("/")
    if colon != -1 and "%" in url[:colon] and (slash == -1 or colon < slash):
        decoded_scheme = unquote(url[:colon]).lower()
        if decoded_scheme not in ALLOWED_SCHEMES:
            raise ControlError(f"URL scheme '{decoded_scheme}' is not allowed")

    match = _SCHEME.match(url)
    # "localhost:8080/x" looks like a scheme but is host:port; bare hosts get https.
    if not match or re.match(r"\d+(/|$)", match.group(2)):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        host = parsed.hostname
    except ValueError as e:  # e.g. an unclosed IPv6 bracket: "[::1"
        raise ControlError(f"Malformed URL: {e}") from e
    scheme = parsed.scheme.lower()
    if scheme in ("http", "https") and not host:
        # Older Python versions parse "https://[]" without raising.
        raise ControlError("Malformed URL: no host")
    if scheme not in ALLOWED_SCHEMES:
        # file:, view-source:, chrome: etc. would let a remote caller read
        # local files or browser internals through the snapshot.
        raise ControlError(f"URL scheme '{scheme}' is not allowed")
    if scheme == "about" and url.lower() != "about:blank":
        # about:config, about:logins etc. expose or change browser internals.
        raise ControlError("Only about:blank is allowed among about: pages")
    return url


def _check_files(
    paths: list[str],
    allowed_dirs: list[str] | None = None,
    allowed_extensions: set[str] | None = None,
) -> list[str]:
    """Resolve upload paths and refuse anything outside the allowed directories.

    An agent reading untrusted pages could be talked into uploading SSH keys or
    password databases, so hidden paths and key-like files are refused too.
    """
    if not paths:
        raise ControlError("No files given")
    if len(paths) > MAX_UPLOAD_FILES:
        raise ControlError(f"At most {MAX_UPLOAD_FILES} files per upload")
    roots = UPLOAD_DIRS if allowed_dirs is None else allowed_dirs
    extensions = UPLOAD_EXTENSIONS if allowed_extensions is None else allowed_extensions
    resolved = []
    for raw in paths:
        path = os.path.realpath(os.path.expanduser(raw))
        if not any(os.path.commonpath([path, root]) == root for root in roots):
            raise ControlError(
                f"'{raw}' is outside the upload directories ({os.pathsep.join(roots)}); "
                "set CLOUTFOX_UPLOAD_DIRS to allow more",
            )
        parts = path.split(os.sep)
        if any(part.startswith(".") for part in parts if part):
            raise ControlError(f"'{raw}' is a hidden path and cannot be uploaded")
        if path.lower().endswith(SECRET_SUFFIXES) or os.path.basename(path).startswith("id_"):
            raise ControlError(f"'{raw}' looks like a key or secret and cannot be uploaded")
        if os.path.splitext(path)[1].lower() not in extensions:
            raise ControlError(
                f"'{raw}' is not an allowed file type ({', '.join(sorted(extensions))}); "
                "set CLOUTFOX_UPLOAD_EXTENSIONS to allow more",
            )
        if not os.path.isfile(path):
            raise ControlError(f"'{raw}' is not a file")
        if os.path.getsize(path) > MAX_UPLOAD_BYTES:
            raise ControlError(f"'{raw}' is larger than {MAX_UPLOAD_BYTES // 1024 // 1024} MB")
        resolved.append(path)
    return resolved


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


class PageController:
    """Executes control actions against a Playwright BrowserContext."""

    def __init__(self, context: Any) -> None:
        self._context = context
        self._current: Any = None
        self._dialog_accept = False
        self._prompt_text: str | None = None
        self._dialogs: deque[dict[str, Any]] = deque(maxlen=20)
        on = getattr(context, "on", None)
        if on is not None:
            on("dialog", self._on_dialog)

    async def _on_dialog(self, dialog: Any) -> None:
        # With a listener attached Playwright no longer dismisses dialogs itself.
        self._dialogs.append(
            {"type": dialog.type, "message": dialog.message, "accepted": self._dialog_accept},
        )
        try:
            if self._dialog_accept:
                await dialog.accept(self._prompt_text or "")
            else:
                await dialog.dismiss()
        except Exception:
            pass

    # --- page selection ---------------------------------------------------

    def _open_pages(self) -> list[Any]:
        return [p for p in self._context.pages if not p.is_closed()]

    async def _page(self) -> Any:
        pages = self._open_pages()
        if self._current is not None and not self._current.is_closed():
            return self._current
        if pages:
            self._current = pages[-1]
            return self._current
        self._current = await self._context.new_page()
        return self._current

    async def _describe(self, page: Any) -> dict[str, Any]:
        return {"url": page.url, "title": await page.title()}

    # --- actions ----------------------------------------------------------

    async def navigate(self, url: str, wait_until: str = "load") -> dict[str, Any]:
        page = await self._page()
        await page.goto(_check_url(url), wait_until=wait_until)
        return await self._describe(page)

    async def back(self) -> dict[str, Any]:
        page = await self._page()
        await page.go_back()
        return await self._describe(page)

    async def forward(self) -> dict[str, Any]:
        page = await self._page()
        await page.go_forward()
        return await self._describe(page)

    async def reload(self) -> dict[str, Any]:
        page = await self._page()
        await page.reload()
        return await self._describe(page)

    async def snapshot(self, max_chars: int = MAX_TEXT) -> dict[str, Any]:
        """Accessibility tree of the page: roles, names and text, compact."""
        page = await self._page()
        aria = await page.locator("body").aria_snapshot()
        aria, truncated = _truncate(aria, max_chars)
        return {**await self._describe(page), "snapshot": aria, "truncated": truncated}

    async def text(self, selector: str = "body", max_chars: int = MAX_TEXT) -> dict[str, Any]:
        page = await self._page()
        content = await page.locator(selector).first.inner_text()
        content, truncated = _truncate(content, max_chars)
        return {"text": content, "truncated": truncated}

    async def click(self, selector: str, timeout: int = 10_000) -> dict[str, Any]:
        page = await self._page()
        await page.locator(selector).first.click(timeout=timeout)
        return await self._describe(page)

    async def type(
        self,
        selector: str,
        text: str,
        submit: bool = False,
        clear: bool = True,
        timeout: int = 10_000,
        delay: float = 0,
    ) -> dict[str, Any]:
        page = await self._page()
        field = page.locator(selector).first
        if clear and not delay:
            await field.fill(text, timeout=timeout)
        else:
            if clear:
                await field.fill("", timeout=timeout)
            await field.press_sequentially(text, delay=delay, timeout=timeout)
        if submit:
            await field.press("Enter")
        return await self._describe(page)

    async def press(self, key: str, selector: str | None = None) -> dict[str, Any]:
        page = await self._page()
        if selector:
            await page.locator(selector).first.press(key)
        else:
            await page.keyboard.press(key)
        return await self._describe(page)

    async def click_at(self, x: float, y: float) -> dict[str, Any]:
        """Click viewport coordinates, as seen on a screenshot of the active tab."""
        page = await self._page()
        await page.mouse.click(x, y)
        return await self._describe(page)

    async def keyboard_type(self, text: str, delay: float = 0) -> dict[str, Any]:
        """Type into whatever element has focus."""
        page = await self._page()
        await page.keyboard.type(text, delay=delay)
        return await self._describe(page)

    async def hover(self, selector: str, timeout: int = 10_000) -> dict[str, Any]:
        page = await self._page()
        await page.locator(selector).first.hover(timeout=timeout)
        return await self._describe(page)

    async def scroll(
        self,
        dy: float = 600,
        dx: float = 0,
        selector: str | None = None,
        timeout: int = 10_000,
    ) -> dict[str, Any]:
        """Scroll an element into view, or turn the mouse wheel over the viewport centre."""
        page = await self._page()
        if selector:
            await page.locator(selector).first.scroll_into_view_if_needed(timeout=timeout)
        else:
            size = await page.evaluate("() => [innerWidth, innerHeight]")
            await page.mouse.move(size[0] / 2, size[1] / 2)
            await page.mouse.wheel(dx, dy)
            await asyncio.sleep(0.3)
        position = await page.evaluate(
            "() => ({x: scrollX, y: scrollY, height: document.documentElement.scrollHeight,"
            " viewport: innerHeight})",
        )
        return {**await self._describe(page), "scroll": position}

    async def select(
        self, selector: str, values: list[str], timeout: int = 10_000
    ) -> dict[str, Any]:
        """Pick options of a <select> by value or visible label."""
        page = await self._page()
        chosen = await page.locator(selector).first.select_option(values, timeout=timeout)
        return {**await self._describe(page), "selected": chosen}

    async def drag(self, source: str, target: str, timeout: int = 10_000) -> dict[str, Any]:
        page = await self._page()
        await page.locator(source).first.drag_to(page.locator(target).first, timeout=timeout)
        return await self._describe(page)

    async def upload(
        self,
        paths: list[str],
        selector: str = "input[type=file]",
        timeout: int = 15_000,
    ) -> dict[str, Any]:
        """Attach local files to a file input, or to the file picker a button opens."""
        files = _check_files(paths)
        page = await self._page()
        target = page.locator(selector).first
        is_input = await target.evaluate(
            "e => e instanceof HTMLInputElement && e.type === 'file'",
            timeout=timeout,
        )
        if is_input:
            await target.set_input_files(files, timeout=timeout)
        else:
            async with page.expect_file_chooser(timeout=timeout) as chooser_info:
                await target.click(timeout=timeout)
            chooser = await chooser_info.value
            await chooser.set_files(files, timeout=timeout)
        return {**await self._describe(page), "uploaded": [os.path.basename(f) for f in files]}

    async def pause(self, ms: int) -> dict[str, Any]:
        """Wait a fixed time, e.g. to let an upload finish or to pace actions."""
        if not 0 < ms <= MAX_PAUSE_MS:
            raise ControlError(f"ms must be between 1 and {MAX_PAUSE_MS}")
        await asyncio.sleep(ms / 1000)
        page = await self._page()
        return await self._describe(page)

    async def dialogs(
        self, accept: bool | None = None, prompt_text: str | None = None
    ) -> dict[str, Any]:
        """Recent alert/confirm/prompt dialogs; optionally change how the next ones are answered."""
        if accept is not None:
            self._dialog_accept = accept
            self._prompt_text = prompt_text
        return {"accept": self._dialog_accept, "recent": list(self._dialogs)}

    async def wait_for(self, selector: str, timeout: int = 15_000) -> dict[str, Any]:
        page = await self._page()
        await page.locator(selector).first.wait_for(timeout=timeout)
        return await self._describe(page)

    async def screenshot(self, full_page: bool = False) -> dict[str, Any]:
        page = await self._page()
        if full_page:
            height = await page.evaluate("() => document.documentElement.scrollHeight")
            if height > MAX_FULL_PAGE_HEIGHT:
                raise ControlError(
                    f"Page is {height}px tall; full-page screenshots are limited to "
                    f"{MAX_FULL_PAGE_HEIGHT}px. Scroll and take viewport screenshots instead.",
                )
        png = await page.screenshot(full_page=full_page, type="png")
        return {**await self._describe(page), "png_base64": base64.b64encode(png).decode()}

    async def evaluate(self, script: str) -> dict[str, Any]:
        page = await self._page()
        return {"result": await page.evaluate(script)}

    async def tabs(self) -> dict[str, Any]:
        current = await self._page()
        pages = self._open_pages()
        return {
            "tabs": [
                {"index": i, "url": p.url, "title": await p.title(), "active": p is current}
                for i, p in enumerate(pages)
            ],
        }

    async def tab_new(self, url: str | None = None) -> dict[str, Any]:
        self._current = await self._context.new_page()
        if url:
            await self._current.goto(_check_url(url))
        return await self.tabs()

    async def tab_select(self, index: int) -> dict[str, Any]:
        pages = self._open_pages()
        if not 0 <= index < len(pages):
            raise ControlError(f"No tab at index {index}")
        self._current = pages[index]
        await self._current.bring_to_front()
        return await self.tabs()

    async def tab_close(self, index: int) -> dict[str, Any]:
        pages = self._open_pages()
        if not 0 <= index < len(pages):
            raise ControlError(f"No tab at index {index}")
        if len(pages) == 1:
            # Closing the last tab closes the profile's browser.
            raise ControlError("Cannot close the last tab; stop the profile instead")
        await pages[index].close()
        self._current = None
        return await self.tabs()

    async def bring_to_front(self) -> dict[str, Any]:
        """Raise the current tab's window, e.g. for a person to take over."""
        page = await self._page()
        await page.bring_to_front()
        return await self._describe(page)

    ACTIONS = (
        "navigate",
        "back",
        "forward",
        "reload",
        "snapshot",
        "text",
        "click",
        "type",
        "press",
        "click_at",
        "keyboard_type",
        "hover",
        "scroll",
        "select",
        "drag",
        "upload",
        "pause",
        "dialogs",
        "wait_for",
        "screenshot",
        "evaluate",
        "tabs",
        "tab_new",
        "tab_select",
        "tab_close",
        "bring_to_front",
    )

    async def dispatch(self, action: str, params: dict[str, Any]) -> Any:
        if action not in self.ACTIONS:
            raise ControlError(f"Unknown action '{action}'")
        try:
            return await getattr(self, action)(**params)
        except TypeError as e:
            raise ControlError(f"Invalid parameters for '{action}': {e}") from e


def _authorized(request: web.Request, token: str) -> bool:
    return secrets.compare_digest(request.headers.get(TOKEN_HEADER, ""), token)


def build_app(
    controller: PageController, token: str, on_shutdown: Callable[[], None] | None = None
) -> web.Application:
    async def handle(request: web.Request) -> web.Response:
        if not _authorized(request, token):
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        try:
            body = await request.json()
            result = await controller.dispatch(body.get("action", ""), body.get("params") or {})
        except ControlError as e:
            return web.json_response({"ok": False, "error": str(e)}, status=400)
        except Exception as e:  # Playwright timeouts, navigation errors, JS errors
            message = " ".join(str(e).split())
            if "Call log:" in message:
                message = message.split("Call log:", 1)[0].strip()
            return web.json_response(
                {"ok": False, "error": f"{type(e).__name__}: {message[:500]}"},
                status=422,
            )
        return web.json_response({"ok": True, "result": result})

    async def shutdown(request: web.Request) -> web.Response:
        if not _authorized(request, token):
            return web.json_response({"ok": False, "error": "unauthorized"}, status=401)
        if on_shutdown is None:
            return web.json_response({"ok": False, "error": "not supported"}, status=404)
        on_shutdown()
        return web.json_response({"ok": True, "result": None})

    app = web.Application(client_max_size=4 * 1024 * 1024)
    app.router.add_post("/action", handle)
    app.router.add_post("/shutdown", shutdown)
    return app


async def serve(
    context: Any, on_shutdown: Callable[[], None] | None = None
) -> tuple[web.AppRunner, int, str]:
    """Start the control server for a context. Returns (runner, port, token).

    `on_shutdown` is called on an authorized `POST /shutdown`."""
    token = secrets.token_urlsafe(24)
    app = build_app(PageController(context), token, on_shutdown)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, port, token
