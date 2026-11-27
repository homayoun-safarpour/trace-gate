"""Read one PR trace as data; execute only trusted-base checker code."""

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

RELATIVE = Path("examples/trajectories/support_good.json")
LIMIT = 100_000


def read_trace(root):
    root = Path(root).resolve()
    path = root
    for part in RELATIVE.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("symlink input refused")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("non-regular input refused")
    with path.open("rb") as stream:
        data = stream.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError("input exceeds 100000 bytes")
    # Full schema and duplicate-key validation belong to the trusted checker.
    return data


def validated_result(result, exit_code):
    verdicts = {
        "PASS",
        "RUBRIC_DRIFT",
        "MISSING_BASELINE",
        "UNKNOWN_TRAJECTORY",
        "REGRESSION",
        "POLICY_VIOLATION",
        "INVALID_TRAJECTORY",
    }
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("verdict"), str)
        or result["verdict"] not in verdicts
    ):
        raise ValueError("invalid checker result")
    passed = result["verdict"] == "PASS"
    if result.get("ok") is not passed or exit_code != (0 if passed else 2):
        raise ValueError("inconsistent checker result")
    return result["verdict"], passed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    trusted = Path(__file__).resolve().parents[1]
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "input_path": str(RELATIVE),
        "trusted_sha": os.getenv("TRUSTED_SHA", "local"),
        "candidate_sha": os.getenv("CANDIDATE_SHA", "local"),
        "scope": (
            "One recorded example trace against trusted-base rubric/baseline. No "
            "candidate code, tools, skill files or repository dependencies executed. Not "
            "a repository safety scan."
        ),
    }
    try:
        data = read_trace(args.candidate)
        report["input_sha256"] = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            trace = Path(temp) / "trace.json"
            trace.write_bytes(data)
            # -I removes current-directory and PYTHONPATH import injection.
            launcher = (
                "import sys;sys.path.insert(0,sys.argv.pop(1));"
                "from trace_gate.cli import main;raise SystemExit(main())"
            )
            p = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    launcher,
                    str(trusted / "src"),
                    "check",
                    str(trace),
                    "--rubric",
                    str(trusted / "examples/rubric.json"),
                    "--baseline",
                    str(trusted / "examples/baselines/support_v1.json"),
                    "--json",
                ],
                cwd=temp,
                capture_output=True,
                timeout=20,
                text=True,
                check=False,
            )
        report["exit_code"] = p.returncode
        # Do not publish raw trace content, model responses or attacker messages.
        result = json.loads(p.stdout)
        report["verdict"], report["passed"] = validated_result(result, p.returncode)
    except (OSError, ValueError, TypeError, RecursionError, subprocess.TimeoutExpired) as exc:
        report["passed"] = False
        report["verdict"] = "INVALID_OR_UNCHECKED"
        report["error_type"] = type(exc).__name__
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    # Only controlled statuses in Markdown; untrusted diagnostic strings omitted.
    summary = (
        "# PR recorded-trace check\n\n"
        + ("PASS" if report["passed"] else "FAIL")
        + "\n\n"
        + report["scope"]
        + "\n"
    )
    (out / "report.md").write_text(summary)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(summary)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
