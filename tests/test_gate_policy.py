"""Gate refusals must not be diluted by averages or incomplete evidence."""

from __future__ import annotations

from dataclasses import replace

import pytest

from tracegate.baseline import Baseline, check_against_baseline, freeze_baseline
from tracegate.score import Rubric, score_trajectory
from tracegate.trajectory import trajectory_from_dict


def report(name="case", tools=("read",), *, rubric):
    return score_trajectory(
        trajectory_from_dict({"name": name, "steps": [{"tool": tool} for tool in tools]}),
        rubric,
    )


@pytest.mark.parametrize("forbidden_count", [1, 10, 100])
@pytest.mark.parametrize("tolerance", [0.05, 1.0])
def test_forbidden_tool_veto_cannot_be_diluted(forbidden_count, tolerance):
    rubric = Rubric(forbidden_tools=tuple(f"forbidden_{i}" for i in range(forbidden_count)))
    good = report(rubric=rubric)
    bad = report(tools=("read", "forbidden_0"), rubric=rubric)
    baseline = freeze_baseline([good], tolerance=tolerance, rubric=rubric)
    result = check_against_baseline([bad], baseline, rubric=rubric)
    assert result.verdict == "POLICY_VIOLATION"
    assert not result.ok
    assert "forbidden_0" in " ".join(result.details)


def test_freeze_rejects_forbidden_tool_even_with_permissive_tolerance():
    rubric = Rubric(forbidden_tools=("delete",))
    bad = report(tools=("delete",), rubric=rubric)
    with pytest.raises(ValueError, match="POLICY_VIOLATION"):
        freeze_baseline([bad], tolerance=1.0, rubric=rubric)


def test_known_case_does_not_hide_unknown_case():
    rubric = Rubric()
    good = report(rubric=rubric)
    unknown = report(name="unreviewed", rubric=rubric)
    baseline = freeze_baseline([good], rubric=rubric)
    result = check_against_baseline([good, unknown], baseline, rubric=rubric)
    assert result.verdict == "UNKNOWN_TRAJECTORY"
    assert not result.ok
    assert "unreviewed" in " ".join(result.details)


def test_omitting_a_baseline_case_fails_closed():
    rubric = Rubric()
    first = report(rubric=rubric)
    second = report(name="required-second-case", rubric=rubric)
    baseline = freeze_baseline([first, second], rubric=rubric)
    result = check_against_baseline([first], baseline, rubric=rubric)
    assert result.verdict == "MISSING_TRAJECTORY"
    assert "required-second-case" in " ".join(result.details)


def test_duplicate_case_names_fail_closed():
    rubric = Rubric()
    good = report(rubric=rubric)
    baseline = freeze_baseline([good], rubric=rubric)
    result = check_against_baseline([good, good], baseline, rubric=rubric)
    assert result.verdict == "DUPLICATE_TRAJECTORY"
    with pytest.raises(ValueError, match="DUPLICATE_TRAJECTORY"):
        freeze_baseline([good, good], rubric=rubric)


def test_missing_fingerprint_is_not_legacy_success():
    rubric = Rubric()
    good = report(rubric=rubric)
    legacy = Baseline.from_dict({"version": 1, "scores": {"case": 1.0}})
    result = check_against_baseline([good], legacy, rubric=rubric)
    assert result.verdict == "MISSING_RUBRIC_FINGERPRINT"
    assert not result.ok
    assert "re-freeze" in " ".join(result.details)


def test_freeze_requires_fingerprint_source():
    good = report(rubric=Rubric())
    with pytest.raises(ValueError, match="rubric"):
        freeze_baseline([good])


def test_refreeze_reviewed_legacy_trace_restores_compatible_baseline():
    rubric = Rubric()
    good = report(rubric=rubric)
    baseline = freeze_baseline([good], rubric=rubric)
    restored = Baseline.from_dict(baseline.to_dict())
    assert restored.version == 1
    assert check_against_baseline([good], restored, rubric=rubric).ok


def test_legacy_bad_pin_cannot_authorize_forbidden_tools():
    rubric = Rubric(forbidden_tools=("delete",))
    good = report(rubric=rubric)
    baseline = freeze_baseline([good], rubric=rubric)
    # Simulates a baseline frozen by the older, permissive scorer.
    legacy_bad = replace(baseline, scores={"case": 0.0}, tolerance=1.0)
    bad = report(tools=("delete",), rubric=rubric)
    assert check_against_baseline([bad], legacy_bad, rubric=rubric).verdict == "POLICY_VIOLATION"


@pytest.mark.parametrize("name", ["", None, 123, []])
def test_report_names_are_validated_before_duplicate_check(name):
    rubric = Rubric()
    good = report(rubric=rubric)
    baseline = freeze_baseline([good], rubric=rubric)
    malformed = replace(good, trajectory_name=name)
    assert check_against_baseline([malformed], baseline, rubric=rubric).verdict == "INVALID_REPORT"
