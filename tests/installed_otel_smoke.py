"""Real console-script OTLP checks using only stdlib and synthetic fixtures."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sysconfig
import tempfile
import unittest
from pathlib import Path


class InstalledOTLP(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="trace-gate-otel-cli-")
        self.addCleanup(self.temporary.cleanup)
        self.cwd = Path(self.temporary.name)
        executable = "trace-gate.exe" if os.name == "nt" else "trace-gate"
        self.cli = Path(sysconfig.get_path("scripts")) / executable
        self.fixtures = Path(__file__).resolve().parents[1] / "examples" / "otel"
        self.env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
        self.env["PYTHONNOUSERSITE"] = "1"
        self.baseline = self.cwd / "baseline.json"

    def run_cli(self, *args, expected=0):
        result = subprocess.run([str(self.cli), *(str(v) for v in args)], cwd=self.cwd,
                                env=self.env, capture_output=True, text=True, timeout=30,
                                check=False)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertNotIn("SYNTHETIC_SECRET", result.stdout + result.stderr)
        return result

    def flags(self, case="support"):
        return [self.fixtures / f"{case}.json", "--input-format", "openinference-otlp",
                "--coverage", self.fixtures / f"{case}-coverage.json",
                "--rubric", self.fixtures / "rubric.json"]

    def freeze(self):
        self.run_cli("freeze", *self.flags(), "--out", self.baseline)

    def test_unknown_coverage_returns_two_with_sanitized_states(self):
        result = self.run_cli("inspect-otel", self.fixtures / "support.json", expected=2)
        data = json.loads(result.stdout)
        self.assertEqual(data["coverage"], "unknown")
        self.assertFalse(data["gate_eligible"])

    def test_inspection_with_declaration_preserves_provenance(self):
        result = self.run_cli("inspect-otel", self.fixtures / "support.json",
                              "--coverage", self.fixtures / "support-coverage.json")
        data = json.loads(result.stdout)
        self.assertEqual(len(data["source_sha256"]), 64)
        self.assertEqual(len(data["coverage_sha256"]), 64)
        self.assertEqual(data["spans"][0]["calls"][0]["call_id"], "call-one")

    def test_freeze_and_check_pass(self):
        self.freeze()
        result = self.run_cli("check", *self.flags(), "--baseline", self.baseline, "--json")
        self.assertEqual(json.loads(result.stdout)["verdict"], "PASS")

    def test_generated_forbidden_call_blocks(self):
        self.freeze()
        result = self.run_cli("check", *self.flags("forbidden"), "--baseline", self.baseline,
                              "--json", expected=2)
        self.assertEqual(json.loads(result.stdout)["verdict"], "POLICY_VIOLATION")

    def test_missing_declaration_does_not_replace_pin(self):
        self.freeze()
        before = self.baseline.read_bytes()
        self.run_cli("freeze", self.fixtures / "support.json", "--input-format",
                     "openinference-otlp", "--rubric", self.fixtures / "rubric.json",
                     "--out", self.baseline, expected=2)
        self.assertEqual(self.baseline.read_bytes(), before)

    def test_freeze_cannot_replace_source_or_coverage(self):
        source = self.cwd / "source.json"
        coverage = self.cwd / "coverage.json"
        source.write_bytes((self.fixtures / "support.json").read_bytes())
        coverage.write_bytes((self.fixtures / "support-coverage.json").read_bytes())
        for target in (source, coverage):
            before = target.read_bytes()
            self.run_cli("freeze", source, "--input-format", "openinference-otlp",
                         "--coverage", coverage, "--rubric", self.fixtures / "rubric.json",
                         "--out", target, expected=2)
            self.assertEqual(target.read_bytes(), before)

    def test_mixed_legacy_call_is_ineligible_even_with_bound_coverage(self):
        source = self.cwd / "mixed.json"
        data = json.loads((self.fixtures / "support.json").read_text())
        span = data["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        span["attributes"].append({"key": "llm.function_call.name",
                                   "value": {"stringValue": "SYNTHETIC_SECRET_FORBIDDEN"}})
        source.write_text(json.dumps(data))
        coverage = self.cwd / "coverage.json"
        declaration = json.loads((self.fixtures / "support-coverage.json").read_text())
        declaration["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        coverage.write_text(json.dumps(declaration))
        result = self.run_cli("inspect-otel", source, "--coverage", coverage, expected=2)
        self.assertFalse(json.loads(result.stdout)["gate_eligible"])
        result = self.run_cli("score", source, "--input-format", "openinference-otlp",
                              "--coverage", coverage, "--rubric", self.fixtures / "rubric.json",
                              expected=2)
        self.assertEqual(result.stdout, "")

    def test_malformed_export_does_not_emit_scores(self):
        source = self.cwd / "malformed.json"
        source.write_text('{"resourceSpans": [], "resourceSpans": []}', encoding="utf-8")
        result = self.run_cli("inspect-otel", source, expected=2)
        self.assertEqual(result.stdout, "")
        self.assertIn("INVALID_OTLP", result.stderr)

    def suite_flags(self, second="support"):
        source = self.cwd / "second.json"
        data = json.loads((self.fixtures / f"{second}.json").read_text())
        for resource in data["resourceSpans"]:
            for scope in resource["scopeSpans"]:
                for span in scope["spans"]:
                    span["traceId"] = "2" * 32
        source.write_text(json.dumps(data))
        coverage = self.cwd / "second-coverage.json"
        declaration = json.loads((self.fixtures / f"{second}-coverage.json").read_text())
        declaration.update(trace_id="2" * 32, case_name="synthetic-second",
                           source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        coverage.write_text(json.dumps(declaration))
        return [self.fixtures / "support.json", source,
                "--input-format", "openinference-otlp", "--rubric", self.fixtures / "rubric.json",
                "--coverage", self.fixtures / "support-coverage.json", "--coverage", coverage]

    def test_multiple_exports_share_one_reviewed_suite_baseline(self):
        flags = self.suite_flags()
        self.run_cli("freeze", *flags, "--out", self.baseline)
        result = self.run_cli("check", *flags, "--baseline", self.baseline, "--json")
        self.assertEqual(json.loads(result.stdout)["verdict"], "PASS")
        self.assertEqual(len(json.loads(self.baseline.read_text())["scores"]), 2)
        result = self.run_cli("check", *self.flags(), "--baseline", self.baseline,
                              "--json", expected=2)
        self.assertEqual(json.loads(result.stdout)["verdict"], "MISSING_TRAJECTORY")

    def test_forbidden_second_export_refuses_suite_and_preserves_pin(self):
        self.run_cli("freeze", *self.suite_flags(), "--out", self.baseline)
        before = self.baseline.read_bytes()
        flags = self.suite_flags("forbidden")
        result = self.run_cli("check", *flags, "--baseline", self.baseline, "--json", expected=2)
        self.assertEqual(json.loads(result.stdout)["verdict"], "POLICY_VIOLATION")
        self.run_cli("freeze", *flags, "--out", self.baseline, expected=2)
        self.assertEqual(self.baseline.read_bytes(), before)

    def test_suite_declaration_count_refuses_before_replacing_pin(self):
        flags = self.suite_flags()
        self.run_cli("freeze", *flags, "--out", self.baseline)
        before = self.baseline.read_bytes()
        result = self.run_cli("freeze", *flags[:-2], "--out", self.baseline, expected=2)
        self.assertEqual(result.stdout, "")
        self.assertIn("one --coverage per export", result.stderr)
        self.assertEqual(self.baseline.read_bytes(), before)

    def test_deep_trace_at_profile_limit_remains_readable(self):
        trace_id = "1" * 32
        spans = []
        for number in range(1, 10001):
            attributes = [{"key": "openinference.span.kind", "value": {
                "stringValue": "TOOL" if number == 10000 else "CHAIN",
            }}]
            if number == 10000:
                attributes.extend([
                    {"key": "tool.name", "value": {"stringValue": "search"}},
                    {"key": "tool.id", "value": {"stringValue": "deep-call"}},
                ])
            span = {
                "traceId": trace_id, "spanId": f"{number:016x}",
                "startTimeUnixNano": "1", "endTimeUnixNano": "3",
                "attributes": attributes,
            }
            if number > 1:
                span["parentSpanId"] = f"{number - 1:016x}"
            spans.append(span)
        source = self.cwd / "deep.json"
        source.write_text(json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]}))
        coverage = self.cwd / "deep-coverage.json"
        coverage.write_text(json.dumps({
            "profile": "openinference-otlp-v1",
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "trace_id": trace_id, "case_name": "synthetic-deep",
            "span_coverage": "complete", "tool_call_coverage": "complete",
        }))
        result = self.run_cli("inspect-otel", source, "--coverage", coverage)
        evidence = json.loads(result.stdout)
        self.assertTrue(evidence["gate_eligible"])
        self.assertEqual(len(evidence["spans"]), 10000)
        self.assertEqual(evidence["spans"][-1]["calls"][0]["call_id"], "deep-call")


if __name__ == "__main__":
    unittest.main(verbosity=2)
