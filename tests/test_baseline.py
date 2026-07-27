"""Tests for the frozen-baseline regression gate — central product claim."""

from __future__ import annotations

import json
from pathlib import Path

from tracegate.baseline import (
    Baseline,
    check_against_baseline,
    freeze_baseline,
    load_baseline,
    write_baseline,
)
from tracegate.score import Rubric, ScoreReport, score_trajectory
from tracegate.trajectory import load_trajectory

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def _good_report() -> ScoreReport:
    traj = load_trajectory(EXAMPLES / "trajectories" / "support_good.json")
    rubric = Rubric.from_dict(
        json.loads((EXAMPLES / "rubric.json").read_text(encoding="utf-8"))
    )
    return score_trajectory(traj, rubric)


def test_freeze_and_check_pass_on_same_scores() -> None:
    report = _good_report()
    baseline = freeze_baseline([report], tolerance=0.0)
    result = check_against_baseline([report], baseline)
    assert result.ok
    assert result.verdict == "PASS"


def test_check_detects_regression_below_floor() -> None:
    """Central claim: a drop below the pinned composite is REGRESSION, not silence."""
    good = _good_report()
    baseline = freeze_baseline([good], tolerance=0.05)
    degraded = ScoreReport(
        trajectory_name=good.trajectory_name,
        metrics=dict(good.metrics),
        composite=good.composite - 0.2,
    )
    result = check_against_baseline([degraded], baseline)
    assert not result.ok
    assert result.verdict == "REGRESSION"


def test_tolerance_allows_small_drop() -> None:
    good = _good_report()
    baseline = freeze_baseline([good], tolerance=0.1)
    slight = ScoreReport(
        trajectory_name=good.trajectory_name,
        metrics=dict(good.metrics),
        composite=good.composite - 0.05,
    )
    result = check_against_baseline([slight], baseline)
    assert result.ok


def test_write_and_load_baseline_roundtrip(tmp_path: Path) -> None:
    report = _good_report()
    baseline = freeze_baseline([report], tolerance=0.02, version=1)
    path = tmp_path / "baseline.json"
    write_baseline(path, baseline)
    loaded = load_baseline(path)
    assert loaded.scores == baseline.scores
    assert loaded.tolerance == 0.02


def test_empty_baseline_is_missing() -> None:
    result = check_against_baseline(
        [ScoreReport(trajectory_name="x", metrics={}, composite=1.0)],
        Baseline(version=1, scores={}),
    )
    assert result.verdict == "MISSING_BASELINE"
