"""Frozen baseline + regression check.

Sharp contribution: pin known-good composites *and* a SHA-256 of the rubric
that produced them. A check refuses to pass if the rubric file drifted (silent
gate skip via softer criteria) or if scores fall below the pinned floor.
Exit codes match the machines-that-judge stack (0 = clean, 2 = fail closed).
"""

from __future__ import annotations

import json
import math
import os
import stat
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tracegate.score import CORE_METRICS, Rubric, ScoreReport, fingerprint_rubric
from tracegate.trajectory import load_json_document

SHA256_HEX_LENGTH = 64
COMPOSITE_ABS_TOLERANCE = 1e-12



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
        if not isinstance(data, dict):
            raise ValueError("baseline must be an object")
        unknown = set(data) - {"version", "scores", "metrics", "tolerance", "rubric_sha256"}
        if unknown:
            raise ValueError(f"unknown baseline fields: {sorted(unknown)!r}")
        scores = data.get("scores", {})
        if not isinstance(scores, dict) or any(
            not isinstance(name, str) or not name.strip() for name in scores
        ):
            raise ValueError("scores must be an object with non-empty case names")
        metrics = data.get("metrics", {})
        if not isinstance(metrics, dict) or any(not isinstance(v, dict) for v in metrics.values()):
            raise ValueError("metrics must be an object of objects")
        return cls(
            version=data.get("version", 1),
            scores=scores,
            metrics=metrics,
            tolerance=data.get("tolerance", 0.0),
            rubric_sha256=data.get("rubric_sha256", ""),
        )


@dataclass(frozen=True)
class CheckResult:
    verdict: str
    details: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verdict == "PASS"


def _unit_interval(value: Any) -> bool:
    return type(value) in (int, float) and 0 <= value <= 1 and math.isfinite(value)


def _report_shape_problem(report: ScoreReport) -> str | None:
    if not _unit_interval(report.composite):
        return "invalid composite"
    if not isinstance(report.metrics, dict) or set(report.metrics) != set(CORE_METRICS):
        return "metrics must contain exactly the four core metric names"
    if any(not _unit_interval(value) for value in report.metrics.values()):
        return "invalid metrics"
    expected = sum(report.metrics[name] for name in CORE_METRICS) / len(CORE_METRICS)
    if not math.isclose(report.composite, expected, rel_tol=0.0,
                        abs_tol=COMPOSITE_ABS_TOLERANCE):
        return "composite does not match the mean of its metrics; rescore the original trajectory"
    if not isinstance(report.forbidden_tools_used, list | tuple) or any(
        not isinstance(name, str) or not name.strip() for name in report.forbidden_tools_used
    ):
        return "forbidden_tools_used must be a list or tuple of non-empty tool names"
    return None


def _report_problem(reports: list[ScoreReport]) -> CheckResult | None:  # noqa: PLR0911
    if any(not isinstance(r, ScoreReport) for r in reports):
        return CheckResult("INVALID_REPORT", ["expected ScoreReport objects"])
    if any(not isinstance(r.trajectory_name, str) or not r.trajectory_name.strip()
           for r in reports):
        return CheckResult("INVALID_REPORT", ["case names must be non-empty strings"])
    duplicates = sorted(name for name, n in Counter(r.trajectory_name for r in reports).items()
                        if n > 1)
    if duplicates:
        return CheckResult("DUPLICATE_TRAJECTORY", [f"duplicate case names: {duplicates!r}"])
    for report in reports:
        if problem := _report_shape_problem(report):
            return CheckResult("INVALID_REPORT", [f"{report.trajectory_name}: {problem}"])
    violations = [
        f"{r.trajectory_name}: POLICY_VIOLATION forbidden_tools_used="
        f"{list(r.forbidden_tools_used)!r} (forbidden_tools={r.metrics['forbidden_tools']:.4f}; "
        "tolerance does not apply)"
        for r in reports if not r.policy_ok
    ]
    if violations:
        return CheckResult("POLICY_VIOLATION", violations)
    return None


def _baseline_problem(baseline: Baseline) -> CheckResult | None:
    if not isinstance(baseline.scores, dict) or any(
        not isinstance(name, str) or not name.strip() for name in baseline.scores
    ):
        return CheckResult("INVALID_BASELINE", ["scores require non-empty case names"])
    if type(baseline.version) is not int or baseline.version != 1:
        return CheckResult("INVALID_BASELINE", ["unsupported baseline version; expected 1"])
    if not baseline.scores:
        return CheckResult("MISSING_BASELINE", ["baseline has no scores"])
    if not _unit_interval(baseline.tolerance):
        return CheckResult("INVALID_BASELINE", ["tolerance must be finite and between 0 and 1"])
    if any(not _unit_interval(score) for score in baseline.scores.values()):
        return CheckResult(
            "INVALID_BASELINE", ["baseline scores must be finite and between 0 and 1"],
        )
    return _fingerprint_problem(baseline.rubric_sha256)


def _fingerprint_problem(digest: Any) -> CheckResult | None:
    if digest is None or digest == "":
        return CheckResult("MISSING_RUBRIC_FINGERPRINT", [
            "baseline has no rubric_sha256; review the rubric and original trajectories, "
            "then re-freeze deliberately (legacy baselines are not trusted automatically)",
        ])
    if (not isinstance(digest, str) or len(digest) != SHA256_HEX_LENGTH
            or any(c not in "0123456789abcdef" for c in digest)):
        return CheckResult(
            "INVALID_BASELINE", ["rubric_sha256 must be 64 lowercase hex characters"],
        )
    return None


def _report_provenance_problem(reports: list[ScoreReport], digest: str) -> CheckResult | None:
    if any(r.rubric_sha256 != digest for r in reports):
        return CheckResult("REPORT_RUBRIC_MISMATCH", [
            "reports must be scored using the pinned rubric; "
            "missing or mismatched report provenance",
        ])
    return None


def freeze_baseline(
    reports: list[ScoreReport],
    *,
    tolerance: float = 0.0,
    version: int = 1,
    rubric: Rubric | None = None,
    rubric_sha256: str = "",
) -> Baseline:
    if problem := _report_problem(reports):
        raise ValueError(f"{problem.verdict}: {'; '.join(problem.details)}")
    scores = {r.trajectory_name: r.composite for r in reports}
    metrics = {r.trajectory_name: dict(r.metrics) for r in reports}
    digest = rubric_sha256 or (fingerprint_rubric(rubric) if rubric is not None else "")
    baseline = Baseline(
        version=version,
        scores=scores,
        metrics=metrics,
        tolerance=tolerance,
        rubric_sha256=digest,
    )
    if rubric is not None and digest != fingerprint_rubric(rubric):
        raise ValueError("RUBRIC_DRIFT: supplied rubric_sha256 does not match rubric")
    if problem := _baseline_problem(baseline):
        raise ValueError(f"{problem.verdict}: {'; '.join(problem.details)}")
    if problem := _report_provenance_problem(reports, digest):
        raise ValueError(f"{problem.verdict}: {'; '.join(problem.details)}")
    return baseline


def write_baseline(path: str | Path, baseline: Baseline) -> None:
    """Stage a complete pin before replacing its directory entry atomically.

    A failed write/flush/sync/close/replace leaves any previous pin untouched.
    The private staging file is in the destination directory, so replacement
    cannot cross filesystems. This is not concurrent-writer locking or a
    guarantee of directory-entry durability after sudden power loss.
    """
    payload = json.dumps(baseline.to_dict(), indent=2, allow_nan=False) + "\n"
    p = Path(path)
    try:
        target_mode = p.lstat().st_mode
    except FileNotFoundError:
        pass
    else:
        if not stat.S_ISREG(target_mode):
            raise ValueError("baseline output must be a regular file, not a symlink or device")
    p.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False, dir=p.parent,
            prefix=".trace-gate-", suffix=".tmp",
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, p)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_baseline(path: str | Path) -> Baseline:
    data = load_json_document(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("baseline must be a JSON object")
    return Baseline.from_dict(data)


def check_against_baseline(  # noqa: PLR0911 - fail-closed checks
    reports: list[ScoreReport],
    baseline: Baseline,
    *,
    rubric: Rubric | None = None,
) -> CheckResult:
    details: list[str] = []
    if problem := _baseline_problem(baseline):
        return problem

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
                f"rubric fingerprint mismatch: current={current[:12]}... "
                f"pinned={baseline.rubric_sha256[:12]}... "
                "(criteria changed; re-freeze deliberately or restore the rubric)"
            ],
        )
    details.append(f"rubric_sha256 OK ({current[:12]}...)")
    if problem := _report_problem(reports):
        return CheckResult(problem.verdict, details + problem.details)

    if problem := _report_provenance_problem(reports, current):
        return CheckResult(problem.verdict, details + problem.details)

    names = {r.trajectory_name for r in reports}
    unknown = sorted(names - baseline.scores.keys())
    missing = sorted(baseline.scores.keys() - names)
    coverage_details = ([f"not in baseline: {unknown!r}"] if unknown else [])
    coverage_details += ([f"baseline cases not supplied: {missing!r}"] if missing else [])
    if unknown or missing:
        verdict = "UNKNOWN_TRAJECTORY" if unknown else "MISSING_TRAJECTORY"
        return CheckResult(verdict, details + coverage_details)

    regressions = 0
    for report in reports:
        name = report.trajectory_name
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

    return CheckResult(verdict="REGRESSION" if regressions else "PASS", details=details)
