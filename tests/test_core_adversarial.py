"""Fail-closed regressions discovered during private release review."""
import json
from dataclasses import replace

import pytest

from tracegate.baseline import Baseline, check_against_baseline, freeze_baseline, load_baseline
from tracegate.score import Rubric, score_trajectory
from tracegate.trajectory import load_json_document, load_trajectory, trajectory_from_dict


def scored(rubric):
    return score_trajectory(trajectory_from_dict({"name": "case", "steps": []}), rubric)


def test_reports_scored_under_other_rubric_cannot_pass_pinned_gate():
    strict = Rubric(forbidden_tools=("delete",))
    baseline = freeze_baseline([scored(strict)], rubric=strict)
    # The old API accepted this forbidden trace scored under a permissive rubric,
    # as long as the caller passed the strict rubric separately at check time.
    permissive = score_trajectory(trajectory_from_dict({
        "name": "case", "steps": [{"tool": "delete"}],
    }), Rubric())
    result = check_against_baseline([permissive], baseline, rubric=strict)
    assert result.verdict == "REPORT_RUBRIC_MISMATCH"
    with pytest.raises(ValueError, match="REPORT_RUBRIC_MISMATCH"):
        freeze_baseline([permissive], rubric=strict)


def test_missing_report_provenance_cannot_pass_or_freeze():
    rubric = Rubric()
    good = scored(rubric)
    baseline = freeze_baseline([good], rubric=rubric)
    missing = replace(good, rubric_sha256="")
    assert not check_against_baseline([missing], baseline, rubric=rubric).ok
    with pytest.raises(ValueError, match="REPORT_RUBRIC_MISMATCH"):
        freeze_baseline([missing], rubric_sha256=baseline.rubric_sha256)


def test_mutating_constructor_list_does_not_change_frozen_rubric():
    forbidden = ["delete"]
    rubric = Rubric(forbidden_tools=forbidden)
    forbidden.clear()
    assert rubric.forbidden_tools == ("delete",)


@pytest.mark.parametrize("data", [{"forbiden_tools": ["delete"]}, {"trajectories": []}])
def test_unknown_rubric_fields_are_not_empty_policy(data):
    with pytest.raises(ValueError, match="unknown rubric"):
        Rubric.from_dict(data)


@pytest.mark.parametrize("key", ["name", "id"])
@pytest.mark.parametrize("value", [None, False, 123, [], {}, "", " "])
def test_explicit_invalid_identity_is_not_coerced_or_fallback(key, value):
    with pytest.raises(ValueError, match=f"trajectory.{key}"):
        trajectory_from_dict({key: value, "steps": []})


@pytest.mark.parametrize("text", [
    '{"x": 1, "x": 2}', '{"x": {"tool": "delete", "tool": "read"}}',
    '{"x": NaN}', '{"x": Infinity}', '{"x": -Infinity}', '{"x": 1e999}',
])
def test_strict_document_parser_rejects_ambiguous_or_nonfinite_values(text):
    with pytest.raises(ValueError):
        load_json_document(text)


def test_file_loaders_do_not_silently_drop_earlier_duplicate_fields(tmp_path):
    trace = tmp_path / "trace.json"
    trace.write_text('{"steps":[{"tool":"delete","tool":"read"}]}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_trajectory(trace)
    baseline = tmp_path / "baseline.json"
    baseline.write_text('{"scores":{"case":1.0,"case":0.0}}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_baseline(baseline)


@pytest.mark.parametrize("data", [[], None, {"scores": {}, "tolernace": 1}])
def test_baseline_rejects_malformed_schema(data):
    with pytest.raises(ValueError):
        Baseline.from_dict(data)


def test_invalid_other_metric_is_rejected():
    rubric = Rubric()
    report = scored(rubric)
    baseline = freeze_baseline([report], rubric=rubric)
    report.metrics["tool_presence"] = float("nan")
    assert check_against_baseline([report], baseline, rubric=rubric).verdict == "INVALID_REPORT"


def test_score_serialization_includes_rubric_binding():
    rubric = Rubric()
    report = scored(rubric)
    assert json.loads(json.dumps(report.to_dict()))["rubric_sha256"] == report.rubric_sha256


@pytest.mark.parametrize("text", [
    '{"steps":[], "steps":[]}', '{"steps":[], "metadata":NaN}',
    '{"steps":[], "metadata":1e999}', '[' * 1500 + ']' * 1500,
])
@pytest.mark.parametrize("command", ["score", "check", "freeze"])
def test_malformed_json_cli_is_controlled_refusal(text, command, tmp_path, capsys):
    from tracegate.cli import main

    trajectory = tmp_path / "trajectory.json"
    trajectory.write_text(text)
    rubric = tmp_path / "rubric.json"
    rubric.write_text("{}")
    args = [command, str(trajectory), "--rubric", str(rubric)]
    target = tmp_path / "baseline.json"
    if command == "check":
        args += ["--baseline", str(target)]
    elif command == "freeze":
        args += ["--out", str(target)]
    assert main(args) == 2
    assert "INVALID_TRAJECTORY" in capsys.readouterr().err
    assert not target.exists()


def test_conflicting_flat_and_nested_call_names_cannot_hide_action():
    with pytest.raises(ValueError, match="mixed flat and nested"):
        trajectory_from_dict({"name": "case", "steps": [{"tool_calls": [
            {"name": "delete", "function": {"name": "read"}},
        ]}]})
