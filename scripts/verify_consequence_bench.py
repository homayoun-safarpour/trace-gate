"""Run the trusted bench regressions and emit machine-readable evidence."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "integrations/consequence-bench"
SHA256_HEX_LENGTH = hashlib.sha256().digest_size * 2
CHECKER_COMMIT = "d4178b8afe98387fecbb5bbbcd380bd7b174a268"
SOURCE_FILES = {
    "vendor/tracegate/__init__.py",
    "vendor/tracegate/baseline.py",
    "vendor/tracegate/cli.py",
    "vendor/tracegate/otel.py",
    "vendor/tracegate/score.py",
    "vendor/tracegate/trajectory.py",
}


def verify_source_lock():
    check = {"name": "pinned-python-source", "passed": False}
    try:
        manifest = json.loads((BENCH / "python/SOURCE-MANIFEST.json").read_text())
        if not isinstance(manifest, dict) or manifest.get("source_commit") != CHECKER_COMMIT:
            raise ValueError("unexpected source identity")
        files = manifest.get("files")
        if not isinstance(files, dict) or set(files) != SOURCE_FILES:
            raise ValueError("source file set must match all six expected files")
        for name, expected in files.items():
            if not isinstance(expected, str) or len(expected) != SHA256_HEX_LENGTH:
                raise ValueError("invalid source digest")
            path = BENCH / "python" / name
            if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ValueError("source mismatch")
        check["passed"] = True
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        check["error"] = type(exc).__name__
    return check


def main():
    out = ROOT / "reports/consequence-bench"
    out.mkdir(parents=True, exist_ok=True)
    checks = [verify_source_lock()]
    commands = [
        (
            "pr-input-boundaries",
            "../..",
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                "integrations/consequence-bench",
                "-p",
                "test_*ci.py",
                "-v",
            ],
        ),
        ("http-backend", "python", [sys.executable, "-m", "unittest", "-v", "test_live.py"]),
        ("receipt", "python", ["node", "test_receipt.cjs"]),
        ("mock-dom", "python", ["node", "test_ui.cjs"]),
        ("browser-engine", "browser", ["node", "test_engine.cjs"]),
        ("python-browser-parity", "browser", [sys.executable, "test_parity.py"]),
        ("browser-app-syntax", "browser", ["node", "--check", "dist/app.js"]),
    ]
    # Never execute vendored checker/tests after a failed integrity preflight.
    for name, folder, command in commands if checks[0]["passed"] else []:
        try:
            p = subprocess.run(
                command,
                cwd=BENCH / folder,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            (out / (name + ".log")).write_text(p.stdout + p.stderr)
            checks.append({"name": name, "passed": p.returncode == 0, "exit_code": p.returncode})
        except (OSError, subprocess.TimeoutExpired) as e:
            checks.append({"name": name, "passed": False, "error": type(e).__name__})
    report = {
        "schema_version": 1,
        "commit": os.getenv("GITHUB_SHA", "local-unpublished"),
        "event": os.getenv("GITHUB_EVENT_NAME", "local"),
        "checker_commit": CHECKER_COMMIT if checks[0]["passed"] else None,
        "expected_checker_commit": CHECKER_COMMIT,
        "checks": checks,
        "passed": all(c["passed"] for c in checks),
        "scope": (
            "Fixed synthetic fixture; Python/JS parity and receipt/UI regression. Not a "
            "skill scanner, browser E2E, general safety certificate, or runtime "
            "enforcement."
        ),
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    summary = "# Consequence bench verification\n\n" + "\n".join(
        "- " + c["name"] + ": " + ("PASS" if c["passed"] else "FAIL") for c in checks
    )
    summary += "\n\n" + report["scope"] + "\n"
    (out / "report.md").write_text(summary)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(summary)
    print(json.dumps(report))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
