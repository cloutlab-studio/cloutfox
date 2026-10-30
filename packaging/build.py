#!/usr/bin/env python3
"""Builds CloutFox's release files.

The app ships as a self-contained bundle: its own Python (python-build-standalone),
the dependencies and the code, so nothing needs a system Python. The packages are
made from that bundle. Camoufox is not in it: the app downloads it on first use.

    python packaging/build.py bundle      build/bundle/cloutfox for this OS
    python packaging/build.py linux       deb, rpm, AppImage, tar.gz and the AUR PKGBUILD
    python packaging/build.py windows     portable zip, setup exe (Inno Setup), MSI (WiX)
    python packaging/build.py source      source tarball of the git HEAD
    python packaging/build.py checksums   dist/SHA256SUMS
    python packaging/build.py notes       this version's CHANGELOG section

Everything downloaded is pinned by version and SHA-256. Results go to dist/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import textwrap
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGING = ROOT / "packaging"
BUILD = ROOT / "build"
CACHE = BUILD / "cache"
BUNDLE = BUILD / "bundle" / "cloutfox"
DIST = ROOT / "dist"

APP_ID = "cloutfox"
APPSTREAM_ID = "studio.cloutlab.cloutfox"
HOMEPAGE = "https://github.com/cloutlab-studio/cloutfox"

_PBS = "https://github.com/astral-sh/python-build-standalone/releases/download/20261013/"
PYTHON = {
    "linux-x86_64": (
        _PBS + "cpython-3.12.15%2B20261013-x86_64-unknown-linux-gnu-install_only.tar.gz",
        "5d546fc004fc2435fa142eb8f42ed8de5eb4725963dc22f7e6671014a80eb560",
    ),
    "windows-x64": (
        _PBS + "cpython-3.12.15%2B20261013-x86_64-pc-windows-msvc-install_only.tar.gz",
        "bbc902d4d187ac4914915bf538196a064b49109a33a104965b5164ced5b80a1e",
    ),
}

TOOLS = {
    "nfpm": (
        "https://github.com/goreleaser/nfpm/releases/download/v2.48.0/nfpm_2.48.0_Linux_x86_64.tar.gz",
        "6d7f9a28b2f397934403950fcbba83f598b08d02edbe79a0815b3b4897341750",
    ),
    "appimagetool": (
        "https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage",
        "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0",
    ),
    "appimage-runtime": (
        "https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64",
        "2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d",
    ),
}

# What the bundle takes from the repository (tracked files only).
APP_PATHS = ("src/", "chrome_engine/", "cloutfox_app.py", "cloutfox_mcp.py", "LICENSE")
APP_SKIP = ("/tests/", "/e2e/", "__pycache__")

# Parts of the standalone Python and of the wheels the app never uses.
PRUNE = (
    "lib/python3.12/test",
    "lib/python3.12/idlelib",
    "lib/python3.12/tkinter",
    "lib/python3.12/turtledemo",
    "lib/python3.12/ensurepip",
    "Lib/test",
    "Lib/idlelib",
    "Lib/tkinter",
    "Lib/turtledemo",
    "Lib/ensurepip",
    "tcl",
)
# A wheel that installs but cannot load (a missing DLL) fails the bundle here. Qt on
# Linux needs system libraries the build machine may lack; the package tests cover it.
IMPORT_CHECK = "import webview, camoufox, src.api.app, src.ui.window"
IMPORT_CHECK_WINDOWS = "import PyQt6.QtWebEngineWidgets, qtpy.QtWebEngineCore, webview.platforms.qt"
KEEP_QT_TRANSLATIONS = ("_ru.qm", "_en.qm")
# The Qt the window needs (pywebview's Qt backend, Qt WebEngine): on Linux the
# other Qt libraries, QML modules and plugins are removed (about half the size).
QT_MODULES = (
    "QtCore",
    "QtGui",
    "QtWidgets",
    "QtNetwork",
    "QtWebChannel",
    "QtWebEngineCore",
    "QtWebEngineWidgets",
    "QtPrintSupport",
    "QtOpenGL",
    "QtOpenGLWidgets",
    "QtQml",
    "QtQuick",
    "QtPositioning",
    "QtDBus",
    "sip",
)
QT_PLUGINS = (
    "platforms",
    "platforminputcontexts",
    "platformthemes",
    "imageformats",
    "iconengines",
    "xcbglintegrations",
    "wayland-decoration-client",
    "wayland-graphics-integration-client",
    "wayland-shell-integration",
    "generic",
    "tls",
    "networkinformation",
    "printsupport",
)

# System libraries the bundle links to, by soname: (Debian/Ubuntu package, Arch package).
# rpm needs no table: it depends on the sonames themselves, so one package fits
# Fedora, RHEL and openSUSE. The build fails on a soname missing here.
GLIBC = ("libc6 (>= 2.34)", "glibc")
SONAMES = {
    "ld-linux-x86-64.so.2": GLIBC,
    "libc.so.6": GLIBC,
    "libm.so.6": GLIBC,
    "libdl.so.2": GLIBC,
    "libpthread.so.0": GLIBC,
    "librt.so.1": GLIBC,
    "libresolv.so.2": GLIBC,
    "libutil.so.1": GLIBC,
    "libstdc++.so.6": ("libstdc++6", "gcc-libs"),
    "libgcc_s.so.1": ("libgcc-s1", "gcc-libs"),
    "libEGL.so.1": ("libegl1", "libglvnd"),
    "libGL.so.1": ("libgl1", "libglvnd"),
    "libX11-xcb.so.1": ("libx11-xcb1", "libx11"),
    "libX11.so.6": ("libx11-6", "libx11"),
    "libXcomposite.so.1": ("libxcomposite1", "libxcomposite"),
    "libXdamage.so.1": ("libxdamage1", "libxdamage"),
    "libXext.so.6": ("libxext6", "libxext"),
    "libXfixes.so.3": ("libxfixes3", "libxfixes"),
    "libXrandr.so.2": ("libxrandr2", "libxrandr"),
    "libXtst.so.6": ("libxtst6", "libxtst"),
    "libasound.so.2": ("libasound2t64 | libasound2", "alsa-lib"),
    "libatk-1.0.so.0": ("libatk1.0-0t64 | libatk1.0-0", "at-spi2-core"),
    "libbrotlicommon.so.1": ("libbrotli1", "brotli"),
    "libbrotlidec.so.1": ("libbrotli1", "brotli"),
    "libcairo-gobject.so.2": ("libcairo-gobject2", "cairo"),
    "libcairo.so.2": ("libcairo2", "cairo"),
    "libcups.so.2": ("libcups2t64 | libcups2", "libcups"),
    "libdbus-1.so.3": ("libdbus-1-3", "dbus"),
    "libdrm.so.2": ("libdrm2", "libdrm"),
    "libexpat.so.1": ("libexpat1", "expat"),
    "libfontconfig.so.1": ("libfontconfig1", "fontconfig"),
    "libfreetype.so.6": ("libfreetype6", "freetype2"),
    "libgbm.so.1": ("libgbm1", "mesa"),
    "libgdk-3.so.0": ("libgtk-3-0t64 | libgtk-3-0", "gtk3"),
    "libgtk-3.so.0": ("libgtk-3-0t64 | libgtk-3-0", "gtk3"),
    "libgdk_pixbuf-2.0.so.0": ("libgdk-pixbuf-2.0-0", "gdk-pixbuf2"),
    "libgio-2.0.so.0": ("libglib2.0-0t64 | libglib2.0-0", "glib2"),
    "libglib-2.0.so.0": ("libglib2.0-0t64 | libglib2.0-0", "glib2"),
    "libgobject-2.0.so.0": ("libglib2.0-0t64 | libglib2.0-0", "glib2"),
    "libgthread-2.0.so.0": ("libglib2.0-0t64 | libglib2.0-0", "glib2"),
    "libgssapi_krb5.so.2": ("libgssapi-krb5-2", "krb5"),
    "libharfbuzz.so.0": ("libharfbuzz0b", "harfbuzz"),
    "libnspr4.so": ("libnspr4", "nspr"),
    "libnss3.so": ("libnss3", "nss"),
    "libnssutil3.so": ("libnss3", "nss"),
    "libsmime3.so": ("libnss3", "nss"),
    "libpango-1.0.so.0": ("libpango-1.0-0", "pango"),
    "libpangocairo-1.0.so.0": ("libpangocairo-1.0-0", "pango"),
    "libudev.so.1": ("libudev1", "systemd-libs"),
    "libwayland-client.so.0": ("libwayland-client0", "wayland"),
    "libwayland-cursor.so.0": ("libwayland-cursor0", "wayland"),
    "libwayland-egl.so.1": ("libwayland-egl1", "wayland"),
    "libxcb-cursor.so.0": ("libxcb-cursor0", "xcb-util-cursor"),
    "libxcb-dri3.so.0": ("libxcb-dri3-0", "libxcb"),
    "libxcb-glx.so.0": ("libxcb-glx0", "libxcb"),
    "libxcb-icccm.so.4": ("libxcb-icccm4", "xcb-util-wm"),
    "libxcb-image.so.0": ("libxcb-image0", "xcb-util-image"),
    "libxcb-keysyms.so.1": ("libxcb-keysyms1", "xcb-util-keysyms"),
    "libxcb-randr.so.0": ("libxcb-randr0", "libxcb"),
    "libxcb-render-util.so.0": ("libxcb-render-util0", "xcb-util-renderutil"),
    "libxcb-render.so.0": ("libxcb-render0", "libxcb"),
    "libxcb-shape.so.0": ("libxcb-shape0", "libxcb"),
    "libxcb-shm.so.0": ("libxcb-shm0", "libxcb"),
    "libxcb-sync.so.1": ("libxcb-sync1", "libxcb"),
    "libxcb-util.so.1": ("libxcb-util1", "xcb-util"),
    "libxcb-xfixes.so.0": ("libxcb-xfixes0", "libxcb"),
    "libxcb-xkb.so.1": ("libxcb-xkb1", "libxcb"),
    "libxcb.so.1": ("libxcb1", "libxcb"),
    "libxkbcommon-x11.so.0": ("libxkbcommon-x11-0", "libxkbcommon-x11"),
    "libxkbcommon.so.0": ("libxkbcommon0", "libxkbcommon"),
    "libxkbfile.so.1": ("libxkbfile1", "libxkbfile"),
    "libz.so.1": ("zlib1g", "zlib"),
    "libzstd.so.1": ("libzstd1", "zstd"),
}
# Camoufox is downloaded later, so its own needs are listed by hand.
CAMOUFOX_SONAMES = ("libgtk-3.so.0", "libasound.so.2", "libX11-xcb.so.1", "libdbus-glib-1.so.2")
SONAMES["libdbus-glib-1.so.2"] = ("libdbus-glib-1-2", "dbus-glib")


SUMMARY = "Anti-detect browser profile manager on Camoufox"
DESCRIPTION = (
    "CloutFox keeps browser profiles apart: each has its own device fingerprint, "
    "cookies, proxy or WireGuard tunnel, timezone and locale. Desktop app with a "
    "REST API and an MCP server for AI agents."
)


def version() -> str:
    import tomllib  # Python 3.11+, like this script

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return data["project"]["version"]


def host() -> str:
    machine = platform.machine().lower()
    if sys.platform == "win32" and machine in ("amd64", "x86_64"):
        return "windows-x64"
    if sys.platform.startswith("linux") and machine in ("x86_64", "amd64"):
        return "linux-x86_64"
    raise SystemExit(f"No bundle for {sys.platform} {machine}")


def say(message: str) -> None:
    print(f"==> {message}", flush=True)


def run(*args: object, **kw) -> None:
    subprocess.run([str(a) for a in args], check=True, **kw)


def fetch(url: str, sha256: str) -> Path:
    """Download into build/cache once, failing unless the SHA-256 matches."""
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / f"{sha256[:12]}-{url.rsplit('/', 1)[-1].replace('%2B', '+')}"
    if not target.exists() or _sha256(target) != sha256:
        say(f"Downloading {url}")
        part = target.with_suffix(target.suffix + ".part")
        with urllib.request.urlopen(url, timeout=120) as resp, open(part, "wb") as out:
            shutil.copyfileobj(resp, out)
        got = _sha256(part)
        if got != sha256:
            part.unlink()
            raise SystemExit(f"SHA-256 mismatch for {url}: {got}")
        part.replace(target)
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True
    ).stdout.decode()
    return [p for p in out.split("\0") if p]


def bundle_python(bundle: Path = BUNDLE) -> Path:
    if sys.platform == "win32":
        return bundle / "python" / "python.exe"
    return bundle / "python" / "bin" / "python3"


# --- the bundle ----------------------------------------------------------------------


def build_bundle() -> None:
    target = host()
    url, sha = PYTHON[target]
    archive = fetch(url, sha)
    if BUNDLE.exists():
        shutil.rmtree(BUNDLE)
    BUNDLE.mkdir(parents=True)
    say(f"Unpacking Python into {BUNDLE}")
    with tarfile.open(archive) as tf:
        tf.extractall(BUNDLE, filter="data")
    python = bundle_python()

    say("Installing the dependencies")
    # CLOUTFOX_WHEELHOUSE: install offline from a folder of wheels made elsewhere.
    wheelhouse = os.environ.get("CLOUTFOX_WHEELHOUSE")
    offline = ["--no-index", "--find-links", wheelhouse] if wheelhouse else []
    run(
        python,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-warn-script-location",
        "--no-compile",
        *offline,
        "-r",
        ROOT / "requirements.txt",
        "-c",
        PACKAGING / "constraints.txt",
    )
    freeze = subprocess.run(
        [str(python), "-m", "pip", "freeze", "--all"], check=True, capture_output=True, text=True
    ).stdout

    say("Copying the app")
    app = BUNDLE / "app"
    for rel in _tracked_files():
        if not rel.startswith(APP_PATHS) or any(s in f"/{rel}" for s in APP_SKIP):
            continue
        dest = app / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    (app / "requirements.lock.txt").write_text(freeze, encoding="utf-8")

    _write_third_party(python)
    run(python, "-m", "pip", "uninstall", "-y", "-q", "pip")
    _prune(BUNDLE / "python")

    say("Compiling Python files")
    run(
        python,
        "-m",
        "compileall",
        "-q",
        "-j",
        "0",
        "--invalidation-mode",
        "unchecked-hash",
        BUNDLE,
    )

    say("Checking the imports")
    run(
        python,
        "-c",
        "import cloutfox_app, os; cloutfox_app.apply_home(os.environ); "
        + IMPORT_CHECK
        + ("; " + IMPORT_CHECK_WINDOWS if target.startswith("windows") else ""),
        cwd=app,
        env={**os.environ, "CLOUTFOX_HOME": str(BUILD / "import-check")},
    )

    if target.startswith("linux"):
        launcher = BUNDLE / APP_ID
        launcher.write_text(
            textwrap.dedent(
                """\
                #!/bin/sh
                here="$(dirname "$(readlink -f "$0")")"
                exec "$here/python/bin/python3" "$here/app/cloutfox_app.py" "$@"
                """
            ),
            encoding="utf-8",
        )
        launcher.chmod(0o755)
    shutil.copy2(ROOT / "LICENSE", BUNDLE / "LICENSE")
    say(f"Bundle ready: {BUNDLE} ({_size(BUNDLE)})")


def _write_third_party(python: Path) -> None:
    """THIRD-PARTY-LICENSES.txt: every bundled distribution with its licence texts."""
    script = textwrap.dedent(
        """
        import importlib.metadata as md, json, sys
        out = []
        for d in sorted(md.distributions(), key=lambda d: d.metadata["Name"].lower()):
            texts = []
            for f in d.files or []:
                name = f.name.upper()
                if name.startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE")):
                    try:
                        texts.append(f.read_text(encoding="utf-8"))
                    except Exception:
                        pass
            out.append({
                "name": d.metadata["Name"],
                "version": d.version,
                "license": d.metadata.get("License-Expression") or d.metadata.get("License") or "",
                "classifiers": [c.split(" :: ")[-1] for c in d.metadata.get_all("Classifier") or []
                                if c.startswith("License ::")],
                "texts": texts,
            })
        json.dump(out, sys.stdout)
        """
    )
    dists = json.loads(
        subprocess.run([str(python), "-c", script], check=True, capture_output=True).stdout
    )
    lines = [
        "CloutFox bundles a Python runtime and the packages below. Each keeps its own",
        "licence; the texts follow the list. CloutFox itself is MIT (see LICENSE).",
        "Camoufox is not bundled: it is downloaded on first use under the MPL-2.0.",
        "",
        "Python (python-build-standalone): PSF-2.0 and the licences of its bundled",
        "libraries, see python/LICENSE.txt or python/share/doc.",
        "",
    ]
    for d in dists:
        short = d["license"].splitlines()[0] if d["license"] else ", ".join(d["classifiers"])
        lines.append(f"{d['name']} {d['version']}: {short[:120] or 'see its licence text'}")
    for d in dists:
        for text in d["texts"]:
            lines += ["", "=" * 78, f"{d['name']} {d['version']}", "=" * 78, "", text.strip()]
    (BUNDLE / "THIRD-PARTY-LICENSES.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _prune(python_dir: Path) -> None:
    for rel in PRUNE:
        path = python_dir / rel
        if path.is_dir():
            shutil.rmtree(path)
    for translations in python_dir.rglob("Qt6/translations"):
        for qm in translations.rglob("*.qm"):
            if not qm.name.endswith(KEEP_QT_TRANSLATIONS):
                qm.unlink()
    for tests in python_dir.rglob("site-packages/*/tests"):
        if tests.is_dir() and not (tests / "__init__.py").exists():
            shutil.rmtree(tests)
    if sys.platform.startswith("linux"):
        # crypt needs libcrypt.so.1, which many distributions no longer install.
        for crypt in python_dir.rglob("lib-dynload/_crypt.*"):
            crypt.unlink()
        for pyqt in python_dir.rglob("site-packages/PyQt6"):
            _prune_qt(pyqt)


def _needed(path: Path) -> list[str]:
    out = subprocess.run(
        ["readelf", "-d", str(path)], capture_output=True, text=True, check=False
    ).stdout
    return [
        line.split("[", 1)[1].split("]", 1)[0] for line in out.splitlines() if "(NEEDED)" in line
    ]


def _prune_qt(pyqt: Path) -> None:
    qt = pyqt / "Qt6"
    lib = qt / "lib"
    for plugins in (qt / "plugins").iterdir():
        if plugins.name not in QT_PLUGINS:
            shutil.rmtree(plugins)
    for name in ("qml", "qsci"):
        if (qt / name).exists():
            shutil.rmtree(qt / name)
    if (pyqt / "bindings").exists():
        shutil.rmtree(pyqt / "bindings")
    shipped = {p.name for p in lib.iterdir()}
    modules = [pyqt / f"{m}.abi3.so" for m in QT_MODULES if (pyqt / f"{m}.abi3.so").exists()]
    roots = [*modules, *(qt / "plugins").rglob("*.so"), *(qt / "libexec").glob("*")]
    keep: set[str] = set()
    queue = list(roots)
    while queue:
        for name in _needed(queue.pop()):
            if name not in keep and (lib / name).exists():
                keep.add(name)
                queue.append(lib / name)
    for path in lib.iterdir():
        if path.is_file() and ".so" in path.name and path.name not in keep:
            path.unlink()
    # Plugins built against Qt parts the wheels do not ship (EGLFS on KMS, PDF) never load.
    for plugin in (qt / "plugins").rglob("*.so"):
        if any(n.startswith("libQt6") and not (lib / n).exists() for n in _needed(plugin)):
            plugin.unlink()
    for module in pyqt.glob("*.abi3.so"):
        if module not in modules:
            module.unlink()
            module.with_name(module.name.split(".")[0] + ".pyi").unlink(missing_ok=True)
    # Only what the wheels shipped: some unused plugins need Qt parts that never came.
    needed = {n for f in [*roots, *(lib / k for k in keep)] for n in _needed(f)}
    missing = sorted((needed & shipped) - {p.name for p in lib.iterdir()})
    if missing:
        raise SystemExit(f"Qt pruning removed libraries still needed: {missing}")


def _size(path: Path) -> str:
    total = sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())
    return f"{total / 1e6:.0f} MB"


# --- Linux ----------------------------------------------------------------------------


def _desktop_file() -> str:
    return textwrap.dedent(
        f"""\
        [Desktop Entry]
        Type=Application
        Name=CloutFox
        GenericName=Browser Profile Manager
        GenericName[ru]=Менеджер профилей браузера
        Comment={SUMMARY}
        Comment[ru]=Антидетект-профили браузера на Camoufox
        Exec={APP_ID}
        Icon={APP_ID}
        Terminal=false
        Categories=Network;WebBrowser;
        Keywords=browser;profiles;camoufox;proxy;antidetect;fingerprint;
        StartupNotify=true
        StartupWMClass={APP_ID}
        """
    )


def _metainfo(ver: str) -> str:
    return textwrap.dedent(
        f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <component type="desktop-application">
          <id>{APPSTREAM_ID}</id>
          <name>CloutFox</name>
          <summary>{SUMMARY}</summary>
          <summary xml:lang="ru">Антидетект-профили браузера на Camoufox</summary>
          <metadata_license>CC0-1.0</metadata_license>
          <project_license>MIT</project_license>
          <developer id="studio.cloutlab">
            <name>Cloutlab</name>
          </developer>
          <description>
            <p>{DESCRIPTION}</p>
          </description>
          <launchable type="desktop-id">{APP_ID}.desktop</launchable>
          <provides>
            <binary>{APP_ID}</binary>
          </provides>
          <url type="homepage">{HOMEPAGE}</url>
          <url type="bugtracker">{HOMEPAGE}/issues</url>
          <content_rating type="oars-1.1"/>
          <releases>
            <release version="{ver}" date="{_release_date(ver)}"/>
          </releases>
        </component>
        """
    )


def _release_date(ver: str) -> str:
    for line in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines():
        if line.startswith(f"## [{ver}] - "):
            return line.rsplit(" - ", 1)[1].strip()
    raise SystemExit(f"CHANGELOG.md has no section for {ver}")


def _tool(name: str) -> Path:
    path = fetch(*TOOLS[name])
    if name == "nfpm":
        out = CACHE / "nfpm"
        if not out.exists():
            with tarfile.open(path) as tf:
                tf.extract("nfpm", CACHE, filter="data")
        path = out
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def system_sonames(bundle: Path = BUNDLE) -> list[str]:
    """Sonames the bundle's ELF files need from the system, plus Camoufox's."""
    inside: set[str] = set()
    elves: list[Path] = []
    for path in bundle.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        inside.add(path.name)
        with open(path, "rb") as f:
            if f.read(4) == b"\x7fELF":
                elves.append(path)
    needed = {n for elf in elves for n in _needed(elf) if not n.startswith("$ORIGIN")}
    return sorted((needed - inside) | set(CAMOUFOX_SONAMES))


def linux_depends(bundle: Path = BUNDLE) -> tuple[list[str], list[str], list[str]]:
    """(deb, rpm, arch) dependencies of the bundle."""
    sonames = system_sonames(bundle)
    unknown = [n for n in sonames if n not in SONAMES]
    if unknown:
        raise SystemExit(f"Add these sonames to SONAMES in packaging/build.py: {unknown}")
    deb = sorted({SONAMES[n][0] for n in sonames})
    rpm = [f"{n}()(64bit)" for n in sonames if SONAMES[n] is not GLIBC]
    arch = sorted({SONAMES[n][1] for n in sonames})
    return deb, rpm, arch


def build_linux() -> None:
    ver = version()
    if not (BUNDLE / APP_ID).exists():
        raise SystemExit("Build the bundle first: python packaging/build.py bundle")
    DIST.mkdir(exist_ok=True)
    share = BUILD / "linux-share"
    if share.exists():
        shutil.rmtree(share)
    (share / "applications").mkdir(parents=True)
    (share / "metainfo").mkdir()
    (share / "applications" / f"{APP_ID}.desktop").write_text(_desktop_file(), encoding="utf-8")
    (share / "metainfo" / f"{APPSTREAM_ID}.metainfo.xml").write_text(
        _metainfo(ver), encoding="utf-8"
    )
    icon = ROOT / "src" / "assets" / "icon.png"

    deb_depends, rpm_depends, arch_depends = linux_depends()
    say("deb and rpm")
    nfpm_config = {
        "name": APP_ID,
        "arch": "amd64",
        "platform": "linux",
        "version": ver,
        "release": "1",
        "section": "web",
        "priority": "optional",
        "maintainer": "Cloutlab <dev@cloutlab.studio>",
        "vendor": "Cloutlab",
        "homepage": HOMEPAGE,
        "license": "MIT",
        "description": f"{SUMMARY}\n{DESCRIPTION}",
        "contents": [
            {"src": str(BUNDLE), "dst": "/opt/cloutfox", "type": "tree"},
            {"src": "/opt/cloutfox/cloutfox", "dst": "/usr/bin/cloutfox", "type": "symlink"},
            {
                "src": str(share / "applications" / f"{APP_ID}.desktop"),
                "dst": f"/usr/share/applications/{APP_ID}.desktop",
            },
            {
                "src": str(share / "metainfo" / f"{APPSTREAM_ID}.metainfo.xml"),
                "dst": f"/usr/share/metainfo/{APPSTREAM_ID}.metainfo.xml",
            },
            {"src": str(icon), "dst": f"/usr/share/icons/hicolor/512x512/apps/{APP_ID}.png"},
            {"src": str(ROOT / "LICENSE"), "dst": "/usr/share/licenses/cloutfox/LICENSE"},
            {
                "src": str(PACKAGING / "linux" / "apparmor-profile"),
                "dst": "/opt/cloutfox/share/apparmor/cloutfox",
            },
        ],
        "scripts": {
            "postinstall": str(PACKAGING / "linux" / "postinstall.sh"),
            "preremove": str(PACKAGING / "linux" / "preremove.sh"),
        },
        "overrides": {
            "deb": {"depends": deb_depends},
            "rpm": {"depends": rpm_depends},
        },
        "rpm": {"group": "Applications/Internet", "summary": SUMMARY, "compression": "xz"},
        "deb": {"fields": {"Bugs": f"{HOMEPAGE}/issues"}, "compression": "xz"},
    }
    config_path = BUILD / "nfpm.json"
    config_path.write_text(json.dumps(nfpm_config, ensure_ascii=False, indent=2), encoding="utf-8")
    nfpm = _tool("nfpm")
    run(nfpm, "package", "-f", config_path, "-p", "deb", "-t", DIST / f"cloutfox_{ver}_amd64.deb")
    run(
        nfpm, "package", "-f", config_path, "-p", "rpm", "-t", DIST / f"cloutfox-{ver}-1.x86_64.rpm"
    )

    say("tar.gz")
    tarball = DIST / f"cloutfox-{ver}-linux-x86_64.tar.gz"
    with tarfile.open(tarball, "w:gz", compresslevel=9) as tf:
        prefix = f"cloutfox-{ver}"
        tf.add(BUNDLE, arcname=prefix)
        tf.add(share / "applications" / f"{APP_ID}.desktop", f"{prefix}/share/{APP_ID}.desktop")
        tf.add(
            share / "metainfo" / f"{APPSTREAM_ID}.metainfo.xml",
            f"{prefix}/share/{APPSTREAM_ID}.metainfo.xml",
        )
        tf.add(icon, f"{prefix}/share/{APP_ID}.png")

    say("AppImage")
    appdir = BUILD / "AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)
    shutil.copytree(BUNDLE, appdir / "usr" / "lib" / APP_ID, symlinks=True)
    (appdir / "usr" / "share" / "metainfo").mkdir(parents=True)
    shutil.copy2(
        share / "metainfo" / f"{APPSTREAM_ID}.metainfo.xml",
        appdir / "usr" / "share" / "metainfo" / f"{APPSTREAM_ID}.appdata.xml",
    )
    shutil.copy2(share / "applications" / f"{APP_ID}.desktop", appdir / f"{APP_ID}.desktop")
    shutil.copy2(icon, appdir / f"{APP_ID}.png")
    shutil.copy2(icon, appdir / ".DirIcon")
    shutil.copy2(PACKAGING / "linux" / "AppRun", appdir / "AppRun")
    (appdir / "AppRun").chmod(0o755)
    appimage = DIST / f"CloutFox-{ver}-x86_64.AppImage"
    run(
        _tool("appimagetool"),
        "--no-appstream",
        "--runtime-file",
        _tool("appimage-runtime"),
        appdir,
        appimage,
        env={**os.environ, "ARCH": "x86_64", "APPIMAGE_EXTRACT_AND_RUN": "1"},
    )

    say("AUR PKGBUILD")
    aur = DIST / "aur"
    aur.mkdir(exist_ok=True)
    sha = _sha256(tarball)
    template = (PACKAGING / "aur" / "PKGBUILD.in").read_text(encoding="utf-8")
    (aur / "PKGBUILD").write_text(
        template.replace("@VERSION@", ver)
        .replace("@SHA256@", sha)
        .replace("@DEPENDS@", " ".join(f"'{d}'" for d in arch_depends)),
        encoding="utf-8",
    )
    (aur / ".SRCINFO").write_text(_srcinfo(ver, sha, arch_depends), encoding="utf-8")
    for path in sorted(DIST.glob("*")):
        if path.is_file():
            print(f"    {path.name}  {path.stat().st_size / 1e6:.0f} MB")


def _srcinfo(ver: str, sha: str, depends: list[str]) -> str:
    lines = [
        "pkgbase = cloutfox-bin",
        f"\tpkgdesc = {SUMMARY}",
        f"\tpkgver = {ver}",
        "\tpkgrel = 1",
        f"\turl = {HOMEPAGE}",
        "\tarch = x86_64",
        "\tlicense = MIT",
        *[f"\tdepends = {d}" for d in depends],
        "\tprovides = cloutfox",
        "\tconflicts = cloutfox",
        "\toptions = !strip",
        "\toptions = !debug",
        f"\tsource = cloutfox-{ver}-linux-x86_64.tar.gz::{HOMEPAGE}/releases/download/v{ver}/cloutfox-{ver}-linux-x86_64.tar.gz",
        f"\tsha256sums = {sha}",
        "",
        "pkgname = cloutfox-bin",
        "",
    ]
    return "\n".join(lines)


# --- Windows --------------------------------------------------------------------------


def _vcvars() -> Path:
    vswhere = (
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        / "Microsoft Visual Studio"
        / "Installer"
        / "vswhere.exe"
    )
    found = subprocess.run(
        [str(vswhere), "-latest", "-products", "*", "-property", "installationPath"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    vcvars = Path(found) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
    if not vcvars.exists():
        raise SystemExit("MSVC (vcvars64.bat) not found: install the C++ build tools")
    return vcvars


def build_launcher(out: Path) -> None:
    """CloutFox.exe: starts the bundled pythonw.exe with the app, icon included."""
    work = BUILD / "launcher"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    for name in ("launcher.c", "launcher.rc"):
        shutil.copy2(PACKAGING / "windows" / name, work / name)
    shutil.copy2(ROOT / "src" / "assets" / "icon.ico", work / "icon.ico")
    ver = version()
    numbers = ",".join((ver.split(".") + ["0", "0", "0"])[:4])
    (work / "version.h").write_text(
        f'#define VERSION_NUMBERS {numbers}\n#define VERSION_TEXT "{ver}"\n', encoding="ascii"
    )
    commands = (
        f'call "{_vcvars()}" >nul && '
        "rc /nologo launcher.rc && "
        "cl /nologo /O2 /W4 /DUNICODE /D_UNICODE launcher.c launcher.res "
        "/Fe:CloutFox.exe /link /SUBSYSTEM:WINDOWS user32.lib shell32.lib"
    )
    subprocess.run(f'cmd /d /s /c "{commands}"', cwd=work, check=True, shell=False)
    shutil.copy2(work / "CloutFox.exe", out / "CloutFox.exe")


def _license_rtf() -> Path:
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    body = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    body = body.replace("\n\n", "\\par\\par ").replace("\n", " ")
    rtf = BUILD / "LICENSE.rtf"
    rtf.write_text("{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Segoe UI;}}\\fs18 " + body + "}", "ascii")
    return rtf


def build_windows() -> None:
    ver = version()
    if not bundle_python().exists():
        raise SystemExit("Build the bundle first: python packaging/build.py bundle")
    DIST.mkdir(exist_ok=True)
    say("CloutFox.exe")
    build_launcher(BUNDLE)

    say("Portable zip")
    portable = DIST / f"CloutFox-{ver}-windows-x64.zip"
    with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(BUNDLE.rglob("*")):
            if path.is_file():
                zf.write(path, Path("CloutFox") / path.relative_to(BUNDLE))

    say("Setup exe (Inno Setup)")
    iscc = shutil.which("iscc") or r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    run(
        iscc,
        "/Q",
        f"/DAppVersion={ver}",
        f"/DSourceDir={BUNDLE}",
        f"/DOutputDir={DIST}",
        f"/DIconFile={ROOT / 'src' / 'assets' / 'icon.ico'}",
        f"/DLicenseFile={ROOT / 'LICENSE'}",
        PACKAGING / "windows" / "cloutfox.iss",
    )

    say("MSI (WiX)")
    run(
        "wix",
        "build",
        PACKAGING / "windows" / "cloutfox.wxs",
        "-arch",
        "x64",
        "-ext",
        "WixToolset.UI.wixext",
        "-d",
        f"Version={ver}",
        "-d",
        f"BundleDir={BUNDLE}",
        "-d",
        f"IconFile={ROOT / 'src' / 'assets' / 'icon.ico'}",
        "-d",
        f"LicenseRtf={_license_rtf()}",
        "-o",
        DIST / f"CloutFox-{ver}-x64.msi",
    )


# --- source and checksums ---------------------------------------------------------------


def build_source() -> None:
    ver = version()
    DIST.mkdir(exist_ok=True)
    out = DIST / f"cloutfox-{ver}-src.tar.gz"
    run(
        "git",
        "archive",
        "--format=tar.gz",
        f"--prefix=cloutfox-{ver}/",
        "-o",
        out,
        "HEAD",
        cwd=ROOT,
    )
    say(f"Source: {out.name}")


def build_checksums() -> None:
    files = sorted(p for p in DIST.iterdir() if p.is_file() and p.name != "SHA256SUMS")
    lines = [f"{_sha256(p)}  {p.name}" for p in files]
    (DIST / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def changes(ver: str) -> str:
    """The CHANGELOG.md section of a version, without its heading."""
    lines = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"## [{ver}]"))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start + 1 : end]).strip()


def notes(ver: str) -> str:
    """The GitHub release text: packaging/release-notes.md filled in for this version."""
    template = (PACKAGING / "release-notes.md").read_text(encoding="utf-8")
    return template.format(
        ver=ver,
        repo=HOMEPAGE,
        download=f"{HOMEPAGE}/releases/download/v{ver}",
        changes=changes(ver),
    )


def release_notes() -> None:
    print(notes(version()))


def main() -> None:
    steps = {
        "bundle": build_bundle,
        "linux": build_linux,
        "windows": build_windows,
        "source": build_source,
        "checksums": build_checksums,
        "notes": release_notes,
    }
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("step", choices=steps)
    steps[parser.parse_args().step]()


if __name__ == "__main__":
    main()
