"""Public CLI contracts for policy, coverage, migration and malformed configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tracegate.cli import main


@pytest.fixture
def inputs(tmp_path):
    def write(name, data):
        path = tmp_path / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    rubric = write("rubric.json", {"forbidden_tools": [f"deny_{i}" for i in range(20)]})
    good = write("good.json", {"name": "case", "steps": [{"tool": "read"}]})
    bad = write("bad.json", {"name": "case", "steps": [{"tool": "deny_0"}]})
    baseline = str(tmp_path / "baseline.json")
    assert main(["freeze", good, "--rubric", rubric, "--out", baseline,
                 "--tolerance", "0.05"]) == 0
    return write, rubric, good, bad, baseline


def check(trace, rubric, baseline):
    return main(["check", trace, "--rubric", rubric, "--baseline", baseline, "--json"])


def test_high_score_does_not_override_policy(inputs, capsys):
    _, rubric, _, bad, baseline = inputs
    capsys.readouterr()
    assert check(bad, rubric, baseline) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == "POLICY_VIOLATION"
    assert result["ok"] is False
    assert "deny_0" in " ".join(result["details"])


def test_score_remains_diagnostic_and_exposes_policy(inputs, capsys):
    _, rubric, _, bad, _ = inputs
    capsys.readouterr()
    assert main(["score", bad, "--rubric", rubric, "--json"]) == 0
    result = json.loads(capsys.readouterr().out)[0]
    assert result["composite"] == 0.9875
    assert result["policy_ok"] is False
    assert result["forbidden_tools_used"] == ["deny_0"]


@pytest.mark.parametrize("existing", [False, True])
def test_forbidden_freeze_never_creates_or_overwrites_pin(inputs, existing, capsys):
    _, rubric, _, bad, baseline = inputs
    path = Path(baseline) if existing else Path(baseline).with_name("new.json")
    before = path.read_bytes() if existing else None
    capsys.readouterr()
    assert main(["freeze", bad, "--rubric", rubric, "--out", str(path)]) == 2
    result = capsys.readouterr()
    assert result.out == ""
    assert "POLICY_VIOLATION" in result.err
    assert (path.read_bytes() if path.exists() else None) == before


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.1, 1.1, True, "0.05", 10**400])
@pytest.mark.parametrize("field", ["tolerance", "score"])
def test_invalid_baseline_numbers_refuse_check(inputs, value, field, capsys):
    write, rubric, good, _, baseline = inputs
    data = json.loads(Path(baseline).read_text(encoding="utf-8"))
    if field == "score":
        data["scores"]["case"] = value
    else:
        data[field] = value
    write("baseline.json", data)
    capsys.readouterr()
    assert check(good, rubric, baseline) == 2
    captured = capsys.readouterr()
    if captured.out:
        assert json.loads(captured.out)["verdict"] == "INVALID_BASELINE"
    else:
        assert "INVALID_BASELINE" in captured.err


@pytest.mark.parametrize("rubric_data", [
    {"forbidden_tools": "delete"}, {"forbidden_tools": None},
    {"forbidden_tools": [""]}, {"max_steps": True}, {"min_steps": 1.5},
    {"min_steps": -1}, {"min_steps": 5, "max_steps": 2},
])
def test_malformed_rubric_is_not_coerced(inputs, rubric_data, capsys):
    write, _, good, _, baseline = inputs
    invalid = write("invalid-rubric.json", rubric_data)
    capsys.readouterr()
    assert check(good, invalid, baseline) == 2
    result = capsys.readouterr()
    assert result.out == ""
    assert "INVALID_RUBRIC" in result.err


@pytest.mark.parametrize("tolerance", ["nan", "inf", "-0.1", "1.1"])
def test_invalid_freeze_tolerance_preserves_pin(inputs, tolerance, capsys):
    _, rubric, good, _, baseline = inputs
    before = Path(baseline).read_bytes()
    assert main(["freeze", good, "--rubric", rubric, "--out", baseline,
                 "--tolerance", tolerance]) == 2
    assert "INVALID_BASELINE" in capsys.readouterr().err
    assert Path(baseline).read_bytes() == before


@pytest.mark.parametrize("target", ["rubric", "trace", "baseline"])
def test_missing_inputs_fail_with_actionable_error(inputs, target, capsys):
    _, rubric, good, _, baseline = inputs
    paths = {"rubric": rubric, "trace": good, "baseline": baseline}
    Path(paths[target]).unlink()
    capsys.readouterr()
    assert check(good, rubric, baseline) == 2
    result = capsys.readouterr()
    assert result.out == ""
    assert "No such file" in result.err
    assert "Traceback" not in result.err
