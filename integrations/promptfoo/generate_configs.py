"""Create reproducible synthetic fixtures and offline Promptfoo JSON configs."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from tracegate.baseline import freeze_baseline
from tracegate.score import Rubric, score_trajectory
from tracegate.trajectory import trajectory_from_dict

HERE = Path(__file__).resolve().parent


def write(name, value):
    (HERE / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main():
    rubric = {
        "required_tools": ["lookup_order", "send_reply"],
        "forbidden_tools": ["delete_order"] + [f"forbidden_demo_{n}" for n in range(19)],
        "ordered_tools": ["lookup_order", "send_reply"],
        "min_steps": 2,
        "max_steps": 12,
    }
    good = {
        "trajectories": [
            {
                "name": name,
                "steps": [
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {"id": "lookup-1", "function": {"name": "lookup_order"}},
                        ],
                    },
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {"id": "reply-1", "function": {"name": "send_reply"}},
                        ],
                    },
                ],
            }
            for name in ["synthetic-order-a", "synthetic-order-b"]
        ]
    }
    parsed_rubric = Rubric.from_dict(rubric)
    baseline = freeze_baseline(
        [score_trajectory(trajectory_from_dict(t), parsed_rubric) for t in good["trajectories"]],
        tolerance=0.05,
        rubric=parsed_rubric,
    ).to_dict()
    write("fixtures/rubric.json", rubric)
    write("fixtures/baseline.json", baseline)
    changed = copy.deepcopy(rubric)
    changed["max_steps"] = 13
    write("fixtures/rubric-drift-policy.json", changed)
    hashless = copy.deepcopy(baseline)
    del hashless["rubric_sha256"]
    write("fixtures/baseline-hashless.json", hashless)
    scenarios = []

    def add(name, evidence, gate_pass, native_pass, verdict, **policy):
        filename = f"fixtures/{name}.json"
        if isinstance(evidence, str):
            (HERE / filename).write_text(evidence, encoding="utf-8")
        else:
            write(filename, evidence)
        scenarios.append(
            {
                "name": name,
                "fixture": filename,
                "gate_pass": gate_pass,
                "native_pass": native_pass,
                "verdict": verdict,
                "rubric_path": policy.get("rubric_path", "fixtures/rubric.json"),
                "baseline_path": policy.get("baseline_path", "fixtures/baseline.json"),
            }
        )

    add("good", good, True, True, "PASS")
    bad = copy.deepcopy(good)
    bad["trajectories"][0]["steps"][0]["tool_calls"].append(
        {"id": "forbidden-2", "function": {"name": "delete_order"}}
    )
    add("forbidden-second-call", bad, False, False, "POLICY_VIOLATION")
    bad = copy.deepcopy(good)
    bad["trajectories"][0]["steps"][0]["tool_calls"] = {"function": {"name": "lookup_order"}}
    add("malformed-tool-calls", bad, False, False, "INVALID_INPUT")
    bad = copy.deepcopy(good)
    bad["trajectories"].pop()
    add("missing-case", bad, False, True, "MISSING_TRAJECTORY")
    bad = copy.deepcopy(good)
    extra = copy.deepcopy(bad["trajectories"][0])
    extra["name"] = "synthetic-unreviewed"
    bad["trajectories"].append(extra)
    add("extra-case", bad, False, True, "UNKNOWN_TRAJECTORY")
    bad = copy.deepcopy(good)
    bad["trajectories"].append(copy.deepcopy(bad["trajectories"][0]))
    add("duplicate-case", bad, False, True, "DUPLICATE_TRAJECTORY")
    bad = copy.deepcopy(good)
    bad["trajectories"][0]["steps"][1]["tool_calls"] = []
    add("quality-regression", bad, False, True, "REGRESSION")
    add("rubric-drift", good, False, True, "RUBRIC_DRIFT",
        rubric_path="fixtures/rubric-drift-policy.json")
    add(
        "missing-fingerprint",
        good,
        False,
        True,
        "MISSING_RUBRIC_FINGERPRINT",
        baseline_path="fixtures/baseline-hashless.json",
    )
    add("invalid-json", '{"trajectories":', False, False, "INVALID_INPUT")
    write("scenarios.json", scenarios)
    write_configs(scenarios, rubric)


def write_configs(scenarios, rubric):
    gate = {
        "description": "trace-gate complete recorded-suite check, synthetic echo provider",
        "prompts": ["{{trace_json}}"],
        "providers": ["echo"],
        "tests": [],
    }
    native = copy.deepcopy(gate)
    native["description"] = "Configured native Python tool-policy check (not a capability ceiling)"
    for scenario in scenarios:
        test = {
            "description": scenario["name"],
            "vars": {"trace_json": (HERE / scenario["fixture"]).read_text(encoding="utf-8")},
            "assert": [
                {
                    "type": "python",
                    "value": "file://trace_gate_assert.py",
                    "weight": 1,
                    "config": {key: scenario[key] for key in ["rubric_path", "baseline_path"]},
                }
            ],
        }
        gate["tests"].append(test)
        other = copy.deepcopy(test)
        other["assert"] = [
            {
                "type": "python",
                "value": "file://native_policy_assert.py",
                "weight": 1,
                "config": {"forbidden_tools": rubric["forbidden_tools"]},
            }
        ]
        native["tests"].append(other)
    write("promptfooconfig.json", gate)
    write("native-policy-config.json", native)
    clean = copy.deepcopy(gate)
    clean["tests"] = clean["tests"][:1]
    write("pass-config.json", clean)
    fail = copy.deepcopy(gate)
    fail["tests"] = fail["tests"][1:2]
    write("fail-config.json", fail)


if __name__ == "__main__":
    main()
