"""Tests for frozen-baseline regression + rubric fingerprint enforcement."""

from __future__ import annotations

import json
from pathlib import Path

from tracegate.baseline import (
    Baseline,
    check_against_baseline,
    fingerprint_rubric,
    freeze_baseline,
    load_baseline,
    write_baseline,
)
from tracegate.score import Rubric, ScoreReport, score_trajectory
from tracegate.trajectory import load_trajectory

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _rubric() -> Rubric:
    return Rubric.from_dict(json.loads((EXAMPLES / "rubric.json").read_text(encoding="utf-8")))


def _good_report() -> ScoreReport:
    traj = load_trajectory(EXAMPLES / "trajectories" / "support_good.json")
    return score_trajectory(traj, _rubric())


def test_freeze_and_check_pass_on_same_scores() -> None:
    report = _good_report()
    rubric = _rubric()
    baseline = freeze_baseline([report], tolerance=0.0, rubric=rubric)
    result = check_against_baseline([report], baseline, rubric=rubric)
    assert result.ok
    assert result.verdict == "PASS"
    assert baseline.rubric_sha256 == fingerprint_rubric(rubric)


def test_check_detects_regression_below_floor() -> None:
    """Central claim: a drop below the pinned composite is REGRESSION, not silence."""
    good = _good_report()
    rubric = _rubric()
    baseline = freeze_baseline([good], tolerance=0.05, rubric=rubric)
    degraded = ScoreReport(
        trajectory_name=good.trajectory_name,
        metrics=dict(good.metrics),
        composite=good.composite - 0.2,
    )
    result = check_against_baseline([degraded], baseline, rubric=rubric)
    assert not result.ok
    assert result.verdict == "REGRESSION"


def test_check_refuses_when_rubric_fingerprint_mismatches() -> None:
    """Advanced claim: softening the rubric cannot silently greenlight a check."""
    good = _good_report()
    rubric = _rubric()
    baseline = freeze_baseline([good], tolerance=0.0, rubric=rubric)
    softened = Rubric(
        required_tools=(),
        forbidden_tools=(),
        ordered_tools=(),
        min_steps=0,
        max_steps=None,
    )
    result = check_against_baseline([good], baseline, rubric=softened)
    assert not result.ok
    assert result.verdict == "RUBRIC_DRIFT"


def test_tolerance_allows_small_drop() -> None:
    good = _good_report()
    rubric = _rubric()
    baseline = freeze_baseline([good], tolerance=0.1, rubric=rubric)
    slight = ScoreReport(
        trajectory_name=good.trajectory_name,
        metrics=dict(good.metrics),
        composite=good.composite - 0.05,
    )
    result = check_against_baseline([slight], baseline, rubric=rubric)
    assert result.ok


def test_write_and_load_baseline_roundtrip(tmp_path: Path) -> None:
    report = _good_report()
    rubric = _rubric()
    baseline = freeze_baseline([report], tolerance=0.02, version=1, rubric=rubric)
    path = tmp_path / "baseline.json"
    write_baseline(path, baseline)
    loaded = load_baseline(path)
    assert loaded.scores == baseline.scores
    assert loaded.tolerance == 0.02
    assert loaded.rubric_sha256 == baseline.rubric_sha256


def test_empty_baseline_is_missing() -> None:
    result = check_against_baseline(
        [ScoreReport(trajectory_name="x", metrics={}, composite=1.0)],
        Baseline(version=1, scores={}),
        rubric=_rubric(),
    )
    assert result.verdict == "MISSING_BASELINE"
