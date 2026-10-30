import pathlib
import re

import pytest

from src.core import config
from src.core.strings import STRINGS

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"


def test_languages_have_same_keys():
    assert set(STRINGS["ru"]) == set(STRINGS["en"])


def test_placeholders_match_between_languages():
    field = re.compile(r"{(\w+)}")
    for key, en in STRINGS["en"].items():
        assert set(field.findall(en)) == set(field.findall(STRINGS["ru"][key])), key


def test_every_used_key_exists():
    used = set()
    for path in SRC.rglob("*.py"):
        used |= set(re.findall(r'get_string\(\s*"(\w+)"', path.read_text(encoding="utf-8")))
    missing = used - set(STRINGS["en"])
    assert not missing, f"get_string keys missing from STRINGS: {sorted(missing)}"


def test_every_key_the_panel_uses_exists():
    # The panel (frontend/) reads the same table through the bridge: t("key").
    used = set()
    panel = SRC.parent / "frontend" / "src"
    for path in [*panel.rglob("*.svelte"), *panel.rglob("*.ts")]:
        text = path.read_text(encoding="utf-8")
        used |= set(re.findall(r'\bt\(\s*"(\w+)"', text))
        # t(cond ? "a" : "b")
        for pair in re.findall(r'\bt\(\s*[\w.!]+\s*\?\s*"(\w+)"\s*:\s*"(\w+)"', text):
            used |= set(pair)
    missing = used - set(STRINGS["en"])
    assert not missing, f"panel keys missing from STRINGS: {sorted(missing)}"


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"LANG": "ru_RU.UTF-8"}, "ru"),
        ({"LANG": "en_US.UTF-8"}, "en"),
        ({"LC_ALL": "de_DE.UTF-8", "LANG": "ru_RU.UTF-8"}, "en"),
        ({"LC_MESSAGES": "ru_UA.UTF-8"}, "ru"),
        ({}, "en"),
    ],
)
def test_system_language(monkeypatch, env, expected):
    monkeypatch.setattr(config.sys, "platform", "linux")
    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert config.system_language() == expected
