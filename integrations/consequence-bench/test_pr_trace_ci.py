import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("checker", ROOT / "scripts/check_pr_trace.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class Inputs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / m.RELATIVE
        self.path.parent.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_regular(self):
        self.path.write_bytes(b"{}")
        self.assertEqual(m.read_trace(self.root), b"{}")

    def test_limit(self):
        self.path.write_bytes(b"x" * 100001)
        with self.assertRaises(ValueError):
            m.read_trace(self.root)

    def test_symlink(self):
        self.path.symlink_to("/etc/passwd")
        with self.assertRaises(ValueError):
            m.read_trace(self.root)

    def test_directory(self):
        self.path.mkdir()
        with self.assertRaises(ValueError):
            m.read_trace(self.root)

    def test_symlink_parent(self):
        self.path.parent.rmdir()
        self.path.parent.symlink_to("/tmp")
        with self.assertRaises(ValueError):
            m.read_trace(self.root)

    def test_missing(self):
        with self.assertRaises(FileNotFoundError):
            m.read_trace(self.root)


class CLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.trusted = self.root / "trusted"
        self.candidate = self.root / "candidate"
        self.out = self.root / "out"
        (self.trusted / "scripts").mkdir(parents=True)
        shutil.copy(ROOT / "scripts/check_pr_trace.py", self.trusted / "scripts/")
        shutil.copytree(ROOT / "src", self.trusted / "src")
        shutil.copytree(ROOT / "examples", self.trusted / "examples")
        shutil.copytree(ROOT / "examples", self.candidate / "examples")

    def tearDown(self):
        self.temp.cleanup()

    def run_check(self):
        p = subprocess.run(
            [
                sys.executable,
                "-I",
                str(self.trusted / "scripts/check_pr_trace.py"),
                "--candidate",
                str(self.candidate),
                "--output",
                str(self.out),
            ],
            cwd=self.candidate,
            check=False,
        )
        return p.returncode, json.loads((self.out / "report.json").read_text())

    def test_good_and_no_candidate_import(self):
        # The checker imports trace_gate; the old name stays planted as well.
        for package in ("trace_gate", "tracegate"):
            (self.candidate / package).mkdir()
            (self.candidate / package / "__init__.py").write_text(
                'raise RuntimeError("DO NOT EXECUTE")'
            )
        (self.candidate / "sitecustomize.py").write_text('raise RuntimeError("DO NOT EXECUTE")')
        code, result = self.run_check()
        self.assertEqual(code, 0)
        self.assertEqual(result["verdict"], "PASS")

    def test_policy_refusal_despite_candidate_policy_tampering(self):
        path = self.candidate / m.RELATIVE
        data = json.loads(path.read_text())
        data["steps"].append(
            {"role": "assistant", "tool": "delete_order", "content": "not executed"}
        )
        path.write_text(json.dumps(data))
        (self.candidate / "examples/rubric.json").write_text("{}")
        code, result = self.run_check()
        self.assertEqual(code, 1)
        self.assertFalse(result["passed"])
        self.assertEqual(result["verdict"], "POLICY_VIOLATION")

    def test_invalid_json(self):
        (self.candidate / m.RELATIVE).write_text("{")
        code, result = self.run_check()
        self.assertEqual(code, 1)
        self.assertFalse(result["passed"])

    def test_missing_input_reports_failure(self):
        (self.candidate / m.RELATIVE).unlink()
        code, result = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual(result["verdict"], "INVALID_OR_UNCHECKED")


if __name__ == "__main__":
    unittest.main()
