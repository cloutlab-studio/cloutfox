import asyncio

import pytest

from src.services.browser.control import ControlError, PageController, _check_files, _check_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("example.com", "https://example.com"),
        ("http://a.vn/x", "http://a.vn/x"),
        ("about:blank", "about:blank"),
        ("localhost:8080/x", "https://localhost:8080/x"),
    ],
)
def test_allowed_urls(url, expected):
    assert _check_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/Windows/win.ini",
        "view-source:https://a.com",
        "javascript:alert(1)",
        "chrome://x",
        "about:config",
        "about:logins",
        "data:text/html,<script>alert(1)</script>",
    ],
)
def test_blocked_urls(url):
    with pytest.raises(ControlError):
        _check_url(url)


class FakePage:
    def __init__(self, url="about:blank"):
        self.url = url
        self.closed = False

    def is_closed(self):
        return self.closed

    async def title(self):
        return "T"

    async def goto(self, url, wait_until="load"):
        self.url = url

    async def close(self):
        self.closed = True

    async def bring_to_front(self):
        pass


class FakeContext:
    def __init__(self, n=1):
        self.pages = [FakePage(f"https://p{i}.test/") for i in range(n)]

    async def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page


def run(coro):
    return asyncio.run(coro)


def test_dispatch_rejects_unknown_action_and_bad_params():
    c = PageController(FakeContext())
    with pytest.raises(ControlError, match="Unknown action"):
        run(c.dispatch("rm_rf", {}))
    with pytest.raises(ControlError, match="Invalid parameters"):
        run(c.dispatch("navigate", {"nope": 1}))


def test_navigate_uses_active_tab():
    ctx = FakeContext(2)
    c = PageController(ctx)
    result = run(c.dispatch("navigate", {"url": "example.com"}))
    assert result == {"url": "https://example.com", "title": "T"}
    assert ctx.pages[-1].url == "https://example.com"


def test_tabs_select_and_close():
    ctx = FakeContext(2)
    c = PageController(ctx)
    tabs = run(c.dispatch("tab_select", {"index": 0}))["tabs"]
    assert [t["active"] for t in tabs] == [True, False]
    tabs = run(c.dispatch("tab_close", {"index": 0}))["tabs"]
    assert [t["url"] for t in tabs] == ["https://p1.test/"]
    with pytest.raises(ControlError, match="last tab"):
        run(c.dispatch("tab_close", {"index": 0}))
    with pytest.raises(ControlError, match="No tab"):
        run(c.dispatch("tab_select", {"index": 5}))


# ---------------------------------------------------------------------------
# Percent-encoded scheme bypass (fix 3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "%66ile:///C:/Windows/win.ini",  # decodes to file:///...
        "java%73cript:alert(1)",  # decodes to javascript:...
        "%76iew-source:https://a.com",  # decodes to view-source:...
    ],
)
def test_percent_encoded_blocked_schemes(url):
    """Percent-encoded disallowed schemes must be caught before scheme detection."""
    with pytest.raises(ControlError):
        _check_url(url)


@pytest.mark.parametrize("url", ["[", "[]", "[::1", "http://[::1"])
def test_malformed_url_is_a_control_error(url):
    with pytest.raises(ControlError):
        _check_url(url)


def test_check_files_accepts_files_in_allowed_dirs(tmp_path):
    card = tmp_path / "card.png"
    card.write_bytes(b"png")
    assert _check_files([str(card)], [str(tmp_path)], {".png"}) == [str(card)]


@pytest.mark.parametrize(
    ("name", "match"),
    [
        (".ssh/id_ed25519", "hidden"),
        ("vault.kdbx", "secret"),
        ("id_rsa", "secret"),
        ("missing.png", "not a file"),
    ],
)
def test_check_files_refuses_secrets_and_missing(tmp_path, name, match):
    path = tmp_path / name
    if name != "missing.png":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
    with pytest.raises(ControlError, match=match):
        _check_files([str(path)], [str(tmp_path)], {".png", ".kdbx", ""})


def test_check_files_refuses_types_outside_the_list(tmp_path):
    doc = tmp_path / "notes.txt"
    doc.write_text("x")
    with pytest.raises(ControlError, match="file type"):
        _check_files([str(doc)], [str(tmp_path)], {".png"})


def test_check_files_refuses_paths_outside_and_symlinks_out(tmp_path):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "secret.png"
    outside.write_text("x")
    (allowed / "link.png").symlink_to(outside)
    with pytest.raises(ControlError, match="outside"):
        _check_files([str(outside)], [str(allowed)], {".png"})
    with pytest.raises(ControlError, match="outside"):
        _check_files([str(allowed / "link.png")], [str(allowed)], {".png"})
    with pytest.raises(ControlError, match="No files"):
        _check_files([], [str(allowed)], {".png"})


class FakeDialog:
    def __init__(self):
        self.type, self.message, self.answer = "confirm", "Leave?", None

    async def accept(self, text=""):
        self.answer = ("accept", text)

    async def dismiss(self):
        self.answer = ("dismiss",)


def test_dialogs_are_dismissed_until_policy_changes():
    c = PageController(FakeContext())
    first, second = FakeDialog(), FakeDialog()
    run(c._on_dialog(first))
    assert first.answer == ("dismiss",)
    assert run(c.dispatch("dialogs", {"accept": True, "prompt_text": "ok"}))["accept"] is True
    run(c._on_dialog(second))
    assert second.answer == ("accept", "ok")
    assert [d["accepted"] for d in run(c.dialogs())["recent"]] == [False, True]


def test_pause_bounds():
    c = PageController(FakeContext())
    with pytest.raises(ControlError):
        run(c.pause(0))
    with pytest.raises(ControlError):
        run(c.pause(60_001))


def test_shutdown_needs_the_token_and_calls_back():
    from aiohttp.test_utils import TestClient, TestServer

    from src.services.browser.control import TOKEN_HEADER, build_app

    closed = []

    async def scenario():
        app = build_app(PageController(FakeContext()), "t" * 32, lambda: closed.append(1))
        async with TestClient(TestServer(app)) as client:
            refused = await client.post("/shutdown", headers={TOKEN_HEADER: "wrong"})
            assert refused.status == 401 and closed == []
            accepted = await client.post("/shutdown", headers={TOKEN_HEADER: "t" * 32})
            assert accepted.status == 200 and closed == [1]
        async with TestClient(TestServer(build_app(PageController(FakeContext()), "t"))) as client:
            assert (await client.post("/shutdown", headers={TOKEN_HEADER: "t"})).status == 404

    run(scenario())
