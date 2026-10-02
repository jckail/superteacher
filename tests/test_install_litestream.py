"""scripts/install_litestream.py must refuse a download that does not match the pinned checksum."""

import hashlib
import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "install_litestream", Path(__file__).resolve().parent.parent / "scripts" / "install_litestream.py"
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def tarball(tmp_path, with_binary=True) -> tuple[Path, str]:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b"#!/bin/sh\necho ok\n" if with_binary else b"nothing here"
        info = tarfile.TarInfo("litestream" if with_binary else "README")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    path = tmp_path / "ls.tar.gz"
    path.write_bytes(buf.getvalue())
    return path, hashlib.sha256(buf.getvalue()).hexdigest()


def test_installs_when_the_checksum_matches(tmp_path):
    path, digest = tarball(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    out = mod.install("0.0.0", digest, str(dest), url=path.as_uri())
    assert Path(out).read_bytes().startswith(b"#!/bin/sh") and Path(out).stat().st_mode & 0o111


def test_refuses_a_checksum_mismatch(tmp_path):
    path, _ = tarball(tmp_path)
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(SystemExit, match="checksum mismatch"):
        mod.install("0.0.0", "0" * 64, str(dest), url=path.as_uri())
    assert not (dest / "litestream").exists()


def test_refuses_an_archive_without_the_binary(tmp_path):
    path, digest = tarball(tmp_path, with_binary=False)
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(SystemExit, match="not found"):
        mod.install("0.0.0", digest, str(dest), url=path.as_uri())
