"""Cookie warm-up: a profile visits a few ordinary sites the way a person would.

The app picks the sites (`pick`) and launches the profile with `options(urls)` in
its launch options. The runner then calls `run_and_close` in one tab instead of
opening the start pages: on each site it accepts the cookie banner, scrolls and
follows 1-3 links inside the site, and prints "WARMUP:<n>/<total> <url>" after
each one. When the list is done the browser closes; the warm-up tabs are not
saved for the next launch.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import re
import threading
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

PREFIX = "WARMUP:"
MAX_SITES = 100
# Seconds on one site, links followed inside it.
DWELL = (20.0, 60.0)
LINKS = (1, 3)
# Hard limit per site on top of the dwell, for a page that never settles.
SITE_TIMEOUT = 60.0
# Seconds for the requests a click starts (a consent banner saving its cookies),
# after the click and again before the browser closes.
SETTLE = 2.0

# Buttons of cookie banners, matched against the whole button text.
_ACCEPT = re.compile(
    r"^\s*("
    r"accept( all)?( cookies)?|allow( all)?( cookies)?|i agree|agree( and continue)?|got it|"
    r"i accept|yes, i agree|"
    r"принять( все)?( cookie| куки)?|согласен|я согласен|разрешить( все)?|хорошо|"
    r"alle akzeptieren|akzeptieren|zustimmen|alle zulassen|"
    r"tout accepter|accepter( et fermer)?|j'accepte|"
    r"aceptar( todo| todas)?|accetta( tutto| tutti)?|aceitar( tudo| todos)?|"
    r"alles accepteren|accepteren|akceptuj( wszystkie)?|zaakceptuj|kabul et|"
    r"přijmout vše|elfogadom|acceptă( tot)?"
    r")\s*[.!]?\s*$",
    re.IGNORECASE,
)
# Accept buttons of common consent platforms, whatever their text.
_CONSENT_SELECTORS = (
    "#onetrust-accept-btn-handler",
    "#didomi-notice-agree-button",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "#CybotCookiebotDialogBodyButtonAccept",
    "#truste-consent-button",
    ".fc-cta-consent",
    "#L2AGLb",
    "button[data-testid='accept-btn']",
)
# Links a warm-up does not follow: accounts, carts, files.
_SKIP_LINK = re.compile(
    r"log-?out|sign-?out|log-?in|sign-?in|sign-?up|register|account|cart|checkout|basket|"
    r"\.(pdf|zip|exe|dmg|apk|msi|rar|7z|mp3|mp4)(\?|$)",
    re.IGNORECASE,
)


# A site written without a scheme: host[:port][/path].
_BARE_SITE = re.compile(r"[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+(:\d{1,5})?(/\S*)?")


def normalize(site: str) -> str | None:
    """An http(s) URL for a site written as a URL or a bare host, or None."""
    site = site.strip()
    if not site or site.startswith("#") or any(c.isspace() for c in site):
        return None
    if "://" not in site:
        if not _BARE_SITE.fullmatch(site):
            return None
        site = "https://" + site
    parts = urlsplit(site)
    try:
        parts.port  # noqa: B018 - raises on a port that is not a number
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return site


def pick(sites: list[str], count: int, rng: random.Random | None = None) -> list[str]:
    """`count` different sites from the list, in random order."""
    unique = list(dict.fromkeys(u for u in map(normalize, sites) if u))
    (rng or random).shuffle(unique)
    return unique[: max(0, min(count, MAX_SITES))]


def options(urls: list[str]) -> dict:
    """Launch options that turn a launch into a warm-up."""
    return {"warmup": {"urls": urls}}


def urls_from(opts: dict) -> list[str]:
    """The sites a runner should warm up with, from its launch options."""
    warm = opts.get("warmup")
    urls = warm.get("urls") if isinstance(warm, dict) else None
    if not isinstance(urls, list):
        return []
    return [u for u in urls if isinstance(u, str) and normalize(u) == u][:MAX_SITES]


def parse_line(line: str) -> tuple[int, int, str] | None:
    """(done, total, url) from a runner's "WARMUP:<done>/<total> <url>" line."""
    head, _, url = line.removeprefix(PREFIX).partition(" ")
    done, _, total = head.partition("/")
    if not (done.isdigit() and total.isdigit()):
        return None
    return int(done), int(total), url


class Progress:
    """Warm-ups of running profiles: sites done of total, for the app and the API."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, dict] = {}

    def update(self, name: str, done: int, total: int) -> None:
        with self._lock:
            self._state[name] = {"done": done, "total": total, "running": True}

    def finish(self, name: str) -> None:
        with self._lock:
            if name in self._state:
                self._state[name]["running"] = False

    def get(self, name: str) -> dict | None:
        """{"done", "total", "running"} of the profile's last warm-up, or None."""
        with self._lock:
            state = self._state.get(name)
            return dict(state) if state else None

    def running(self, name: str) -> dict | None:
        state = self.get(name)
        return state if state and state["running"] else None


# --- in the browser (runner side) ----------------------------------------------------


async def _pause(rng: random.Random, low: float, high: float) -> None:
    await asyncio.sleep(rng.uniform(low, high))


async def accept_cookies(page: Any) -> bool:
    """Click the cookie banner's accept button if the page (or one of its frames) has one."""
    for frame in page.frames[:12]:
        candidates = [frame.locator(s).first for s in _CONSENT_SELECTORS]
        candidates += [
            frame.get_by_role("button", name=_ACCEPT).first,
            frame.get_by_role("link", name=_ACCEPT).first,
        ]
        for locator in candidates:
            with contextlib.suppress(Exception):
                if await locator.is_visible():
                    # Camoufox moves the cursor to the button the way a hand would.
                    await locator.click(timeout=8000)
                    await asyncio.sleep(SETTLE)
                    return True
    return False


async def browse(page: Any, seconds: float, rng: random.Random) -> None:
    """Read the page for about `seconds`: scroll down in uneven steps, sometimes back up."""
    loop = asyncio.get_running_loop()
    end = loop.time() + seconds
    while loop.time() < end:
        step = rng.randint(180, 650) * (-1 if rng.random() < 0.15 else 1)
        with contextlib.suppress(Exception):
            await page.mouse.wheel(0, step)
        await asyncio.sleep(min(max(0.0, end - loop.time()), rng.uniform(0.6, 2.4)))


def _same_site(host: str, other: str) -> bool:
    base = host.removeprefix("www.")
    return other in (host, base) or other.endswith("." + base)


async def follow_link(page: Any, rng: random.Random) -> bool:
    """Open a random visible link that stays on the site; False when there is none."""
    current = urlsplit(page.url)
    if not current.hostname:
        return False
    links = await page.eval_on_selector_all(
        "a[href]",
        """els => els.map((a, i) => {
            const r = a.getBoundingClientRect();
            return {i, href: a.href, shown: r.width > 4 && r.height > 4};
        })""",
    )
    here = page.url.split("#", 1)[0]
    choices = []
    for link in links:
        target = urlsplit(link["href"])
        if (
            link["shown"]
            and target.scheme in ("http", "https")
            and target.hostname
            and _same_site(current.hostname, target.hostname)
            and link["href"].split("#", 1)[0] != here
            and not _SKIP_LINK.search(link["href"])
        ):
            choices.append(link)
    if not choices:
        return False
    link = rng.choice(choices)
    locator = page.locator("a[href]").nth(link["i"])
    with contextlib.suppress(Exception):
        await locator.scroll_into_view_if_needed(timeout=3000)
        await locator.click(timeout=5000)
        await page.wait_for_load_state("domcontentloaded", timeout=20000)
    if page.url.split("#", 1)[0] == here:
        # The click opened a new tab (closed by run) or did nothing: go there directly.
        await page.goto(link["href"], wait_until="domcontentloaded", timeout=30000)
    return True


async def visit(page: Any, url: str, rng: random.Random) -> None:
    """One site: open it, accept cookies, read it and a few pages inside it."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + rng.uniform(*DWELL)
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await _pause(rng, 1.5, 3.5)
    accepted = await accept_cookies(page)
    links = rng.randint(*LINKS)
    for n in range(links + 1):
        left = deadline - loop.time()
        if left <= 0:
            return
        await browse(page, left / (links + 1 - n), rng)
        if not accepted:
            # Many banners show up a few seconds after the page.
            accepted = await accept_cookies(page)
        if n < links and not await follow_link(page, rng):
            await browse(page, max(0.0, deadline - loop.time()), rng)
            return


def _short(error: BaseException) -> str:
    text = " ".join(str(error).split()).split("Call log:", 1)[0].strip()
    return f"{type(error).__name__}: {text[:160]}" if text else type(error).__name__


async def run(
    context: Any, urls: list[str], say: Callable[[str], None], rng: random.Random | None = None
) -> int:
    """Visit every site in one tab; returns how many went through without an error."""
    rng = rng or random.Random()
    page = context.pages[0] if context.pages else await context.new_page()

    def close_popup(popup: Any) -> None:
        # Sites open tabs and windows; the warm-up stays in its one tab.
        if popup is not page:
            asyncio.get_running_loop().create_task(popup.close())

    context.on("page", close_popup)
    ok = 0
    for n, url in enumerate(urls, 1):
        try:
            await asyncio.wait_for(visit(page, url, rng), DWELL[1] + SITE_TIMEOUT)
            ok += 1
        except asyncio.CancelledError:
            raise
        except BaseException as e:
            say(f"Warm-up: {url} failed ({_short(e)})")
        say(f"{PREFIX}{n}/{len(urls)} {url}")
    return ok


async def run_and_close(
    context: Any, urls: list[str], say: Callable[[str], None], close: asyncio.Event
) -> None:
    """The runner's warm-up task: visit the sites, then end the session."""
    try:
        ok = await run(context, urls, say)
        await asyncio.sleep(SETTLE)
        say(f"Warm-up done: {ok} of {len(urls)} sites")
    finally:
        close.set()
