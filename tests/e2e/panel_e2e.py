"""The built panel paints every screen in a real browser, with a stand-in bridge.

The Python side cannot see the window: a page that loads but fails in
JavaScript leaves a blank white window and no trace, which is what a dead panel
looks like on Windows. This renders the committed panel, waits for the profile
list, opens the command palette and saves a screenshot. Exits non-zero on
failure.

    python -m playwright install --with-deps chromium   # once
    python tests/e2e/panel_e2e.py [output-folder]
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import pathlib
import sys
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parents[2]
DIST = ROOT / "src" / "ui" / "dist"
OUT = pathlib.Path(
    sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="cloutfox-panel-e2e-")
)
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT))

ROW = {
    "name": "e2e-profile",
    "os": "windows",
    "engine": "camoufox",
    "proxy": "192.0.2.10:8080",
    "scheme": "http",
    "wireguard": None,
    "timezone": None,
    "locale": None,
    "tags": ["e2e"],
    "notes": "",
    "status": "active",
    "temporary": False,
    "rotate": False,
    "last": {"at": None, "ip": None, "country": "US"},
    "running": False,
    "loading": False,
    "failed": False,
    "since": "",
    "warmup": None,
    "device": "1920x1080 · 8 CPU",
    "encrypted": False,
    "sealed": False,
    "locked": False,
}


def page_script() -> str:
    """A fake bridge in front of the page: the panel's own screens, no Python."""
    from src.core.strings import STRINGS

    rows = []
    for i in range(1, 25):
        row = dict(ROW, name=f"e2e-profile-{i:02d}")
        if i <= 4:
            row["folder"] = "Clients/Germany"
        elif i <= 8:
            row["folder"] = "Clients"
        elif i <= 10:
            row["folder"] = "Ads"
        if i == 1:
            row |= {"running": True, "since": "10:00", "warmup": {"done": 3, "total": 10}}
        rows.append(row)
    settings = {
        "geo_guard": False,
        "backup_dir": "",
        "backup_hours": 0,
        "backup_keep": 7,
        "last_backup": "",
        "warmup_sites": ["example.com"],
        "warmup_count": 10,
        "language": "en",
        "sound": True,
        "sound_volume": 60,
        "motion": "system",
        "cursor": True,
        "auto_update_check": True,
        "update_asked": True,
        "update_skipped": "",
    }
    options = {
        "statuses": ["", "new", "active"],
        "folders": ["Ads", "Archive", "Clients", "Clients/Germany"],
        "extensions": [],
        "max_bulk": 500,
        "warmup_counts": [3, 5],
        "backup_hours": [0, 6],
        "backup_keep": [3],
    }
    boot = {
        "locked": False,
        "language": "en",
        "strings": STRINGS["en"],
        "settings": settings,
        "version": "e2e",
        "platform": "linux",
        "panel_restarts": 0,
    }
    return f"""
const state = {{
  boot: {json.dumps(boot, ensure_ascii=False)},
  rows: {json.dumps(rows, ensure_ascii=False)},
  options: {json.dumps(options, ensure_ascii=False)},
  settings: {json.dumps(settings, ensure_ascii=False)},
  update: {{available: true, current: "3.1.1", latest: "9.9.9", url: "https://example.com/", skipped: false}}
}};
const api = {{
  boot: async () => state.boot,
  start: async () => ({{}}),
  panel_ready: async () => ({{}}),
  snapshot: async () => ({{profiles: state.rows, help: [], master: false,
    update: state.update}}),
  log_history: async () => [{{id: 1, at: "10:00:00", text: "e2e"}}],
  options: async () => state.options,
  settings: async () => state.settings,
  set_language: async (code) => ({{language: code, strings: state.boot.strings}})
}};
// An unlisted call answers {{}} so a new panel call cannot turn this into a
// false failure. "then" stays empty: a thenable answer would never resolve.
window.pywebview = {{api: new Proxy(api, {{get: (target, key) => key === "then" ? undefined : (key in target ? target[key] : async () => ({{}}))}})}};
"""


class _Quiet(http.server.SimpleHTTPRequestHandler):
    """Serve the panel's own files; no favicon, so the browser has nothing to miss."""

    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:
        if self.path.split("?")[0] == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        super().do_GET()


def serve(directory: pathlib.Path) -> tuple[http.server.ThreadingHTTPServer, int]:
    handler = functools.partial(_Quiet, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def main() -> int:
    from playwright.sync_api import sync_playwright

    index = DIST / "index.html"
    if not index.is_file():
        print(f"the panel is not built: {index} is missing", file=sys.stderr)
        return 1

    server, port = serve(DIST)
    errors: list[str] = []
    try:
        with sync_playwright() as playwright:
            # A local run may use a Chromium of another version than this
            # Playwright expects; CI installs the matching one.
            binary = os.environ.get("CLOUTFOX_E2E_CHROMIUM")
            browser = (
                playwright.chromium.launch(executable_path=binary)
                if binary
                else playwright.chromium.launch()
            )
            page = browser.new_page(viewport={"width": 1400, "height": 860})
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.on(
                "console",
                lambda m: (
                    errors.append(f"console {m.type}: {m.text}")
                    if m.type == "error" and "favicon" not in m.text.lower()
                    else None
                ),
            )
            page.add_init_script(page_script())
            page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load")

            first = page.wait_for_selector("text=e2e-profile-01", timeout=20_000)
            assert first.is_visible(), "the first profile row is not visible"
            count = page.locator("text=e2e-profile-").count()
            assert count >= 20, f"only {count} rows drawn: the list did not render"
            assert page.locator(".rail").count() == 1, "no rail: the shell did not mount"
            # The folder tree: two roots, a subfolder and an empty one that still shows.
            assert page.locator("text=9.9.9").count() >= 1, "the update bar is missing"
            for name in ("Clients", "Germany", "Ads", "Archive"):
                assert page.locator(f".rail :text-is('{name}')").count() >= 1, f"no folder {name}"

            # Let the row cascade finish before the picture says anything.
            page.wait_for_timeout(1500)
            page.screenshot(path=str(OUT / "panel.png"), full_page=False)

            page.keyboard.press("Control+k")
            page.wait_for_selector(".palette, [role=dialog]", timeout=5_000)
            page.keyboard.press("Escape")

            # The window's minimum size: the narrow layout must not scroll sideways.
            page.set_viewport_size({"width": 1180, "height": 680})
            page.wait_for_timeout(600)
            overflow = page.evaluate(
                "document.documentElement.scrollWidth - document.documentElement.clientWidth"
            )
            assert overflow <= 0, f"the panel scrolls sideways by {overflow}px at 1180x680"
            page.screenshot(path=str(OUT / "panel-small.png"), full_page=False)
            browser.close()
    finally:
        server.shutdown()

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"screenshots: {OUT / 'panel.png'}, {OUT / 'panel-small.png'}")
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
