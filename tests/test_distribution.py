"""Archive handling in the distribution verifier uses synthetic fixtures only."""

from __future__ import annotations

import io
import re
import runpy
import tarfile
from pathlib import Path

import pytest

VERIFIER = runpy.run_path(str(Path(__file__).resolve().parents[1] /
                            "scripts/verify_distribution.py"))


def test_release_version_matches_package_and_metadata():
    from importlib.metadata import version

    import tracegate

    project = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    declared = re.search(r'^version = "([^"]+)"$', project, re.MULTILINE)
    assert declared is not None
    assert declared.group(1) == tracegate.__version__ == version("trace-gate")


def archive(tmp_path, name, *, symlink=False):
    path = tmp_path / "source.tar.gz"
    with tarfile.open(path, "w:gz") as source:
        member = tarfile.TarInfo(name)
        if symlink:
            member.type = tarfile.SYMTYPE
            member.linkname = "/tmp/outside"
            source.addfile(member)
        else:
            data = b"[build-system]\n"
            member.size = len(data)
            source.addfile(member, io.BytesIO(data))
    return path


def test_source_archive_extracts_to_one_root(tmp_path):
    path = archive(tmp_path, "trace_gate-0.1.0/pyproject.toml")
    root = VERIFIER["extract_source"](path, tmp_path / "unpacked")
    assert (root / "pyproject.toml").read_bytes() == b"[build-system]\n"


@pytest.mark.parametrize("name", [
    "../outside.txt", "/tmp/outside.txt", "root/../../outside.txt", "root\\outside.txt",
])
def test_source_archive_rejects_unsafe_paths(tmp_path, name):
    path = archive(tmp_path, name)
    with pytest.raises(ValueError, match="Unsafe source archive path"):
        VERIFIER["extract_source"](path, tmp_path / "unpacked")


def test_source_archive_rejects_symlinks(tmp_path):
    path = archive(tmp_path, "root/linked", symlink=True)
    with pytest.raises(ValueError, match="Unsupported source archive member"):
        VERIFIER["extract_source"](path, tmp_path / "unpacked")


@pytest.mark.parametrize("second_name", [
    "root/README.md", "root/./README.md", "root//README.md", "./root/README.md",
])
def test_source_archive_rejects_duplicate_normalized_paths_before_writing(tmp_path, second_name):
    path = tmp_path / "duplicate.tar.gz"
    with tarfile.open(path, "w:gz") as source:
        for name, payload in [
            ("root/pyproject.toml", b"[build-system]\n"),
            ("root/README.md", b"original\n"),
            (second_name, b"replacement\n"),
        ]:
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            source.addfile(member, io.BytesIO(payload))
    destination = tmp_path / "unpacked"
    with pytest.raises(ValueError, match="Duplicate source archive path"):
        VERIFIER["extract_source"](path, destination)
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize("second_is_dir", [False, True])
def test_source_archive_rejects_duplicate_directory_headers(tmp_path, second_is_dir):
    path = tmp_path / "collision.tar.gz"
    with tarfile.open(path, "w:gz") as source:
        directory = tarfile.TarInfo("root")
        directory.type = tarfile.DIRTYPE
        source.addfile(directory)
        duplicate = tarfile.TarInfo("./root/")
        duplicate.type = tarfile.DIRTYPE if second_is_dir else tarfile.REGTYPE
        source.addfile(duplicate)
    destination = tmp_path / "unpacked"
    with pytest.raises(ValueError, match="Duplicate source archive path"):
        VERIFIER["extract_source"](path, destination)
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize("name", ["", ".", "./"])
def test_source_archive_rejects_empty_normalized_paths(tmp_path, name):
    path = archive(tmp_path, name)
    with pytest.raises(ValueError, match="Unsafe source archive path"):
        VERIFIER["extract_source"](path, tmp_path / "unpacked")


def test_source_archive_accepts_one_normalized_path(tmp_path):
    path = archive(tmp_path, "./root//pyproject.toml")
    root = VERIFIER["extract_source"](path, tmp_path / "unpacked")
    assert (root / "pyproject.toml").read_bytes() == b"[build-system]\n"


def test_source_archive_requires_project_root(tmp_path):
    path = archive(tmp_path, "root/README.md")
    with pytest.raises(ValueError, match="Expected one source archive root"):
        VERIFIER["extract_source"](path, tmp_path / "unpacked")


def test_source_archive_rejects_empty_archive(tmp_path):
    path = tmp_path / "empty.tar.gz"
    with tarfile.open(path, "w:gz"):
        pass
    with pytest.raises(ValueError, match="Expected one source archive root"):
        VERIFIER["extract_source"](path, tmp_path / "unpacked")


def distribution_pair(tmp_path, source_code=b"VALUE = 1\n", wheel_code=b"VALUE = 1\n"):
    import zipfile

    source = tmp_path / "source"
    package = source / "src" / "tracegate"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(source_code)
    wheel = tmp_path / "trace_gate-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("tracegate/__init__.py", wheel_code)
    return wheel, source


def test_source_wheel_package_match(tmp_path):
    wheel, source = distribution_pair(tmp_path)
    VERIFIER["check_wheel_source"](wheel, source)


def test_source_wheel_code_mismatch_rejected(tmp_path):
    wheel, source = distribution_pair(tmp_path, wheel_code=b"VALUE = 2\n")
    with pytest.raises(ValueError, match="does not match the source archive"):
        VERIFIER["check_wheel_source"](wheel, source)


@pytest.mark.parametrize("missing_from", ["source", "wheel"])
def test_source_wheel_module_set_mismatch_rejected(tmp_path, missing_from):
    import zipfile

    wheel, source = distribution_pair(tmp_path)
    if missing_from == "wheel":
        (source / "src/tracegate/extra.py").write_text("EXTRA = True\n")
    else:
        with zipfile.ZipFile(wheel, "a") as archive:
            archive.writestr("tracegate/extra.py", b"EXTRA = True\n")
    with pytest.raises(ValueError, match="does not match the source archive"):
        VERIFIER["check_wheel_source"](wheel, source)


def test_source_wheel_duplicate_module_rejected(tmp_path):
    import zipfile

    wheel, source = distribution_pair(tmp_path)
    with zipfile.ZipFile(wheel, "a") as archive, pytest.warns(UserWarning):
        archive.writestr("tracegate/__init__.py", b"VALUE = 1\n")
    with pytest.raises(ValueError, match="Duplicate Python module"):
        VERIFIER["check_wheel_source"](wheel, source)


def test_source_wheel_empty_package_rejected(tmp_path):
    wheel, source = distribution_pair(tmp_path)
    (source / "src/tracegate/__init__.py").unlink()
    with pytest.raises(ValueError, match="does not match the source archive"):
        VERIFIER["check_wheel_source"](wheel, source)


def test_manifest_excludes_installed_promptfoo_dependencies(tmp_path, monkeypatch):
    from setuptools.command.egg_info import FileList

    manifest = (Path(__file__).resolve().parents[1] / "MANIFEST.in").read_text()
    wanted = Path("integrations/promptfoo/runtime-lock/package-lock.json")
    unwanted = Path("integrations/promptfoo/runtime-lock/node_modules/dependency/package.json")
    for path in (wanted, unwanted):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n")
    monkeypatch.chdir(tmp_path)
    files = FileList()
    files.findall()
    for line in manifest.splitlines():
        files.process_template_line(line)
    assert str(wanted) in files.files
    assert str(unwanted) not in files.files
