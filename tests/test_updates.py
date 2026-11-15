"""The opt-in update check: version comparison and a trusted answer only."""

import json

import pytest

from src.services import updates

GOOD = {
    "tag_name": "v3.2.0",
    "html_url": "https://github.com/cloutlab-studio/cloutfox/releases/tag/v3.2.0",
}


def _answer(payload: dict) -> bytes:
    return json.dumps(payload).encode()


def test_versions_compare_numerically():
    assert updates.is_newer("3.1.10", "3.1.9")
    assert updates.is_newer("v3.2.0", "3.1.9")
    assert updates.is_newer("4.0", "3.1.1")
    assert not updates.is_newer("3.1.1", "3.1.1")
    assert not updates.is_newer("3.1.0", "3.1.1")
    assert not updates.is_newer("nonsense", "3.1.1")
    assert not updates.is_newer("3.1.1", "nonsense")


def test_parse_ignores_a_prefix_and_a_suffix():
    assert updates.parse_version("v3.1.1") == (3, 1, 1)
    assert updates.parse_version("3.2.0-beta.1") == (3, 2, 0)
    assert updates.parse_version("") is None
    assert updates.parse_version("latest") is None


def test_latest_reads_the_github_answer():
    release = updates.latest(fetch=lambda url: _answer(GOOD))
    assert release.version == "3.2.0"
    assert release.url == GOOD["html_url"]


def test_a_page_off_our_releases_is_refused():
    with pytest.raises(updates.UpdateError):
        updates.latest(fetch=lambda url: _answer({**GOOD, "html_url": "https://example.com/evil"}))


def test_a_broken_answer_raises():
    for payload in (
        {},
        {"tag_name": "v1.0.0"},
        ["nope"],
        {"tag_name": "vNaN", "html_url": GOOD["html_url"]},
    ):
        with pytest.raises(updates.UpdateError):
            updates.latest(fetch=lambda url, p=payload: _answer(p))
    with pytest.raises(updates.UpdateError):
        updates.latest(fetch=lambda url: b"not json")


def test_the_request_names_the_app(monkeypatch):
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size):
            assert size == updates.MAX_BYTES
            return _answer(GOOD)

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["user_agent"] = request.get_header("User-agent")
        seen["timeout"] = timeout
        return Response()

    monkeypatch.setattr(updates.urllib.request, "urlopen", fake_urlopen)
    release = updates.latest()
    assert release.version == "3.2.0"
    assert seen["url"] == updates.API
    assert seen["user_agent"].startswith("CloutFox/")
    assert seen["timeout"] == updates.TIMEOUT
