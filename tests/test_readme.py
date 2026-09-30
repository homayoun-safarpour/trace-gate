from pathlib import Path

from tracegate.cli import main

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8-sig")
REGRESS = str(ROOT / "examples" / "trajectories" / "support_regress.json")
RUBRIC = str(ROOT / "examples" / "rubric.json")
BASELINE = str(ROOT / "examples" / "baselines" / "support_v1.json")


def test_readme_spoken_h1_is_trace_gate():
    assert README.lstrip().startswith("# trace-gate\n")


def test_readme_first_screen_matches_top100_craft():
    pip_at = README.find("pip install")
    interview_at = README.find("Interview pack")
    problem_at = README.find("## The problem")
    assert 0 <= pip_at < interview_at
    assert 0 <= pip_at < problem_at
    head = "\n".join(README.splitlines()[:22])
    assert "# trace-gate" in head
    assert "git clone https://github.com/homayoun-safarpour/trace-gate" in head
    assert "pip install -e" in head
    assert "support_regress.json" in head
    assert "verdict: REGRESSION" in head
    assert "composite=0.5000" in head
    assert "Interview pack" not in head
    assert "\u2014" not in head
    assert "verdict: PASS" not in head


def test_readme_stranger_check_is_regression():
    code = main(
        [
            "check",
            REGRESS,
            "--rubric",
            RUBRIC,
            "--baseline",
            BASELINE,
        ]
    )
    assert code == 2
