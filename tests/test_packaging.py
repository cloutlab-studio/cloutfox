import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _pins() -> dict[str, str]:
    pins = {}
    for line in (ROOT / "packaging" / "constraints.txt").read_text().splitlines():
        if "==" in line and not line.startswith("#"):
            name, ver = line.split("==")
            pins[name.lower().replace("_", "-")] = ver
    return pins


def _minor(ver: str) -> str:
    return ".".join(ver.split(".")[:2])


def test_qt_and_webengine_share_a_minor_version():
    pins = _pins()
    minors = {
        _minor(pins[name])
        for name in ("pyqt6", "pyqt6-qt6", "pyqt6-webengine", "pyqt6-webengine-qt6")
    }
    assert len(minors) == 1, minors


def test_release_notes_link_every_package():
    import re
    import sys

    sys.path.insert(0, str(ROOT / "packaging"))
    import build

    ver = build.version()
    text = build.notes(ver)
    linked = set(re.findall(rf"/releases/download/v{re.escape(ver)}/([^)\s]+)\)", text))
    assert linked == {
        f"CloutFox-{ver}-setup-x64.exe",
        f"CloutFox-{ver}-x64.msi",
        f"CloutFox-{ver}-windows-x64.zip",
        f"cloutfox_{ver}_amd64.deb",
        f"cloutfox-{ver}-1.x86_64.rpm",
        f"CloutFox-{ver}-x86_64.AppImage",
        f"cloutfox-{ver}-linux-x86_64.tar.gz",
        f"cloutfox-{ver}-src.tar.gz",
        "SHA256SUMS",
    }
    assert not re.search(r"\{(ver|repo|download|changes)\}", text)
    assert "### Added" in text
