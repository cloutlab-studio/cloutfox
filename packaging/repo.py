"""Build the apt and dnf repositories served at software.cloutlab.studio.

Takes the .deb and .rpm of one release, signs them with the packages key (when
one is loaded in GNUPGHOME), writes the indices and a small landing page, and
leaves a folder that GitHub Pages can serve:

    site/apt/dists/stable/...            apt index, signed
    site/apt/pool/main/c/cloutfox/*.deb
    site/apt/cloutfox.gpg, .asc          the public key
    site/rpm/x86_64/*.rpm + repodata/    dnf index
    site/index.html                      how to add the repository

    python3 packaging/repo.py build --dist dist --site site

No server is involved: the release workflow deploys the folder to Pages.
"""

from __future__ import annotations

import argparse
import email.utils
import gzip
import hashlib
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tarfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
KEYS = ROOT / "packaging" / "keys"
BASE_URL = "https://software.cloutlab.studio"
SUITE = "stable"
COMPONENT = "main"
ARCH = "amd64"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CloutFox packages</title>
<style>
  :root {{ color-scheme: light dark }}
  body {{ margin: 0 auto; max-width: 46rem; padding: 3rem 1.25rem 5rem;
         font: 16px/1.6 system-ui, -apple-system, "Segoe UI", sans-serif }}
  h1 {{ font-size: 2rem; margin: 0 0 .25rem }}
  p.lead {{ margin-top: 0; opacity: .75 }}
  h2 {{ margin-top: 2.5rem; font-size: 1.15rem }}
  pre {{ overflow-x: auto; padding: 1rem; border-radius: 8px;
        background: rgba(127,127,127,.12) }}
  code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace }}
  footer {{ margin-top: 3rem; font-size: .9rem; opacity: .7 }}
  a {{ color: inherit }}
</style>
</head>
<body>
<h1>CloutFox packages</h1>
<p class="lead">The apt and dnf repositories for
<a href="https://github.com/cloutlab-studio/cloutfox">CloutFox</a>, version {version}.
Updates arrive with the normal system update.</p>
<p>The .deb and .rpm from the <a href="https://github.com/cloutlab-studio/cloutfox/releases">releases page</a>
add this repository by themselves when installed. The commands below do the same by hand.</p>

<h2>Debian, Ubuntu, Mint</h2>
<pre><code>sudo curl -fsSL {base}/apt/cloutfox.gpg -o /usr/share/keyrings/cloutfox.gpg
echo "deb [signed-by=/usr/share/keyrings/cloutfox.gpg] {base}/apt {suite} {component}" \\
  | sudo tee /etc/apt/sources.list.d/cloutfox.list
sudo apt update
sudo apt install cloutfox</code></pre>
<p>Later updates: <code>sudo apt update &amp;&amp; sudo apt upgrade</code>.</p>

<h2>Fedora, RHEL, openSUSE</h2>
<pre><code>sudo curl -fsSL {base}/apt/cloutfox.asc -o /etc/pki/rpm-gpg/cloutfox.asc
sudo tee /etc/yum.repos.d/cloutfox.repo &lt;&lt;'EOF'
[cloutfox]
name=CloutFox
baseurl={base}/rpm/x86_64
enabled=1
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/cloutfox.asc
metadata_expire=6h
EOF
sudo dnf install cloutfox</code></pre>
<p>Later updates: <code>sudo dnf upgrade</code>. On openSUSE put the same file into
<code>/etc/zypp/repos.d/</code> and use <code>zypper</code>.</p>

<h2>Windows and AppImage</h2>
<p>CloutFox updates itself: when a new version is out, a bar above the profile list offers
"Install update", and Settings → About has the same button.</p>

<h2>Signing key</h2>
<p>The repository and its packages are signed with
<a href="{base}/apt/cloutfox.gpg">cloutfox.gpg</a> (fingerprint <code>{fingerprint}</code>).</p>

<footer>
  <a href="https://github.com/cloutlab-studio/cloutfox">Source</a> ·
  <a href="https://github.com/cloutlab-studio/cloutfox/releases">All downloads</a> ·
  built {date}
</footer>
</body>
</html>
"""


class RepoError(Exception):
    """The packages or the tools needed to index them are missing."""


def _run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True, **kwargs)
    except FileNotFoundError as e:
        raise RepoError(f"{command[0]} is not installed") from e
    except subprocess.CalledProcessError as e:
        raise RepoError(f"{command[0]} failed: {(e.stderr or e.stdout).strip()[:300]}") from e


def _ar_members(path: pathlib.Path):
    """Yield (name, bytes) of an ar archive: .deb is one."""
    data = path.read_bytes()
    if not data.startswith(b"!<arch>\n"):
        raise RepoError(f"{path.name} is not a .deb (no ar header)")
    offset = 8
    while offset + 60 <= len(data):
        header = data[offset : offset + 60]
        name = header[:16].decode("ascii", "replace").strip().rstrip("/")
        size = int(header[48:58].decode("ascii").strip())
        start = offset + 60
        yield name, data[start : start + size]
        offset = start + size + (size % 2)


def deb_control(path: pathlib.Path) -> dict[str, str]:
    """The control fields of a .deb, read without dpkg."""
    for name, blob in _ar_members(path):
        if not name.startswith("control.tar"):
            continue
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tar:
            member = next((m for m in tar.getmembers() if m.name.lstrip("./") == "control"), None)
            if member is None:
                raise RepoError(f"{path.name} has no control file")
            text = tar.extractfile(member).read().decode("utf-8", "replace")
        fields: dict[str, str] = {}
        key = None
        for line in text.splitlines():
            if line.startswith((" ", "\t")) and key:
                fields[key] += " " + line.strip()
            elif ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
        return fields
    raise RepoError(f"{path.name} has no control.tar member")


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def packages_index(repo: pathlib.Path, files: list[pathlib.Path]) -> str:
    """The Packages file: one stanzas block per .deb, Filename relative to the repo root."""
    blocks = []
    for path in sorted(files):
        fields = deb_control(path)
        for required in ("Package", "Version", "Architecture"):
            if not fields.get(required):
                raise RepoError(f"{path.name} has no {required} field")
        relative = path.relative_to(repo).as_posix()
        stanza = [
            f"Package: {fields['Package']}",
            f"Version: {fields['Version']}",
            f"Architecture: {fields['Architecture']}",
        ]
        for key in ("Maintainer", "Installed-Size", "Depends", "Section", "Priority", "Homepage"):
            if fields.get(key):
                stanza.append(f"{key}: {fields[key]}")
        stanza += [
            f"Filename: {relative}",
            f"Size: {path.stat().st_size}",
            f"SHA256: {_sha256(path)}",
            "",
        ]
        blocks.append("\n".join(stanza))
    return "\n".join(blocks)


def release_file(index_dir: pathlib.Path, version: str) -> str:
    """The Release file: repo fields plus checksums of the index files (signed separately)."""
    lines = [
        "Origin: Cloutlab",
        "Label: CloutFox",
        f"Suite: {SUITE}",
        f"Codename: {SUITE}",
        f"Version: {version}",
        f"Architectures: {ARCH}",
        f"Components: {COMPONENT}",
        "Description: CloutFox packages",
        f"Date: {email.utils.formatdate(usegmt=True)}",
        "Acquire-By-Hash: no",
    ]
    entries = [
        p
        for p in sorted(index_dir.rglob("*"))
        if p.is_file() and p.parent == index_dir / COMPONENT / f"binary-{ARCH}"
    ]
    for algorithm, label in (("sha256", "SHA256"), ("md5", "MD5Sum")):
        lines.append(f"{label}:")
        for path in entries:
            digest = hashlib.new(algorithm, path.read_bytes()).hexdigest()
            relative = path.relative_to(index_dir).as_posix()
            lines.append(f" {digest} {path.stat().st_size} {relative}")
    return "\n".join(lines) + "\n"


def _has_secret_key() -> bool:
    try:
        done = subprocess.run(
            ["gpg", "--batch", "--list-secret-keys", "--with-colons"],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return False
    return done.returncode == 0 and any(
        line.startswith("sec:") for line in done.stdout.splitlines()
    )


def sign_release(index_dir: pathlib.Path) -> bool:
    """InRelease and Release.gpg beside Release; False when no key is loaded."""
    if not _has_secret_key():
        return False
    release = index_dir / "Release"
    _run(
        [
            "gpg",
            "--batch",
            "--yes",
            "--armor",
            "--clearsign",
            "-o",
            str(index_dir / "InRelease"),
            str(release),
        ]
    )
    _run(
        [
            "gpg",
            "--batch",
            "--yes",
            "--armor",
            "--detach-sign",
            "-o",
            str(index_dir / "Release.gpg"),
            str(release),
        ]
    )
    return True


def sign_rpms(files: list[pathlib.Path]) -> bool:
    """rpm --addsign every package; False when no key is loaded."""
    if not files or not _has_secret_key():
        return False
    key = subprocess.run(
        ["gpg", "--batch", "--list-secret-keys", "--with-colons"], capture_output=True, text=True
    )
    fingerprint = secret_fingerprint(key.stdout)
    if not fingerprint:
        return False
    for path in files:
        _run(["rpm", "--define", f"_gpg_name {fingerprint}", "--addsign", str(path)])
    unsigned = [path.name for path in files if not rpm_signed(path)]
    if unsigned:
        raise RepoError(f"rpm --addsign left these unsigned: {unsigned}")
    return True


def secret_fingerprint(colons: str) -> str | None:
    """The fingerprint of the first secret key in `gpg --with-colons` output.

    The `sec` record does not carry it: the `fpr` record right after it does.
    Reading field 10 of `sec` gave an empty name, so 3.1.2 shipped unsigned rpms
    that dnf, with gpgcheck=1, refused to install.
    """
    after_sec = False
    for line in colons.splitlines():
        if line.startswith("sec:"):
            after_sec = True
        elif after_sec and line.startswith("fpr:"):
            return line.split(":")[9] or None
    return None


def rpm_signed(path: pathlib.Path) -> bool:
    done = subprocess.run(
        [
            "rpm",
            "-qp",
            "--nosignature",
            "--qf",
            "%{RSAHEADER:pgpsig}|%{SIGPGP:pgpsig}|%{OPENPGP:pgpsig}",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    fields = done.stdout.strip().split("|")
    return done.returncode == 0 and any(f and f != "(none)" for f in fields)


def build_apt(dist: pathlib.Path, site: pathlib.Path, version: str) -> list[pathlib.Path]:
    debs = sorted(dist.glob("*.deb"))
    if not debs:
        raise RepoError("no .deb in dist")
    pool = site / "apt" / "pool" / "main" / "c" / "cloutfox"
    pool.mkdir(parents=True, exist_ok=True)
    for deb in debs:
        shutil.copy2(deb, pool / deb.name)
    index_dir = site / "apt" / "dists" / SUITE / f"{COMPONENT}" / f"binary-{ARCH}"
    index_dir.mkdir(parents=True, exist_ok=True)
    packages = packages_index(site / "apt", sorted(pool.glob("*.deb")))
    (index_dir / "Packages").write_text(packages, encoding="utf-8")
    # mtime=0: the same packages always give the same index, byte for byte.
    (index_dir / "Packages.gz").write_bytes(gzip.compress(packages.encode("utf-8"), mtime=0))
    release_dir = site / "apt" / "dists" / SUITE
    (release_dir / "Release").write_text(release_file(release_dir, version), encoding="utf-8")
    sign_release(release_dir)
    for name in ("cloutfox.gpg", "cloutfox.asc"):
        source = KEYS / name
        if source.is_file():
            shutil.copy2(source, site / "apt" / name)
    return debs


def build_rpm(dist: pathlib.Path, site: pathlib.Path) -> list[pathlib.Path]:
    rpms = sorted(dist.glob("*.rpm"))
    if not rpms:
        raise RepoError("no .rpm in dist")
    folder = site / "rpm" / "x86_64"
    folder.mkdir(parents=True, exist_ok=True)
    for rpm in rpms:
        shutil.copy2(rpm, folder / rpm.name)
    sign_rpms(sorted(folder.glob("*.rpm")))
    _run(["createrepo_c", "--quiet", "--checksum", "sha256", "--database", str(folder)])
    sign_repomd(folder / "repodata")
    return rpms


def sign_repomd(repodata: pathlib.Path) -> bool:
    """repomd.xml.asc and repomd.xml.key: zypper refuses a repository without them."""
    if not _has_secret_key():
        return False
    _run(
        [
            "gpg",
            "--batch",
            "--yes",
            "--armor",
            "--detach-sign",
            "-o",
            str(repodata / "repomd.xml.asc"),
            str(repodata / "repomd.xml"),
        ]
    )
    shutil.copy2(KEYS / "cloutfox.asc", repodata / "repomd.xml.key")
    return True


def fingerprint() -> str:
    done = subprocess.run(
        [
            "gpg",
            "--batch",
            "--with-colons",
            "--import-options",
            "show-only",
            "--import",
            str(KEYS / "cloutfox.asc"),
        ],
        capture_output=True,
        text=True,
    )
    for line in done.stdout.splitlines():
        if line.startswith("fpr:"):
            return line.split(":")[9]
    return "unknown"


def version_of(dist: pathlib.Path) -> str:
    debs = sorted(dist.glob("*.deb"))
    if debs:
        return deb_control(debs[0]).get("Version", "0")
    rpms = sorted(dist.glob("*.rpm"))
    if rpms:
        return rpms[0].name.split("-")[1] if "-" in rpms[0].name else "0"
    raise RepoError("no packages in dist")


RELEASES = "https://github.com/cloutlab-studio/cloutfox/releases"


def manifest(version: str, sums: str) -> dict:
    """latest.json: what the app's update check reads (src/services/updates.py)."""
    assets = {}
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) == 2 and len(parts[0]) == 64:
            assets[parts[1].lstrip("*")] = parts[0].lower()
    upstream = version.split("-")[0]
    return {
        "version": upstream,
        "url": f"{RELEASES}/tag/v{upstream}",
        "published": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "assets": assets,
    }


def build(
    dist: pathlib.Path, site: pathlib.Path, base_url: str = BASE_URL, sums: str | None = None
) -> dict:
    if site.exists():
        shutil.rmtree(site)
    site.mkdir(parents=True)
    version = version_of(dist)
    build_apt(dist, site, version)
    build_rpm(dist, site)
    sums_file = dist / "SHA256SUMS"
    if sums is None and sums_file.exists():
        sums = sums_file.read_text(encoding="utf-8")
    if sums is not None:
        (site / "latest.json").write_text(
            json.dumps(manifest(version, sums), indent=2) + "\n", encoding="utf-8"
        )
    (site / "index.html").write_text(
        PAGE.format(
            version=version,
            base=base_url.rstrip("/"),
            suite=SUITE,
            component=COMPONENT,
            fingerprint=fingerprint(),
            date=time.strftime("%d %B %Y", time.gmtime()),
        ),
        encoding="utf-8",
    )
    return {"version": version, "apt": SUITE, "rpm": "x86_64", "site": str(site)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=["build"])
    parser.add_argument("--dist", default="dist")
    parser.add_argument("--site", default="site")
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args(argv)
    try:
        print(build(pathlib.Path(args.dist), pathlib.Path(args.site), args.base_url))
    except RepoError as e:
        print(f"repo: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
