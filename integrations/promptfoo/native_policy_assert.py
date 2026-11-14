"""Independent native Promptfoo Python comparator, configured to check tool policy.

Intentionally no trace-gate dependency or baseline/fingerprint logic. This is a
configured baseline, not a claim about the maximum capabilities of Promptfoo.
"""

from __future__ import annotations

import json
from typing import Any


def tool_names(step):
    if not isinstance(step, dict):
        raise ValueError("step must be an object")
    names = []
    if step.get("tool") is not None:
        names.append(step["tool"])
    if "tool_calls" in step:
        if not isinstance(step["tool_calls"], list):
            raise ValueError("tool_calls must be an array")
        for call in step["tool_calls"]:
            if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
                raise ValueError("expected function object")
            names.append(call["function"].get("name"))
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError("expected non-empty tool names")
    return names


def get_assert(output: Any, context: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(output) if isinstance(output, str) else output
        if not isinstance(data, dict) or not isinstance(data.get("trajectories"), list):
            raise ValueError("expected trajectories array")
        forbidden = set(context["config"]["forbidden_tools"])
        for trace in data["trajectories"]:
            if not isinstance(trace, dict) or not isinstance(trace.get("steps"), list):
                raise ValueError("expected steps array")
            for step in trace["steps"]:
                names = tool_names(step)
                violations = sorted(forbidden.intersection(names))
                if violations:
                    return {"pass": False, "score": 0, "reason": f"forbidden tools: {violations}"}
        return {
            "pass": True,
            "score": 1,
            "reason": "configured native tool-policy assertion passed",
        }
    except (ValueError, TypeError, KeyError) as exc:
        return {"pass": False, "score": 0, "reason": f"invalid trace: {exc}"}
