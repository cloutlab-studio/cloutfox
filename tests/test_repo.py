"""The apt and dnf repository builder: indexes from packages, no tools needed."""

import gzip
import hashlib
import io
import pathlib
import sys
import tarfile

import pytest

# The builder lives in packaging/, which the installed `packaging` package shadows.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "packaging"))
import repo  # noqa: E402


def _ar(path: pathlib.Path, members: list[tuple[str, bytes]]) -> pathlib.Path:
    out = bytearray(b"!<arch>\n")
    for name, data in members:
        header = f"{name:<16}{0:<12}{0:<6}{0:<6}{0o100644:<8}{len(data):<10}`\n".encode()
        out += header + data
        if len(data) % 2:
            out += b"\n"
    path.write_bytes(bytes(out))
    return path


def _control_tar(fields: dict[str, str]) -> bytes:
    text = "\n".join(f"{key}: {value}" for key, value in fields.items()).encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo("./control")
        info.size = len(text)
        tar.addfile(info, io.BytesIO(text))
    return buffer.getvalue()


def make_deb(folder: pathlib.Path, name: str, version: str) -> pathlib.Path:
    folder.mkdir(parents=True, exist_ok=True)
    return _ar(
        folder / name,
        [
            ("debian-binary", b"2.0\n"),
            (
                "control.tar.gz",
                _control_tar({"Package": "cloutfox", "Version": version, "Architecture": "amd64"}),
            ),
            ("data.tar.gz", b""),
        ],
    )


def test_control_is_read_without_dpkg(tmp_path):
    deb = make_deb(tmp_path, "cloutfox_1.2.3_amd64.deb", "1.2.3")
    assert repo.deb_control(deb)["Version"] == "1.2.3"
    assert repo.deb_control(deb)["Package"] == "cloutfox"


def test_packages_index_points_into_the_pool(tmp_path):
    deb = make_deb(
        tmp_path / "apt" / "pool" / "main" / "c" / "cloutfox", "cloutfox_1.2.3_amd64.deb", "1.2.3"
    )
    text = repo.packages_index(tmp_path / "apt", [deb])
    assert "Package: cloutfox" in text
    assert "Version: 1.2.3" in text
    assert "Filename: pool/main/c/cloutfox/cloutfox_1.2.3_amd64.deb" in text
    assert f"SHA256: {hashlib.sha256(deb.read_bytes()).hexdigest()}" in text
    assert f"Size: {deb.stat().st_size}" in text


def test_release_lists_the_checksums_of_the_index(tmp_path):
    index = tmp_path / "dists" / "stable" / "main" / "binary-amd64"
    index.mkdir(parents=True)
    (index / "Packages").write_text("Package: cloutfox\n")
    (index / "Packages.gz").write_bytes(gzip.compress(b"Package: cloutfox\n", mtime=0))
    release_dir = index.parent.parent
    text = repo.release_file(release_dir, "1.2.3")
    assert "Suite: stable" in text and "Components: main" in text
    digest = hashlib.sha256((index / "Packages").read_bytes()).hexdigest()
    assert f" {digest} " in text and "main/binary-amd64/Packages" in text
    assert "main/binary-amd64/Packages.gz" in text
    assert "Date:" in text


def test_a_missing_package_set_is_an_error(tmp_path):
    with pytest.raises(repo.RepoError):
        repo.build_apt(tmp_path, tmp_path / "site", "1.0")


def test_version_comes_from_the_package(tmp_path):
    make_deb(tmp_path, "cloutfox_1.2.3_amd64.deb", "1.2.3")
    assert repo.version_of(tmp_path) == "1.2.3"


def test_secret_fingerprint_comes_from_the_fpr_record():
    colons = "\n".join(
        [
            "sec:u:4096:1:6A3ED7A0B8E30C7E:1:::u:::scESC:::+:::23::0:",
            "fpr:::::::::C9ADFF851AB7B416539C033C6A3ED7A0B8E30C7E:",
            "uid:u::::1::ABC::CloutFox packages::::::::::0:",
            "ssb:u:4096:1:1111:1::::::e:::+:::23:",
            "fpr:::::::::2222222222222222222222222222222222222222:",
        ]
    )
    assert repo.secret_fingerprint(colons) == "C9ADFF851AB7B416539C033C6A3ED7A0B8E30C7E"
    assert repo.secret_fingerprint("") is None


def test_manifest_lists_the_release_files():
    sums = (
        f"{'a' * 64}  CloutFox-3.2.0-setup-x64.exe\n{'b' * 64} *cloutfox_3.2.0_amd64.deb\nnoise\n"
    )
    data = repo.manifest("3.2.0-1", sums)
    assert data["version"] == "3.2.0"
    assert data["url"].endswith("/releases/tag/v3.2.0")
    assert data["assets"] == {
        "CloutFox-3.2.0-setup-x64.exe": "a" * 64,
        "cloutfox_3.2.0_amd64.deb": "b" * 64,
    }
