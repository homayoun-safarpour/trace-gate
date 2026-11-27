"""Check the PyPI publish workflow's safety properties, not GitHub Actions semantics."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/publish.yml").read_text()
JOBS = WORKFLOW.split("jobs:\n", 1)[1]
BUILD = JOBS.split("  publish:\n", 1)[0]
PUBLISH = JOBS.split("  publish:\n", 1)[1]


def test_only_a_published_release_starts_it():
    trigger = WORKFLOW.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert trigger.strip() == "release:\n    types: [published]"
    for other in ("push:", "pull_request", "workflow_dispatch", "schedule:"):
        assert other not in WORKFLOW


def test_upload_rights_only_in_the_publish_job():
    top = WORKFLOW.split("\njobs:\n", 1)[0]
    assert "permissions:\n  contents: read\n" in top
    assert WORKFLOW.count("id-token: write") == 1
    assert "id-token: write" in PUBLISH
    assert "    needs: build\n" in PUBLISH
    assert "      name: pypi\n" in PUBLISH


def test_no_stored_credentials():
    assert "secrets." not in WORKFLOW
    assert "password" not in WORKFLOW
    assert "persist-credentials: false" in BUILD


def test_every_action_is_pinned_to_a_commit():
    uses = re.findall(r"uses: ([^\s#]+)", WORKFLOW)
    assert len(uses) == 5
    for action in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action), action


def test_build_job_checks_before_upload():
    steps = [
        'test "$TAG" = "v$version"',
        "python -m build --no-isolation",
        "python scripts/verify_distribution.py --dist-dir dist",
        "sha256sum dist/*",
    ]
    positions = [BUILD.index(step) for step in steps]
    assert positions == sorted(positions)
    assert "TAG: ${{ github.event.release.tag_name }}" in BUILD
    assert "${{ github.event.release.tag_name }}" not in BUILD.split("run: |", 1)[1]
    assert "gh-action-pypi-publish" in PUBLISH and "gh-action-pypi-publish" not in BUILD
