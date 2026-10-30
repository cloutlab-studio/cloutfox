"""Cookie warm-up: picking sites, launch options, progress, the API and a real run."""

import asyncio
import json
import random

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.container import Container
from src.core.settings import DEFAULT_WARMUP_SITES, Settings, SettingsStore
from src.models.profile import Profile
from src.services.browser import launcher as launcher_mod
from src.services.browser import warmup
from src.services.browser.launcher import BrowserLauncher


def test_pick_normalises_dedupes_and_samples():
    sites = [
        "example.com",
        "https://example.com",
        "http://a.example/x",
        "not a site",
        "",
        "ftp://b",
    ]
    picked = warmup.pick(sites, 10, random.Random(1))
    assert sorted(picked) == ["http://a.example/x", "https://example.com"]
    assert len(warmup.pick(list(DEFAULT_WARMUP_SITES), 5)) == 5
    assert warmup.pick(sites, 0) == []


@pytest.mark.parametrize(
    ("site", "url"),
    [
        ("example.com", "https://example.com"),
        ("news.example.com/world", "https://news.example.com/world"),
        ("http://127.0.0.1:8080/x", "http://127.0.0.1:8080/x"),
        ("javascript:alert(1)", None),
        ("file:///etc/passwd", None),
        ("https://example.com:port/", None),
        ("two words.com", None),
        ("# comment", None),
    ],
)
def test_normalize(site, url):
    assert warmup.normalize(site) == url


def test_launch_options_round_trip():
    opts = warmup.options(["https://example.com", "http://a.example/"])
    assert warmup.urls_from(opts) == ["https://example.com", "http://a.example/"]
    assert warmup.urls_from({"warmup": {"urls": ["javascript:alert(1)", 3]}}) == []
    assert warmup.urls_from({}) == []


def test_progress_lines():
    assert warmup.parse_line("WARMUP:3/10 https://example.com") == (3, 10, "https://example.com")
    assert warmup.parse_line("WARMUP:x/10") is None
    progress = warmup.Progress()
    progress.update("p", 3, 10)
    assert progress.running("p") == {"done": 3, "total": 10, "running": True}
    progress.finish("p")
    assert progress.running("p") is None and progress.get("p")["done"] == 3


def test_settings_keep_a_list_of_sites(tmp_path):
    path = tmp_path / "settings.json"
    assert Settings().warmup_sites == list(DEFAULT_WARMUP_SITES)
    path.write_text(json.dumps({"warmup_sites": ["a.example", 5, "b.example"], "warmup_count": 4}))
    store = SettingsStore(path)
    assert store.current.warmup_sites == ["a.example", "b.example"]
    assert store.current.warmup_count == 4


class _Proc:
    def __init__(self, lines):
        self.stdout = iter(lines)

    def poll(self):
        return None


def test_launcher_reports_progress_and_logs_it(monkeypatch):
    bl = BrowserLauncher()
    seen, logs = [], []
    bl.on_warmup = lambda *a: seen.append(a)
    lines = ["WARMUP:1/2 https://a.example\n", "WARMUP:2/2 https://b.example\n", "BROWSER_CLOSED\n"]
    monkeypatch.setattr(launcher_mod, "terminate", lambda *a, **k: None)
    proc = _Proc(lines)
    proc.stdout = type(
        "S", (), {"readline": iter(lines + [""]).__next__, "close": lambda s: None}
    )()
    bl._monitor_process(proc, "p", logs.append, None, lambda: None, launcher_mod._LaunchResult())
    assert seen == [("p", 1, 2), ("p", 2, 2)]
    assert any("2/2" in line and "b.example" in line for line in logs)


def test_warmup_launch_passes_the_sites_and_starts_at_zero(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    spawned = []
    monkeypatch.setattr(
        launcher_mod, "spawn_browser", lambda profile, *a, **opts: spawned.append(opts)
    )
    monkeypatch.setattr(launcher_mod, "wait_for_exit", lambda *a: None)
    bl = BrowserLauncher()
    monkeypatch.setattr(bl, "_monitor_process", lambda *a: None)
    seen = []
    bl.on_warmup = lambda *a: seen.append(a)
    bl.start_thread(Profile(name="p"), lambda m: None, extra=warmup.options(["https://a.example"]))
    assert spawned[0]["warmup"] == {"urls": ["https://a.example"]}
    assert seen == [("p", 0, 1)]
    bl._active_sessions.clear()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    container = Container()
    container.settings.update(warmup_sites=["a.example", "b.example", "c.example"], warmup_count=2)
    calls = []

    def start_thread(profile, log, on_start=None, on_ready=None, on_stop=None, extra=None):
        calls.append((profile.name, extra))
        return True

    bl = container.browser_launcher
    monkeypatch.setattr(bl, "start_thread", start_thread)
    c = TestClient(create_app(container), base_url="http://127.0.0.1")
    c.calls, c.container = calls, container
    assert c.post("/api/v1/profiles", json={"name": "p"}).status_code == 201
    return c


def test_api_starts_a_warmup_with_settings_or_own_sites(client):
    r = client.post("/api/v1/browser/p/warmup?wait=false", json={})
    assert r.status_code == 202, r.text
    urls = client.calls[-1][1]["warmup"]["urls"]
    assert len(urls) == 2 and set(urls) <= {
        "https://a.example",
        "https://b.example",
        "https://c.example",
    }
    r = client.post("/api/v1/browser/p/warmup?wait=false", json={"urls": ["x.example"], "count": 5})
    assert client.calls[-1][1]["warmup"]["urls"] == ["https://x.example"]
    r = client.post("/api/v1/browser/p/warmup", json={"urls": ["javascript:alert(1)"]})
    assert r.status_code == 400
    assert client.post("/api/v1/browser/nope/warmup", json={}).status_code == 404


def test_api_reports_warmup_progress(client):
    assert client.get("/api/v1/browser/p/warmup").json() == {
        "name": "p",
        "running": False,
        "done": 0,
        "total": 0,
    }
    client.container.warmup.update("p", 4, 10)
    assert client.get("/api/v1/browser/p/warmup").json()["done"] == 4


# --- real browser ----------------------------------------------------------------------


def _camoufox_fetched() -> bool:
    try:
        from camoufox.pkgman import installed_verstr

        return bool(installed_verstr())
    except Exception:
        return False


_PAGE = """<html><body>
<div id="banner" style="position:fixed;bottom:0">We use cookies
  <button onclick="fetch('/accepted', {{cache: 'no-store'}});document.getElementById('banner').remove()">Accept all</button>
</div>
<h1>{title}</h1><div style="height:2600px">text</div>
<a href="/a">A</a> <a href="/b">B</a> <a href="/logout">Log out</a>
<a href="https://example.org/">elsewhere</a>
</body></html>"""


@pytest.mark.skipif(not _camoufox_fetched(), reason="Camoufox not fetched")
def test_real_warmup_accepts_cookies_follows_links_and_closes(monkeypatch, tmp_path, capsys):
    from aiohttp import web

    from src.services.browser import launch_opts, runner

    hits: list[str] = []

    async def page(request):
        hits.append(request.path)
        response = web.Response(text=_PAGE.format(title=request.path), content_type="text/html")
        response.set_cookie("seen", "1")
        return response

    async def main() -> int:
        app = web.Application()
        app.router.add_get("/{tail:.*}", page)
        site_runner = web.AppRunner(app, access_log=None)
        await site_runner.setup()
        site = web.TCPSite(site_runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        urls = [f"http://127.0.0.1:{port}/one", f"http://127.0.0.1:{port}/two"]
        monkeypatch.setenv(launch_opts.ENV, json.dumps(warmup.options(urls)))
        try:
            return await runner.run_browser("p", "None", "linux")
        finally:
            await site_runner.cleanup()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner, "HEADLESS", True)
    monkeypatch.setattr(runner, "RESTORE_TABS", True)
    monkeypatch.setattr(runner, "exit_ip", lambda *_: None)
    monkeypatch.setattr(warmup, "DWELL", (9.0, 10.0))
    monkeypatch.setattr(warmup, "LINKS", (1, 1))
    assert asyncio.run(asyncio.wait_for(main(), 150)) == 0

    out = capsys.readouterr().out
    assert "WARMUP:1/2" in out and "WARMUP:2/2" in out
    assert "Warm-up done: 2 of 2 sites" in out and "BROWSER_CLOSED" in out
    assert hits.count("/accepted") == 2
    assert {"/a", "/b"} & set(hits)
    assert "/logout" not in hits
    assert not (tmp_path / "camoufox_data" / "p" / "tabs.json").exists()
