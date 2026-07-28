"""CLI exit-code contract for CI wiring."""

from __future__ import annotations

import json
from pathlib import Path

from tracegate.cli import main

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
GOOD = str(EXAMPLES / "trajectories" / "support_good.json")
RUBRIC = str(EXAMPLES / "rubric.json")


def test_score_cli_exits_zero() -> None:
    assert main(["score", GOOD, "--rubric", RUBRIC]) == 0


def test_check_cli_exits_zero_on_pass(tmp_path: Path) -> None:
    baseline = tmp_path / "base.json"
    assert main(["freeze", GOOD, "--rubric", RUBRIC, "--out", str(baseline)]) == 0
    assert main(["check", GOOD, "--rubric", RUBRIC, "--baseline", str(baseline)]) == 0


def test_check_cli_exits_two_on_regression(tmp_path: Path) -> None:
    """Gate contract: REGRESSION -> exit 2 so CI / loop-engine gates fail closed."""
    baseline = tmp_path / "base.json"
    assert main(["freeze", GOOD, "--rubric", RUBRIC, "--out", str(baseline)]) == 0
    # Inflate the pinned composite so the same good trajectory falls below the floor.
    data = json.loads(baseline.read_text(encoding="utf-8"))
    data["scores"]["support-agent-good"] = 1.5
    data["tolerance"] = 0.0
    baseline.write_text(json.dumps(data), encoding="utf-8")
    code = main(["check", GOOD, "--rubric", RUBRIC, "--baseline", str(baseline)])
    assert code == 2


def test_check_cli_exits_two_on_rubric_drift(tmp_path: Path) -> None:
    """Softening criteria without re-freeze must fail closed (exit 2)."""
    baseline = tmp_path / "base.json"
    soft = tmp_path / "soft.json"
    soft.write_text(
        json.dumps(
            {
                "required_tools": [],
                "forbidden_tools": [],
                "ordered_tools": [],
                "min_steps": 0,
            }
        ),
        encoding="utf-8",
    )
    assert main(["freeze", GOOD, "--rubric", RUBRIC, "--out", str(baseline)]) == 0
    assert main(["check", GOOD, "--rubric", str(soft), "--baseline", str(baseline)]) == 2


def test_freeze_writes_scores(tmp_path: Path) -> None:
    baseline = tmp_path / "base.json"
    code = main(
        ["freeze", GOOD, "--rubric", RUBRIC, "--out", str(baseline), "--tolerance", "0.01"]
    )
    assert code == 0
    data = json.loads(baseline.read_text(encoding="utf-8"))
    assert "support-agent-good" in data["scores"]
    assert data["tolerance"] == 0.01
    assert len(data["rubric_sha256"]) == 64
