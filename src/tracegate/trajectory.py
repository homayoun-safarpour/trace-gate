"""Validated, framework-neutral agent trajectories (no tools are executed)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class TrajectoryValidationError(ValueError):
    """Invalid evidence must not be converted into a scored trajectory."""


@dataclass(frozen=True)
class ToolCall:
    """One recorded attempt, not proof that its action succeeded."""

    name: str
    id: str | None = None


@dataclass(frozen=True)
class Step:
    """One message/step; nested calls do not increase the step count."""

    role: str
    tool: str | None = None
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True)
class Trajectory:
    """A structurally validated recorded run; not an authenticity guarantee."""

    name: str
    steps: tuple[Step, ...] = field(default_factory=tuple)

    @property
    def tools(self) -> tuple[str, ...]:
        return tuple(call.name for call in self.tool_calls)

    @property
    def tool_calls(self) -> tuple[ToolCall, ...]:
        return tuple(
            call
            for step in self.steps
            for call in (step.tool_calls or ((ToolCall(step.tool),) if step.tool else ()))
        )


def _nonempty_string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrajectoryValidationError(f"{location}: expected a non-empty string")
    return value


def _call_from_mapping(raw: Any, location: str) -> ToolCall:
    if not isinstance(raw, dict):
        raise TrajectoryValidationError(f"{location}: expected an object")
    if "function" in raw and "name" in raw:
        raise TrajectoryValidationError(f"{location}: mixed flat and nested call names")
    function = raw.get("function", raw)
    if not isinstance(function, dict):
        raise TrajectoryValidationError(f"{location}.function: expected an object")
    name = _nonempty_string(function.get("name"), f"{location}.name")
    call_id = raw.get("id")
    if "id" in raw:
        call_id = _nonempty_string(call_id, f"{location}.id")
    return ToolCall(name, call_id)


def _step_from_mapping(raw: dict[str, Any], location: str = "step") -> Step:
    # With nested calls, name is message-participant metadata, not a tool alias.
    tool = raw.get("tool")
    if "tool_calls" not in raw and tool is None:
        tool = raw.get("name")
    if "tool" in raw and raw["tool"] is not None:
        tool = _nonempty_string(raw["tool"], f"{location}.tool")
    elif tool is not None:
        tool = _nonempty_string(tool, f"{location}.name")
    role = str(raw.get("role") or raw.get("type") or "assistant")
    content = str(raw.get("content") or raw.get("input") or "")
    calls: tuple[ToolCall, ...] = ()
    if "tool_calls" in raw:
        nested = raw["tool_calls"]
        if not isinstance(nested, list):
            raise TrajectoryValidationError(f"{location}.tool_calls: expected a list")
        calls = tuple(
            _call_from_mapping(call, f"{location}.tool_calls[{i}]")
            for i, call in enumerate(nested)
        )
        # Mixing two representations cannot establish ordering or duplication.
        if tool is not None and calls:
            raise TrajectoryValidationError(f"{location}: mixed direct and nested tool calls")
    if calls:
        tool = calls[0].name  # Compatibility view only; scoring uses all calls.
    return Step(role=role, tool=tool, content=content, tool_calls=calls)


def trajectory_from_dict(data: dict[str, Any]) -> Trajectory:
    if not isinstance(data, dict):
        raise TrajectoryValidationError("trajectory: expected an object")
    # Unnamed standalone scoring remains supported, but supplied identities must
    # never be coerced or silently replaced by a different fallback identity.
    for key in ("name", "id"):
        if key in data:
            _nonempty_string(data[key], f"trajectory.{key}")
    name = data.get("name", data.get("id", "unnamed"))
    keys = [key for key in ("steps", "messages", "trajectory") if key in data]
    if len(keys) != 1:
        raise TrajectoryValidationError("trajectory: expected exactly one step-list field")
    key = keys[0]
    raw_steps = data[key]
    if not isinstance(raw_steps, list):
        raise TrajectoryValidationError(f"{key}: expected a list")
    steps = []
    seen_ids: set[str] = set()
    for i, raw in enumerate(raw_steps):
        location = f"{key}[{i}]"
        if not isinstance(raw, dict):
            raise TrajectoryValidationError(f"{location}: expected an object")
        step = _step_from_mapping(raw, location)
        for call in step.tool_calls:
            if call.id is not None:
                if call.id in seen_ids:
                    raise TrajectoryValidationError(f"{location}: duplicate tool call ID")
                seen_ids.add(call.id)
        steps.append(step)
    return Trajectory(name=name, steps=tuple(steps))


def load_json_document(value: str) -> Any:
    """Decode evidence/policy without duplicate-key or non-finite ambiguity."""
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = item
        return result

    def reject_constant(constant: str) -> None:
        raise ValueError(f"non-finite JSON constant: {constant}")

    def finite_float(number: str) -> float:
        import math
        result = float(number)
        if not math.isfinite(result):
            raise ValueError(f"non-finite JSON number: {number}")
        return result

    try:
        return json.loads(value, object_pairs_hook=unique_object,
                          parse_constant=reject_constant, parse_float=finite_float)
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds the supported depth") from exc


def load_trajectory(path: str | Path) -> Trajectory:
    p = Path(path)
    try:
        data = load_json_document(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise TrajectoryValidationError(str(exc)) from exc
    return trajectory_from_dict(data)
