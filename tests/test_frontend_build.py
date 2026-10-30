"""The built panel in src/ui/dist matches frontend/ (there is no CI to rebuild it)."""

import hashlib
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DIST = ROOT / "src" / "ui" / "dist"


def _sources() -> list[pathlib.Path]:
    # Must match sourceFiles() in frontend/vite.config.ts.
    files = []
    for base in (FRONTEND, ROOT / "src" / "assets" / "fonts"):
        for path in base.rglob("*"):
            rel = path.relative_to(base).parts
            if any(p == "node_modules" or p.startswith(".") for p in rel) or not path.is_file():
                continue
            files.append(path)
    files.append(ROOT / "src" / "assets" / "icon.png")
    return sorted(files, key=lambda p: p.relative_to(ROOT).as_posix())


def _hash() -> str:
    h = hashlib.sha256()
    for path in _sources():
        rel = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        if not re.search(r"\.(ttf|png)$", rel):
            data = data.replace(b"\r\n", b"\n")
        h.update(rel.encode() + b"\0" + data + b"\0")
    return h.hexdigest()


def test_build_is_fresh():
    built = (DIST / ".source-hash").read_text(encoding="utf-8").strip()
    assert built == _hash(), (
        "frontend/ changed: run `cd frontend && npm run build` and commit src/ui/dist"
    )


def test_build_has_a_strict_csp():
    html = (DIST / "index.html").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in html
    assert "default-src 'self'" in html and "unsafe-inline' 'self'" not in html


def test_panel_never_renders_raw_html():
    # Text from agents and websites must stay text.
    for path in (FRONTEND / "src").rglob("*.svelte"):
        assert "{@html" not in path.read_text(encoding="utf-8"), path
    for path in (FRONTEND / "src").rglob("*.ts"):
        text = path.read_text(encoding="utf-8")
        assert "innerHTML" not in text and "insertAdjacentHTML" not in text, path


def test_bundled_fonts_keep_their_licences():
    names = {p.name for p in (DIST / "fonts").iterdir()}
    assert {"OFL-InterTight.txt", "OFL-IBMPlexMono.txt"} <= names
