"""Deterministic trajectory scorers.

No LLM calls. Each scorer returns a float in [0, 1]. The composite score is the
mean of enabled scorers. Specs live in a JSON "rubric" so CI pins expectations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tracegate.trajectory import Trajectory


@dataclass(frozen=True)
class Rubric:
    """What a good trajectory looks like for one task."""

    required_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    ordered_tools: tuple[str, ...] = ()
    min_steps: int = 0
    max_steps: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rubric:
        max_steps = data.get("max_steps")
        return cls(
            required_tools=tuple(data.get("required_tools") or ()),
            forbidden_tools=tuple(data.get("forbidden_tools") or ()),
            ordered_tools=tuple(data.get("ordered_tools") or ()),
            min_steps=int(data.get("min_steps") or 0),
            max_steps=int(max_steps) if max_steps is not None else None,
        )


@dataclass
class ScoreReport:
    """Per-metric scores plus composite mean."""

    trajectory_name: str
    metrics: dict[str, float] = field(default_factory=dict)
    composite: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "trajectory_name": self.trajectory_name,
            "metrics": dict(self.metrics),
            "composite": self.composite,
        }


def _tool_presence(traj: Trajectory, required: tuple[str, ...]) -> float:
    if not required:
        return 1.0
    present = set(traj.tools)
    hits = sum(1 for t in required if t in present)
    return hits / len(required)


def _forbidden_penalty(traj: Trajectory, forbidden: tuple[str, ...]) -> float:
    if not forbidden:
        return 1.0
    present = set(traj.tools)
    violations = sum(1 for t in forbidden if t in present)
    if violations == 0:
        return 1.0
    return max(0.0, 1.0 - violations / len(forbidden))


def _tool_order(traj: Trajectory, ordered: tuple[str, ...]) -> float:
    """Score how well the required ordered subsequence appears in the tool list."""
    if not ordered:
        return 1.0
    tools = list(traj.tools)
    idx = 0
    matched = 0
    for want in ordered:
        while idx < len(tools):
            if tools[idx] == want:
                matched += 1
                idx += 1
                break
            idx += 1
        else:
            break
    return matched / len(ordered)


def _step_band(traj: Trajectory, min_steps: int, max_steps: int | None) -> float:
    n = len(traj.steps)
    if n < min_steps:
        return 0.0
    if max_steps is not None and n > max_steps:
        return 0.0
    return 1.0


def score_trajectory(traj: Trajectory, rubric: Rubric) -> ScoreReport:
    metrics = {
        "tool_presence": _tool_presence(traj, rubric.required_tools),
        "forbidden_tools": _forbidden_penalty(traj, rubric.forbidden_tools),
        "tool_order": _tool_order(traj, rubric.ordered_tools),
        "step_band": _step_band(traj, rubric.min_steps, rubric.max_steps),
    }
    composite = sum(metrics.values()) / len(metrics)
    return ScoreReport(trajectory_name=traj.name, metrics=metrics, composite=composite)
