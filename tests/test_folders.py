"""Folders: the tree, moving profiles with it, and the rules for names."""

import json

import pytest

from src.services.profile.codec import profile_from_dict
from src.services.profile.manager import ProfileManager


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return ProfileManager()


@pytest.fixture
def home(tmp_path):
    return tmp_path


def test_a_folder_exists_while_empty(manager, home):
    ok, path = manager.add_folder("Clients/Germany")
    assert ok and path == "Clients/Germany"
    assert manager.list_folders() == ["Clients", "Clients/Germany"]
    saved = json.loads((home / "folders.json").read_text(encoding="utf-8"))
    assert saved == ["Clients", "Clients/Germany"]


def test_moving_profiles_creates_the_folder(manager):
    manager.add_profile("p1", "", "windows")
    manager.add_profile("p2", "", "windows")
    assert manager.move_profiles(["p1", "p2"], "Work") == (2, "Work")
    assert manager.profiles["p1"].folder == "Work"
    assert "Work" in manager.list_folders()


def test_a_created_profile_can_name_its_folder(manager):
    manager.add_profile("p1", "", "windows", folder="Ads/Facebook")
    assert manager.profiles["p1"].folder == "Ads/Facebook"
    assert manager.list_folders() == ["Ads", "Ads/Facebook"]


def test_rename_takes_the_subtree_and_its_profiles(manager):
    manager.add_profile("p1", "", "windows", folder="Clients/Germany")
    manager.add_folder("Clients/Germany/Berlin")
    ok, path = manager.rename_folder("Clients", "Customers")
    assert ok and path == "Customers"
    assert manager.profiles["p1"].folder == "Customers/Germany"
    assert manager.list_folders() == ["Customers", "Customers/Germany", "Customers/Germany/Berlin"]


def test_delete_raises_profiles_one_level(manager):
    manager.add_profile("p1", "", "windows", folder="A/B")
    manager.add_profile("p2", "", "windows", folder="A")
    assert manager.delete_folder("A") == 2
    assert manager.profiles["p1"].folder == ""
    assert manager.profiles["p2"].folder == ""
    assert manager.list_folders() == []
    # Deleting a subfolder leaves its parent and moves the profiles into it.
    manager.move_profiles(["p1"], "A/B")
    assert manager.delete_folder("A/B") == 1
    assert manager.profiles["p1"].folder == "A"
    assert manager.list_folders() == ["A"]


def test_names_follow_the_rules(manager):
    for bad in ("", "A/B/C/D", "A/../B", "bad.", "CON", "a" * 49):
        ok, _ = manager.add_folder(bad)
        assert not ok, bad
    # Typed sloppily, stored tidily: spaces are trimmed and empty levels dropped.
    ok, path = manager.add_folder(" Клиенты // Германия ")
    assert ok and path == "Клиенты/Германия"


def test_a_folder_cannot_go_into_itself(manager):
    manager.add_folder("A/B")
    ok, message = manager.rename_folder("A", "A/C")
    assert not ok
    assert "внутрь" in message or "itself" in message


def test_codec_keeps_a_valid_folder_only():
    assert profile_from_dict({"name": "p", "folder": " A/B "}).folder == "A/B"
    assert profile_from_dict({"name": "p", "folder": "../../etc"}).folder == ""
    assert profile_from_dict({"name": "p"}).folder == ""
