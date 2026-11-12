"""Original synthetic regression tests for parser completeness and validation."""
import json

import pytest

from tracegate.cli import main
from tracegate.score import Rubric, score_trajectory
from tracegate.trajectory import Step, Trajectory, TrajectoryValidationError, trajectory_from_dict


def call(name, ident):
    return {"function": {"name": name}, "id": ident}


def test_all_calls_ids_order_and_one_step():
    traj = trajectory_from_dict({"messages": [{"tool_calls": [
        call("read_report", "a"), call("read_report", "b"), call("send_email", "c")
    ]}]})
    assert traj.tools == ("read_report", "read_report", "send_email")
    assert tuple(c.id for c in traj.tool_calls) == ("a", "b", "c")
    assert len(traj.steps) == 1
    report = score_trajectory(traj, Rubric(forbidden_tools=("send_email",), max_steps=1))
    assert report.metrics["forbidden_tools"] == 0
    assert report.metrics["step_band"] == 1


@pytest.mark.parametrize("key", ["steps", "messages", "trajectory"])
def test_explicit_empty_list_is_structurally_valid(key):
    assert trajectory_from_dict({key: []}).steps == ()


@pytest.mark.parametrize("data", [
    {}, [], {"steps": None}, {"steps": False}, {"steps": {}},
    {"steps": [], "messages": [{"tool": "send_email"}]},
    {"steps": [None]}, {"steps": ["bad"]},
    {"steps": [{"tool_calls": None}]}, {"steps": [{"tool_calls": {}}]},
    {"steps": [{"tool_calls": [None]}]},
    {"steps": [{"tool_calls": [{"function": None}]}]},
    {"steps": [{"tool_calls": [{"function": {}}]}]},
    {"steps": [{"tool_calls": [call("", "a")]}]},
    {"steps": [{"tool_calls": [call("x", None)]}]},
    {"steps": [{"tool_calls": [call("x", 1)]}]},
    {"steps": [{"tool": 2}]}, {"steps": [{"tool": ""}]},
    {"steps": [{"tool": "x", "tool_calls": [call("y", "a")]}]},
])
def test_malformed_records_rejected(data):
    with pytest.raises(TrajectoryValidationError):
        trajectory_from_dict(data)


def test_bad_middle_call_cannot_create_partial_safe_trajectory():
    with pytest.raises(TrajectoryValidationError, match=r"messages\[0\].tool_calls\[1\]"):
        trajectory_from_dict({"messages": [{"tool_calls": [
            call("read_report", "a"), None, call("send_email", "c")
        ]}]})


@pytest.mark.parametrize("split", [False, True])
def test_duplicate_ids_rejected_across_or_within_steps(split):
    calls = [call("read_report", "a"), call("send_email", "a")]
    steps = [{"tool_calls": [c]} for c in calls] if split else [{"tool_calls": calls}]
    with pytest.raises(TrajectoryValidationError, match="duplicate"):
        trajectory_from_dict({"steps": steps})


def test_legacy_shape_and_constructor_supported():
    traj = trajectory_from_dict({"steps": [{"tool": "read_report"}, {"name": "send_email"}]})
    assert traj.tools == ("read_report", "send_email")
    assert Trajectory("legacy", (Step("assistant", "x"),)).tools == ("x",)


def test_nested_calls_without_ids_and_flat_shape_supported():
    traj = trajectory_from_dict({"steps": [{"tool_calls": [
        {"function": {"name": "x"}}, {"name": "y"}
    ]}]})
    assert traj.tools == ("x", "y")
    assert tuple(c.id for c in traj.tool_calls) == (None, None)


def test_content_is_not_action_metadata():
    traj = trajectory_from_dict({"steps": [{"content": "send_email succeeded"}]})
    assert traj.tools == ()


@pytest.mark.parametrize("command", ["score", "check", "freeze"])
def test_cli_invalid_input_fails_closed_without_writing(command, tmp_path, capsys):
    trace = tmp_path / "bad.json"
    trace.write_text(json.dumps({"steps": [None]}))
    rubric = tmp_path / "rubric.json"
    rubric.write_text("{}")
    output = tmp_path / "out.json"
    args = [command, str(trace), "--rubric", str(rubric)]
    if command == "check":
        args += ["--baseline", str(output)]
    elif command == "freeze":
        args += ["--out", str(output)]
    assert main(args) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "INVALID_TRAJECTORY" in captured.err
    assert not output.exists()


def test_named_assistant_metadata_does_not_mask_nested_calls():
    traj = trajectory_from_dict({"messages": [{"role": "assistant", "name": "researcher",
        "tool_calls": [call("read_report", "a"), call("send_email", "b")]}]})
    assert traj.tools == ("read_report", "send_email")


def test_named_message_with_empty_calls_is_not_a_tool():
    traj = trajectory_from_dict({"messages": [{"name": "researcher", "tool_calls": []}]})
    assert traj.tools == ()
