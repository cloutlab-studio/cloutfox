"""Packing a profile back after a stop, when a killed browser still holds its files."""

import pytest

from src.services.security import crypto, profile_data
from src.services.security.profile_data import ProfileData
from src.services.security.vault import Vault

FAST_KDF = {"alg": "argon2id", "t": 1, "m": 8, "p": 1}


@pytest.fixture(autouse=True)
def fast_kdf(monkeypatch, tmp_path):
    monkeypatch.setattr(crypto, "DEFAULT_KDF", FAST_KDF)
    work = tmp_path / "ram"
    work.mkdir()
    monkeypatch.setattr(profile_data, "work_root", lambda: work)
    monkeypatch.setattr(profile_data.time, "sleep", lambda seconds: None)


@pytest.fixture
def data(tmp_path):
    (tmp_path / "data" / "p").mkdir(parents=True)
    (tmp_path / "data" / "p" / "cookies.sqlite").write_text("cookie")
    d = ProfileData(
        str(tmp_path / "data"),
        str(tmp_path / "enc"),
        str(tmp_path / "keys.json"),
        Vault(tmp_path / "vault.json"),
    )
    d.encrypt("p", "pw")
    d.unlock("p", "pw")
    return d


def test_pack_is_retried_when_a_file_is_still_locked(data, monkeypatch):
    work = data.acquire("p")
    real = data._pack
    calls = {"n": 0}

    def flaky(name, src, key):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("the browser still holds its files")
        return real(name, src, key)

    monkeypatch.setattr(data, "_pack", flaky)
    data.release("p")

    assert calls["n"] == 2
    assert not work.exists()
    assert data.container("p").stat().st_size > 0


def test_a_hopeless_pack_keeps_the_newer_copy_for_the_next_start(data, monkeypatch):
    work = data.acquire("p")
    real = data._pack

    def blocked(name, src, key):
        raise PermissionError("still open")

    monkeypatch.setattr(data, "_pack", blocked)
    before = data.container("p").stat().st_mtime_ns
    data.release("p")

    assert work.exists() and (work / profile_data._OPEN_MARKER).exists()
    assert data.container("p").stat().st_mtime_ns == before
    # The next start reuses the newer unpacked copy, not the older container.
    monkeypatch.setattr(data, "_pack", real)
    assert data.acquire("p") == work
    data.release("p")
