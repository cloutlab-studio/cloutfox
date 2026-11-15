"""Deleting trees on Windows: read-only entries and files another process holds."""

import shutil
import stat
import sys

import pytest

from src.utils import fs


def test_remove_tree_removes_a_tree(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "f.txt").write_text("x")
    assert fs.remove_tree(tmp_path / "a")
    assert not (tmp_path / "a").exists()


def test_remove_tree_missing_dir_is_gone(tmp_path):
    assert fs.remove_tree(tmp_path / "nope") is True


def test_remove_tree_takes_a_read_only_file(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    target = root / "lock"
    target.write_text("x")
    target.chmod(0o400)
    assert fs.remove_tree(root)
    assert not root.exists()


def test_remove_tree_retries_a_file_another_process_holds(tmp_path, monkeypatch):
    root = tmp_path / "p"
    root.mkdir()
    (root / "f").write_text("x")
    real = shutil.rmtree
    calls = {"n": 0}

    def flaky(path, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("another process holds the file")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(fs.shutil, "rmtree", flaky)
    monkeypatch.setattr(fs.time, "sleep", lambda seconds: None)
    assert fs.remove_tree(root)
    assert calls["n"] == 3


def test_remove_tree_reports_a_hopeless_tree(tmp_path, monkeypatch):
    root = tmp_path / "p"
    root.mkdir()
    (root / "f").write_text("x")

    def blocked(*args, **kwargs):
        raise PermissionError("busy")

    monkeypatch.setattr(fs.shutil, "rmtree", blocked)
    monkeypatch.setattr(fs.time, "sleep", lambda seconds: None)
    assert fs.remove_tree(root) is False
    assert root.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="mode bits are a POSIX idea")
def test_write_private_keeps_the_file_for_its_owner(tmp_path):
    target = tmp_path / "profiles.json"
    target.write_text("old")
    fs.write_private(target, b"{}")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="mode bits are a POSIX idea")
def test_make_private_keeps_the_folder_for_its_owner(tmp_path):
    folder = tmp_path / "data"
    folder.mkdir()
    folder.chmod(0o755)
    fs.make_private(folder)
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700


@pytest.mark.skipif(sys.platform == "win32", reason="mode bits are a POSIX idea")
def test_profiles_file_and_data_dirs_are_private(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from src.services.profile.manager import ProfileManager

    manager = ProfileManager()
    manager.add_profile("p", "", "windows")
    mode = lambda path: stat.S_IMODE(path.stat().st_mode)  # noqa: E731
    assert mode(tmp_path / "profiles.json") == 0o600
    assert mode(tmp_path / "camoufox_data") == 0o700
    assert mode(tmp_path / "camoufox_data" / "p") == 0o700
