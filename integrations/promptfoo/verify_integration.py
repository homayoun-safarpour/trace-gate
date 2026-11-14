"""Exercise the real pinned Promptfoo CLI, not a mock of its Python interface.

Run with the Python environment containing the reviewed trace-gate wheel. Pass
--cli /path/to/node_modules/promptfoo/dist/src/entrypoint.js. No auto-installation.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import tracegate

HERE = Path(__file__).resolve().parent
VERSION = "0.125.1"


def run_eval(cli, config, expected, destination, label):
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is required")
    with tempfile.TemporaryDirectory(prefix="trace-gate-promptfoo-") as directory:
        root = Path(directory)
        # No user API keys, user config, or inherited pass-rate override.
        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(root),
            "LANG": "C.UTF-8",
            "PROMPTFOO_CONFIG_DIR": str(root / "config"),
            "PROMPTFOO_DISABLE_TELEMETRY": "true",
            "PROMPTFOO_DISABLE_UPDATE": "true",
            "PROMPTFOO_DISABLE_REMOTE_GENERATION": "true",
            "PROMPTFOO_PYTHON": sys.executable,
            "PROMPTFOO_PASS_RATE_THRESHOLD": "100",
            "PROMPTFOO_FAILED_TEST_EXIT_CODE": "2",
        }
        output = destination / f"{label}-results.json"
        command = [
            node,
            str(cli),
            "eval",
            "--config",
            str(config),
            "--output",
            str(output),
            "--no-write",
            "--no-cache",
            "--no-share",
            "--no-table",
            "--no-progress-bar",
            "--max-concurrency",
            "1",
        ]
        process = subprocess.run(
            command, cwd=root, env=env, text=True, capture_output=True, timeout=180, check=False
        )
        (destination / f"{label}-cli.log").write_text(process.stdout + process.stderr)
    expected_exit = 0 if all(expected.values()) else 2
    if process.returncode != expected_exit:
        raise AssertionError(f"{label}: exit {process.returncode}, expected {expected_exit}")
    data = json.loads(output.read_text())
    rows = data["results"]["results"]
    actual = {row["testCase"]["description"]: row["success"] for row in rows}
    if len(rows) != len(expected) or actual != expected:
        raise AssertionError(f"{label}: actual {actual!r}, expected {expected!r}")
    if data["results"]["stats"]["errors"] != 0:
        raise AssertionError(f"{label}: unexpected runtime errors")
    for row in rows:
        if row["provider"]["id"] != "echo" or row["cost"] != 0:
            raise AssertionError("only free local echo evaluations are supported here")
        if row["response"]["tokenUsage"]["total"] != 0:
            raise AssertionError("expected zero model tokens")
    return {
        "exit": process.returncode,
        "stats": data["results"]["stats"],
        "cases": [
            {
                "name": row["testCase"]["description"],
                "pass": row["success"],
                "score": row["score"],
                "reason": row["gradingResult"]["componentResults"][0]["reason"],
            }
            for row in rows
        ],
    }


def test_misconfiguration(cli, destination):
    """Prove documented outer-framework overrides, not ship them as gate configs."""
    original = json.loads((HERE / "fail-config.json").read_text())
    results = {}
    with tempfile.TemporaryDirectory(prefix="trace-gate-config-") as directory:
        for label in ["weight-zero", "threshold-zero"]:
            config = copy.deepcopy(original)
            assertion = config["tests"][0]["assert"][0]
            assertion["value"] = "file://" + str(HERE / "trace_gate_assert.py")
            if label == "weight-zero":
                assertion["weight"] = 0
            else:
                config["tests"][0]["threshold"] = 0
            path = Path(directory) / f"{label}.json"
            path.write_text(json.dumps(config))
            results[label] = run_eval(
                cli, path, {"forbidden-second-call": True}, destination, label
            )
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, default=HERE / "evidence")
    args = parser.parse_args()
    cli = args.cli.resolve()
    package = cli.parents[2]
    metadata = json.loads((package / "package.json").read_text())
    if metadata["name"] != "promptfoo" or metadata["version"] != VERSION:
        raise RuntimeError(f"expected official promptfoo {VERSION}")
    destination = args.evidence.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    scenarios = json.loads((HERE / "scenarios.json").read_text())
    results = {
        "promptfoo_version": VERSION,
        "tracegate_modules_sha256": {
            name: hashlib.sha256((Path(tracegate.__file__).parent / name).read_bytes()).hexdigest()
            for name in ("score.py", "baseline.py", "trajectory.py")
        },
        "adapter_sha256": hashlib.sha256((HERE / "trace_gate_assert.py").read_bytes()).hexdigest(),
        "runtime_lock_sha256": hashlib.sha256(
            (HERE / "runtime-lock/package-lock.json").read_bytes()
        ).hexdigest(),
        "python": platform.python_version(),
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        "platform": platform.platform(),
        "wrapper_sha256": hashlib.sha256(
            (cli.parent / "python/wrapper.py").read_bytes()
        ).hexdigest(),
        "gate": run_eval(
            cli,
            HERE / "promptfooconfig.json",
            {s["name"]: s["gate_pass"] for s in scenarios},
            destination,
            "gate",
        ),
        "native_policy": run_eval(
            cli,
            HERE / "native-policy-config.json",
            {s["name"]: s["native_pass"] for s in scenarios},
            destination,
            "native-policy",
        ),
        "pass_smoke": run_eval(cli, HERE / "pass-config.json", {"good": True}, destination, "pass"),
        "fail_smoke": run_eval(
            cli, HERE / "fail-config.json", {"forbidden-second-call": False}, destination, "fail"
        ),
        "documented_override_hazards": test_misconfiguration(cli, destination),
    }
    (destination / "comparison.json").write_text(json.dumps(results, indent=2) + "\n")
    print(
        "Verified: 20 comparison rows, pass/fail CLI exits, and 2 override hazards; 0 model tokens."
    )


if __name__ == "__main__":
    main()
