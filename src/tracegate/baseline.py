"""Frozen baseline + regression check.

The sharp improvement over "score a trajectory once": pin a known-good score
file, then fail CI when a new run drops below it. Exit codes match the rest of
the machines-that-judge stack (0 = clean, 2 = regression).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tracegate.score import ScoreReport


@dataclass(frozen=True)
class Baseline:
    """Pinned scores for one or more trajectories."""

    version: int
    scores: dict[str, float]  # trajectory_name -> composite
    metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    tolerance: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "tolerance": self.tolerance,
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
        )


@dataclass(frozen=True)
class CheckResult:
    verdict: str  # PASS | REGRESSION | MISSING_BASELINE | UNKNOWN_TRAJECTORY
    details: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verdict == "PASS"


def freeze_baseline(
    reports: list[ScoreReport],
    *,
    tolerance: float = 0.0,
    version: int = 1,
) -> Baseline:
    scores = {r.trajectory_name: r.composite for r in reports}
    metrics = {r.trajectory_name: dict(r.metrics) for r in reports}
    return Baseline(version=version, scores=scores, metrics=metrics, tolerance=tolerance)


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
) -> CheckResult:
    details: list[str] = []
    if not baseline.scores:
        return CheckResult(verdict="MISSING_BASELINE", details=["baseline has no scores"])

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
