"""One-time profiles, the agent activity log, requests for a person, broadcast."""

import threading

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.container import Container
from src.services.agent.activity import ActivityLog, summarize
from src.services.agent.human import HumanRequests
from src.services.browser import launcher as launcher_mod
from src.services.profile.manager import TEMP_PREFIX, ProfileManager


class FakeProc:
    def poll(self):
        return None


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(launcher_mod, "spawn_browser", lambda p, d=None, **kw: FakeProc())
    monkeypatch.setattr(launcher_mod, "wait_for_exit", lambda *a: None)
    monkeypatch.setattr(launcher_mod, "terminate", lambda *a, **k: None)
    container = Container()
    bl = container.browser_launcher

    def fake_monitor(proc, name, log, on_ready, notify_stopped, result):
        bl._controls[name] = (1, "t")
        result.settle(True)

    monkeypatch.setattr(bl, "_monitor_process", fake_monitor)
    calls = []

    def fake_call(port, token, action, params, timeout):
        calls.append((action, params))
        if action == "click" and params.get("selector") == "#missing":
            raise launcher_mod.BrowserControlError("Timeout", status=400)
        return {"ok": action}

    monkeypatch.setattr(bl, "_call_control", fake_call)
    client = TestClient(create_app(container), base_url="http://127.0.0.1")
    yield client, container, calls
    bl._active_sessions.clear()


def test_summarize_hides_typed_text_and_scripts():
    assert summarize("type", {"selector": "#p", "text": "hunter2"}) == {
        "selector": "#p",
        "text": "<7 chars>",
    }
    assert summarize("evaluate", {"script": "x.value='hunter2'"})["script"] == "<17 chars>"
    assert summarize("dialogs", {"accept": True, "prompt_text": "pin 1234"}) == {
        "accept": True,
        "prompt_text": "<8 chars>",
    }
    assert summarize("navigate", {"url": "https://a.example/cb?token=abc#x"}) == {
        "url": "https://a.example/cb"
    }
    assert summarize("upload", {"paths": ["/home/x/Pictures/a.png"]}) == {"paths": ["a.png"]}


def test_activity_log_persists_next_to_the_profile(tmp_path):
    log = ActivityLog(lambda name: tmp_path)
    log.record("p", "navigate", {"url": "https://example.com/"}, True, None)
    log.record("p", "type", {"selector": "#q", "text": "secret"}, False, "boom")
    assert [e["action"] for e in log.entries("p")] == ["navigate", "type"]
    assert "secret" not in (tmp_path / "agent_actions.jsonl").read_text()
    assert [e["ok"] for e in ActivityLog(lambda n: tmp_path).entries("p")] == [True, False]


def test_human_request_wait_and_answer():
    changes = []
    human = HumanRequests(lambda: changes.append(1))
    request = human.ask("p", "solve the captcha")
    assert human.wait(request.id, 0).status == "pending"
    threading.Timer(0.05, human.answer, args=(request.id, True)).start()
    assert human.wait(request.id, 2).status == "done"
    other = human.ask("p", "2FA")
    human.drop_profile("p")
    assert human.get(other.id).status == "declined" and changes


def test_temporary_profiles_are_never_saved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pm = ProfileManager()
    name = pm.add_temporary("", "linux")
    assert name.startswith(TEMP_PREFIX) and pm.profiles[name].temporary
    assert name not in (tmp_path / "profiles.json").read_text()
    # A crash leaves its data behind; the next start removes it.
    (tmp_path / "camoufox_data" / name / "cookies.sqlite").write_text("x")
    ProfileManager()
    assert not (tmp_path / "camoufox_data" / name).exists()


def test_api_temp_profile_is_deleted_when_stopped(app):
    client, container, _ = app
    r = client.post("/api/v1/browser/temp", json={"os_type": "linux"})
    assert r.status_code == 201, r.text
    name = r.json()["name"]
    assert container.profile_manager.profiles[name].temporary
    assert client.post(f"/api/v1/browser/{name}/stop").status_code == 200
    assert name not in container.profile_manager.profiles
    assert client.post("/api/v1/browser/temp", json={"proxy": "nope"}).status_code == 400


def test_api_activity_and_broadcast(app):
    client, container, calls = app
    for n in ("a", "b"):
        client.post("/api/v1/profiles", json={"name": n})
        client.post(f"/api/v1/browser/{n}/launch")
    r = client.post(
        "/api/v1/browser/broadcast",
        json={
            "profiles": ["a", "b", "a"],
            "action": "navigate",
            "params": {"url": "https://x.example/"},
        },
    )
    assert r.json()["results"] == {
        "a": {"ok": True, "result": {"ok": "navigate"}},
        "b": {"ok": True, "result": {"ok": "navigate"}},
    }
    client.post("/api/v1/browser/a/page/click", json={"selector": "#missing"})
    entries = client.get("/api/v1/browser/a/activity").json()["entries"]
    assert [(e["action"], e["ok"]) for e in entries] == [("navigate", True), ("click", False)]
    assert (
        client.post(
            "/api/v1/browser/broadcast", json={"profiles": ["a"], "action": "rm"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/browser/broadcast", json={"profiles": ["zz"], "action": "tabs"}
        ).status_code
        == 404
    )


def test_api_human_request_round_trip(app):
    client, container, _ = app
    client.post("/api/v1/profiles", json={"name": "a"})
    assert client.post("/api/v1/browser/a/human", json={"reason": "x"}).status_code == 409
    client.post("/api/v1/browser/a/launch")
    r = client.post("/api/v1/browser/a/human", json={"reason": "solve the captcha"})
    assert r.status_code == 201 and r.json()["status"] == "pending"
    request_id = r.json()["id"]
    container.human_requests.answer(request_id, True)
    assert client.get(f"/api/v1/browser/a/human/{request_id}").json()["status"] == "done"
    assert client.get(f"/api/v1/browser/b/human/{request_id}").status_code == 404
