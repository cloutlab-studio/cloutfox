"""Browser extensions shared by all profiles: unpacked folders under EXTENSIONS_DIR.

Each profile lists the folder names it loads. Camoufox takes them as `addons`,
the Chrome engine as --load-extension. An extension is added from an .xpi,
.zip or .crx file (all zip archives) or from an unpacked folder, and loads
only in profiles of the engine it was made for (`engine_of`).
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import zipfile

from ...core.config import EXTENSIONS_DIR

# Written at install when the file type says which browser the extension is for.
_ENGINE_MARK = ".cloutfox-engine"
_ENGINES = ("camoufox", "chrome")

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class ExtensionError(Exception):
    pass


def _valid_id(ext_id: str) -> bool:
    """A plain folder name inside EXTENSIONS_DIR (no separators, no "..")."""
    return isinstance(ext_id, str) and _ID.fullmatch(ext_id) is not None and ".." not in ext_id


def root() -> pathlib.Path:
    return pathlib.Path(EXTENSIONS_DIR)


def _manifest(path: pathlib.Path) -> dict | None:
    try:
        return json.loads((path / "manifest.json").read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def engine_of(path: pathlib.Path, manifest: dict | None = None) -> str:
    """The engine that loads an unpacked extension: "camoufox" for a Firefox add-on
    (installed from an .xpi, a gecko key in the manifest, or Mozilla's signature),
    "chrome" otherwise."""
    try:
        mark = (path / _ENGINE_MARK).read_text(encoding="utf-8").strip()
    except OSError:
        mark = ""
    if mark in _ENGINES:
        return mark
    manifest = manifest if manifest is not None else _manifest(path) or {}
    for key in ("browser_specific_settings", "applications"):
        settings = manifest.get(key)
        if isinstance(settings, dict) and "gecko" in settings:
            return "camoufox"
    if any((path / "META-INF" / name).is_file() for name in ("mozilla.rsa", "cose.sig")):
        return "camoufox"
    return "chrome"


def available() -> list[dict]:
    """[{"id": folder, "name": ..., "version": ..., "engine": ...}] of every installed
    extension."""
    out = []
    if not root().is_dir():
        return out
    for path in sorted(root().iterdir()):
        manifest = _manifest(path) if path.is_dir() else None
        if manifest is None:
            continue
        name = manifest.get("name", path.name)
        if isinstance(name, str) and name.startswith("__MSG_"):
            name = path.name
        out.append(
            {
                "id": path.name,
                "name": str(name),
                "version": str(manifest.get("version", "")),
                "engine": engine_of(path, manifest),
            }
        )
    return out


def _installed(ids: list[str]) -> list[tuple[str, pathlib.Path]]:
    return [
        (ext_id, root() / ext_id)
        for ext_id in ids
        if _valid_id(ext_id) and _manifest(root() / ext_id) is not None
    ]


def paths(ids: list[str], engine: str) -> list[str]:
    """Absolute folders of the given extensions that are installed and made for `engine`."""
    return [str(path.resolve()) for _, path in _installed(ids) if engine_of(path) == engine]


def mismatched(ids: list[str], engine: str) -> list[str]:
    """The given installed extensions that are made for the other engine."""
    return [ext_id for ext_id, path in _installed(ids) if engine_of(path) != engine]


def _target(name: str) -> pathlib.Path:
    stem = _SAFE.sub("-", name).strip("-.") or "extension"
    target, n = root() / stem, 2
    while target.exists():
        target, n = root() / f"{stem}-{n}", n + 1
    return target


def install(source: str) -> str:
    """Install from an archive or a folder; returns the new extension's id."""
    src = pathlib.Path(source)
    root().mkdir(parents=True, exist_ok=True)
    target = _target(src.stem if src.is_file() else src.name)
    try:
        if src.is_dir():
            if _manifest(src) is None:
                raise ExtensionError("no manifest.json in this folder")
            shutil.copytree(src, target)
        else:
            with zipfile.ZipFile(src) as archive:
                base = target.resolve()
                for member in archive.infolist():
                    dest = (target / member.filename).resolve()
                    if not dest.is_relative_to(base):
                        raise ExtensionError(f"unsafe path in archive: {member.filename}")
                archive.extractall(target)
            if _manifest(target) is None:
                raise ExtensionError("no manifest.json in this archive")
            engine = {".xpi": "camoufox", ".crx": "chrome"}.get(src.suffix.lower())
            if engine:
                (target / _ENGINE_MARK).write_text(engine, encoding="utf-8")
    except (OSError, zipfile.BadZipFile) as e:
        shutil.rmtree(target, ignore_errors=True)
        raise ExtensionError(str(e)) from e
    except ExtensionError:
        shutil.rmtree(target, ignore_errors=True)
        raise
    return target.name


def remove(ext_id: str) -> None:
    if _valid_id(ext_id):
        shutil.rmtree(root() / ext_id, ignore_errors=True)
