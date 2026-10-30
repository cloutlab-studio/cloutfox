"""CloutFox runner for the Chrome engine.

Same command line and stdout protocol as src/services/browser/runner.py, so
BrowserLauncher can start a Chrome profile exactly like a Camoufox one:

    python -m chrome_engine.runner <name> <proxy> <os> [timezone] [locale]

prints CONTROL:<port>:<token>, then BROWSER_STARTED, and BROWSER_CLOSED when
the last tab closes (or LAUNCH_FAILED: ...). The page-control server, tab
restore and tab snapshots are CloutFox's own, shared with Camoufox.
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chrome_engine import fetch
from chrome_engine.engine import ChromeEngine
from src.core.config import HEADLESS, RESTORE_TABS
from src.services.browser import control, launch_opts, session, warmup
from src.services.browser.runner import open_first_tabs, snapshot_tabs

_shutdown = asyncio.Event()


def _say(message: str) -> None:
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((message + "\n").encode("utf-8", errors="replace"))
        sys.stdout.flush()


def _compact(exc: BaseException, limit: int = 220) -> str:
    text = " ".join(str(exc).split())
    text = text.split("Call log:", 1)[0].strip()
    return text[:limit] + ("..." if len(text) > limit else "")


def _install_progress() -> fetch.Progress:
    """Report download progress every 10% (the launcher shows these lines in the log)."""
    last = -1

    def report(done: int, total: int) -> None:
        nonlocal last
        pct = done * 100 // total if total else 0
        if pct // 10 != last // 10:
            last = pct
            _say(f"Downloading Chrome engine: {pct}% ({done / 1e6:.0f}/{total / 1e6:.0f} MB)")

    return report


async def ensure_installed() -> None:
    """Download the pinned browser build on first use."""
    if fetch.installed_executable():
        return
    _say("Chrome engine is not installed yet; downloading it once...")
    await asyncio.to_thread(fetch.install, progress=_install_progress())
    _say("Chrome engine installed")


async def run_browser(
    profile_name: str,
    proxy_str: str,
    os_type: str,
    timezone: str = "",
    locale: str = "",
) -> int:
    profile_dir = launch_opts.profile_dir(profile_name)
    opts = launch_opts.load()
    proxy_str = launch_opts.proxy(proxy_str, opts)
    proxy = proxy_str if proxy_str and proxy_str != "None" else None
    warmup_urls = warmup.urls_from(opts)
    # A warm-up's tabs are not the person's session: neither restored nor saved.
    keep_tabs = RESTORE_TABS and not warmup_urls
    extensions = ",".join(opts.get("extensions") or [])
    engine = ChromeEngine(
        profile_dir,
        platform=os_type,
        proxy=proxy,
        headless=HEADLESS,
        # "" keeps the timezone / locale following the proxy's exit IP.
        timezone=timezone,
        locale=locale,
        extra_args=(
            [f"--disable-extensions-except={extensions}", f"--load-extension={extensions}"]
            if extensions
            else []
        ),
    )
    _say(f"Starting Chrome engine for {profile_name}...")
    try:
        await ensure_installed()
        await asyncio.to_thread(
            launch_opts.rotate_before_launch, opts.get("proxy_rotate_url"), _say
        )
        if opts.get("internal_tunnel"):
            # Pinned timezone and locale: the engine looks nothing up, and behind
            # a proxy its WebRTC policy already sends no UDP outside it.
            launch_opts.check_internal_tunnel(timezone, locale, bool(opts.get("geo_guard")), _say)
        elif opts.get("geo_guard"):
            await asyncio.to_thread(launch_opts.geo_guard, proxy, timezone, locale, _say)
        context = await engine.start()
    except asyncio.CancelledError:
        _say("LAUNCH_CANCELLED")
        await engine.stop()
        return 1
    except Exception as e:
        _say(f"LAUNCH_FAILED: {type(e).__name__}: {_compact(e)}")
        await engine.stop()
        return 1

    try:
        for warning in engine.warnings:
            _say(f"Warning: {warning}")
        if engine.geo:
            _say(launch_opts.geo_line(engine.geo.ip, engine.geo.country))
        if not context.pages:
            await context.new_page()
        if not warmup_urls:
            await open_first_tabs(context, profile_dir, opts.get("start_urls") or [])

        close_event = asyncio.Event()

        def on_page_close(_page: object) -> None:
            if not [p for p in context.pages if not p.is_closed()]:
                close_event.set()

        def watch(page: object) -> None:
            page.on("close", on_page_close)

        for page in context.pages:
            watch(page)
        context.on("page", watch)
        context.on("close", lambda _: close_event.set())

        control_runner, port, token = await control.serve(context, _shutdown.set)
        # CONTROL must precede BROWSER_STARTED (see the Camoufox runner).
        _say(f"CONTROL:{port}:{token}")
        _say("BROWSER_STARTED")

        snapshot_task = (
            asyncio.create_task(snapshot_tabs(context, profile_dir, close_event))
            if keep_tabs
            else None
        )
        warmup_task = (
            asyncio.create_task(warmup.run_and_close(context, warmup_urls, _say, close_event))
            if warmup_urls
            else None
        )
        close_task = asyncio.create_task(close_event.wait())
        shutdown_task = asyncio.create_task(_shutdown.wait())
        done, pending = await asyncio.wait(
            [close_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED
        )
        if close_task in done:
            _say("BROWSER_CLOSED")
        elif keep_tabs:
            session.save(profile_dir, [p.url for p in context.pages if not p.is_closed()])
        if snapshot_task:
            snapshot_task.cancel()
        if warmup_task:
            warmup_task.cancel()
            await asyncio.gather(warmup_task, return_exceptions=True)
        await control_runner.cleanup()
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        return 0
    finally:
        await engine.stop()


async def _async_main(argv: list[str]) -> int:
    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _shutdown.set)
    except NotImplementedError:
        pass
    return await run_browser(*argv[:5])


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 4:
        _say("Usage: python -m chrome_engine.runner <name> <proxy> <os> [timezone] [locale]")
        return 1
    try:
        return asyncio.run(_async_main(sys.argv[1:]))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
