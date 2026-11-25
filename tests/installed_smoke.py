"""Synthetic console-script contracts, run with stdlib unittest in a clean venv.

This filename deliberately does not match pytest's test_*.py discovery pattern.
Run via scripts/verify_distribution.py after building the distribution.
"""

from __future__ import annotations

import json
import os
import subprocess
import sysconfig
import tempfile
import unittest
from pathlib import Path


class InstalledCLI(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="trace-gate-cli-")
        self.addCleanup(self.work.cleanup)
        self.cwd = Path(self.work.name)
        name = "trace-gate.exe" if os.name == "nt" else "trace-gate"
        self.cli = Path(sysconfig.get_path("scripts")) / name
        self.env = {
            key: value for key, value in os.environ.items()
            if key not in {"PYTHONPATH", "PYTHONHOME"}
        }
        self.env["PYTHONNOUSERSITE"] = "1"
        self.rubric = self.write("rubric.json", {
            "required_tools": ["read_report"],
            "forbidden_tools": ["send_email"],
            "min_steps": 1,
            "max_steps": 1,
        })
        self.good_data = {"name": "synthetic-run", "messages": [{
            "role": "assistant", "name": "researcher", "tool_calls": [
                {"id": "call-1", "function": {"name": "read_report"}},
                {"id": "call-2", "function": {"name": "read_report"}},
            ],
        }]}
        self.good = self.write("good.json", self.good_data)
        self.bad = self.write("regression.json", {
            "name": "synthetic-run", "messages": [{"tool_calls": [
                {"id": "call-1", "function": {"name": "read_report"}},
                {"id": "call-2", "function": {"name": "send_email"}},
            ]}],
        })
        self.invalid = self.write("invalid.json", {"messages": [None]})
        self.baseline = self.cwd / "baseline.json"

    def write(self, name, data):
        path = self.cwd / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def run_cli(self, *args, expected=0):
        result = subprocess.run(
            [str(self.cli), *(str(arg) for arg in args)],
            cwd=self.cwd, env=self.env, text=True, capture_output=True, timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def freeze(self):
        self.run_cli("freeze", self.good, "--rubric", self.rubric, "--out", self.baseline)

    def check(self, trace, *, expected=0, rubric=None, baseline=None):
        return self.run_cli(
            "check", trace, "--rubric", rubric or self.rubric,
            "--baseline", baseline or self.baseline, "--json", expected=expected,
        )

    def test_help_entry_point(self):
        self.assertIn("freeze", self.run_cli("--help").stdout)

    def test_json_score(self):
        result = self.run_cli("score", self.good, "--rubric", self.rubric, "--json")
        report = json.loads(result.stdout)[0]
        self.assertEqual(report["composite"], 1.0)
        self.assertEqual(report["metrics"]["step_band"], 1.0)

    def test_freeze_and_pass(self):
        self.freeze()
        self.assertEqual(json.loads(self.check(self.good).stdout)["verdict"], "PASS")

    def test_second_forbidden_call_is_policy_violation(self):
        self.freeze()
        result = self.check(self.bad, expected=2)
        self.assertEqual(json.loads(result.stdout)["verdict"], "POLICY_VIOLATION")

    def test_rubric_drift_fails_closed(self):
        self.freeze()
        soft = self.write("soft.json", {})
        result = self.check(self.good, rubric=soft, expected=2)
        self.assertEqual(json.loads(result.stdout)["verdict"], "RUBRIC_DRIFT")

    def test_unknown_trajectory_fails_closed(self):
        self.freeze()
        self.good_data["name"] = "renamed-run"
        unknown = self.write("unknown.json", self.good_data)
        result = self.check(unknown, expected=2)
        self.assertEqual(json.loads(result.stdout)["verdict"], "UNKNOWN_TRAJECTORY")

    def test_empty_baseline_fails_closed(self):
        self.freeze()
        data = json.loads(self.baseline.read_text(encoding="utf-8"))
        data["scores"] = {}
        empty = self.write("empty-baseline.json", data)
        result = self.check(self.good, baseline=empty, expected=2)
        self.assertEqual(json.loads(result.stdout)["verdict"], "MISSING_BASELINE")

    def test_invalid_score_has_no_partial_report(self):
        result = self.run_cli("score", self.invalid, "--rubric", self.rubric, expected=2)
        self.assertEqual(result.stdout, "")
        self.assertIn("INVALID_TRAJECTORY", result.stderr)

    def test_invalid_check_fails_closed(self):
        self.freeze()
        result = self.check(self.invalid, expected=2)
        self.assertEqual(result.stdout, "")
        self.assertIn("INVALID_TRAJECTORY", result.stderr)

    def test_invalid_freeze_preserves_existing_pin(self):
        self.freeze()
        before = self.baseline.read_bytes()
        result = self.run_cli(
            "freeze", self.invalid, "--rubric", self.rubric,
            "--out", self.baseline, expected=2,
        )
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.baseline.read_bytes(), before)

    def test_invalid_freeze_does_not_create_pin(self):
        self.run_cli(
            "freeze", self.invalid, "--rubric", self.rubric,
            "--out", self.baseline, expected=2,
        )
        self.assertFalse(self.baseline.exists())

    def test_duplicate_call_id_rejected(self):
        calls = self.good_data["messages"][0]["tool_calls"]
        calls[1]["id"] = calls[0]["id"]
        duplicate = self.write("duplicate.json", self.good_data)
        result = self.run_cli("score", duplicate, "--rubric", self.rubric, expected=2)
        self.assertIn("INVALID_TRAJECTORY", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_forbidden_tool_cannot_hide_behind_tolerance(self):
        self.run_cli("freeze", self.good, "--rubric", self.rubric,
                     "--out", self.baseline, "--tolerance", "1.0")
        result = self.check(self.bad, expected=2)
        self.assertEqual(json.loads(result.stdout)["verdict"], "POLICY_VIOLATION")

    def test_mixed_known_unknown_fails_closed(self):
        self.freeze()
        self.good_data["name"] = "unknown"
        unknown = self.write("unknown.json", self.good_data)
        result = self.run_cli("check", self.good, unknown, "--rubric", self.rubric,
                              "--baseline", self.baseline, "--json", expected=2)
        self.assertEqual(json.loads(result.stdout)["verdict"], "UNKNOWN_TRAJECTORY")

    def test_legacy_hashless_baseline_requires_migration(self):
        self.freeze()
        data = json.loads(self.baseline.read_text(encoding="utf-8"))
        del data["rubric_sha256"]
        self.write("baseline.json", data)
        result = self.check(self.good, expected=2)
        self.assertEqual(json.loads(result.stdout)["verdict"], "MISSING_RUBRIC_FINGERPRINT")
        self.freeze()
        self.assertEqual(json.loads(self.check(self.good).stdout)["verdict"], "PASS")

    def test_policy_refusal_preserves_pin(self):
        self.freeze()
        before = self.baseline.read_bytes()
        result = self.run_cli("freeze", self.bad, "--rubric", self.rubric,
                             "--out", self.baseline, expected=2)
        self.assertIn("POLICY_VIOLATION", result.stderr)
        self.assertEqual(self.baseline.read_bytes(), before)

    def test_successful_refreeze_replaces_complete_pin(self):
        self.freeze()
        self.run_cli("freeze", self.good, "--rubric", self.rubric,
                     "--out", self.baseline, "--tolerance", "0.05")
        self.assertEqual(json.loads(self.baseline.read_text())["tolerance"], 0.05)
        self.assertEqual(json.loads(self.check(self.good).stdout)["verdict"], "PASS")
        self.assertFalse(list(self.cwd.glob(".trace-gate-*.tmp")))

    def test_freeze_refuses_unrelated_symlink_output(self):
        other = self.cwd / "unrelated.json"
        other.write_bytes(b"unrelated original\n")
        try:
            self.baseline.symlink_to(other)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        result = self.run_cli("freeze", self.good, "--rubric", self.rubric,
                             "--out", self.baseline, expected=2)
        self.assertEqual(result.stdout, "")
        self.assertIn("FREEZE_REFUSED", result.stderr)
        self.assertTrue(self.baseline.is_symlink())
        self.assertEqual(other.read_bytes(), b"unrelated original\n")

    def test_freeze_does_not_mutate_unrelated_hardlink(self):
        other = self.cwd / "unrelated.json"
        other.write_bytes(b"unrelated original\n")
        try:
            self.baseline.hardlink_to(other)
        except (OSError, NotImplementedError):
            self.skipTest("hardlinks unavailable")
        self.freeze()
        self.assertEqual(other.read_bytes(), b"unrelated original\n")
        self.assertFalse(self.baseline.samefile(other))
        self.assertEqual(json.loads(self.check(self.good).stdout)["verdict"], "PASS")

    def test_freeze_refuses_directory_output(self):
        self.baseline.mkdir()
        result = self.run_cli("freeze", self.good, "--rubric", self.rubric,
                             "--out", self.baseline, expected=2)
        self.assertEqual(result.stdout, "")
        self.assertIn("FREEZE_REFUSED", result.stderr)
        self.assertTrue(self.baseline.is_dir())
        self.assertFalse(list(self.baseline.iterdir()))
        self.assertFalse(list(self.cwd.glob(".trace-gate-*.tmp")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
