"""The GitHub Action wraps `trace-gate check`; these tests lock its contract and the demo."""
import html
import re
from pathlib import Path

from trace_gate.cli import main

ROOT = Path(__file__).resolve().parents[1]
ACTION = (ROOT / "action.yml").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8-sig")
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def _script_lines(text):
    """Lines that a shell will run: the body of every `run:` step."""
    lines, inside, indent = [], False, 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("run:"):
            rest = stripped[len("run:"):].strip()
            if rest == "|":
                inside, indent = True, len(line) - len(line.lstrip())
            else:
                lines.append(rest)
            continue
        if inside:
            if stripped and len(line) - len(line.lstrip()) <= indent:
                inside = False
            else:
                lines.append(stripped)
    return lines


def test_action_is_composite_with_the_three_required_inputs():
    assert 'using: "composite"' in ACTION
    for name in ("trajectory:", "rubric:", "baseline:"):
        assert name in ACTION
    assert "verdict:" in ACTION and "exit-code:" in ACTION


def test_action_file_ships_in_the_source_package():
    # CI runs this suite from the unpacked source archive, so the file must be listed there.
    manifest = (ROOT / "MANIFEST.in").read_text(encoding="utf-8")
    assert "action.yml" in manifest.splitlines()[0].split()


def test_action_never_expands_inputs_inside_a_shell_script():
    scripts = _script_lines(ACTION)
    assert len(scripts) > 5
    assert not [line for line in scripts if "${{" in line]


def test_action_runs_the_documented_command_and_keeps_its_exit_code():
    command = 'trace-gate check "$TG_TRAJECTORY" --rubric "$TG_RUBRIC" --baseline "$TG_BASELINE"'
    assert command in ACTION
    assert 'exit "$code"' in ACTION


def test_ci_proves_the_action_passes_good_and_blocks_regressed():
    assert "uses: ./" in CI
    assert 'test "$GOOD" = "PASS"' in CI
    assert 'test "$BAD" = "POLICY_VIOLATION"' in CI
    assert 'test "$BAD_OUTCOME" = "failure"' in CI


def test_readme_shows_the_action_after_the_first_screen():
    at = README.find("uses: homayoun-safarpour/trace-gate@")
    assert at > README.find("pip install -e")
    assert at < README.find("## What each result means")


def _visible_text(svg):
    """The text a reader sees in the SVG, with tags removed and whitespace collapsed."""
    parts = re.findall(r">([^<>]+)<", svg)
    return " ".join(html.unescape(" ".join(parts)).split())


def test_demo_shows_only_real_output(capsys):
    demo = _visible_text((ROOT / "docs" / "demo.svg").read_text(encoding="utf-8"))
    for name, code in (("support_regress", 2), ("support_good", 0)):
        got = main(
            [
                "check",
                str(ROOT / "examples" / "trajectories" / f"{name}.json"),
                "--rubric",
                str(ROOT / "examples" / "rubric.json"),
                "--baseline",
                str(ROOT / "examples" / "baselines" / "support_v1.json"),
            ]
        )
        assert got == code
        printed = capsys.readouterr()
        for line in (printed.out + printed.err).strip().splitlines():
            assert " ".join(line.split()) in demo
        assert f"exit {code}" in demo
