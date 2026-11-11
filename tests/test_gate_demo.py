"""The diagram is based on actual synthetic CLI output and remains reproducible."""

import json
import runpy
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = runpy.run_path(str(ROOT / "scripts/render_gate_demo.py"))


def test_demo_proof_matches_current_cli():
    recorded = json.loads((ROOT / "docs/gate-proof.json").read_text(encoding="utf-8"))
    actual = DEMO["capture_demo"]()
    assert actual == recorded
    assert [c["exit_code"] for c in actual["cases"]] == [0, 2, 2, 2]
    forbidden = actual["cases"][1]
    assert forbidden["first_case_score"]["composite"] > actual["quality_floor"]
    assert forbidden["result"]["verdict"] == "POLICY_VIOLATION"
    svg = (ROOT / "docs/gate-proof.svg").read_text(encoding="utf-8")
    assert DEMO["render_svg"](actual) == svg
    assert ET.fromstring(svg).tag.endswith("svg")
