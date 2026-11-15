"""The diagnostics archive: useful to the developer, free of secrets."""

import json
import zipfile

from src.core import config
from src.core.settings import Settings
from src.models.profile import Profile
from src.services import diagnostics


class _Data:
    def is_encrypted(self, name: str) -> bool:
        return name == "sealed"


class _Profiles:
    profiles = {
        "alpha": Profile(
            name="alpha",
            proxy="user:pass@192.0.2.10:8080",
            tags=["fb"],
            status="active",
            last_launch={"at": "2026-10-29T14:05:00+03:00", "ip": "192.0.2.10", "country": "US"},
        ),
        "sealed": Profile(
            name="sealed",
            wireguard="198.51.100.7:51820",
            proxy_rotate_url="https://rotate.test/change?key=ROTATESECRET",
        ),
    }


class _Launcher:
    def running_profile_names(self) -> set[str]:
        return {"alpha"}


class _Container:
    settings = type("S", (), {"current": Settings()})()
    profile_data = _Data()
    profile_manager = _Profiles()
    browser_launcher = _Launcher()


def _texts(archive: bytes) -> dict[str, str]:
    import io

    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        return {name: zf.read(name).decode("utf-8", errors="replace") for name in zf.namelist()}


def test_archive_holds_no_secrets(tmp_path, monkeypatch):
    log = tmp_path / "logs"
    log.mkdir()
    (log / "cloutfox_20260101.log").write_text("started\n", encoding="utf-8")
    monkeypatch.setattr(config, "LOG_DIR", str(log))

    texts = _texts(diagnostics.build(_Container()))
    joined = "\n".join(texts.values())

    for secret in ("user:pass", "192.0.2.10", "198.51.100.7", "ROTATESECRET", "rotate.test"):
        assert secret not in joined, secret
    assert set(texts) >= {"environment.json", "profiles.json", "processes.txt", "README.txt"}
    assert "logs/cloutfox_20260101.log" in texts

    profiles = json.loads(texts["profiles.json"])
    alpha = next(p for p in profiles["profiles"] if p["name"] == "alpha")
    assert alpha["has_proxy"] is True
    assert alpha["proxy_scheme"] == ""
    assert alpha["running"] is True


def test_panel_numbers_are_untrusted(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", str(tmp_path))
    panel = {
        "device_pixel_ratio": 2,
        "screen": "3840x2160",
        "user_agent": "x" * 5000,
        "secret": "nope",
        "nested": {"a": 1},
        "heap_used": True,
    }
    env = json.loads(_texts(diagnostics.build(_Container(), panel))["environment.json"])
    assert env["panel"]["device_pixel_ratio"] == 2
    assert len(env["panel"]["user_agent"]) == diagnostics.MAX_TEXT
    assert "secret" not in env["panel"] and "nested" not in env["panel"]
    assert env["panel"]["heap_used"] is True


def test_export_writes_the_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", str(tmp_path))
    dest = tmp_path / "out" / "report.zip"
    diagnostics.export(_Container(), dest)
    assert dest.is_file()
    assert not (tmp_path / "out" / "report.zip.tmp").exists()
    with zipfile.ZipFile(dest) as zf:
        assert "environment.json" in zf.namelist()


def test_locked_vault_still_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOG_DIR", str(tmp_path))

    class Locked(_Container):
        @property
        def profile_manager(self):
            raise RuntimeError("profiles are locked by the master password")

    report = json.loads(_texts(diagnostics.build(Locked()))["profiles.json"])
    assert report["locked"] is True
    assert report["error"] == "RuntimeError"
