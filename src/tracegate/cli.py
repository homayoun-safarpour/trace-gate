"""CLI: score / freeze / check agent trajectories against a frozen baseline."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from tracegate.baseline import (
    check_against_baseline,
    freeze_baseline,
    load_baseline,
    write_baseline,
)
from tracegate.otel import ExportValidationError, load_export
from tracegate.score import Rubric, ScoreReport, score_trajectory
from tracegate.trajectory import TrajectoryValidationError, load_json_document, load_trajectory


def _load_rubric(path: str | Path) -> Rubric:
    data = load_json_document(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("rubric must be a JSON object")
    return Rubric.from_dict(data)


def _score_paths(
    traj_paths: list[str], rubric: Rubric, *, input_format="trajectory",
    coverage: list[str] | None = None,
):
    if input_format == "openinference-otlp" and (
        rubric.min_steps != 0 or rubric.max_steps is not None
    ):
        raise ExportValidationError("OTLP call projection does not support message step bounds")
    reports = []
    for index, p in enumerate(traj_paths):
        traj = (
            load_export(p, coverage[index]).to_trajectory()
            if input_format == "openinference-otlp"
            else load_trajectory(p)
        )
        reports.append(score_trajectory(traj, rubric))
    return reports


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0911 - CLI refusals
    parser = argparse.ArgumentParser(
        prog="trace-gate",
        description="Score agent trajectories and gate deploys on a frozen baseline.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    score_p = sub.add_parser("score", help="score one or more trajectory JSON files")
    score_p.add_argument("trajectories", nargs="+", help="path(s) to trajectory JSON")
    score_p.add_argument("--rubric", required=True, help="path to rubric JSON")
    score_p.add_argument("--json", action="store_true", help="machine-readable output")

    freeze_p = sub.add_parser("freeze", help="write a baseline from current scores")
    freeze_p.add_argument("trajectories", nargs="+")
    freeze_p.add_argument("--rubric", required=True)
    freeze_p.add_argument("--out", required=True, help="baseline JSON path")
    freeze_p.add_argument("--tolerance", type=float, default=0.0)

    check_p = sub.add_parser("check", help="compare scores to a frozen baseline (CI gate)")
    check_p.add_argument("trajectories", nargs="+")
    check_p.add_argument("--rubric", required=True)
    check_p.add_argument("--baseline", required=True)
    check_p.add_argument("--json", action="store_true")

    inspect_p = sub.add_parser("inspect-otel", help="inspect one offline OTLP JSON trace safely")
    inspect_p.add_argument("export")
    inspect_p.add_argument("--coverage", help="optional source-hash-bound coverage declaration")
    inspect_p.add_argument("--out", help="sanitized diagnostic JSON path; defaults to stdout")
    for command in (score_p, freeze_p, check_p):
        command.add_argument(
            "--input-format", choices=("trajectory", "openinference-otlp"), default="trajectory"
        )
        command.add_argument(
            "--coverage", action="append",
            help="one coverage declaration per OTLP export, repeated in export order",
        )

    args = parser.parse_args(argv)
    if args.cmd == "inspect-otel":
        return _inspect_otel(args)
    if args.input_format == "openinference-otlp":
        if not args.coverage or len(args.trajectories) != len(args.coverage):
            print(
                "INVALID_TRAJECTORY: OTLP scoring requires one --coverage per export, "
                "in export order",
                file=sys.stderr,
            )
            return 2
    elif args.coverage:
        print("INVALID_TRAJECTORY: --coverage requires OTLP input", file=sys.stderr)
        return 2
    try:
        rubric = _load_rubric(args.rubric)
    except (OSError, ValueError) as exc:
        print(f"INVALID_RUBRIC: {exc}", file=sys.stderr)
        return 2
    try:
        reports = _score_paths(
            args.trajectories, rubric, input_format=args.input_format, coverage=args.coverage
        )
    except (TrajectoryValidationError, json.JSONDecodeError, OSError) as exc:
        print(f"INVALID_TRAJECTORY: {exc}", file=sys.stderr)
        return 2

    if args.cmd == "score":
        _print_reports(reports, as_json=args.json)
        return 0
    if args.cmd == "freeze":
        return _freeze(args, reports, rubric)
    return _check(args, reports, rubric)


def _protect_inputs(target: Path, inputs: list[Path]) -> None:
    """Refuse direct, symlink and hardlink aliases before writing an artifact."""
    if target.resolve() in [path.resolve() for path in inputs] or (
        target.exists() and any(target.samefile(path) for path in inputs)
    ):
        raise ValueError("output would replace an input")


def _inspect_otel(args: argparse.Namespace) -> int:
    try:
        evidence = load_export(args.export, args.coverage)
        output = json.dumps(evidence.to_dict(), indent=2) + "\n"
        if args.out:
            inputs = [Path(args.export).resolve()]
            if args.coverage:
                inputs.append(Path(args.coverage).resolve())
            target = Path(args.out)
            _protect_inputs(target, inputs)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", delete=False, dir=target.parent
                ) as stream:
                    temporary = Path(stream.name)
                    stream.write(output)
                os.replace(temporary, target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        else:
            print(output, end="")
        return 0 if evidence.gate_eligible else 2
    except (ValueError, OSError):
        print(
            "INVALID_OTLP: cannot inspect malformed, unsupported or unreadable export",
            file=sys.stderr,
        )
        return 2


def _print_reports(reports: list[ScoreReport], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps([r.to_dict() for r in reports], indent=2))
        return
    for r in reports:
        print(f"{r.trajectory_name}: composite={r.composite:.4f}")
        for k, v in r.metrics.items():
            print(f"  {k}={v:.4f}")
        print(f"  policy_ok={str(r.policy_ok).lower()}")
        if r.forbidden_tools_used:
            print(f"  forbidden_tools_used={list(r.forbidden_tools_used)!r}")


def _freeze(args: argparse.Namespace, reports: list[ScoreReport], rubric: Rubric) -> int:
    try:
        baseline = freeze_baseline(reports, tolerance=args.tolerance, rubric=rubric)
        inputs = [Path(path) for path in args.trajectories] + [Path(args.rubric)]
        if args.coverage:
            inputs.extend(Path(path) for path in args.coverage)
        _protect_inputs(Path(args.out), inputs)
        write_baseline(args.out, baseline)
    except (ValueError, OSError) as exc:
        print(f"FREEZE_REFUSED: {exc}", file=sys.stderr)
        return 2
    print(
        f"wrote baseline -> {args.out} "
        f"({len(baseline.scores)} trajectories, rubric_sha256={baseline.rubric_sha256[:12]}...)"
    )
    return 0


def _check(args: argparse.Namespace, reports: list[ScoreReport], rubric: Rubric) -> int:
    try:
        baseline = load_baseline(args.baseline)
    except (ValueError, OSError) as exc:
        print(f"INVALID_BASELINE: {exc}", file=sys.stderr)
        return 2
    result = check_against_baseline(reports, baseline, rubric=rubric)
    if args.json:
        print(
            json.dumps(
                {"verdict": result.verdict, "ok": result.ok, "details": result.details},
                indent=2,
            )
        )
    else:
        print(f"verdict: {result.verdict}")
        for line in result.details:
            print(f"  {line}")
    # Only PASS permits the caller to advance.
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
