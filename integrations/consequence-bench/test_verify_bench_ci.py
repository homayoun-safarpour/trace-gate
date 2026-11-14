"""Failure evidence and trusted result contracts, without executing test doubles."""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bench = load("verify_consequence_bench")
checker = load("check_pr_trace")


class FailureEvidence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bench = self.root / "integrations/consequence-bench"
        shutil.copytree(bench.BENCH / "python", self.bench / "python")
        self.manifest = self.bench / "python/SOURCE-MANIFEST.json"

    def tearDown(self):
        self.temp.cleanup()

    def assert_recorded_failure(self):
        with (
            patch.object(bench, "ROOT", self.root),
            patch.object(bench, "BENCH", self.bench),
            patch.object(bench.subprocess, "run") as execute,
            patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(self.root / "summary.md")}),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(bench.main(), 1)
            execute.assert_not_called()
        report = json.loads((self.root / "reports/consequence-bench/report.json").read_text())
        self.assertFalse(report["passed"])
        self.assertEqual(len(report["checks"]), 1)
        self.assertFalse(report["checks"][0]["passed"])
        self.assertIsNone(report["checker_commit"])
        self.assertTrue((self.root / "summary.md").is_file())

    def test_valid_manifest(self):
        with patch.object(bench, "BENCH", self.bench):
            self.assertTrue(bench.verify_source_lock()["passed"])

    def test_missing_manifest(self):
        self.manifest.unlink()
        self.assert_recorded_failure()

    def test_malformed_manifest(self):
        self.manifest.write_text("{")
        self.assert_recorded_failure()

    def test_nonobject_manifest(self):
        self.manifest.write_text("[]")
        self.assert_recorded_failure()

    def test_empty_file_set(self):
        self.manifest.write_text(json.dumps({"source_commit": bench.CHECKER_COMMIT, "files": {}}))
        self.assert_recorded_failure()

    def test_missing_source_file(self):
        (self.bench / "python/vendor/tracegate/cli.py").unlink()
        self.assert_recorded_failure()

    def test_changed_source_file(self):
        (self.bench / "python/vendor/tracegate/cli.py").write_text('raise RuntimeError("not run")')
        self.assert_recorded_failure()

    def test_unexpected_source_identity(self):
        manifest = json.loads(self.manifest.read_text())
        manifest["source_commit"] = "unreviewed"
        self.manifest.write_text(json.dumps(manifest))
        self.assert_recorded_failure()

    def test_unexpected_file_path(self):
        manifest = json.loads(self.manifest.read_text())
        manifest["files"]["../../unrelated"] = "0" * 64
        self.manifest.write_text(json.dumps(manifest))
        self.assert_recorded_failure()


class ResultContract(unittest.TestCase):
    def test_pass(self):
        self.assertEqual(
            checker.validated_result({"verdict": "PASS", "ok": True}, 0), ("PASS", True)
        )

    def test_refusal(self):
        self.assertEqual(
            checker.validated_result({"verdict": "REGRESSION", "ok": False}, 2),
            ("REGRESSION", False),
        )

    def test_malformed_results(self):
        for value in [None, [], "PASS", {}, {"verdict": "unknown", "ok": True}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                checker.validated_result(value, 0)

    def test_inconsistent_results(self):
        for result, code in [
            ({"verdict": "PASS", "ok": False}, 0),
            ({"verdict": "PASS", "ok": True}, 2),
            ({"verdict": "REGRESSION", "ok": True}, 0),
        ]:
            with self.subTest(result=result, code=code), self.assertRaises(ValueError):
                checker.validated_result(result, code)


class WorkflowGuard(unittest.TestCase):
    def test_exact_main_ref_before_checkout(self):
        workflow = (ROOT / ".github/workflows/consequence-bench.yml").read_text()
        marker = "      - name: Require exact trusted main ref\n        run: |\n"
        self.assertLess(workflow.index(marker), workflow.index("      - uses:"))
        body = workflow.split(marker, 1)[1].split("      - uses:", 1)[0]
        script = "\n".join(line[10:] for line in body.splitlines())
        for ref, expected in [
            ("refs/heads/main", 0),
            ("refs/heads/Main", 1),
            ("refs/heads/release/0.2.0", 1),
        ]:
            with self.subTest(ref=ref), tempfile.TemporaryDirectory() as temp:
                env = os.environ.copy()
                env.update(GITHUB_REF=ref, GITHUB_STEP_SUMMARY=str(Path(temp) / "summary.md"))
                result = subprocess.run(
                    ["bash", "-e", "-c", script], cwd=temp, env=env, check=False
                )
                self.assertEqual(result.returncode, expected)
                if expected:
                    report = json.loads(
                        (Path(temp) / "reports/consequence-bench/report.json").read_text()
                    )
                    self.assertEqual(report["verdict"], "REF_NOT_TRUSTED")
                    self.assertFalse(report["passed"])

    def test_no_pending_run_replacement(self):
        for name in ["consequence-bench.yml", "pr-recorded-trace.yml"]:
            self.assertNotIn("concurrency:", (ROOT / ".github/workflows" / name).read_text())


if __name__ == "__main__":
    unittest.main()
