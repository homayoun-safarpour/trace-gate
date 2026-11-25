"""Fail-closed behaviour found by the code review of 25 Nov 2026.

The review was made on origin/main e568e30 (version 0.1.0). These are the same
33 cases, ported to the 0.2.0 verdicts and error lines in docs/EXIT_CODES.md:
input errors go to stderr as one INVALID_* or FREEZE_REFUSED line and exit 2.
Every case must refuse; none may print a PASS.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from tracegate.baseline import (
    Baseline,
    check_against_baseline,
    freeze_baseline,
)
from tracegate.cli import main
from tracegate.score import Rubric, ScoreReport, fingerprint_rubric, score_trajectory
from tracegate.trajectory import trajectory_from_dict

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
GOOD = str(EXAMPLES / "trajectories" / "support_good.json")
REGRESS = str(EXAMPLES / "trajectories" / "support_regress.json")
RUBRIC = str(EXAMPLES / "rubric.json")
BASELINE = str(EXAMPLES / "baselines" / "support_v1.json")
ERROR_PREFIXES = ("INVALID_TRAJECTORY:", "INVALID_RUBRIC:", "INVALID_BASELINE:",
                  "FREEZE_REFUSED:")


def _write(path: Path, data: object) -> str:
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def _clean_report(name: str = "n") -> ScoreReport:
    """A report with the four core metrics, as the scorer makes it."""
    rubric = Rubric(required_tools=("x",))
    return score_trajectory(trajectory_from_dict({"name": name, "steps": [{"tool": "x"}]}),
                            rubric)


# 1. Every entry of a tool_calls list is a tool call.


def test_forbidden_tool_in_second_tool_call_is_blocked(tmp_path: Path, capsys) -> None:
    run = _write(
        tmp_path / "multi.json",
        {
            "name": "support-agent-good",
            "steps": [
                {"role": "user", "content": "x"},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"function": {"name": "lookup_order"}},
                        {"function": {"name": "refund_all"}},
                    ],
                },
                {"role": "assistant", "tool": "send_reply"},
            ],
        },
    )
    assert main(["check", run, "--rubric", RUBRIC, "--baseline", BASELINE]) == 2
    out = capsys.readouterr().out
    assert "verdict: POLICY_VIOLATION" in out
    assert "forbidden_tools_used=['refund_all']" in out


def test_every_entry_of_tool_calls_is_extracted() -> None:
    traj = trajectory_from_dict(
        {
            "name": "n",
            "steps": [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {"function": {"name": "a"}},
                        {"function": {"name": "b"}},
                        {"name": "c"},
                    ],
                }
            ],
        }
    )
    assert traj.tools == ("a", "b", "c")
    assert len(traj.steps) == 1


# 2. A run name missing from the baseline is UNKNOWN_TRAJECTORY, even beside a known run.


def test_unknown_run_name_beside_known_run_is_unknown_trajectory(tmp_path: Path, capsys) -> None:
    data = json.loads(Path(GOOD).read_text(encoding="utf-8"))
    data["name"] = "renamed-run"
    renamed = _write(tmp_path / "renamed.json", data)
    code = main(["check", GOOD, renamed, "--rubric", RUBRIC, "--baseline", BASELINE])
    assert code == 2
    out = capsys.readouterr().out
    assert "verdict: UNKNOWN_TRAJECTORY" in out
    assert "not in baseline: ['renamed-run']" in out


# 3. A forbidden tool call blocks the run whatever the composite is.


def test_forbidden_tool_call_blocks_check_within_tolerance(tmp_path: Path, capsys) -> None:
    rubric = _write(
        tmp_path / "r10.json",
        {
            "required_tools": ["lookup_order", "send_reply"],
            "forbidden_tools": ["refund_all", "a", "b", "c", "d", "e", "f", "g", "h", "i"],
            "ordered_tools": ["lookup_order", "send_reply"],
            "min_steps": 2,
            "max_steps": 12,
        },
    )
    good = _write(
        tmp_path / "good.json",
        {"name": "r", "steps": [{"tool": "lookup_order"}, {"tool": "send_reply"}]},
    )
    bad = _write(
        tmp_path / "bad.json",
        {
            "name": "r",
            "steps": [{"tool": "lookup_order"}, {"tool": "refund_all"}, {"tool": "send_reply"}],
        },
    )
    base = str(tmp_path / "base.json")
    assert main(["freeze", good, "--rubric", rubric, "--out", base, "--tolerance", "0.05"]) == 0
    capsys.readouterr()
    assert main(["check", bad, "--rubric", rubric, "--baseline", base]) == 2
    out = capsys.readouterr().out
    assert "verdict: POLICY_VIOLATION" in out
    assert "r: POLICY_VIOLATION forbidden_tools_used=['refund_all']" in out
    assert "tolerance does not apply" in out


def test_score_report_names_forbidden_tools_called() -> None:
    rubric = Rubric(forbidden_tools=("delete_order", "refund_all"))
    traj = trajectory_from_dict(
        {"name": "n", "steps": [{"tool": "refund_all"}, {"tool": "refund_all"}]}
    )
    report = score_trajectory(traj, rubric)
    assert report.forbidden_tools_used == ("refund_all",)
    assert report.policy_ok is False


# 4. A baseline without a valid rubric pin is refused.


def test_baseline_without_rubric_pin_is_refused(tmp_path: Path, capsys) -> None:
    data = json.loads(Path(BASELINE).read_text(encoding="utf-8"))
    del data["rubric_sha256"]
    nopin = _write(tmp_path / "nopin.json", data)
    soft = _write(
        tmp_path / "soft.json",
        {"required_tools": [], "forbidden_tools": [], "ordered_tools": [], "min_steps": 0},
    )
    assert main(["check", REGRESS, "--rubric", soft, "--baseline", nopin]) == 2
    out = capsys.readouterr().out
    assert "verdict: MISSING_RUBRIC_FINGERPRINT" in out
    assert "PASS" not in out


@pytest.mark.parametrize(
    "pin,verdict",
    [
        ("", "MISSING_RUBRIC_FINGERPRINT"),
        ("abc", "INVALID_BASELINE"),
        ("Z" * 64, "INVALID_BASELINE"),
        (None, "MISSING_RUBRIC_FINGERPRINT"),
        (5, "INVALID_BASELINE"),
    ],
)
def test_baseline_with_malformed_rubric_pin_is_refused(pin: object, verdict: str) -> None:
    rubric = Rubric(required_tools=("x",))
    baseline = Baseline(version=1, scores={"n": 1.0}, rubric_sha256=pin)  # type: ignore[arg-type]
    result = check_against_baseline([_clean_report()], baseline, rubric=rubric)
    assert result.verdict == verdict


def test_freeze_without_rubric_is_refused() -> None:
    with pytest.raises(ValueError, match="MISSING_RUBRIC_FINGERPRINT"):
        freeze_baseline([_clean_report()])


# 5. Non-finite numbers never pass.


def test_nan_tolerance_is_refused_on_freeze(tmp_path: Path, capsys) -> None:
    out = str(tmp_path / "b.json")
    code = main(["freeze", GOOD, "--rubric", RUBRIC, "--out", out, "--tolerance", "nan"])
    assert code == 2
    assert not Path(out).exists()
    err = capsys.readouterr().err
    assert err.startswith("FREEZE_REFUSED:")
    assert "tolerance" in err


@pytest.mark.parametrize("value", ["NaN", -0.1])
def test_bad_tolerance_in_baseline_file_is_refused(tmp_path: Path, capsys, value: object) -> None:
    raw = Path(BASELINE).read_text(encoding="utf-8")
    assert '"tolerance": 0.05' in raw
    raw = raw.replace('"tolerance": 0.05', f'"tolerance": {value}')
    path = tmp_path / "b.json"
    path.write_text(raw, encoding="utf-8")
    assert main(["check", GOOD, "--rubric", RUBRIC, "--baseline", str(path)]) == 2
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "INVALID_BASELINE" in captured.out + captured.err
    assert "PASS" not in captured.out


def test_nan_score_in_baseline_file_is_refused(tmp_path: Path, capsys) -> None:
    raw = Path(BASELINE).read_text(encoding="utf-8")
    assert '"support-agent-good": 1.0' in raw
    raw = raw.replace('"support-agent-good": 1.0', '"support-agent-good": NaN')
    path = tmp_path / "b.json"
    path.write_text(raw, encoding="utf-8")
    assert main(["check", GOOD, "--rubric", RUBRIC, "--baseline", str(path)]) == 2
    _assert_one_line_error(capsys)


def test_nan_composite_never_passes() -> None:
    rubric = Rubric(required_tools=("x",))
    baseline = freeze_baseline([_clean_report()], rubric=rubric)
    report = _clean_report()
    report.composite = math.nan
    assert check_against_baseline([report], baseline, rubric=rubric).verdict == "INVALID_REPORT"


# 6. A message's "name" field is not a tool call.


def test_message_name_field_is_not_a_tool_call(tmp_path: Path, capsys) -> None:
    run = _write(
        tmp_path / "names.json",
        {
            "name": "support-agent-good",
            "steps": [
                {"role": "user", "name": "lookup_order", "content": "hi"},
                {"role": "tool", "name": "send_reply", "content": "{}"},
            ],
        },
    )
    assert main(["check", run, "--rubric", RUBRIC, "--baseline", BASELINE]) == 2
    assert "verdict: REGRESSION" in capsys.readouterr().out


def test_name_is_read_for_tool_use_blocks() -> None:
    traj = trajectory_from_dict(
        {
            "name": "n",
            "steps": [
                {"type": "tool_use", "name": "lookup_order"},
                {"type": "function_call", "name": "send_reply"},
                {"role": "assistant", "name": "bot", "content": "hello"},
            ],
        }
    )
    assert traj.tools == ("lookup_order", "send_reply")


# 7. Missing files and bad input exit 2 with one error line, never a traceback.


def _assert_one_line_error(capsys) -> None:
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    lines = [ln for ln in captured.err.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert lines[0].startswith(ERROR_PREFIXES)
    assert "PASS" not in captured.out


def test_missing_trajectory_file_exits_two_with_one_error_line(tmp_path: Path, capsys) -> None:
    missing = str(tmp_path / "nope.json")
    assert main(["check", missing, "--rubric", RUBRIC, "--baseline", BASELINE]) == 2
    _assert_one_line_error(capsys)


def test_missing_baseline_file_exits_two_with_one_error_line(tmp_path: Path, capsys) -> None:
    missing = str(tmp_path / "nope.json")
    assert main(["check", GOOD, "--rubric", RUBRIC, "--baseline", missing]) == 2
    _assert_one_line_error(capsys)


@pytest.mark.parametrize(
    "step",
    [
        {"role": "assistant", "tool_calls": {"a": 1}},
        {"role": "assistant", "tool_calls": [{"function": {}}]},
        {"role": "assistant", "tool_calls": ["lookup_order"]},
        "not a step",
    ],
)
def test_malformed_step_exits_two(tmp_path: Path, capsys, step: object) -> None:
    run = _write(tmp_path / "t.json", {"name": "x", "steps": [step]})
    assert main(["score", run, "--rubric", RUBRIC]) == 2
    _assert_one_line_error(capsys)


def test_non_integer_min_steps_exits_two(tmp_path: Path, capsys) -> None:
    rubric = _write(tmp_path / "r.json", {"min_steps": "two"})
    assert main(["score", GOOD, "--rubric", rubric]) == 2
    _assert_one_line_error(capsys)


def test_invalid_json_exits_two(tmp_path: Path, capsys) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert main(["check", GOOD, "--rubric", RUBRIC, "--baseline", str(bad)]) == 2
    _assert_one_line_error(capsys)


# 8. Rubric tool fields must be lists of strings.


@pytest.mark.parametrize(
    "rubric",
    [
        {"required_tools": "lookup_order"},
        {"forbidden_tools": "refund_all"},
        {"ordered_tools": [1, 2]},
        {"max_steps": 1.5},
        {"min_steps": True},
    ],
)
def test_malformed_rubric_field_is_refused(tmp_path: Path, capsys, rubric: dict) -> None:
    path = _write(tmp_path / "r.json", rubric)
    assert main(["score", GOOD, "--rubric", path]) == 2
    _assert_one_line_error(capsys)


def test_forbidden_call_below_floor_is_a_policy_violation(capsys) -> None:
    """The forbidden call is named, and the tolerance never applies to it."""
    assert main(["check", REGRESS, "--rubric", RUBRIC, "--baseline", BASELINE]) == 2
    digest = fingerprint_rubric(Rubric.from_dict(json.loads(Path(RUBRIC).read_text("utf-8"))))
    assert capsys.readouterr().out == (
        "verdict: POLICY_VIOLATION\n"
        f"  rubric_sha256 OK ({digest[:12]}...)\n"
        "  support-agent-good: POLICY_VIOLATION forbidden_tools_used=['delete_order'] "
        "(forbidden_tools=0.5000; tolerance does not apply)\n"
    )
