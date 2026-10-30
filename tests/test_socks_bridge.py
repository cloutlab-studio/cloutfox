"""Camoufox profiles with a SOCKS5 proxy that needs a password go through a loopback bridge."""

import asyncio
import socket

import pytest

from chrome_engine.tests.servers import Origin, Socks5Proxy
from src.services.browser import runner
from src.utils.proxy_parser import parse_proxy


def _camoufox_fetched() -> bool:
    try:
        from camoufox.pkgman import installed_verstr

        return bool(installed_verstr())
    except Exception:
        return False


@pytest.mark.parametrize(
    ("proxy", "bridged"),
    [
        ("socks5://user:pass@192.0.2.1:1080", True),
        ("socks5h://user:pass@192.0.2.1:1080", True),
        ("socks5://192.0.2.1:1080:user:pass", True),
        ("socks5://192.0.2.1:1080", False),
        ("http://user:pass@192.0.2.1:8080", False),
        ("http://user:pass@127.0.0.1:40000", True),
        ("http://127.0.0.1:40000", False),
        ("192.0.2.1:8080:user:pass", False),
        ("None", False),
    ],
)
def test_socks5_and_tunnel_logins_are_bridged(proxy, bridged):
    assert runner.needs_bridge(parse_proxy(proxy)) is bridged


def _fake_launch(monkeypatch, tmp_path):
    seen = {}

    def camoufox(**config):
        seen.update(config)
        server = config["proxy"]["server"]
        seen["listening"] = server.startswith("http://127.0.0.1:") and _listening(server)
        raise RuntimeError("stop after the launch options")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner, "AsyncCamoufox", camoufox)
    monkeypatch.setattr(runner, "load_or_create", lambda *_: {})
    monkeypatch.setattr(runner, "exit_ip", lambda *_: "203.0.113.5")
    return seen


def _listening(server: str) -> bool:
    host, port = server.removeprefix("http://").rsplit(":", 1)
    with socket.socket() as sock:
        return sock.connect_ex((host, int(port))) == 0


def test_launch_gets_the_bridge_and_stops_it(monkeypatch, tmp_path, capsys):
    seen = _fake_launch(monkeypatch, tmp_path)
    proxy = "socks5://user:s3cret@192.0.2.1:1080"
    assert asyncio.run(runner.run_browser("p", proxy, "windows")) == 1

    server = seen["proxy"]["server"]
    assert server.startswith("http://127.0.0.1:")
    assert set(seen["proxy"]) == {"server"}
    assert seen["listening"]
    assert not _listening(server)
    assert "s3cret" not in capsys.readouterr().out


def test_other_proxies_go_to_camoufox_unchanged(monkeypatch, tmp_path):
    seen = _fake_launch(monkeypatch, tmp_path)
    proxy = "http://user:pass@192.0.2.1:8080"
    asyncio.run(runner.run_browser("p", proxy, "windows"))
    assert seen["proxy"] == parse_proxy(proxy)


@pytest.mark.skipif(not _camoufox_fetched(), reason="Camoufox not fetched")
def test_real_camoufox_through_socks5_with_a_password(monkeypatch, tmp_path):
    seen: dict = {}

    async def main() -> int:
        origin = await Origin().start()
        socks = await Socks5Proxy(hosts={"origin.test": "127.0.0.1"}).start()

        async def first_tabs(context, _profile_dir, _start_urls):
            page = context.pages[0]
            await page.goto(f"http://origin.test:{origin.port}/")
            seen["body"] = await page.inner_text("body")
            runner._shutdown.set()

        monkeypatch.setattr(runner, "open_first_tabs", first_tabs)
        try:
            return await runner.run_browser("p", socks.url, "linux")
        finally:
            seen["targets"] = socks.targets
            seen["port"] = origin.port
            await socks.stop()
            await origin.stop()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner, "HEADLESS", True)
    monkeypatch.setattr(runner, "RESTORE_TABS", False)
    # No exit IP: the test proxy has no internet, and geoip is not under test.
    monkeypatch.setattr(runner, "exit_ip", lambda *_: None)
    runner._shutdown.clear()
    try:
        assert asyncio.run(asyncio.wait_for(main(), 120)) == 0
    finally:
        runner._shutdown.clear()

    assert seen["body"] == "origin-ok"
    # The name reached the SOCKS5 proxy unresolved.
    assert ("domain", "origin.test", seen["port"]) in seen["targets"]


def test_launcher_passes_the_proxy_in_the_environment(monkeypatch, tmp_path):
    seen = _fake_launch(monkeypatch, tmp_path)
    monkeypatch.setenv("CLOUTFOX_LAUNCH_OPTS", '{"proxy": "http://user:pass@192.0.2.1:8080"}')
    asyncio.run(runner.run_browser("p", "-", "windows"))
    assert seen["proxy"] == parse_proxy("http://user:pass@192.0.2.1:8080")
