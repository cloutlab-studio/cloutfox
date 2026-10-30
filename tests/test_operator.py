"""Settings, shared extensions, the geo guard and backups."""

import json
import zipfile
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.container import Container
from src.core.settings import Settings, SettingsStore
from src.models.profile import Profile
from src.services import backup
from src.services.browser import extensions, launch_opts
from src.services.proxy.geo_check import GeoCheckResult, GeoWarning, SourceResult
from src.services.security import crypto
from src.services.security.vault import Vault

FAST_KDF = {"alg": "argon2id", "t": 1, "m": 8, "p": 1}


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(extensions, "EXTENSIONS_DIR", str(tmp_path / "extensions"))
    monkeypatch.setattr(crypto, "DEFAULT_KDF", FAST_KDF)
    return tmp_path


def _xpi(path, manifest=None, extra=None):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest or {"name": "Demo", "version": "1.2"}))
        for name, data in (extra or {}).items():
            z.writestr(name, data)
    return str(path)


# --- settings --------------------------------------------------------------------------


def test_settings_keep_known_values_of_the_right_type(workdir):
    path = workdir / "settings.json"
    path.write_text(json.dumps({"geo_guard": True, "backup_hours": "6", "nope": 1}))
    store = SettingsStore(path)
    assert store.current.geo_guard is True
    assert store.current.backup_hours == 0
    store.update(backup_hours=12)
    assert SettingsStore(path).current.backup_hours == 12
    with pytest.raises(TypeError):
        store.update(nope=1)


def test_unreadable_settings_fall_back_to_defaults(workdir):
    (workdir / "settings.json").write_text("{broken")
    assert SettingsStore(workdir / "settings.json").current == Settings()


# --- extensions ------------------------------------------------------------------------


def test_install_list_resolve_and_remove(workdir):
    ext_id = extensions.install(_xpi(workdir / "demo addon.xpi"))
    assert ext_id == "demo-addon"
    assert extensions.available() == [
        {"id": "demo-addon", "name": "Demo", "version": "1.2", "engine": "camoufox"}
    ]
    # The same file again gets its own folder.
    assert extensions.install(_xpi(workdir / "demo addon.xpi")) == "demo-addon-2"
    assert extensions.paths(["demo-addon", "missing", "../etc"], "camoufox") == [
        str((workdir / "extensions" / "demo-addon").resolve())
    ]
    extensions.remove("demo-addon")
    extensions.remove("..")
    assert [e["id"] for e in extensions.available()] == ["demo-addon-2"]
    assert (workdir / "extensions").is_dir()


def test_install_from_a_folder_and_localised_names(workdir):
    src = workdir / "unpacked"
    src.mkdir()
    (src / "manifest.json").write_text(json.dumps({"name": "__MSG_appName__", "version": "3"}))
    ext_id = extensions.install(str(src))
    assert extensions.available() == [
        {"id": ext_id, "name": ext_id, "version": "3", "engine": "chrome"}
    ]


def test_install_refuses_unsafe_or_empty_archives(workdir):
    with pytest.raises(extensions.ExtensionError, match="unsafe"):
        extensions.install(_xpi(workdir / "evil.xpi", extra={"../../escape.txt": "x"}))
    assert not (workdir / "escape.txt").exists()
    with zipfile.ZipFile(workdir / "empty.zip", "w") as z:
        z.writestr("readme.txt", "no manifest")
    with pytest.raises(extensions.ExtensionError, match="manifest"):
        extensions.install(str(workdir / "empty.zip"))
    (workdir / "bad.xpi").write_bytes(b"not a zip")
    with pytest.raises(extensions.ExtensionError):
        extensions.install(str(workdir / "bad.xpi"))
    assert extensions.available() == []


@pytest.mark.parametrize(
    ("file", "manifest", "extra", "engine"),
    [
        ("a.xpi", None, None, "camoufox"),
        ("a.crx", None, None, "chrome"),
        ("a.zip", None, None, "chrome"),
        (
            "a.zip",
            {"name": "A", "browser_specific_settings": {"gecko": {"id": "a@x"}}},
            None,
            "camoufox",
        ),
        ("a.zip", {"name": "A", "applications": {"gecko": {}}}, None, "camoufox"),
        ("a.zip", None, {"META-INF/mozilla.rsa": "sig"}, "camoufox"),
        ("a.zip", None, {"_metadata/verified_contents.json": "[]"}, "chrome"),
    ],
)
def test_engine_follows_file_type_and_manifest(workdir, file, manifest, extra, engine):
    ext_id = extensions.install(_xpi(workdir / file, manifest, extra))
    assert extensions.available()[0]["engine"] == engine
    other = "chrome" if engine == "camoufox" else "camoufox"
    assert extensions.paths([ext_id], engine) and not extensions.paths([ext_id], other)
    assert extensions.mismatched([ext_id, "gone"], other) == [ext_id]
    assert extensions.mismatched([ext_id], engine) == []


def test_launch_skips_extensions_of_the_other_engine(workdir, monkeypatch):
    from src.services.browser import launcher as launcher_mod
    from src.services.browser.launcher import BrowserLauncher

    firefox = extensions.install(_xpi(workdir / "ff.xpi"))
    chrome = extensions.install(_xpi(workdir / "ch.crx"))
    spawned = []
    monkeypatch.setattr(
        launcher_mod, "spawn_browser", lambda profile, *a, **k: spawned.append(profile)
    )
    monkeypatch.setattr(launcher_mod, "wait_for_exit", lambda *a: None)
    bl = BrowserLauncher()
    monkeypatch.setattr(bl, "_monitor_process", lambda *a: None)
    logs = []
    profile = Profile(name="p", extensions=[firefox, chrome])
    bl.start_thread(profile, logs.append)
    assert any(chrome in line for line in logs)
    assert not any(firefox in line for line in logs[1:])
    opts = json.loads(launch_opts.encode(profile))
    assert opts["extensions"] == [str((workdir / "extensions" / firefox).resolve())]
    bl._active_sessions.clear()


def test_launch_options_carry_extension_paths_and_app_options(workdir):
    ext_id = extensions.install(_xpi(workdir / "demo.xpi"))
    profile = Profile(name="p", extensions=[ext_id, "gone"])
    opts = json.loads(launch_opts.encode(profile, geo_guard=True))
    assert opts["extensions"] == [str((workdir / "extensions" / ext_id).resolve())]
    assert opts["geo_guard"] is True


def test_api_lists_extensions_and_refuses_unknown_ids(workdir):
    ext_id = extensions.install(_xpi(workdir / "demo.xpi"))
    client = TestClient(create_app(Container()), base_url="http://127.0.0.1")
    assert client.get("/api/v1/extensions").json()["extensions"][0]["id"] == ext_id
    r = client.post("/api/v1/profiles", json={"name": "p", "extensions": [ext_id]})
    assert r.status_code == 201, r.text
    assert r.json()["extensions"] == [ext_id]
    r = client.patch("/api/v1/profiles/p", json={"extensions": ["missing"]})
    assert r.status_code == 400
    assert "missing" in r.json()["detail"]
    assert client.patch("/api/v1/profiles/p", json={"extensions": []}).json()["extensions"] == []
    chrome_ext = extensions.install(_xpi(workdir / "other.crx"))
    r = client.patch("/api/v1/profiles/p", json={"extensions": [chrome_ext]})
    assert r.status_code == 400 and "not made for camoufox" in r.json()["detail"]
    r = client.post(
        "/api/v1/profiles", json={"name": "c", "extensions": [ext_id], "engine": "chrome"}
    )
    assert r.status_code == 400 and "not made for chrome" in r.json()["detail"]


# --- geo guard -------------------------------------------------------------------------


def _geo(monkeypatch, exit_ip, warnings=(), error=None, country="DE", sources=None):
    from src.services.proxy import geo_check

    if sources is None:
        sources = [SourceResult("cloudflare", ip=exit_ip, country=country)]
    result = GeoCheckResult(
        exit_ip, country, "Europe/Berlin", "de-DE", "Europe/Berlin", False, "de-DE", False,
        sources, list(warnings), error,
    )  # fmt: skip
    monkeypatch.setattr(geo_check, "check_geo", lambda *a: result)


def test_geo_guard_passes_a_clean_exit(monkeypatch):
    _geo(monkeypatch, "203.0.113.5")
    said = []
    launch_opts.geo_guard("socks5://user:pass@203.0.113.5:1080", "", "", said.append)
    assert "203.0.113.5" in said[-1]


@pytest.mark.parametrize(
    "warnings, exit_ip",
    [
        ([GeoWarning("hosting", {"source": "ipinfo"})], "203.0.113.5"),
        (
            [GeoWarning("country_mismatch", {"source": "ip-api", "got": "FR", "expected": "DE"})],
            "203.0.113.5",
        ),
        ([], None),
    ],
)
def test_geo_guard_stops_mismatches_and_unknown_exits(monkeypatch, warnings, exit_ip):
    _geo(monkeypatch, exit_ip, warnings, "timeout")
    with pytest.raises(launch_opts.GeoGuardError):
        launch_opts.geo_guard(None, "", "", lambda _: None)


def test_geo_guard_fails_closed_when_nothing_could_be_compared(monkeypatch):
    # No GeoIP country for the exit: compare() has nothing to check.
    _geo(monkeypatch, "203.0.113.5", country=None)
    with pytest.raises(launch_opts.GeoGuardError, match="country"):
        launch_opts.geo_guard(None, "", "", lambda _: None)
    # Every outside source failed: no warnings, but no check either.
    failed = [SourceResult(s, error="timed out") for s in ("cloudflare", "ipinfo", "ip-api")]
    _geo(monkeypatch, "203.0.113.5", sources=failed)
    with pytest.raises(launch_opts.GeoGuardError, match="no source"):
        launch_opts.geo_guard(None, "", "", lambda _: None)


# --- backups ---------------------------------------------------------------------------


def _home(root):
    (root / "profiles.json").write_text('{"p": {"name": "p"}}')
    (root / "settings.json").write_text("{}")
    data = root / "camoufox_data" / "p"
    data.mkdir(parents=True)
    (data / "cookies.sqlite").write_bytes(b"cookie" * 1000)
    (data / "lock").symlink_to("127.0.0.1:+4242")
    temp = root / "camoufox_data" / "temp-1234"
    temp.mkdir()
    (temp / "junk").write_text("x")


def test_plain_backup_round_trip_skips_links_and_one_time_profiles(workdir):
    _home(workdir)
    dest = workdir / "backups"
    dest.mkdir()
    path = backup.backup_now(str(dest), 7, Vault(workdir / "vault.json"))
    assert path.suffix == ".zip"
    out = workdir / "restored"
    backup.restore(str(path), str(out))
    assert (out / "camoufox_data" / "p" / "cookies.sqlite").read_bytes() == b"cookie" * 1000
    assert (out / "profiles.json").exists()
    assert not (out / "camoufox_data" / "p" / "lock").exists()
    assert not (out / "camoufox_data" / "temp-1234").exists()
    with pytest.raises(backup.BackupError, match="not empty"):
        backup.restore(str(path), str(out))


def test_encrypted_backup_opens_with_password_or_recovery_key(workdir):
    _home(workdir)
    vault = Vault(workdir / "vault.json")
    recovery = vault.enable("correct horse")
    dest = workdir / "backups"
    dest.mkdir()
    path = backup.backup_now(str(dest), 7, vault)
    assert path.suffix == ".cfxbak"
    assert b"cookie" not in path.read_bytes()
    with pytest.raises(backup.BackupError, match="encrypted"):
        backup.restore(str(path), str(workdir / "a"))
    with pytest.raises(backup.BackupError, match="wrong"):
        backup.restore(str(path), str(workdir / "b"), "wrong horse")
    backup.restore(str(path), str(workdir / "c"), "correct horse")
    backup.restore(str(path), str(workdir / "d"), recovery)
    for out in ("c", "d"):
        cookies = workdir / out / "camoufox_data" / "p" / "cookies.sqlite"
        assert cookies.read_bytes() == b"cookie" * 1000


def test_prune_keeps_the_newest_and_ignores_other_files(workdir):
    dest = workdir / "backups"
    dest.mkdir()
    for stamp in ("20260101-000000", "20260102-000000", "20260103-000000"):
        (dest / f"{backup.PREFIX}{stamp}.zip").write_text("x")
    (dest / "notes.txt").write_text("mine")
    backup.prune(dest, 2)
    assert sorted(p.name for p in dest.iterdir()) == [
        f"{backup.PREFIX}20260102-000000.zip",
        f"{backup.PREFIX}20260103-000000.zip",
        "notes.txt",
    ]


def test_backup_is_due_only_when_on_and_old_enough():
    now = datetime(2026, 10, 29, 12, 0)
    assert not backup.due(Settings(backup_dir="/b", backup_hours=0), now)
    assert not backup.due(Settings(backup_dir="", backup_hours=6), now)
    assert backup.due(Settings(backup_dir="/b", backup_hours=6), now)
    recent = (now - timedelta(hours=5)).isoformat()
    old = (now - timedelta(hours=7)).isoformat()
    assert not backup.due(Settings(backup_dir="/b", backup_hours=6, last_backup=recent), now)
    assert backup.due(Settings(backup_dir="/b", backup_hours=6, last_backup=old), now)


def test_self_destruct_also_removes_this_apps_backups(workdir):
    dest = workdir / "backups"
    dest.mkdir()
    (dest / f"{backup.PREFIX}20260101-000000.zip").write_text("x")
    (dest / "notes.txt").write_text("mine")
    container = Container()
    container.settings.update(backup_dir=str(dest))
    (dest / f"{backup.PREFIX}20260102-000000.zip.part").write_text("half")
    paths = container.wipe_paths()
    assert str(dest / f"{backup.PREFIX}20260101-000000.zip") in paths
    assert str(dest / f"{backup.PREFIX}20260102-000000.zip.part") in paths
    assert str(dest / "notes.txt") not in paths
    # The emptied app neither shows the old folder nor makes new backups.
    assert container.settings.current.backup_dir == ""
    with pytest.raises(backup.BackupError):
        container.backups.run_now()


def test_a_cancelled_backup_leaves_nothing(workdir):
    import threading

    _home(workdir)
    dest = workdir / "backups"
    dest.mkdir()
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(backup.BackupError, match="cancelled"):
        backup.backup_now(str(dest), 7, Vault(workdir / "vault.json"), cancel)
    assert list(dest.iterdir()) == []


def test_a_failed_backup_shreds_its_partial_file(workdir, monkeypatch):
    import threading

    from src.services.security import service

    _home(workdir)
    dest = workdir / "backups"
    dest.mkdir()
    shredded = []

    def spy(path):
        shredded.append((path.name, path.stat().st_size))
        service.shred(path)

    monkeypatch.setattr(backup, "shred", spy)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(backup.BackupError):
        backup.backup_now(str(dest), 7, Vault(workdir / "vault.json"), cancel)
    assert len(shredded) == 1
    assert shredded[0][0].endswith(".part")
    assert list(dest.iterdir()) == []


def test_shred_overwrites_large_files_in_steps(tmp_path, monkeypatch):
    from src.services.security import service

    sizes = []
    real = service.os.urandom
    monkeypatch.setattr(service.os, "urandom", lambda n: sizes.append(n) or real(n))
    big = tmp_path / "big.bin"
    big.write_bytes(b"\0" * ((3 << 20) + 5))
    service.shred(big)
    assert not big.exists()
    assert sizes == [1 << 20, 1 << 20, 1 << 20, 5]
