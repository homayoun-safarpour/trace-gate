"""Reviewed pins survive failed writes; unrelated linked files are not modified."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

import tracegate.baseline as baseline_module
from tracegate.baseline import freeze_baseline, load_baseline, write_baseline
from tracegate.cli import main
from tracegate.score import Rubric, score_trajectory
from tracegate.trajectory import trajectory_from_dict

ORIGINAL = b"reviewed original bytes\n"
FAILURES = ("create", "write", "flush", "fsync", "close", "replace")


@pytest.fixture
def baseline():
    rubric = Rubric()
    report = score_trajectory(trajectory_from_dict({"name": "case", "steps": []}), rubric)
    return freeze_baseline([report], rubric=rubric)


def inject_failure(monkeypatch, stage, exception=OSError):
    """Fail at an actual I/O boundary, including after a partial staged write."""
    create = baseline_module.tempfile.NamedTemporaryFile

    def fail():
        raise exception("synthetic " + stage + " failure")

    class Stream:
        def __init__(self, *args, **kwargs):
            if stage == "create":
                fail()
            self.stream = create(*args, **kwargs)
            self.name = self.stream.name

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()
            if stage == "close":
                fail()

        def write(self, value):
            if stage == "write":
                self.stream.write(value[:20])
                self.stream.flush()
                fail()
            return self.stream.write(value)

        def flush(self):
            if stage == "flush":
                fail()
            return self.stream.flush()

        def fileno(self):
            return self.stream.fileno()

    monkeypatch.setattr(baseline_module.tempfile, "NamedTemporaryFile", Stream)
    if stage in {"fsync", "replace"}:
        monkeypatch.setattr(baseline_module.os, stage, lambda *args: fail())


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("stage", FAILURES)
def test_io_failure_preserves_pin_and_cleans_staging(baseline, tmp_path, monkeypatch,
                                                  existing, stage):
    target = tmp_path / "baseline.json"
    if existing:
        target.write_bytes(ORIGINAL)
    before = set(tmp_path.iterdir())
    inject_failure(monkeypatch, stage)
    with pytest.raises(OSError, match="synthetic"):
        write_baseline(target, baseline)
    assert set(tmp_path.iterdir()) == before
    assert (target.read_bytes() if existing else target.exists()) == (
        ORIGINAL if existing else False
    )


@pytest.mark.parametrize("existing", [False, True])
def test_keyboard_interrupt_before_commit_preserves_pin(baseline, tmp_path, monkeypatch, existing):
    target = tmp_path / "baseline.json"
    if existing:
        target.write_bytes(ORIGINAL)
    before = set(tmp_path.iterdir())
    inject_failure(monkeypatch, "write", KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        write_baseline(target, baseline)
    assert set(tmp_path.iterdir()) == before
    assert (target.read_bytes() if existing else target.exists()) == (
        ORIGINAL if existing else False
    )


def test_replacement_sees_old_pin_and_complete_closed_staging(baseline, tmp_path, monkeypatch):
    target = tmp_path / "baseline.json"
    target.write_bytes(ORIGINAL)
    replace = os.replace
    create = baseline_module.tempfile.NamedTemporaryFile
    streams = []

    def capture(*args, **kwargs):
        stream = create(*args, **kwargs)
        streams.append(stream)
        return stream

    def commit(source, destination):
        assert destination == target
        assert target.read_bytes() == ORIGINAL
        assert Path(source).parent == target.parent
        assert json.loads(Path(source).read_text(encoding="utf-8")) == baseline.to_dict()
        assert streams[0].closed
        replace(source, destination)

    monkeypatch.setattr(baseline_module.tempfile, "NamedTemporaryFile", capture)
    monkeypatch.setattr(baseline_module.os, "replace", commit)
    write_baseline(target, baseline)
    assert load_baseline(target) == baseline
    assert set(tmp_path.iterdir()) == {target}


@pytest.mark.parametrize("dangling", [False, True])
def test_symlink_output_refused_without_following_it(baseline, tmp_path, dangling):
    other = tmp_path / "other.json"
    if not dangling:
        other.write_bytes(ORIGINAL)
    target = tmp_path / "baseline.json"
    try:
        target.symlink_to(other)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError, match="regular file"):
        write_baseline(target, baseline)
    assert target.is_symlink()
    assert (other.read_bytes() if not dangling else other.exists()) == (
        ORIGINAL if not dangling else False
    )
    assert not list(tmp_path.glob(".trace-gate-*.tmp"))


def test_hardlink_output_replaces_only_requested_directory_entry(baseline, tmp_path):
    other = tmp_path / "other.json"
    other.write_bytes(ORIGINAL)
    target = tmp_path / "baseline.json"
    try:
        target.hardlink_to(other)
    except (OSError, NotImplementedError):
        pytest.skip("hardlinks unavailable")
    write_baseline(target, baseline)
    assert other.read_bytes() == ORIGINAL
    assert not target.samefile(other)
    assert load_baseline(target) == baseline


def test_directory_output_refused_before_staging(baseline, tmp_path):
    target = tmp_path / "baseline.json"
    target.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        write_baseline(target, baseline)
    assert set(tmp_path.iterdir()) == {target}
    assert not list(target.iterdir())


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO requires POSIX")
def test_fifo_output_refused_without_opening_or_replacing_it(baseline, tmp_path):
    target = tmp_path / "baseline.json"
    os.mkfifo(target)
    with pytest.raises(ValueError, match="regular file"):
        write_baseline(target, baseline)
    assert stat.S_ISFIFO(target.lstat().st_mode)
    assert set(tmp_path.iterdir()) == {target}


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_completed_pin_has_private_staging_permissions(baseline, tmp_path, existing):
    target = tmp_path / "baseline.json"
    if existing:
        target.write_bytes(ORIGINAL)
    write_baseline(target, baseline)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


@pytest.mark.parametrize("existing", [False, True])
def test_serialization_failure_does_not_touch_filesystem(baseline, tmp_path, existing):
    target = tmp_path / "parent" / "baseline.json"
    if existing:
        target.parent.mkdir()
        target.write_bytes(ORIGINAL)
    baseline.metrics["case"]["tool_presence"] = float("nan")
    with pytest.raises(ValueError):
        write_baseline(target, baseline)
    assert (target.read_bytes() if existing else target.parent.exists()) == (
        ORIGINAL if existing else False
    )


def test_nested_parent_created_and_unicode_roundtrips(baseline, tmp_path):
    baseline.scores["caf\u00e9"] = baseline.scores.pop("case")
    baseline.metrics["caf\u00e9"] = baseline.metrics.pop("case")
    target = tmp_path / "nested" / "parent" / "baseline.json"
    write_baseline(str(target), baseline)
    assert load_baseline(target) == baseline
    assert target.read_bytes().endswith(b"\n")
    assert set(target.parent.iterdir()) == {target}


@pytest.mark.parametrize("stage", FAILURES)
def test_cli_io_failure_is_refusal_without_success_message(tmp_path, monkeypatch, capsys, stage):
    trajectory = tmp_path / "trace.json"
    trajectory.write_text('{"name":"case","steps":[]}', encoding="utf-8")
    rubric = tmp_path / "rubric.json"
    rubric.write_text("{}", encoding="utf-8")
    target = tmp_path / "baseline.json"
    target.write_bytes(ORIGINAL)
    before = set(tmp_path.iterdir())
    inject_failure(monkeypatch, stage)
    assert main(["freeze", str(trajectory), "--rubric", str(rubric),
                 "--out", str(target)]) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "FREEZE_REFUSED" in output.err
    assert "Traceback" not in output.err
    assert target.read_bytes() == ORIGINAL
    assert set(tmp_path.iterdir()) == before
