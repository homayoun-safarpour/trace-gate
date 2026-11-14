"""Check real loop-engine decisions against installed trace-gate CLI outcomes.

Use a disposable environment containing the reviewed trace-gate wheel and pinned
agent-loop-engine package. No installation, network request or model call occurs.
Only fixed synthetic gate commands are executed. This harness requires POSIX
shell quoting; no Windows integration claim is made.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

import tracegate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPECTED_TARGET = "Review the next synthetic case"
RECOVERY_TICKS = 2


def identity() -> dict:
    lock = json.loads((HERE / "upstream-lock.json").read_text())
    distribution = importlib.metadata.distribution("agent-loop-engine")
    if distribution.version != lock["version"]:
        raise ValueError("installed loop-engine version differs from the reviewed pin")
    directory = Path(distribution.locate_file("loopengine")).resolve()
    actual = {"src/loopengine/" + path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in directory.glob("*.py")}
    expected = {name: item["sha256"] for name, item in lock["files"].items()
                if name.startswith("src/loopengine/")}
    if actual != expected:
        raise ValueError("installed loop-engine modules differ from the reviewed pin")
    return {"python": platform.python_version(), "loop_engine_version": distribution.version,
            "loop_engine_commit": lock["commit"], "loop_engine_modules": actual,
            "trace_gate_version": tracegate.__version__, "trace_gate_modules": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in Path(tracegate.__file__).resolve().parent.glob("*.py")}}


def write_json(path: Path, data) -> Path:
    path.write_text(json.dumps(data))
    return path


def build_cases(work: Path) -> list[tuple]:
    examples = ROOT / "examples"
    good = examples / "trajectories/support_good.json"
    rubric = examples / "rubric.json"
    baseline = examples / "baselines/support_v1.json"

    def arguments(*sources, policy=rubric, pin=baseline):
        return ["check", *sources, "--rubric", policy, "--baseline", pin, "--json"]

    malformed = work / "malformed.json"
    malformed.write_text('{"steps": [')
    regressed = json.loads(good.read_text())
    regressed["steps"] = [step for step in regressed["steps"] if step.get("tool") != "lookup_order"]
    regression = write_json(work / "regression.json", regressed)
    unknown = json.loads(good.read_text())
    unknown["name"] = "unreviewed-case"
    unknown_path = write_json(work / "unknown.json", unknown)
    drift = json.loads(rubric.read_text())
    drift["required_tools"] = ["send_reply"]
    drift_path = write_json(work / "drift.json", drift)
    hashless = json.loads(baseline.read_text())
    hashless.pop("rubric_sha256")
    hashless_path = write_json(work / "hashless.json", hashless)
    return [
        ("clean", arguments(good), 0, "PASS"),
        ("forbidden", arguments(examples / "trajectories/support_regress.json"),
         2, "POLICY_VIOLATION"),
        ("regression", arguments(regression), 2, "REGRESSION"),
        ("unknown-case", arguments(good, unknown_path), 2, "UNKNOWN_TRAJECTORY"),
        ("duplicate-case", arguments(good, good), 2, "DUPLICATE_TRAJECTORY"),
        ("rubric-drift", arguments(good, policy=drift_path), 2, "RUBRIC_DRIFT"),
        ("hashless-baseline", arguments(good, pin=hashless_path),
         2, "MISSING_RUBRIC_FINGERPRINT"),
        ("malformed-input", arguments(malformed), 2, None),
        ("missing-baseline", arguments(good, pin=work / "absent.json"), 2, None),
    ]


def run_case(case: tuple, work: Path, evidence: Path, *, journal: Path | None = None) -> dict:
    label, arguments, expected, verdict = case
    env = {"PATH": os.defpath, "HOME": str(work), "LANG": "C.UTF-8"}
    command = [sys.executable, "-I", "-m", "tracegate.cli", *(str(arg) for arg in arguments)]
    direct = subprocess.run(command, env=env, cwd=work, text=True,
                            capture_output=True, timeout=30, check=False)
    if direct.returncode != expected:
        raise AssertionError(f"{label}: unexpected direct trace-gate exit {direct.returncode}")
    if verdict is not None and json.loads(direct.stdout)["verdict"] != verdict:
        raise AssertionError(f"{label}: unexpected trace-gate verdict")
    journal = journal or work / f"{label}-journal.md"
    state = work / "LOOP_STATE.md"
    gate = "trace=" + shlex.join(command)
    result = subprocess.run(
        [sys.executable, "-I", "-m", "loopengine.cli", "tick", "--state", str(state),
         "--journal", str(journal), "--gate", gate, "--json"],
        env=env, cwd=work, text=True, capture_output=True, timeout=40, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"{label}: decision CLI unexpectedly failed {result.returncode}")
    decision = json.loads(result.stdout)
    action = "advance" if expected == 0 else "repair"
    target = EXPECTED_TARGET if expected == 0 else "trace"
    if decision["action"] != action or decision["target"] != target:
        raise AssertionError(f"{label}: gate outcome did not reach the expected decision")
    journal_text = journal.read_text()
    status = "PASS" if expected == 0 else "FAIL"
    if f"trace={status}" not in journal_text or f"**{action}** -> {target}" not in journal_text:
        raise AssertionError(f"{label}: journal omitted gate or decision evidence")
    (evidence / f"{label}-trace.log").write_text(direct.stdout + direct.stderr)
    (evidence / f"{label}-decision.json").write_text(result.stdout)
    (evidence / f"{label}-journal.md").write_text(journal_text)
    return {"name": label, "trace_exit": direct.returncode, "verdict": verdict,
            "decision_cli_exit": result.returncode, "action": action, "target": target}


def verify(evidence: Path) -> dict:
    if os.name != "posix":
        raise ValueError("this integration verifier requires a POSIX shell")
    provenance = identity()
    results = []
    # Spaces and apostrophes deliberately exercise safe shell quoting for gate arguments.
    with tempfile.TemporaryDirectory(prefix="trace gate's loop check ") as directory:
        work = Path(directory)
        state = work / "LOOP_STATE.md"
        original = (HERE / "LOOP_STATE.md").read_bytes()
        state.write_bytes(original)
        cases = build_cases(work)
        for case in cases:
            results.append(run_case(case, work, evidence))
        journal = work / "recovery-journal.md"
        results.append(run_case(("recovery-red", *cases[1][1:]), work, evidence, journal=journal))
        before = journal.read_bytes()
        results.append(run_case(("recovery-green", *cases[0][1:]), work, evidence, journal=journal))
        if (not journal.read_bytes().startswith(before)
                or journal.read_text().count("\n## ") != RECOVERY_TICKS):
            raise AssertionError("second tick did not append exactly one journal entry")
        if state.read_bytes() != original:
            raise AssertionError("decision engine changed the demonstration backlog")
    return {"cases": results, "count": len(results), "identity": provenance,
            "state_unchanged": True, "recovery_journal_appends": True,
            "network_calls": "none implemented", "model_calls": 0,
            "platform_scope": "POSIX"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    report = verify(args.evidence.resolve())
    (args.evidence / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Verified {report['count']} real trace-gate-to-loop-engine decisions; "
          "repair is a decision, not a nonzero loop-engine exit.")


if __name__ == "__main__":
    main()
