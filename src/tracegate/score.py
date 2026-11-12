"""Deterministic trajectory scorers.

No LLM calls. Each scorer returns a float in [0, 1]. The diagnostic composite
is the mean of all four metrics, including defaults for unconstrained metrics.
Forbidden tools also produce an independent hard-policy signal for the gate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from tracegate.trajectory import Trajectory

CORE_METRICS = ("tool_presence", "forbidden_tools", "tool_order", "step_band")


@dataclass(frozen=True)
class Rubric:
    """What a good trajectory looks like for one task."""

    required_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    ordered_tools: tuple[str, ...] = ()
    min_steps: int = 0
    max_steps: int | None = None

    def __post_init__(self) -> None:
        for field_name in ("required_tools", "forbidden_tools", "ordered_tools"):
            names = getattr(self, field_name)
            if not isinstance(names, list | tuple) or any(
                not isinstance(name, str) or not name.strip() for name in names
            ):
                raise ValueError(f"{field_name} must be a list of non-empty tool names")
            object.__setattr__(self, field_name, tuple(names))
        for field_name in ("min_steps", "max_steps"):
            value = getattr(self, field_name)
            if field_name == "max_steps" and value is None:
                continue
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.max_steps is not None and self.min_steps > self.max_steps:
            raise ValueError("min_steps must not exceed max_steps")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rubric:
        if not isinstance(data, dict):
            raise ValueError("rubric must be an object")
        unknown = set(data) - {"required_tools", "forbidden_tools", "ordered_tools",
                               "min_steps", "max_steps"}
        if unknown:
            raise ValueError(f"unknown rubric fields: {sorted(unknown)!r}")
        # Validate before tuple conversion: a bare string must not become characters.
        for name in ("required_tools", "forbidden_tools", "ordered_tools"):
            if name in data and not isinstance(data[name], list):
                raise ValueError(f"{name} must be a list of non-empty tool names")
        return cls(
            required_tools=tuple(data.get("required_tools", ())),
            forbidden_tools=tuple(data.get("forbidden_tools", ())),
            ordered_tools=tuple(data.get("ordered_tools", ())),
            min_steps=data.get("min_steps", 0),
            max_steps=data.get("max_steps"),
        )


def fingerprint_rubric(rubric: Rubric) -> str:
    """Stable SHA-256 over the rubric fields that affect scores."""
    payload = {
        "required_tools": list(rubric.required_tools),
        "forbidden_tools": list(rubric.forbidden_tools),
        "ordered_tools": list(rubric.ordered_tools),
        "min_steps": rubric.min_steps,
        "max_steps": rubric.max_steps,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class ScoreReport:
    """Quality diagnostics and observed hard-policy violations, kept separate."""

    trajectory_name: str
    metrics: dict[str, float] = field(default_factory=dict)
    composite: float = 0.0
    forbidden_tools_used: tuple[str, ...] = ()
    rubric_sha256: str = ""

    @property
    def policy_ok(self) -> bool:
        # The metric fallback covers reports made with the original API.
        return not self.forbidden_tools_used and self.metrics.get("forbidden_tools") == 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "trajectory_name": self.trajectory_name,
            "metrics": dict(self.metrics),
            "composite": self.composite,
            "forbidden_tools_used": list(self.forbidden_tools_used),
            "policy_ok": self.policy_ok,
            "rubric_sha256": self.rubric_sha256,
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
    forbidden = set(rubric.forbidden_tools)
    used = tuple(dict.fromkeys(tool for tool in traj.tools if tool in forbidden))
    return ScoreReport(
        trajectory_name=traj.name, metrics=metrics, composite=composite,
        forbidden_tools_used=used, rubric_sha256=fingerprint_rubric(rubric),
    )
