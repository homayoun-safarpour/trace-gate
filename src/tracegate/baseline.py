"""Frozen baseline + regression check.

Sharp contribution: pin known-good composites *and* a SHA-256 of the rubric
that produced them. A check refuses to pass if the rubric file drifted (silent
gate skip via softer criteria) or if scores fall below the pinned floor.
Exit codes match the machines-that-judge stack (0 = clean, 2 = fail closed).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tracegate.score import Rubric, ScoreReport


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


@dataclass(frozen=True)
class Baseline:
    """Pinned scores for one or more trajectories."""

    version: int
    scores: dict[str, float]  # trajectory_name -> composite
    metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    tolerance: float = 0.0
    rubric_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "tolerance": self.tolerance,
            "rubric_sha256": self.rubric_sha256,
            "scores": dict(self.scores),
            "metrics": {k: dict(v) for k, v in self.metrics.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Baseline:
        metrics_raw = data.get("metrics") or {}
        metrics = {
            str(k): {str(mk): float(mv) for mk, mv in v.items()}
            for k, v in metrics_raw.items()
            if isinstance(v, dict)
        }
        scores = {str(k): float(v) for k, v in (data.get("scores") or {}).items()}
        return cls(
            version=int(data.get("version") or 1),
            scores=scores,
            metrics=metrics,
            tolerance=float(data.get("tolerance") or 0.0),
            rubric_sha256=str(data.get("rubric_sha256") or ""),
        )


@dataclass(frozen=True)
class CheckResult:
    verdict: str
    # PASS | REGRESSION | MISSING_BASELINE | UNKNOWN_TRAJECTORY | RUBRIC_DRIFT
    details: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verdict == "PASS"


def freeze_baseline(
    reports: list[ScoreReport],
    *,
    tolerance: float = 0.0,
    version: int = 1,
    rubric: Rubric | None = None,
    rubric_sha256: str = "",
) -> Baseline:
    scores = {r.trajectory_name: r.composite for r in reports}
    metrics = {r.trajectory_name: dict(r.metrics) for r in reports}
    digest = rubric_sha256 or (fingerprint_rubric(rubric) if rubric is not None else "")
    return Baseline(
        version=version,
        scores=scores,
        metrics=metrics,
        tolerance=tolerance,
        rubric_sha256=digest,
    )


def write_baseline(path: str | Path, baseline: Baseline) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(baseline.to_dict(), indent=2) + "\n", encoding="utf-8")


def load_baseline(path: str | Path) -> Baseline:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("baseline must be a JSON object")
    return Baseline.from_dict(data)


def check_against_baseline(
    reports: list[ScoreReport],
    baseline: Baseline,
    *,
    rubric: Rubric | None = None,
) -> CheckResult:
    details: list[str] = []
    if not baseline.scores:
        return CheckResult(verdict="MISSING_BASELINE", details=["baseline has no scores"])

    if baseline.rubric_sha256:
        if rubric is None:
            return CheckResult(
                verdict="RUBRIC_DRIFT",
                details=["baseline pins rubric_sha256 but no rubric was supplied to check"],
            )
        current = fingerprint_rubric(rubric)
        if current != baseline.rubric_sha256:
            return CheckResult(
                verdict="RUBRIC_DRIFT",
                details=[
                    f"rubric fingerprint mismatch: current={current[:12]}… "
                    f"pinned={baseline.rubric_sha256[:12]}… "
                    "(criteria changed; re-freeze deliberately or restore the rubric)"
                ],
            )
        details.append(f"rubric_sha256 OK ({current[:12]}…)")

    regressions = 0
    for report in reports:
        name = report.trajectory_name
        if name not in baseline.scores:
            details.append(f"{name}: not in baseline (skip)")
            continue
        pinned = baseline.scores[name]
        floor = pinned - baseline.tolerance
        if report.composite + 1e-12 < floor:
            regressions += 1
            details.append(
                f"{name}: REGRESSION composite={report.composite:.4f} "
                f"< floor={floor:.4f} (pinned={pinned:.4f}, tol={baseline.tolerance})"
            )
        else:
            details.append(
                f"{name}: PASS composite={report.composite:.4f} "
                f">= floor={floor:.4f} (pinned={pinned:.4f})"
            )

    if not any(r.trajectory_name in baseline.scores for r in reports):
        return CheckResult(verdict="UNKNOWN_TRAJECTORY", details=details or ["no overlap"])

    if regressions:
        return CheckResult(verdict="REGRESSION", details=details)
    return CheckResult(verdict="PASS", details=details)
