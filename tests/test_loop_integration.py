"""Companion harness contract checks; the real runtime has a separate verifier."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "integrations/loop-engine"


def harness():
    spec = importlib.util.spec_from_file_location("loop_verifier_under_test",
                                                HERE / "verify_integration.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_readme_references_packaged_state_and_explains_decision_exit():
    readme = (ROOT / "README.md").read_text()
    assert "--state integrations/loop-engine/LOOP_STATE.md" in readme
    assert (HERE / "LOOP_STATE.md").is_file()
    assert "exits 0 even when its decision is `repair`" in readme
    assert "recursive-include integrations/loop-engine *.py *.json *.md" in (
        ROOT / "MANIFEST.in").read_text()


def test_companion_pin_covers_all_runtime_modules():
    lock = json.loads((HERE / "upstream-lock.json").read_text())
    assert lock["version"] == "0.1.0"
    assert len(lock["commit"]) == 40
    modules = {Path(name).name for name in lock["files"] if name.startswith("src/loopengine/")}
    assert modules == {"__init__.py", "cli.py", "gates.py", "decide.py", "journal.py", "state.py"}


def test_pinned_identity_does_not_import_companion_code(tmp_path, monkeypatch):
    module = harness()
    package = tmp_path / "loopengine"
    package.mkdir()
    code = b'raise AssertionError("this module must not be imported by identity")\n'
    (package / "__init__.py").write_bytes(code)
    lock = {"version": "0.1.0", "commit": "1" * 40, "files": {
        "src/loopengine/__init__.py": {"sha256": hashlib.sha256(code).hexdigest()}}}
    (tmp_path / "upstream-lock.json").write_text(json.dumps(lock))
    monkeypatch.setattr(module, "HERE", tmp_path)
    monkeypatch.setattr(module.importlib.metadata, "distribution", lambda _: SimpleNamespace(
        version="0.1.0", locate_file=lambda name: tmp_path / name))
    assert module.identity()["loop_engine_commit"] == "1" * 40
    (package / "extra.py").write_text("# unreviewed")
    with pytest.raises(ValueError, match="modules differ"):
        module.identity()
    (package / "extra.py").unlink()
    (package / "__init__.py").write_text("# changed")
    with pytest.raises(ValueError, match="modules differ"):
        module.identity()


def test_identity_refuses_unreviewed_version(monkeypatch):
    module = harness()
    monkeypatch.setattr(module.importlib.metadata, "distribution", lambda _: SimpleNamespace(
        version="9.9.9"))
    with pytest.raises(ValueError, match="version differs"):
        module.identity()


def test_synthetic_cases_include_policy_quality_and_configuration_failures(tmp_path):
    cases = harness().build_cases(tmp_path)
    names = {case[0] for case in cases}
    assert names == {"clean", "forbidden", "regression", "unknown-case", "duplicate-case",
                     "rubric-drift", "hashless-baseline", "malformed-input", "missing-baseline"}
    assert [case[2] for case in cases].count(0) == 1
