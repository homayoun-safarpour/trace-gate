"""Check a built wheel and its source archive without source-tree imports.

Prerequisites: install requirements-ci.txt and the built wheel in a disposable
tooling virtual environment. No network is used by this verifier's commands.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path, PurePosixPath

PROBE = r"""
import hashlib, importlib.metadata, json, pathlib, sys
import tracegate
dist = importlib.metadata.distribution('trace-gate')
if tracegate.__version__ != dist.version:
    raise SystemExit('package __version__ differs from distribution metadata')
module = pathlib.Path(tracegate.__file__).resolve()
if not module.is_relative_to(pathlib.Path(sys.prefix).resolve()):
    raise SystemExit('tracegate was not imported from this environment')
direct = json.loads(dist.read_text('direct_url.json') or '{}')
if direct.get('dir_info', {}).get('editable'):
    raise SystemExit('editable install is not distribution verification')
if dist.requires:
    raise SystemExit('unexpected runtime dependency: ' + repr(dist.requires))
hashes = {
    str(p): hashlib.sha256(dist.locate_file(p).read_bytes()).hexdigest()
    for p in dist.files or []
    if str(p).startswith('tracegate/') and str(p).endswith('.py')
}
print(json.dumps({'module': str(module), 'version': dist.version, 'hashes': hashes}))
"""


def run(args, *, cwd, env, capture=False):
    print("+ " + " ".join(str(arg) for arg in args), flush=True)
    return subprocess.run(
        [str(arg) for arg in args], cwd=cwd, env=env, text=True,
        capture_output=capture, check=True, timeout=180,
    )


def extract_source(archive: Path, destination: Path) -> Path:
    """Reject ambiguous paths before extracting regular files/directories."""
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        seen: set[PurePosixPath] = set()
        for member in members:
            name = PurePosixPath(member.name)
            if not name.parts or name.is_absolute() or ".." in name.parts or "\\" in member.name:
                raise ValueError(f"Unsafe source archive path: {member.name}")
            # PurePosixPath normalizes './' and repeated separators. Distinct
            # archive headers must not silently overwrite the same output path.
            if name in seen:
                raise ValueError(f"Duplicate source archive path: {member.name}")
            seen.add(name)
            if not (member.isdir() or member.isfile()):
                raise ValueError(f"Unsupported source archive member: {member.name}")
        for member in members:
            name = PurePosixPath(member.name)
            target = destination.joinpath(*name.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as stream, target.open("wb") as output:
                    shutil.copyfileobj(stream, output)
    roots = list(destination.iterdir())
    if len(roots) != 1 or not (roots[0] / "pyproject.toml").is_file():
        raise ValueError("Expected one source archive root containing pyproject.toml")
    return roots[0]


def check_wheel_source(wheel: Path, source: Path) -> None:
    """Refuse a wheel and source archive containing different package code."""
    package = source / "src" / "tracegate"
    expected = {
        path.relative_to(source / "src").as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in package.rglob("*.py")
        if path.is_file()
    }
    with zipfile.ZipFile(wheel) as archive:
        names = [name for name in archive.namelist()
                 if name.startswith("tracegate/") and name.endswith(".py")]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate Python module in wheel")
        actual = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in names}
    if not expected or actual != expected:
        raise ValueError("Wheel package code does not match the source archive")
    print("Verified wheel/source package code match", flush=True)


def check_installed(python, wheel, *, cwd, env):
    result = run([python, "-I", "-c", PROBE], cwd=cwd, env=env, capture=True)
    installed = json.loads(result.stdout)
    with zipfile.ZipFile(wheel) as archive:
        expected = {
            name: hashlib.sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
            if name.startswith("tracegate/") and name.endswith(".py")
        }
    if not expected or installed["hashes"] != expected:
        raise ValueError("Installed package does not match the supplied wheel")
    print(f"Verified non-editable wheel import: {installed['module']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    args = parser.parse_args()
    dist = args.dist_dir.resolve()
    wheels = list(dist.glob("trace_gate-*.whl"))
    sources = list(dist.glob("trace_gate-*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        parser.error("Use a clean dist directory with exactly one wheel and one source archive")
    env = {key: value for key, value in os.environ.items()
           if key not in {"PYTHONPATH", "PYTHONHOME"}}
    env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONNOUSERSITE="1",
               PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_CONFIG_FILE=os.devnull)
    with tempfile.TemporaryDirectory(prefix="trace-gate-distribution-") as temporary:
        work = Path(temporary)
        source = extract_source(sources[0], work / "source")
        check_wheel_source(wheels[0], source)
        check_installed(sys.executable, wheels[0], cwd=source, env=env)
        # Test files and fixtures come exclusively from the source distribution.
        run([sys.executable, "-I", "-m", "pytest", "--import-mode=importlib", "-q"],
            cwd=source, env=env)
        runtime = work / "runtime"
        # Match python -m venv on POSIX: copying a relocatable interpreter
        # (for example Python 3.10 standalone builds) loses its stdlib path.
        venv.EnvBuilder(with_pip=True, symlinks=os.name != "nt").create(runtime)
        python = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run([python, "-I", "-m", "pip", "install", "--no-index", "--no-deps",
             "--no-cache-dir", wheels[0]], cwd=work, env=env)
        check_installed(python, wheels[0], cwd=work, env=env)
        run([python, "-I", source / "tests/installed_smoke.py"], cwd=work, env=env)
        run([python, "-I", source / "tests/installed_otel_smoke.py"], cwd=work, env=env)
        run([python, "-I", "-m", "unittest", "discover", "-s",
             source / "integrations/promptfoo/tests", "-v"], cwd=work, env=env)
    print("PASS: packaged unit tests, isolated CLI and Promptfoo wrapper checks", flush=True)


if __name__ == "__main__":
    main()
