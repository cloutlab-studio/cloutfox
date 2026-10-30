"""The panel's bridge: what the page can read and change."""

import json

import pytest

from src.core.container import Container
from src.services.browser import launcher as launcher_mod
from src.ui.bridge import Bridge
from src.ui.push import Pump


class FakeProc:
    def poll(self):
        return None


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(launcher_mod, "spawn_browser", lambda p, d=None, **kw: FakeProc())
    monkeypatch.setattr(launcher_mod, "wait_for_exit", lambda *a: None)
    monkeypatch.setattr(launcher_mod, "terminate", lambda *a, **k: None)
    started = []
    b = Bridge(Container(), lambda: started.append(True))
    b._started = started
    yield b
    b._c.browser_launcher._active_sessions.clear()


def test_start_opens_once_and_starts_the_api(bridge):
    assert bridge.boot()["locked"] is False
    assert bridge.start() == {}
    assert bridge.start() == {}
    assert bridge._started == [True]


def test_snapshot_never_carries_credentials_or_the_rotate_link(bridge):
    bridge.start()
    form = {
        "name": "fb-01",
        "proxy": "socks5://user:secret@192.0.2.10:1080",
        "proxy_rotate_url": "https://provider.example/change?key=topsecret",
        "tags": "fb, us",
    }
    assert bridge.profile_save(None, form) is None
    snap = bridge.snapshot()
    text = json.dumps(snap)
    assert "secret" not in text and "topsecret" not in text
    row = snap["profiles"][0]
    assert row["proxy"] == "192.0.2.10:1080" and row["scheme"] == "socks5"
    assert row["rotate"] is True and row["tags"] == ["fb", "us"]
    # The editor gets the full values; the rest of the page never does.
    detail = bridge.profile_detail("fb-01")
    assert detail["proxy"] == form["proxy"]
    assert detail["proxy_rotate_url"] == form["proxy_rotate_url"]


def test_profile_save_reports_the_field_that_is_wrong(bridge):
    bridge.start()
    assert bridge.profile_save(None, {"name": "../x"})["field"] == "name"
    assert bridge.profile_save(None, {"name": "ok", "proxy": "not a proxy"})["field"] == "proxy"
    assert bridge.profile_save(None, {"name": "ok", "timezone": "Mars/Base"})["field"] == "geo"
    assert bridge.profile_save(None, {"name": "ok", "start_urls": "ftp://x"})["field"] == "extra"
    assert bridge.profile_save(None, {"name": "ok"}) is None
    assert bridge.profile_save(None, {"name": "ok"})["field"] == "name"  # exists


def test_delete_skips_running_profiles(bridge):
    bridge.start()
    for name in ("a", "b"):
        bridge.profile_save(None, {"name": name})
    bl = bridge._c.browser_launcher
    bl._active_sessions["a"] = FakeProc()
    assert bridge.profile_delete(["a", "b"]) == {"deleted": 1, "skipped": 1}
    assert [p["name"] for p in bridge.snapshot()["profiles"]] == ["a"]


def test_settings_update_checks_keys_and_types(bridge):
    assert "error" in bridge.settings_update({"backup_dir": "/tmp"})
    assert "error" in bridge.settings_update({"sound": "yes"})
    assert "error" in bridge.settings_update({"sound_volume": True})
    assert "error" in bridge.settings_update({"motion": "wild"})
    s = bridge.settings_update(
        {"sound": False, "sound_volume": 250, "warmup_sites": ["bbc.com", "not a site"]}
    )
    assert s["sound"] is False and s["sound_volume"] == 100
    assert s["warmup_sites"] == ["bbc.com"]


def test_language_switch_is_saved(bridge):
    result = bridge.set_language("en")
    assert result["language"] == "en" and result["strings"]["launch"] == "Launch"
    assert bridge._c.settings.current.language == "en"
    bridge.set_language("ru")


def test_open_external_takes_only_web_links(bridge, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    assert "error" in bridge.open_external("file:///etc/passwd")
    assert bridge.open_external("https://example.com") == {}
    assert opened == ["https://example.com"]


def test_pump_sends_escaped_data(bridge):
    bridge.start()
    sent = []
    pump = Pump(bridge._c, sent.append)
    pump.log({"id": 1, "at": "00:00:00", "text": "</script><img src=x onerror=alert(1)>"})
    pump.changed()
    pump.tick()
    assert len(sent) == 2
    payload = sent[0].split("push(", 1)[1].rsplit(")", 1)[0]
    assert json.loads(payload)["lines"][0]["text"].startswith("</script>")
    assert json.loads(sent[1].split("push(", 1)[1].rsplit(")", 1)[0]) == {"type": "changed"}
    pump.tick()
    assert len(sent) == 2  # nothing new, nothing sent
