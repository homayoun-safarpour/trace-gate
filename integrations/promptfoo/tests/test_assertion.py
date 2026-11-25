"""Standard-library tests for the official external Python assertion interface."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = load_module("trace_gate_assert")
native = load_module("native_policy_assert")
SCENARIOS = json.loads((HERE / "scenarios.json").read_text())


class AssertionTests(unittest.TestCase):
    def context(self):
        return {
            "config": {
                "rubric_path": "fixtures/rubric.json",
                "baseline_path": "fixtures/baseline.json",
            }
        }

    def output(self):
        return (HERE / "fixtures/good.json").read_text()

    def test_scenario_expectations(self):
        forbidden = json.loads((HERE / "fixtures/rubric.json").read_text())["forbidden_tools"]
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario["name"]):
                context = {
                    "config": {key: scenario[key] for key in ["rubric_path", "baseline_path"]}
                }
                output = (HERE / scenario["fixture"]).read_text()
                actual = adapter.get_assert(output, context)
                self.assertIs(actual["pass"], scenario["gate_pass"])
                self.assertEqual(actual["score"], float(scenario["gate_pass"]))
                self.assertTrue(actual["reason"].startswith(scenario["verdict"] + ":"))
                other = native.get_assert(output, {"config": {"forbidden_tools": forbidden}})
                self.assertIs(other["pass"], scenario["native_pass"])
                json.dumps(actual, allow_nan=False)

    def test_drift_fixture_is_policy_not_overwritten_evidence(self):
        scenario = next(s for s in SCENARIOS if s["name"] == "rubric-drift")
        self.assertNotEqual(scenario["fixture"], scenario["rubric_path"])
        policy = json.loads((HERE / scenario["rubric_path"]).read_text())
        self.assertIn("forbidden_tools", policy)
        self.assertEqual(policy["max_steps"], 13)

    def test_overflowing_json_number_rejected(self):
        output = self.output().replace('"trajectories":', '"ignored": 1e999, "trajectories":', 1)
        self.assertFalse(adapter.get_assert(output, self.context())["pass"])

    def test_policy_is_reloaded_between_assertions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rubric.json"
            original = (HERE / "fixtures/rubric.json").read_text()
            path.write_text(original)
            context = self.context()
            context["config"]["rubric_path"] = str(path)
            self.assertTrue(adapter.get_assert(self.output(), context)["pass"])
            changed = json.loads(original)
            changed["forbidden_tools"] = []
            path.write_text(json.dumps(changed))
            self.assertFalse(adapter.get_assert(self.output(), context)["pass"])
            path.write_text(original)
            self.assertTrue(adapter.get_assert(self.output(), context)["pass"])

    def test_mapping_output_supported(self):
        self.assertTrue(adapter.get_assert(json.loads(self.output()), self.context())["pass"])

    def test_failed_policy_score_cannot_be_quality_composite(self):
        output = (HERE / "fixtures/forbidden-second-call.json").read_text()
        result = adapter.get_assert(output, self.context())
        self.assertFalse(result["pass"])
        self.assertEqual(result["score"], 0)
        self.assertGreater(result["named_scores"]["quality_mean"], 0.95)

    def test_missing_or_invalid_config_fails(self):
        for context in [
            None,
            {},
            {"config": []},
            {"config": {}},
            {"config": {"rubric_path": "does-not-exist", "baseline_path": "x"}},
        ]:
            with self.subTest(context=context):
                self.assertFalse(adapter.get_assert(self.output(), context)["pass"])

    def test_no_paths_from_provider_output(self):
        self.assertFalse(adapter.get_assert("fixtures/good.json", self.context())["pass"])
        self.assertFalse(
            adapter.get_assert({"rubric_path": "fixtures/rubric.json"}, self.context())["pass"]
        )

    def test_empty_suite_does_not_skip(self):
        result = adapter.get_assert({"trajectories": []}, self.context())
        self.assertFalse(result["pass"])
        self.assertTrue(result["reason"].startswith("MISSING_TRAJECTORY:"))

    def test_duplicate_json_keys_rejected(self):
        output = (
            '{"trajectories": [], "trajectories": '
            + json.dumps(json.loads(self.output())["trajectories"])
            + "}"
        )
        self.assertFalse(adapter.get_assert(output, self.context())["pass"])

    def test_nonfinite_json_rejected(self):
        self.assertFalse(adapter.get_assert('{"trajectories":NaN}', self.context())["pass"])

    def test_duplicate_call_ids_rejected(self):
        output = json.loads(self.output())
        output["trajectories"][0]["steps"][1]["tool_calls"][0]["id"] = "lookup-1"
        self.assertFalse(adapter.get_assert(output, self.context())["pass"])

    def test_unrelated_working_directory(self):
        previous = Path.cwd()
        try:
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                self.assertTrue(adapter.get_assert(self.output(), self.context())["pass"])
        finally:
            os.chdir(previous)

    def test_inputs_not_mutated(self):
        output, context = json.loads(self.output()), self.context()
        before = copy.deepcopy((output, context))
        adapter.get_assert(output, context)
        self.assertEqual((output, context), before)

    def test_configs_do_not_weaken_gate(self):
        for filename in ["promptfooconfig.json", "pass-config.json", "fail-config.json"]:
            config = json.loads((HERE / filename).read_text())
            self.assertEqual(config["providers"], ["echo"])
            self.assertNotIn("threshold", config)
            self.assertNotIn("defaultTest", config)
            for test in config["tests"]:
                self.assertNotIn("threshold", test)
                self.assertEqual(len(test["assert"]), 1)
                assertion = test["assert"][0]
                self.assertEqual(assertion["type"], "python")
                self.assertEqual(assertion["weight"], 1)
                self.assertNotIn("threshold", assertion)


if __name__ == "__main__":
    unittest.main()
