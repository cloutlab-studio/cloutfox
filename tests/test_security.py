"""Master password, recovery key, self-destruct and per-profile encryption."""

import io
import json
import pathlib

import pytest

from src.services.profile.manager import ProfileManager
from src.services.security import crypto, profile_data
from src.services.security.profile_data import ProfileData, ProfileLocked
from src.services.security.service import SecurityService
from src.services.security.vault import Vault, VaultError

FAST_KDF = {"alg": "argon2id", "t": 1, "m": 8, "p": 1}


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch, tmp_path):
    # Real parameters cost ~0.3 s per derivation; tests derive dozens of keys.
    monkeypatch.setattr(crypto, "DEFAULT_KDF", FAST_KDF)
    work = tmp_path / "ram"
    work.mkdir()
    monkeypatch.setattr(profile_data, "work_root", lambda: work)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    vault = Vault(tmp_path / "vault.json")
    data = ProfileData(
        str(tmp_path / "camoufox_data"),
        str(tmp_path / "encrypted"),
        str(tmp_path / "keys.json"),
        vault,
    )
    pm = ProfileManager(vault, data)
    security = SecurityService(
        vault,
        data,
        lambda: pm,
        lambda: [str(tmp_path / "profiles.json"), str(tmp_path / "camoufox_data")],
    )
    return tmp_path, vault, data, pm, security


def _fill(path: pathlib.Path) -> None:
    (path / "storage").mkdir(parents=True, exist_ok=True)
    (path / "cookies.sqlite").write_bytes(b"secret-cookie" * 100_000)
    (path / "storage" / "x.txt").write_text("hello")
    # Firefox keeps a "lock" symlink in a running profile.
    (path / "lock").symlink_to("127.0.0.1:+4242")


# --- stream format ---------------------------------------------------------------------


def _stream(data: bytes, key: bytes) -> bytes:
    out = io.BytesIO()
    w = crypto.StreamWriter(out, key, b"TEST\n", {"v": 1})
    w.write(data)
    w.close()
    return out.getvalue()


def _read(blob: bytes, key: bytes) -> bytes:
    src = io.BytesIO(blob)
    header = crypto.read_header(src, b"TEST\n")
    return crypto.StreamReader(src, key, b"TEST\n", header).read()


def test_stream_round_trip_across_chunks():
    key = crypto.new_key()
    data = bytes(range(256)) * 9000  # > 2 chunks
    assert _read(_stream(data, key), key) == data
    assert _read(_stream(b"", key), key) == b""


def test_stream_detects_wrong_key_tamper_and_truncation():
    key = crypto.new_key()
    blob = _stream(b"x" * (crypto.CHUNK + 10), key)
    with pytest.raises(crypto.DecryptError):
        _read(blob, crypto.new_key())
    tampered = bytearray(blob)
    tampered[-5] ^= 1
    with pytest.raises(crypto.DecryptError):
        _read(bytes(tampered), key)
    # Cutting off the final chunk must not read as a complete, shorter stream.
    last_chunk = 4 + 10 + 16  # length, 10 bytes of data, GCM tag
    with pytest.raises(crypto.DecryptError):
        _read(blob[:-last_chunk], key)


# --- vault -----------------------------------------------------------------------------


def test_vault_enable_unlock_change_and_recovery(tmp_path):
    v = Vault(tmp_path / "vault.json")
    assert not v.enabled and v.unlock("anything")
    recovery = v.enable("correct horse")
    dek = v.dek
    assert "correct horse" not in (tmp_path / "vault.json").read_text()

    v2 = Vault(tmp_path / "vault.json")
    assert v2.enabled and not v2.unlocked
    assert not v2.unlock("wrong password")
    assert v2.unlock("correct horse") and v2.dek == dek
    v2.change("battery staple")
    assert not Vault(tmp_path / "vault.json").unlock("correct horse")

    v3 = Vault(tmp_path / "vault.json")
    assert not v3.unlock_with_recovery("AAAA-BBBB")
    assert v3.unlock_with_recovery(recovery.lower().replace("-", " ")) and v3.dek == dek


def test_duress_password_is_recognised_and_must_differ(tmp_path):
    v = Vault(tmp_path / "vault.json")
    with pytest.raises(VaultError):
        v.set_duress("boom-boom")
    v.enable("master-pass")
    with pytest.raises(VaultError):
        v.set_duress("master-pass")
    v.set_duress("boom-boom")
    v2 = Vault(tmp_path / "vault.json")
    assert v2.is_duress("boom-boom") and not v2.is_duress("master-pass")
    with pytest.raises(VaultError):
        v.change("boom-boom")


def test_damaged_vault_does_not_turn_encryption_off(tmp_path):
    (tmp_path / "vault.json").write_text("{not json")
    with pytest.raises(VaultError):
        Vault(tmp_path / "vault.json")


# --- profiles.json ---------------------------------------------------------------------


def test_profiles_json_is_sealed_with_the_master_password(env):
    tmp_path, vault, data, pm, security = env
    pm.add_profile("shop", "socks5://user:pass@203.0.113.10:1080", "windows")
    security.enable_master("master-pass")
    raw = (tmp_path / "profiles.json").read_bytes()
    assert b"203.0.113.10" not in raw and b"shop" not in raw

    locked = Vault(tmp_path / "vault.json")
    unreadable = ProfileManager(locked, data)
    assert unreadable.load_error and not unreadable.profiles
    unreadable.add_profile("x", "", "windows")  # must not overwrite the sealed file
    assert (tmp_path / "profiles.json").read_bytes() == raw

    locked.unlock("master-pass")
    assert "shop" in ProfileManager(locked, data).profiles

    security.disable_master()
    assert b"203.0.113.10" in (tmp_path / "profiles.json").read_bytes()
    assert not (tmp_path / "vault.json").exists()


# --- profile data ----------------------------------------------------------------------


def test_profile_password_encryption_round_trip(env):
    tmp_path, vault, data, pm, _ = env
    pm.add_profile("p", "", "windows")
    _fill(data.plain_dir("p"))
    data.encrypt("p", "profile-pass")
    assert not data.plain_dir("p").exists()
    assert b"secret-cookie" not in data.container("p").read_bytes()
    assert data.path("p") is None

    fresh = ProfileData(str(data.data_dir), str(data.encrypted_dir), str(data.keys_file), vault)
    assert fresh.needs_password("p")
    with pytest.raises(ProfileLocked):
        fresh.acquire("p")
    assert not fresh.unlock("p", "nope")
    assert fresh.unlock("p", "profile-pass")
    work = fresh.acquire("p")
    assert (work / "storage" / "x.txt").read_text() == "hello"
    assert not (work / "lock").exists()
    (work / "storage" / "x.txt").write_text("changed")
    fresh.release("p")
    assert not work.exists()

    fresh.decrypt("p")
    assert (data.plain_dir("p") / "storage" / "x.txt").read_text() == "changed"
    assert not data.container("p").exists() and not fresh.is_encrypted("p")


def test_acquire_is_shared_and_packs_on_last_release(env):
    _, _, data, pm, security = env
    security.enable_master("master-pass")
    pm.add_profile("p", "", "windows")
    _fill(data.plain_dir("p"))
    data.encrypt("p", None)
    a = data.acquire("p")
    b = data.acquire("p")
    assert a == b
    data.release("p")
    assert a.exists()
    data.release("p")
    assert not a.exists()


def test_without_master_a_profile_needs_its_own_password(env):
    _, _, data, pm, _ = env
    pm.add_profile("p", "", "windows")
    with pytest.raises(profile_data.ProfileDataError):
        data.encrypt("p", None)


def test_master_off_decrypts_master_only_profiles_and_keeps_password_ones(env):
    tmp_path, vault, data, pm, security = env
    security.enable_master("master-pass")
    for name in ("m", "both"):
        pm.add_profile(name, "", "windows")
        _fill(data.plain_dir(name))
    data.encrypt("m", None)
    data.encrypt("both", "profile-pass")
    assert data.key_by("both") == ["password", "master"]
    security.disable_master()
    assert not data.is_encrypted("m") and (data.plain_dir("m") / "storage" / "x.txt").exists()
    assert data.key_by("both") == ["password"]
    fresh = ProfileData(str(data.data_dir), str(data.encrypted_dir), str(data.keys_file), vault)
    assert fresh.unlock("both", "profile-pass")


def test_master_on_adds_the_outer_layer_to_password_profiles(env):
    _, vault, data, pm, security = env
    pm.add_profile("p", "", "windows")
    _fill(data.plain_dir("p"))
    data.encrypt("p", "profile-pass")
    security.enable_master("master-pass")
    assert data.key_by("p") == ["password", "master"]
    fresh = ProfileData(str(data.data_dir), str(data.encrypted_dir), str(data.keys_file), vault)
    assert fresh.unlock("p", "profile-pass")


def test_rename_and_delete_follow_the_container(env):
    _, _, data, pm, security = env
    security.enable_master("master-pass")
    pm.add_profile("old", "", "windows")
    _fill(data.plain_dir("old"))
    data.encrypt("old", None)
    assert pm.update_profile("old", "new", "", "windows")
    assert data.is_encrypted("new") and not data.is_encrypted("old")
    assert "new" in json.loads(data.keys_file.read_text())
    pm.delete_profile("new")
    assert not data.is_encrypted("new")
    assert "new" not in json.loads(data.keys_file.read_text())


def test_export_of_an_encrypted_profile_is_plain(env):
    tmp_path, _, data, pm, security = env
    security.enable_master("master-pass")
    pm.add_profile("p", "", "windows")
    _fill(data.plain_dir("p"))
    data.encrypt("p", None)
    ok, zip_path = pm.export_profile("p", str(tmp_path))
    assert ok
    import zipfile

    assert "data/storage/x.txt" in zipfile.ZipFile(zip_path).namelist()
    assert not data.is_open("p")


# --- self-destruct ---------------------------------------------------------------------


def test_self_destruct_wipes_keys_then_data(env):
    tmp_path, vault, data, pm, security = env
    security.enable_master("master-pass")
    security.set_duress("burn-it-all")
    pm.add_profile("p", "", "windows")
    _fill(data.plain_dir("p"))
    data.encrypt("p", None)
    pm.add_profile("plain", "", "windows")
    _fill(data.plain_dir("plain"))

    fresh_vault = Vault(tmp_path / "vault.json")
    fresh = SecurityService(fresh_vault, data, lambda: pm, security._wipe_paths)
    assert fresh.locked
    assert fresh.unlock("master-pass ") == "wrong"
    assert fresh.unlock("burn-it-all") == "wiped"
    for gone in ("vault.json", "keys.json", "encrypted", "profiles.json", "camoufox_data"):
        assert not (tmp_path / gone).exists(), gone
    assert not fresh.locked and not fresh_vault.enabled


def test_api_refuses_a_profile_that_needs_its_password(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from src.api.app import create_app
    from src.core.container import Container

    monkeypatch.chdir(tmp_path)
    container = Container()
    client = TestClient(create_app(container), base_url="http://127.0.0.1")
    client.post("/api/v1/profiles", json={"name": "p"})
    container.profile_data.encrypt("p", "profile-pass")
    container.profile_data.lock_all()
    body = client.get("/api/v1/profiles/p").json()
    assert body["encrypted"] and body["needs_password"]
    assert client.post("/api/v1/browser/p/launch").status_code == 423
    assert client.get("/api/v1/profiles/p/cookies").status_code == 423


def test_a_failed_pack_keeps_the_unpacked_copy(env, monkeypatch):
    _, _, data, pm, security = env
    security.enable_master("master-pass")
    pm.add_profile("p", "", "windows")
    _fill(data.plain_dir("p"))
    data.encrypt("p", None)
    work = data.acquire("p")
    (work / "storage" / "x.txt").write_text("session")

    def disk_full(*_):
        raise OSError("No space left on device")

    monkeypatch.setattr(data, "_pack", disk_full)
    with pytest.raises(OSError):
        data.release("p")
    monkeypatch.undo()
    monkeypatch.setattr(profile_data, "work_root", lambda: work.parent.parent)
    assert (data.acquire("p") / "storage" / "x.txt").read_text() == "session"
