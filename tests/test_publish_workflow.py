"""Check the PyPI publish workflow's safety properties, not GitHub Actions semantics.

These assertions are strict on purpose: any change to the workflow should need a
matching review of this file.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github/workflows/publish.yml").read_text()
LINES = WORKFLOW.splitlines()
JOBS = WORKFLOW.split("\njobs:\n", 1)[1]
BUILD, PUBLISH = JOBS.split("\n  publish:\n", 1)

# Every GitHub expression the workflow may contain, as whole lines.
EXPRESSION_LINES = {
    "  group: publish-${{ github.ref }}",
    "    if: ${{ !github.event.release.prerelease }}",
    "          TAG: ${{ github.event.release.tag_name }}",
    "          GH_TOKEN: ${{ github.token }}",
}


def run_scripts():
    """Yield the body of every run step, one-line or block."""
    for index, line in enumerate(LINES):
        match = re.match(r"^(\s*)(?:- )?run: (.*)$", line)
        if not match:
            continue
        if match.group(2) != "|":
            yield match.group(2)
            continue
        indent = len(match.group(1))
        body = []
        for following in LINES[index + 1:]:
            if following.strip() and len(following) - len(following.lstrip()) <= indent:
                break
            body.append(following)
        yield "\n".join(body)


def test_only_a_published_final_release_starts_it():
    trigger = WORKFLOW.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
    assert trigger.strip() == "release:\n    types: [published]"
    assert BUILD.startswith("  build:\n    if: ${{ !github.event.release.prerelease }}\n")
    assert "    needs: build\n" in PUBLISH


def test_expressions_only_in_reviewed_lines():
    found = {line for line in LINES if "${{" in line}
    assert found == EXPRESSION_LINES
    for script in run_scripts():
        assert "${{" not in script


def test_permissions_are_exact():
    assert WORKFLOW.count("permissions:") == 3
    assert "\npermissions:\n  contents: read\n\n" in WORKFLOW
    assert "    permissions:\n      contents: read\n      checks: read\n    steps:" in BUILD
    assert "    permissions:\n      id-token: write\n    steps:" in PUBLISH
    assert "id-token" not in BUILD


@pytest.mark.parametrize("word", [
    "continue-on-error", "|| true", "||", "set +e", "repository-url", "repository_url",
    "secrets", "password", "write-all", "pull_request_target", "workflow_run",
    "workflow_dispatch", "always()", "release.name", "release.body", "skip-existing",
])
def test_forbidden_text(word):
    assert word not in WORKFLOW


def test_only_one_condition():
    assert [line.strip() for line in LINES if re.match(r"^\s*if:", line)] == [
        "if: ${{ !github.event.release.prerelease }}"]


def test_every_action_is_pinned_to_a_commit():
    uses = re.findall(r"uses: (\S+)", WORKFLOW)
    assert len(uses) == 5
    for action in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action), action


def test_build_checks_come_before_the_build_and_in_order():
    steps = [
        'test "$TAG" = "v$version"',
        "git merge-base --is-ancestor HEAD origin/main",
        'test "$passed" -ge 1',
        "python -m build --no-isolation",
        "python scripts/verify_distribution.py --dist-dir dist",
        "sha256sum dist/*",
    ]
    positions = [BUILD.index(step) for step in steps]
    assert positions == sorted(positions)
    assert "check_name=Release+readiness" in BUILD
    assert "fetch-depth: 0" in BUILD and "persist-credentials: false" in BUILD


def test_publish_job_only_downloads_and_uploads():
    steps = re.findall(r"^      - (?:uses|name): (.*)$", PUBLISH, re.MULTILINE)
    assert [step.split("@")[0] for step in steps] == [
        "actions/download-artifact",
        "Checksums of the files about to be uploaded",
        "pypa/gh-action-pypi-publish",
    ]
    assert PUBLISH.rstrip().endswith("# v1.14.3")
    assert "      name: pypi\n" in PUBLISH
