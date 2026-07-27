"""Agent trajectory model — tool calls extracted from a JSON run record.

Format is deliberately small and framework-agnostic. A trajectory is a list of
steps. Each step may name a tool that was called. This is the same *shape* of
signal that trajectory evaluators in langchain-ai/agentevals inspect, without
pulling in LangChain or LLM judges.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Step:
    """One agent step. ``tool`` is None for pure reasoning / message steps."""

    role: str
    tool: str | None = None
    content: str = ""


@dataclass(frozen=True)
class Trajectory:
    """A recorded agent run."""

    name: str
    steps: tuple[Step, ...] = field(default_factory=tuple)

    @property
    def tools(self) -> tuple[str, ...]:
        return tuple(s.tool for s in self.steps if s.tool)


def _step_from_mapping(raw: dict[str, Any]) -> Step:
    tool = raw.get("tool") or raw.get("name")
    if tool is not None:
        tool = str(tool)
    role = str(raw.get("role") or raw.get("type") or "assistant")
    content = str(raw.get("content") or raw.get("input") or "")
    # OpenAI-style tool_calls nesting
    if tool is None and "tool_calls" in raw and raw["tool_calls"]:
        first = raw["tool_calls"][0]
        if isinstance(first, dict):
            fn = first.get("function") or first
            if isinstance(fn, dict) and fn.get("name"):
                tool = str(fn["name"])
    return Step(role=role, tool=tool, content=content)


def trajectory_from_dict(data: dict[str, Any]) -> Trajectory:
    name = str(data.get("name") or data.get("id") or "unnamed")
    raw_steps = data.get("steps") or data.get("messages") or data.get("trajectory") or []
    if not isinstance(raw_steps, list):
        raise ValueError("trajectory steps must be a list")
    steps = tuple(_step_from_mapping(s) for s in raw_steps if isinstance(s, dict))
    return Trajectory(name=name, steps=steps)


def load_trajectory(path: str | Path) -> Trajectory:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"trajectory file must be a JSON object: {p}")
    return trajectory_from_dict(data)
