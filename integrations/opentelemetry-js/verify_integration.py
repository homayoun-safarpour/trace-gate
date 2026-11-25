"""Exercise real SDK-generated synthetic OTLP JSON against the installed wheel.

Requires an existing, pinned Node runtime. Never installs packages or contacts a
collector. Completeness declarations are created only for this generator's fixtures.
"""
from __future__ import annotations

import argparse
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
from tracegate.otel import load_export

HERE = Path(__file__).resolve().parent
EXPECTED_ISSUES = {
    "events": "unsupported_span_events_or_links",
    "dropped-attributes": "dropped_telemetry",
    "missing-call-id": "unknown_call_id",
}


def declaration(source: Path, target: Path, *, case_name="synthetic-sdk-case") -> None:
    # Only invoked for known, freshly generated synthetic fixture paths.
    target.write_text(json.dumps({
        "profile": "openinference-otlp-v1",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "trace_id": "1" * 32, "case_name": case_name,
        "span_coverage": "complete", "tool_call_coverage": "complete",
    }))


def validate_fixtures(fixtures: Path) -> dict:
    provenance = json.loads((fixtures / "provenance.json").read_text())
    recorded = json.loads((HERE / "fixtures/provenance.json").read_text())
    if provenance["fixtures"] != recorded["fixtures"]:
        raise AssertionError("SDK output differs from recorded fixtures; review before accepting")
    for name, expected in provenance["fixtures"].items():
        if hashlib.sha256((fixtures / name).read_bytes()).hexdigest() != expected:
            raise AssertionError("Generated fixture hash mismatch")
    return provenance


def verify_suite(fixtures: Path, work: Path, cli) -> None:
    """Check several freshly generated exports as one exact-case baseline suite."""
    rubric = work / "rubric.json"
    baseline = work / "suite-baseline.json"
    for name, case in (("good", "sdk-first"), ("repeated-name", "sdk-second"),
                       ("forbidden-generated", "sdk-second"), ("events", "sdk-second")):
        declaration(fixtures / f"{name}.json", work / f"suite-{name}.json", case_name=case)

    def args(names=("good", "repeated-name")):
        result = [fixtures / f"{name}.json" for name in names]
        result += ["--input-format", "openinference-otlp", "--rubric", rubric]
        for name in names:
            result += ["--coverage", work / f"suite-{name}.json"]
        return result

    result = cli("suite-score", "score", *args(), "--json")
    assert [r["trajectory_name"] for r in json.loads(result.stdout)] == ["sdk-first", "sdk-second"]
    cli("suite-freeze", "freeze", *args(), "--out", baseline)
    before = baseline.read_bytes()
    for label, names, expected, verdict in (
        ("pass", ("good", "repeated-name"), 0, "PASS"),
        ("reversed", ("repeated-name", "good"), 0, "PASS"),
        ("missing", ("good",), 2, "MISSING_TRAJECTORY"),
        ("duplicate", ("good", "good"), 2, "DUPLICATE_TRAJECTORY"),
        ("forbidden", ("good", "forbidden-generated"), 2, "POLICY_VIOLATION"),
    ):
        result = cli(f"suite-{label}", "check", *args(names), "--baseline", baseline,
                     "--json", expected=expected)
        assert json.loads(result.stdout)["verdict"] == verdict
    result = cli("suite-invalid-second", "score", *args(("good", "events")),
                 "--json", expected=2)
    assert result.stdout == ""
    for name in ("forbidden-generated", "events"):
        cli(f"suite-freeze-{name}", "freeze", *args(("good", name)),
            "--out", baseline, expected=2)
        assert baseline.read_bytes() == before
    coverage = work / "suite-repeated-name.json"
    saved = coverage.read_bytes()
    cli("suite-protect-second-coverage", "freeze", *args(), "--out", coverage, expected=2)
    assert coverage.read_bytes() == saved
    wrong = args()
    wrong[-1], wrong[-3] = wrong[-3], wrong[-1]
    result = cli("suite-swapped-coverage", "score", *wrong, "--json", expected=2)
    assert result.stdout == ""
    result = cli("suite-missing-coverage", "score", *args()[:-2], "--json", expected=2)
    assert result.stdout == ""
    declaration(fixtures / "repeated-name.json", coverage, case_name="sdk-unknown")
    result = cli("suite-unknown-case", "check", *args(), "--baseline", baseline,
                 "--json", expected=2)
    assert json.loads(result.stdout)["verdict"] == "UNKNOWN_TRAJECTORY"
    assert baseline.read_bytes() == before


def verify(fixtures: Path, evidence: Path) -> dict:
    provenance = validate_fixtures(fixtures)
    checks = []
    with tempfile.TemporaryDirectory(prefix="trace-gate-sdk-check-") as directory:
        work = Path(directory)
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(work), "LANG": "C.UTF-8"}

        def cli(label, *args, expected=0):
            command = [sys.executable, "-I", "-m", "tracegate.cli", *(str(a) for a in args)]
            result = subprocess.run(command, env=env, cwd=work, text=True,
                                    capture_output=True, timeout=30, check=False)
            if result.returncode != expected:
                raise AssertionError(f"{label}: exit {result.returncode}, expected {expected}")
            if "SYNTHETIC_PAYLOAD" in result.stdout + result.stderr:
                raise AssertionError(f"{label}: payload leaked into CLI output")
            (evidence / f"{label}.log").write_text(result.stdout + result.stderr)
            checks.append({"name": label, "exit": result.returncode, "expected_exit": expected})
            return result

        rubric = work / "rubric.json"
        rubric.write_text(json.dumps({"required_tools": ["search"],
                                      "forbidden_tools": ["delete_database"]}))
        baseline = work / "baseline.json"
        for name in provenance["fixtures"]:
            declaration(fixtures / name, work / (Path(name).stem + "-coverage.json"))

        def args(name):
            return [fixtures / f"{name}.json", "--input-format", "openinference-otlp",
                    "--coverage", work / f"{name}-coverage.json", "--rubric", rubric]

        unknown = cli("unknown-coverage", "inspect-otel", fixtures / "good.json", expected=2)
        assert json.loads(unknown.stdout)["coverage"] == "unknown"
        for name in ("good", "forbidden-generated", "repeated-name"):
            result = cli(f"inspect-{name}", "inspect-otel", fixtures / f"{name}.json",
                         "--coverage", work / f"{name}-coverage.json")
            assert json.loads(result.stdout)["gate_eligible"]
        good = load_export(fixtures / "good.json", work / "good-coverage.json")
        assert good.to_trajectory().tools == ("search",)
        assert any(span.status == "error" for span in good.spans)
        repeated = load_export(
            fixtures / "repeated-name.json", work / "repeated-name-coverage.json"
        )
        assert repeated.to_trajectory().tools == ("search", "search")
        assert [c.id for c in repeated.to_trajectory().tool_calls] == ["call-one", "call-two"]
        cli("freeze-good", "freeze", *args("good"), "--out", baseline)
        before = baseline.read_bytes()
        passed = cli("check-good", "check", *args("good"), "--baseline", baseline, "--json")
        assert json.loads(passed.stdout)["verdict"] == "PASS"
        failed = cli("check-forbidden", "check", *args("forbidden-generated"),
                     "--baseline", baseline, "--json", expected=2)
        assert json.loads(failed.stdout)["verdict"] == "POLICY_VIOLATION"
        cli("freeze-forbidden", "freeze", *args("forbidden-generated"),
            "--out", baseline, expected=2)
        assert baseline.read_bytes() == before
        for name, issue in EXPECTED_ISSUES.items():
            result = cli(f"inspect-{name}", "inspect-otel", fixtures / f"{name}.json",
                         "--coverage", work / f"{name}-coverage.json", expected=2)
            assert issue in json.loads(result.stdout)["issues"]
            result = cli(f"score-{name}", "score", *args(name), expected=2)
            assert result.stdout == ""
            cli(f"freeze-{name}", "freeze", *args(name), "--out", baseline, expected=2)
            assert baseline.read_bytes() == before
        changed = work / "changed.json"
        changed.write_bytes((fixtures / "good.json").read_bytes() + b"\n")
        result = cli("hash-mismatch", "inspect-otel", changed,
                     "--coverage", work / "good-coverage.json", expected=2)
        assert result.stdout == ""
        verify_suite(fixtures, work, cli)
    return {"checks": checks, "count": len(checks), "python": platform.python_version(),
            "tracegate_version": tracegate.__version__, "provenance": provenance,
            "otel_module_sha256": hashlib.sha256(
                (Path(tracegate.__file__).parent / "otel.py").read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True,
                        help="existing package.json/package-lock.json/node_modules directory")
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    node = shutil.which("node")
    if node is None:
        parser.error("Node is required; this verifier does not install it")
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="trace-gate-sdk-generate-") as directory:
        work = Path(directory)
        fixtures = work / "fixtures"
        result = subprocess.run(
            [node, str(HERE / "generate.cjs"), str(args.runtime_root.resolve()), str(fixtures)],
            env={"PATH": os.environ.get("PATH", ""), "HOME": str(work), "LANG": "C.UTF-8"},
            cwd=work, text=True, capture_output=True, timeout=60, check=True,
        )
        (evidence / "generator.log").write_text(result.stdout + result.stderr)
        shutil.copytree(fixtures, evidence / "generated", dirs_exist_ok=True)
        report = verify(fixtures, evidence)
    (evidence / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Verified {report['count']} installed CLI checks "
          "against six real SDK-generated fixtures.")


if __name__ == "__main__":
    main()
