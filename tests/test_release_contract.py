"""Check the current explicit release gate, not general GitHub Actions semantics."""
import itertools
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/ci.yml").read_text()
AGGREGATE = WORKFLOW.split("  release-ready:\n", 1)[1]
EXPECTED_JOBS = {"test", "promptfoo", "loop-engine"}
STATES = ("success", "failure", "skipped", "cancelled")


def test_release_gate_covers_every_validation_job():
    # These assertions intentionally require review if the workflow structure changes.
    jobs = set(re.findall(r"^  ([a-z][a-z-]*):$", WORKFLOW.split("jobs:\n", 1)[1],
                          re.MULTILINE))
    assert jobs == EXPECTED_JOBS | {"release-ready"}
    needs = re.search(r"^    needs: \[(.*?)\]$", AGGREGATE, re.MULTILINE)
    assert needs is not None
    assert {name.strip() for name in needs.group(1).split(",")} == EXPECTED_JOBS
    assert "if: ${{ always() }}" in AGGREGATE
    values = re.findall(r"^          (\w+): \$\{\{ needs\.([\w-]+)\.result \}\}$",
                        AGGREGATE, re.MULTILINE)
    assert dict(values) == {"TEST_RESULT": "test", "PROMPTFOO_RESULT": "promptfoo",
                            "LOOP_RESULT": "loop-engine"}


@pytest.mark.skipif(shutil.which("bash") is None, reason="release runner uses bash")
@pytest.mark.parametrize("states", itertools.product(STATES, repeat=3))
def test_release_gate_accepts_only_all_success(states):
    script = AGGREGATE.split("        run: |\n", 1)[1]
    lines = script.splitlines()
    assert all(not line or line.startswith("          ") for line in lines)
    script = "\n".join(line[10:] for line in lines)
    env = dict(zip(("TEST_RESULT", "PROMPTFOO_RESULT", "LOOP_RESULT"), states, strict=True))
    result = subprocess.run([shutil.which("bash"), "-e", "-o", "pipefail", "-c", script],
                            env=env, capture_output=True, text=True, timeout=5, check=False)
    assert (result.returncode == 0) == all(state == "success" for state in states)


def test_release_instructions_name_all_required_jobs():
    documentation = (ROOT / "docs/RELEASING.md").read_text()
    for job in EXPECTED_JOBS:
        assert f"`{job}`" in documentation
