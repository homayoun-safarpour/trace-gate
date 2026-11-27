"""The README first screen and its outputs are checked against the real CLI."""

import re
from pathlib import Path

from trace_gate.cli import main

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8-sig")
REGRESS = str(ROOT / "examples" / "trajectories" / "support_regress.json")
GOOD = str(ROOT / "examples" / "trajectories" / "support_good.json")
RUBRIC = str(ROOT / "examples" / "rubric.json")
BASELINE = str(ROOT / "examples" / "baselines" / "support_v1.json")
FIRST_COMMAND = (
    "trace-gate check examples/trajectories/support_regress.json "
    "--rubric examples/rubric.json --baseline examples/baselines/support_v1.json"
)


def test_readme_spoken_h1_is_trace_gate():
    assert README.lstrip().startswith("# trace-gate\n")


def test_readme_first_screen_matches_top100_craft():
    pip_at = README.find("pip install")
    interview_at = README.find("Interview pack")
    problem_at = README.find("## The problem")
    assert 0 <= pip_at < interview_at
    assert 0 <= pip_at < problem_at
    head = "\n".join(README.splitlines()[:25])
    assert "# trace-gate" in head
    assert "git clone https://github.com/homayoun-safarpour/trace-gate" in head
    assert "pip install -e" in head
    assert FIRST_COMMAND in head
    assert "verdict: POLICY_VIOLATION" in head
    assert "forbidden_tools_used=['delete_order']" in head
    assert "tolerance does not apply" in head
    assert "That command exits 2." in head
    assert "Interview pack" not in head
    assert chr(0x2014) not in README
    assert "verdict: PASS" not in head


def test_readme_stranger_check_is_policy_violation():
    assert main(FIRST_COMMAND.split()[1:]) == 2


def test_readme_outputs_match_cli(capsys, tmp_path):
    """Both text blocks are the real output: the first command, then the approved run."""
    examples = re.findall(r"```text\n(.*?)\n```", README, re.DOTALL)
    assert len(examples) == 2
    assert main(["check", REGRESS, "--rubric", RUBRIC, "--baseline", BASELINE]) == 2
    assert capsys.readouterr().out.strip() == examples[0]
    baseline = str(tmp_path / "baseline.json")
    assert main(["freeze", GOOD, "--rubric", RUBRIC, "--out", baseline,
                 "--tolerance", "0.05"]) == 0
    capsys.readouterr()
    assert main(["check", GOOD, "--rubric", RUBRIC, "--baseline", baseline]) == 0
    assert capsys.readouterr().out.strip() == examples[1]


def test_readme_lists_every_check_verdict():
    for verdict in ("PASS", "POLICY_VIOLATION", "REGRESSION", "RUBRIC_DRIFT",
                    "MISSING_RUBRIC_FINGERPRINT", "MISSING_BASELINE", "UNKNOWN_TRAJECTORY",
                    "MISSING_TRAJECTORY", "DUPLICATE_TRAJECTORY", "INVALID_BASELINE"):
        assert f"| `{verdict}` |" in README
