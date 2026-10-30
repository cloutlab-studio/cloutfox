"""Tags, notes, status, start pages, last launch, bulk creation, clone and IP rotation."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.container import Container
from src.models.profile import Profile
from src.services.browser import launch_opts, runner
from src.services.profile import bulk
from src.services.profile.manager import ProfileManager

PROXY_A = "socks5://user:pass@203.0.113.10:1080"
PROXY_B = "http://user:pass@198.51.100.20:8080"


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def client(workdir):
    return TestClient(create_app(Container()), base_url="http://127.0.0.1")


# --- storage ---------------------------------------------------------------------------


def test_old_profiles_load_with_empty_organisation(workdir):
    (workdir / "profiles.json").write_text(
        json.dumps({"old": {"name": "old", "proxy": None, "os_type": "linux"}}), encoding="utf-8"
    )
    p = ProfileManager().profiles["old"]
    assert (p.tags, p.notes, p.status, p.start_urls, p.proxy_rotate_url, p.last_launch) == (
        [],
        "",
        "",
        [],
        None,
        None,
    )


def test_bad_stored_values_fall_back_instead_of_dropping_the_profile(workdir):
    (workdir / "profiles.json").write_text(
        json.dumps(
            {
                "p": {
                    "name": "p",
                    "tags": "FB,  us ,fb",
                    "status": "deleted",
                    "start_urls": ["https://example.com/", "javascript:alert(1)"],
                    "proxy_rotate_url": "ftp://x",
                    "last_launch": "yesterday",
                }
            }
        ),
        encoding="utf-8",
    )
    p = ProfileManager().profiles["p"]
    assert p.tags == ["fb", "us"]
    assert p.status == ""
    assert p.start_urls == ["https://example.com/"]
    assert p.proxy_rotate_url is None
    assert p.last_launch is None


def test_meta_and_last_launch_persist(workdir):
    pm = ProfileManager()
    pm.add_profile("a", "", "windows", tags="x, y", notes="n")
    pm.set_meta("a", status="active", start_urls="https://example.com/\n\nhttps://example.org/")
    pm.record_launch("a", "203.0.113.10", "DE")
    p = ProfileManager().profiles["a"]
    assert p.tags == ["x", "y"] and p.notes == "n" and p.status == "active"
    assert p.start_urls == ["https://example.com/", "https://example.org/"]
    assert p.last_launch["ip"] == "203.0.113.10" and p.last_launch["country"] == "DE"


def test_set_meta_refuses_identity_fields(workdir):
    pm = ProfileManager()
    pm.add_profile("a", "", "windows")
    with pytest.raises(TypeError):
        pm.set_meta("a", proxy=PROXY_A)


def test_clone_copies_settings_not_data(workdir):
    pm = ProfileManager()
    pm.add_profile("src", PROXY_A, "macos", "Europe/Berlin", None, tags=["fb"], notes="n")
    pm.record_launch("src", "203.0.113.10", "DE")
    (workdir / "camoufox_data" / "src" / "fingerprint.json").write_text("{}")
    assert pm.clone_profile("src", "copy")
    copy = pm.profiles["copy"]
    assert (copy.proxy, copy.os_type, copy.timezone, copy.tags, copy.notes) == (
        PROXY_A,
        "macos",
        "Europe/Berlin",
        ["fb"],
        "n",
    )
    assert copy.last_launch is None
    assert not (workdir / "camoufox_data" / "copy" / "fingerprint.json").exists()
    copy.tags.append("changed")
    assert pm.profiles["src"].tags == ["fb"]
    assert not pm.clone_profile("src", "COPY")


# --- bulk helpers ----------------------------------------------------------------------


def test_expand_names_pads_numbers():
    assert bulk.expand_names("fb-{n}", 3, 9) == ["fb-09", "fb-10", "fb-11"]
    assert bulk.expand_names("shop", 2) == ["shop-1", "shop-2"]
    with pytest.raises(bulk.BulkError):
        bulk.expand_names("a/{n}", 2)
    with pytest.raises(bulk.BulkError):
        bulk.expand_names("x{n}", 0)


def test_assign_proxies_modes():
    assert bulk.assign_proxies(2, []) == ["", ""]
    assert bulk.assign_proxies(3, [PROXY_A]) == [PROXY_A] * 3
    assert bulk.assign_proxies(2, [PROXY_A, PROXY_B, PROXY_A]) == [PROXY_A, PROXY_B]
    with pytest.raises(bulk.BulkError):
        bulk.assign_proxies(3, [PROXY_A, PROXY_B])
    assert set(bulk.assign_proxies(5, [PROXY_A, PROXY_B], "random")) <= {PROXY_A, PROXY_B}
    with pytest.raises(bulk.BulkError):
        bulk.assign_proxies(1, ["not a proxy"])


def test_parse_profile_list():
    rows = bulk.parse_profile_list(f"# comment\nfb-01;{PROXY_A};fb,us;first\nfb-02\n")
    assert rows[0] == {"name": "fb-01", "proxy": PROXY_A, "tags": "fb,us", "notes": "first"}
    assert rows[1] == {"name": "fb-02", "proxy": "", "tags": "", "notes": ""}
    with pytest.raises(bulk.BulkError, match="2"):
        bulk.parse_profile_list("ok\nbad;nope")


# --- API -------------------------------------------------------------------------------


def test_api_create_with_meta_and_filter(client):
    r = client.post(
        "/api/v1/profiles",
        json={
            "name": "a",
            "tags": ["FB"],
            "status": "new",
            "proxy_rotate_url": "https://x.example/r",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["tags"] == ["fb"] and body["status"] == "new" and body["has_rotate_url"]
    assert "proxy_rotate_url" not in body
    client.post("/api/v1/profiles", json={"name": "b"})
    assert [p["name"] for p in client.get("/api/v1/profiles?tag=fb").json()["profiles"]] == ["a"]
    assert [p["name"] for p in client.get("/api/v1/profiles?status=").json()["profiles"]] == ["b"]


@pytest.mark.parametrize(
    "body",
    [
        {"status": "deleted"},
        {"start_urls": ["file:///etc/passwd"]},
        {"proxy_rotate_url": "javascript:x"},
        {"notes": "x" * 2001},
    ],
)
def test_api_rejects_bad_meta(client, body):
    assert client.post("/api/v1/profiles", json={"name": "a", **body}).status_code == 400


def test_api_patch_meta_only_changes_supplied(client):
    client.post("/api/v1/profiles", json={"name": "a", "tags": ["x"], "notes": "keep"})
    r = client.patch("/api/v1/profiles/a", json={"status": "banned"})
    assert r.json()["status"] == "banned" and r.json()["notes"] == "keep"
    r = client.patch("/api/v1/profiles/a", json={"proxy_rotate_url": ""})
    assert r.json()["has_rotate_url"] is False


def test_api_bulk_create_and_skip_existing(client):
    client.post("/api/v1/profiles", json={"name": "fb-02"})
    r = client.post(
        "/api/v1/profiles/bulk",
        json={
            "pattern": "fb-{n}",
            "count": 3,
            "proxies": [PROXY_A, PROXY_B, PROXY_A],
            "tags": ["fb"],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json() == {"created": ["fb-1", "fb-2", "fb-3"], "skipped": []}
    r = client.post("/api/v1/profiles/bulk", json={"pattern": "fb-0{n}", "count": 2})
    assert r.json() == {"created": ["fb-01"], "skipped": ["fb-02"]}
    profiles = {p["name"]: p for p in client.get("/api/v1/profiles").json()["profiles"]}
    assert profiles["fb-2"]["proxy"] == PROXY_B and profiles["fb-1"]["tags"] == ["fb"]


def test_api_bulk_not_enough_proxies(client):
    r = client.post(
        "/api/v1/profiles/bulk", json={"pattern": "x{n}", "count": 3, "proxies": [PROXY_A, PROXY_B]}
    )
    assert r.status_code == 400
    assert client.get("/api/v1/profiles").json()["total"] == 0


def test_api_import_list(client):
    r = client.post("/api/v1/profiles/import-list", json={"text": f"a;{PROXY_A};t1,t2;hello\nb"})
    assert r.json()["created"] == ["a", "b"]
    a = client.get("/api/v1/profiles/a").json()
    assert a["proxy"] == PROXY_A and a["tags"] == ["t1", "t2"] and a["notes"] == "hello"


def test_api_set_proxies_and_clone(client):
    for n in ("a", "b"):
        client.post("/api/v1/profiles", json={"name": n})
    r = client.post("/api/v1/profiles/proxies", json={"names": ["a", "b"], "proxies": [PROXY_A]})
    assert r.json()["updated"] == ["a", "b"]
    assert client.get("/api/v1/profiles/b").json()["proxy"] == PROXY_A
    assert (
        client.post("/api/v1/profiles/proxies", json={"names": ["nope"], "proxies": []}).status_code
        == 404
    )
    r = client.post("/api/v1/profiles/a/clone", json={"name": "a2"})
    assert r.status_code == 201 and r.json()["proxy"] == PROXY_A
    assert client.post("/api/v1/profiles/a/clone", json={"name": "a2"}).status_code == 409


def test_api_rotate_needs_a_link(client, monkeypatch):
    from src.api.routes import profiles as routes

    client.post("/api/v1/profiles", json={"name": "a"})
    assert client.post("/api/v1/profiles/a/rotate-ip").status_code == 400
    client.patch("/api/v1/profiles/a", json={"proxy_rotate_url": "https://x.example/r?key=k"})
    monkeypatch.setattr(routes, "rotate_ip", lambda url: (True, "ok"))
    assert client.post("/api/v1/profiles/a/rotate-ip").json() == {"success": True, "message": "ok"}


# --- launch options --------------------------------------------------------------------


def test_launch_opts_round_trip(monkeypatch):
    p = Profile(
        name="p", start_urls=["https://example.com/"], proxy_rotate_url="https://r.example/"
    )
    monkeypatch.setenv(launch_opts.ENV, launch_opts.encode(p))
    assert launch_opts.load() == {
        "start_urls": ["https://example.com/"],
        "proxy_rotate_url": "https://r.example/",
        "extensions": [],
    }
    line = launch_opts.geo_line("2001:db8::1", "DE")
    assert launch_opts.parse_geo_line(line) == {"ip": "2001:db8::1", "country": "DE"}
    monkeypatch.setenv(launch_opts.ENV, "not json")
    assert launch_opts.load() == {}


class _Ctx:
    def __init__(self):
        self.pages = [object()]


def test_start_urls_open_only_without_saved_tabs(monkeypatch, tmp_path, capsys):
    opened = []

    async def fake_restore(context, urls):
        opened.append(list(urls))
        return len(urls)

    monkeypatch.setattr(runner, "restore_tabs", fake_restore)
    monkeypatch.setattr(runner, "RESTORE_TABS", True)
    monkeypatch.setattr(runner.session, "load", lambda d: [])
    asyncio.run(runner.open_first_tabs(_Ctx(), str(tmp_path), ["https://example.com/"]))
    assert opened == [[], ["https://example.com/"]]

    opened.clear()
    monkeypatch.setattr(runner.session, "load", lambda d: ["https://saved.example/"])
    asyncio.run(runner.open_first_tabs(_Ctx(), str(tmp_path), ["https://example.com/"]))
    assert opened == [["https://saved.example/"]]


def test_launcher_reports_geo_when_ready():
    import io

    from src.services.browser.launcher import BrowserLauncher, _LaunchResult

    class Proc:
        stdout = io.StringIO(launch_opts.geo_line("203.0.113.10", "DE") + "\nBROWSER_STARTED\n")

    bl = BrowserLauncher()
    seen = []
    bl.on_launched = lambda name, geo: seen.append((name, geo))
    bl._monitor_process(Proc(), "p", lambda m: None, None, lambda: None, _LaunchResult())
    assert seen == [("p", {"ip": "203.0.113.10", "country": "DE"})]


def test_zip_import_drops_the_rotate_link(workdir):
    pm = ProfileManager()
    pm.add_profile("a", "", "windows", proxy_rotate_url="https://evil.example/r", tags=["x"])
    pm.record_launch("a", "203.0.113.10", "DE")
    ok, zip_path = pm.export_profile("a", str(workdir), include_data=False)
    assert ok
    pm.delete_profile("a")
    assert pm.import_profile(zip_path) == (True, "a")
    p = pm.profiles["a"]
    assert p.proxy_rotate_url is None and p.last_launch is None and p.tags == ["x"]
