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


# --- latest.json --------------------------------------------------------------------------

DIGEST = "a" * 64
MANIFEST = {
    "version": "3.2.0",
    "url": "https://github.com/cloutlab-studio/cloutfox/releases/tag/v3.2.0",
    "assets": {"CloutFox-3.2.0-setup-x64.exe": DIGEST, "bad": "short"},
}


def test_latest_prefers_our_manifest():
    asked = []

    def fetch(url):
        asked.append(url)
        return _answer(MANIFEST)

    release = updates.latest(fetch=fetch)
    assert asked == [updates.MANIFEST]
    assert release.version == "3.2.0"
    assert release.sums == {"CloutFox-3.2.0-setup-x64.exe": DIGEST}


def test_latest_falls_back_to_github_when_the_site_fails():
    def fetch(url):
        if url == updates.MANIFEST:
            raise updates.UpdateError("software.cloutlab.studio answered 404")
        return _answer(GOOD)

    release = updates.latest(fetch=fetch)
    assert release.version == "3.2.0" and release.sums is None


def test_a_manifest_pointing_elsewhere_is_refused_too():
    def fetch(url):
        if url == updates.MANIFEST:
            return _answer({**MANIFEST, "url": "https://example.com/x"})
        raise updates.UpdateError("GitHub answered 403")

    with pytest.raises(updates.UpdateError):
        updates.latest(fetch=fetch)


# --- how this copy is replaced -------------------------------------------------------------


def _windows_app(tmp_path, where: str, uninstaller: bool):
    root = tmp_path / where / "CloutFox"
    (root / "app").mkdir(parents=True)
    if uninstaller:
        (root / "unins000.exe").write_bytes(b"")
    return root


def test_windows_setup_for_the_user(tmp_path):
    root = _windows_app(tmp_path, "Local/Programs", True)
    env = {"LOCALAPPDATA": str(tmp_path / "Local"), "ProgramFiles": str(tmp_path / "PF")}
    plan = updates.plan("3.2.0", env, "win32", root / "app")
    assert plan == updates.Plan("inno", "CloutFox-3.2.0-setup-x64.exe", str(root), "user")


def test_windows_setup_for_all_users(tmp_path):
    root = _windows_app(tmp_path, "PF", True)
    env = {"LOCALAPPDATA": str(tmp_path / "Local"), "ProgramFiles": str(tmp_path / "PF")}
    assert updates.plan("3.2.0", env, "win32", root / "app").scope == "machine"


def test_windows_msi_and_zip(tmp_path):
    env = {"LOCALAPPDATA": str(tmp_path / "Local"), "ProgramFiles": str(tmp_path / "PF")}
    msi = _windows_app(tmp_path, "PF", False)
    assert updates.plan("3.2.0", env, "win32", msi / "app").kind == "msi"
    unpacked = _windows_app(tmp_path, "Downloads", False)
    assert updates.plan("3.2.0", env, "win32", unpacked / "app") is None


def test_linux_kinds(tmp_path, monkeypatch):
    image = tmp_path / "CloutFox.AppImage"
    plan = updates.plan("3.2.0", {"APPIMAGE": str(image)}, "linux", tmp_path / "app")
    assert plan.kind == "appimage" and plan.root == str(image)
    assert updates.plan("3.2.0", {}, "linux", tmp_path / "app") is None
    monkeypatch.setattr(updates, "LINUX_PREFIX", tmp_path)
    monkeypatch.setattr(updates, "distro_kind", lambda: "rpm")
    assert updates.plan("3.2.0", {}, "linux", tmp_path / "app").asset == (
        "cloutfox-3.2.0-1.x86_64.rpm"
    )


def test_windows_script_waits_installs_and_starts_again(tmp_path):
    root = tmp_path / "It's here"
    file = tmp_path / "dl" / "CloutFox-3.2.0-setup-x64.exe"
    script = updates.windows_script(updates.Plan("inno", file.name, str(root), "user"), file, 4242)
    wait, install, start = (
        script.index("Wait-Process -Id 4242"),
        script.index("/VERYSILENT"),
        (script.index("CloutFox.exe'")),
    )
    assert wait < install < start
    assert "/CURRENTUSER" in script and "It''s here" in script
    msi = updates.windows_script(updates.Plan("msi", "x.msi", str(root), "machine"), file, 1)
    assert "msiexec.exe" in msi and "-Verb RunAs" in msi


def test_relaunch_waits_for_this_process():
    command = updates.relaunch_command(updates.Plan("appimage", "x", "/tmp/CloutFox.AppImage"), 77)
    assert command[:2] == ["/bin/sh", "-c"]
    assert command[-2:] == ["77", "/tmp/CloutFox.AppImage"]
    source = updates.relaunch_command(None, 78)
    assert source[source.index("78") + 1 :][-1].endswith(("cloutfox_app.py", "cloutfox"))


def _fresh(root):
    import uuid

    folder = root / uuid.uuid4().hex
    folder.mkdir()
    return str(folder)


def test_download_checks_the_manifest_sum(tmp_path, monkeypatch):
    def fake_download(url, dest, say=None):
        dest.write_bytes(b"x")
        return "b" * 64

    monkeypatch.setattr(updates, "_download", fake_download)
    target = updates.Plan("inno", "CloutFox-3.2.0-setup-x64.exe", str(tmp_path), "user")
    good = updates.Release("3.2.0", MANIFEST["url"], {target.asset: "b" * 64})
    monkeypatch.setattr(updates.tempfile, "mkdtemp", lambda prefix: _fresh(tmp_path))
    assert updates.download(target, good).read_bytes() == b"x"
    bad = updates.Release("3.2.0", MANIFEST["url"], {target.asset: DIGEST})
    with pytest.raises(updates.UpdateError, match="checksum"):
        updates.download(target, bad)


def test_package_failure_keeps_the_app(tmp_path, monkeypatch):
    file = tmp_path / "dl" / "cloutfox.rpm"
    file.parent.mkdir()
    file.write_bytes(b"")
    spawned = []
    monkeypatch.setattr(updates, "spawn_detached", spawned.append)

    class Done:
        returncode = 126
        stdout = ""

    monkeypatch.setattr(updates.subprocess, "run", lambda *a, **k: Done())
    with pytest.raises(updates.UpdateError, match="password"):
        updates.install(updates.Plan("rpm", file.name, "/opt/cloutfox"), file, 5)
    assert spawned == []
    Done.returncode = 0
    file.parent.mkdir(exist_ok=True)
    updates.install(updates.Plan("rpm", file.name, "/opt/cloutfox"), file, 5)
    assert spawned and "5" in spawned[0]


def test_installed_version_reads_the_file_on_disk(tmp_path):
    (tmp_path / "src" / "api").mkdir(parents=True)
    (tmp_path / "src" / "api" / "app.py").write_text('x = 1\nVERSION = "3.9.0"\n')
    assert updates.installed_version(tmp_path) == "3.9.0"
    assert updates.installed_version(tmp_path / "missing") is None


def test_app_is_the_folder_with_cloutfox_app():
    assert (updates.APP / "cloutfox_app.py").is_file()
    assert updates.installed_version() is not None
