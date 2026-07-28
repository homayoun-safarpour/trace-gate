"""CLI: score / freeze / check agent trajectories against a frozen baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tracegate.baseline import (
    check_against_baseline,
    freeze_baseline,
    load_baseline,
    write_baseline,
)
from tracegate.score import Rubric, score_trajectory
from tracegate.trajectory import load_trajectory


def _load_rubric(path: str | Path) -> Rubric:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("rubric must be a JSON object")
    return Rubric.from_dict(data)


def _score_paths(traj_paths: list[str], rubric: Rubric):
    reports = []
    for p in traj_paths:
        traj = load_trajectory(p)
        reports.append(score_trajectory(traj, rubric))
    return reports


def main(argv: list[str] | None = None) -> int:
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

    args = parser.parse_args(argv)
    rubric = _load_rubric(args.rubric)
    reports = _score_paths(args.trajectories, rubric)

    if args.cmd == "score":
        if args.json:
            print(json.dumps([r.to_dict() for r in reports], indent=2))
        else:
            for r in reports:
                print(f"{r.trajectory_name}: composite={r.composite:.4f}")
                for k, v in r.metrics.items():
                    print(f"  {k}={v:.4f}")
        return 0

    if args.cmd == "freeze":
        baseline = freeze_baseline(reports, tolerance=args.tolerance, rubric=rubric)
        write_baseline(args.out, baseline)
        print(
            f"wrote baseline -> {args.out} "
            f"({len(baseline.scores)} trajectories, rubric_sha256={baseline.rubric_sha256[:12]}…)"
        )
        return 0

    if args.cmd == "check":
        baseline = load_baseline(args.baseline)
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
        # Exit contract: 0 pass, 2 fail-closed (regression / drift / missing / unknown)
        return 0 if result.ok else 2

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
