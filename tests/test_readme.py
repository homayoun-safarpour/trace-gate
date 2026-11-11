"""Documentation examples are checked against the real CLI, not marketing keywords."""

import re
from pathlib import Path

from tracegate.cli import main

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8-sig")
REGRESS = str(ROOT / "examples" / "trajectories" / "support_regress.json")
GOOD = str(ROOT / "examples" / "trajectories" / "support_good.json")
RUBRIC = str(ROOT / "examples" / "rubric.json")
BASELINE = str(ROOT / "examples" / "baselines" / "support_v1.json")


def test_readme_starts_with_a_reproducible_policy_failure():
    assert README.lstrip().startswith("# trace-gate: regression checks for agent traces\n")
    head = "\n".join(README.splitlines()[:28])
    assert "python -m pip install ." in head
    assert "support_regress.json" in head
    assert "verdict: POLICY_VIOLATION" in head
    assert "tolerance does not apply" in head
    assert "Interview pack" not in head


def test_readme_outputs_match_cli(capsys):
    examples = re.findall(r"```text\n(.*?)\n```", README, re.DOTALL)
    for path, status, expected in zip((REGRESS, GOOD), (2, 0), examples, strict=True):
        assert main(["check", path, "--rubric", RUBRIC, "--baseline", BASELINE]) == status
        assert capsys.readouterr().out.strip() == expected
