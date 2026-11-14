"""The gate rejects internally inconsistent reports rather than repairing evidence."""
from dataclasses import replace

import pytest

from tracegate.baseline import check_against_baseline, freeze_baseline
from tracegate.score import CORE_METRICS, Rubric, score_trajectory
from tracegate.trajectory import trajectory_from_dict


def inputs():
    rubric = Rubric(required_tools=("search",))
    report = score_trajectory(trajectory_from_dict({
        "name": "case", "steps": [{"tool": "search"}],
    }), rubric)
    return rubric, report, freeze_baseline([report], rubric=rubric)


def assert_rejected(rubric, report, baseline):
    result = check_against_baseline([report], baseline, rubric=rubric)
    assert result.verdict == "INVALID_REPORT"
    assert not result.ok
    with pytest.raises(ValueError, match="INVALID_REPORT"):
        freeze_baseline([report], rubric=rubric)


@pytest.mark.parametrize("metric", ["tool_presence", "tool_order", "step_band"])
def test_stale_composite_cannot_hide_an_edited_metric(metric):
    rubric, report, baseline = inputs()
    report.metrics[metric] = 0.0
    assert_rejected(rubric, report, baseline)
    assert report.composite == 1.0  # Refuse; never silently rewrite the report.


@pytest.mark.parametrize("composite", [0.0, 0.9, 1.0 - 1e-9])
def test_edited_composite_cannot_disagree_with_metrics(composite):
    rubric, report, baseline = inputs()
    assert_rejected(rubric, replace(report, composite=composite), baseline)


@pytest.mark.parametrize("metric", CORE_METRICS)
def test_missing_core_metric_cannot_pass_or_freeze(metric):
    rubric, report, baseline = inputs()
    del report.metrics[metric]
    assert_rejected(rubric, report, baseline)


@pytest.mark.parametrize("metrics", [
    {}, None, [], {"forbidden_tools": 1.0},
    dict.fromkeys((*CORE_METRICS, "custom_metric"), 1.0),
    dict.fromkeys(("tool_presence", "forbidden_tools", "tool_order", "step_bnad"), 1.0),
])
def test_malformed_or_unknown_metric_schema_is_rejected(metrics):
    rubric, report, baseline = inputs()
    assert_rejected(rubric, replace(report, metrics=metrics), baseline)


@pytest.mark.parametrize("value", [None, False, "", "delete", [None], [""], [" "], [12]])
def test_malformed_forbidden_tool_list_is_rejected(value):
    rubric, report, baseline = inputs()
    assert_rejected(rubric, replace(report, forbidden_tools_used=value), baseline)


def test_metric_dictionary_order_and_integer_ones_do_not_change_acceptance():
    rubric, report, baseline = inputs()
    report.metrics = dict.fromkeys(reversed(CORE_METRICS), 1)
    report.forbidden_tools_used = []
    assert check_against_baseline([report], baseline, rubric=rubric).ok
    assert freeze_baseline([report], rubric=rubric).scores == baseline.scores


def test_tiny_arithmetic_roundoff_is_allowed():
    rubric, report, baseline = inputs()
    report.composite -= 5e-13
    assert check_against_baseline([report], baseline, rubric=rubric).ok


def test_real_rescoring_remains_a_regression_not_invalid_evidence():
    rubric, _, baseline = inputs()
    report = score_trajectory(trajectory_from_dict({"name": "case", "steps": []}), rubric)
    assert report.composite == 0.75
    assert check_against_baseline([report], baseline, rubric=rubric).verdict == "REGRESSION"


def test_fresh_forbidden_tool_report_still_triggers_independent_veto():
    rubric = Rubric(forbidden_tools=("delete",))
    good = score_trajectory(trajectory_from_dict({"name": "case", "steps": []}), rubric)
    baseline = freeze_baseline([good], rubric=rubric, tolerance=1.0)
    bad = score_trajectory(trajectory_from_dict({
        "name": "case", "steps": [{"tool": "delete"}],
    }), rubric)
    assert check_against_baseline([bad], baseline, rubric=rubric).verdict == "POLICY_VIOLATION"
