"""Promptfoo Python assertion for a complete recorded trace-gate suite.

The provider output is evidence, never a filename, executable, or policy source.
Rubric/baseline paths come only from the trusted assertion configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tracegate.baseline import Baseline, check_against_baseline
from tracegate.score import Rubric, score_trajectory
from tracegate.trajectory import load_json_document, trajectory_from_dict

HERE = Path(__file__).resolve().parent


_load_json = load_json_document


def _read_policy(config: dict[str, Any], key: str) -> dict[str, Any]:
    path = config.get(key)
    if not isinstance(path, str) or not path.strip():
        raise ValueError(f"assertion config requires {key}")
    # Relative paths are anchored to this file, not the process's working directory.
    data = _load_json((HERE / path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{key} must contain a JSON object")
    return data


def get_assert(output: Any, context: dict[str, Any]) -> dict[str, Any]:
    """Return the documented Promptfoo GradingResult contract, fail closed.

    One output contains every baseline case: {"trajectories": [trace, ...]}.
    A failure's score is always zero; quality metrics remain diagnostic only.
    """
    try:
        if not isinstance(context, dict) or not isinstance(context.get("config"), dict):
            raise ValueError("missing trusted assertion config")
        config = context["config"]
        rubric = Rubric.from_dict(_read_policy(config, "rubric_path"))
        baseline = Baseline.from_dict(_read_policy(config, "baseline_path"))
        data = _load_json(output) if isinstance(output, str) else output
        if not isinstance(data, dict) or set(data) != {"trajectories"}:
            raise ValueError("output must be an object containing only trajectories")
        if not isinstance(data["trajectories"], list):
            raise ValueError("trajectories must be an array")
        reports = [score_trajectory(trajectory_from_dict(t), rubric) for t in data["trajectories"]]
        result = check_against_baseline(reports, baseline, rubric=rubric)
        return {
            "pass": result.ok,
            "score": 1.0 if result.ok else 0.0,
            "reason": result.verdict + ": " + "; ".join(result.details),
            "named_scores": {
                "trace_gate": 1.0 if result.ok else 0.0,
                "quality_mean": sum(r.composite for r in reports) / len(reports)
                if reports
                else 0.0,
            },
        }
    except (OSError, ValueError, TypeError, AttributeError, RecursionError) as exc:
        # No missing evidence/configuration is a successful skip. Unexpected import
        # or runtime failures are also failed assertions in Promptfoo itself.
        return {"pass": False, "score": 0.0, "reason": f"INVALID_INPUT: {exc}"}
