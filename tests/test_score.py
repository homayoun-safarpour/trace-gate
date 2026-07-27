"""Tests for trajectory loading and scoring claims."""

from __future__ import annotations

from pathlib import Path

from tracegate.score import Rubric, score_trajectory
from tracegate.trajectory import load_trajectory, trajectory_from_dict

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def test_load_example_trajectory_extracts_tools() -> None:
    traj = load_trajectory(EXAMPLES / "trajectories" / "support_good.json")
    assert traj.name == "support-agent-good"
    assert traj.tools == ("lookup_order", "send_reply")


def test_openai_style_tool_calls_nested() -> None:
    traj = trajectory_from_dict(
        {
            "name": "nested",
            "messages": [
                {
                    "role": "assistant",
                    "tool_calls": [{"function": {"name": "search"}}],
                }
            ],
        }
    )
    assert traj.tools == ("search",)


def test_good_trajectory_scores_high_on_rubric() -> None:
    traj = load_trajectory(EXAMPLES / "trajectories" / "support_good.json")
    rubric = Rubric.from_dict(
        {
            "required_tools": ["lookup_order", "send_reply"],
            "forbidden_tools": ["delete_order"],
            "ordered_tools": ["lookup_order", "send_reply"],
            "min_steps": 2,
            "max_steps": 12,
        }
    )
    report = score_trajectory(traj, rubric)
    assert report.composite == 1.0
    assert report.metrics["tool_presence"] == 1.0
    assert report.metrics["forbidden_tools"] == 1.0


def test_forbidden_tool_lowers_score() -> None:
    traj = load_trajectory(EXAMPLES / "trajectories" / "support_bad.json")
    rubric = Rubric.from_dict(
        {
            "required_tools": ["lookup_order", "send_reply"],
            "forbidden_tools": ["delete_order"],
            "ordered_tools": ["lookup_order", "send_reply"],
            "min_steps": 2,
        }
    )
    report = score_trajectory(traj, rubric)
    assert report.metrics["forbidden_tools"] < 1.0
    assert report.metrics["tool_presence"] < 1.0
    assert report.composite < 1.0
