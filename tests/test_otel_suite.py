"""One reviewed, hash-bound declaration per export in an offline OTLP suite."""
import hashlib
import json
from pathlib import Path

import pytest

from tracegate.cli import main

FIXTURES = Path(__file__).resolve().parents[1] / "integrations/opentelemetry-js/fixtures"


@pytest.fixture
def suite(tmp_path):
    rubric = tmp_path / "rubric.json"
    rubric.write_text(json.dumps({"required_tools": ["search"],
                                  "forbidden_tools": ["delete_database"]}))
    pairs = []
    for name in ("good", "repeated-name"):
        source = tmp_path / f"{name}.json"
        source.write_bytes((FIXTURES / f"{name}.json").read_bytes())
        coverage = tmp_path / f"{name}-coverage.json"
        coverage.write_text(json.dumps({
            "profile": "openinference-otlp-v1",
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "trace_id": "1" * 32, "case_name": name,
            "span_coverage": "complete", "tool_call_coverage": "complete",
        }))
        pairs.append((source, coverage))
    return pairs, rubric, tmp_path / "baseline.json"


def arguments(pairs, rubric):
    args = [str(source) for source, _ in pairs]
    args += ["--input-format", "openinference-otlp", "--rubric", str(rubric)]
    for _, coverage in pairs:
        args += ["--coverage", str(coverage)]
    return args


def set_coverage(path, **changes):
    data = json.loads(path.read_text())
    data.update(changes)
    path.write_text(json.dumps(data))


def replace_source(pair, name):
    source, coverage = pair
    source.write_bytes((FIXTURES / f"{name}.json").read_bytes())
    set_coverage(coverage, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())


def freeze(suite):
    pairs, rubric, baseline = suite
    assert main(["freeze", *arguments(pairs, rubric), "--out", str(baseline)]) == 0
    return baseline.read_bytes()


def test_score_freeze_and_check_whole_suite(suite, capsys):
    pairs, rubric, baseline = suite
    assert main(["score", *arguments(pairs, rubric), "--json"]) == 0
    reports = json.loads(capsys.readouterr().out)
    assert [r["trajectory_name"] for r in reports] == ["good", "repeated-name"]
    freeze(suite)
    assert set(json.loads(baseline.read_text())["scores"]) == {"good", "repeated-name"}
    capsys.readouterr()
    assert main(["check", *arguments(pairs, rubric), "--baseline", str(baseline), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "PASS"


def test_reordering_pairs_preserves_case_identity(suite, capsys):
    pairs, rubric, baseline = suite
    freeze(suite)
    capsys.readouterr()
    assert main(["check", *arguments(pairs[::-1], rubric),
                 "--baseline", str(baseline), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "PASS"


@pytest.mark.parametrize("count", [0, 1, 3])
@pytest.mark.parametrize("command", ["score", "freeze", "check"])
def test_declaration_count_must_match_before_reading_inputs(suite, capsys, count, command):
    pairs, rubric, baseline = suite
    before = freeze(suite)
    capsys.readouterr()
    args = [str(p[0]) for p in pairs] + ["--input-format", "openinference-otlp",
                                       "--rubric", str(rubric)]
    for _ in range(count):
        args += ["--coverage", str(pairs[0][1])]
    if command == "freeze":
        args += ["--out", str(baseline)]
    elif command == "check":
        args += ["--baseline", str(baseline)]
    assert main([command, *args]) == 2
    result = capsys.readouterr()
    assert result.out == ""
    assert "one --coverage per export" in result.err
    assert baseline.read_bytes() == before


def test_swapped_declarations_fail_on_source_hash(suite, capsys):
    pairs, rubric, baseline = suite
    before = freeze(suite)
    capsys.readouterr()
    swapped = [(pairs[0][0], pairs[1][1]), (pairs[1][0], pairs[0][1])]
    assert main(["freeze", *arguments(swapped, rubric), "--out", str(baseline)]) == 2
    result = capsys.readouterr()
    assert result.out == ""
    assert "hash mismatch" in result.err
    assert baseline.read_bytes() == before


@pytest.mark.parametrize("kind", ["events", "dropped-attributes", "missing-call-id", "malformed"])
@pytest.mark.parametrize("index", [0, 1])
def test_any_invalid_export_refuses_whole_suite_without_partial_scores(suite, capsys, kind, index):
    pairs, rubric, baseline = suite
    before = freeze(suite)
    if kind == "malformed":
        pairs[index][0].write_text('{"resourceSpans": []')
        set_coverage(pairs[index][1], source_sha256=hashlib.sha256(
            pairs[index][0].read_bytes()).hexdigest())
    else:
        replace_source(pairs[index], kind)
    capsys.readouterr()
    for command, extra in (("score", ["--json"]), ("freeze", ["--out", str(baseline)]),
                           ("check", ["--baseline", str(baseline), "--json"])):
        assert main([command, *arguments(pairs, rubric), *extra]) == 2
        result = capsys.readouterr()
        assert result.out == ""
        assert "SYNTHETIC_PAYLOAD" not in result.err
        assert baseline.read_bytes() == before


@pytest.mark.parametrize("state", ["unknown", "incomplete"])
def test_second_export_needs_complete_coverage(suite, capsys, state):
    pairs, rubric, baseline = suite
    before = freeze(suite)
    set_coverage(pairs[1][1], tool_call_coverage=state)
    capsys.readouterr()
    assert main(["freeze", *arguments(pairs, rubric), "--out", str(baseline)]) == 2
    assert capsys.readouterr().out == ""
    assert baseline.read_bytes() == before


@pytest.mark.parametrize("problem,verdict", [
    ("missing", "MISSING_TRAJECTORY"), ("unknown", "UNKNOWN_TRAJECTORY"),
    ("duplicate", "DUPLICATE_TRAJECTORY"), ("forbidden", "POLICY_VIOLATION"),
])
def test_suite_cannot_hide_missing_unknown_duplicate_or_forbidden_case(suite, capsys,
                                                                    problem, verdict):
    pairs, rubric, baseline = suite
    before = freeze(suite)
    if problem == "missing":
        pairs = pairs[:1]
    elif problem == "unknown":
        set_coverage(pairs[1][1], case_name="unreviewed")
    elif problem == "duplicate":
        set_coverage(pairs[1][1], case_name="good")
    else:
        replace_source(pairs[1], "forbidden-generated")
    capsys.readouterr()
    assert main(["check", *arguments(pairs, rubric), "--baseline", str(baseline), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == verdict
    assert baseline.read_bytes() == before
    if problem in {"duplicate", "forbidden"}:
        assert main(["freeze", *arguments(pairs, rubric), "--out", str(baseline)]) == 2
        assert baseline.read_bytes() == before


def test_one_regression_fails_the_whole_suite(suite, capsys):
    pairs, rubric, baseline = suite
    # This separate policy requires both tools and forbids neither. Only synthetic inputs.
    rubric.write_text(json.dumps({"required_tools": ["search", "delete_database"]}))
    replace_source(pairs[1], "forbidden-generated")
    freeze(suite)
    replace_source(pairs[1], "good")
    capsys.readouterr()
    assert main(["check", *arguments(pairs, rubric), "--baseline", str(baseline), "--json"]) == 2
    data = json.loads(capsys.readouterr().out)
    assert data["verdict"] == "REGRESSION"
    assert any("good: PASS" in detail for detail in data["details"])
    assert any("repeated-name: REGRESSION" in detail for detail in data["details"])


@pytest.mark.parametrize("target_kind", ["source", "coverage", "rubric"])
@pytest.mark.parametrize("alias_kind", ["direct", "symlink", "hardlink"])
def test_freeze_protects_every_suite_input(suite, tmp_path, target_kind, alias_kind):
    pairs, rubric, _ = suite
    target = rubric if target_kind == "rubric" else pairs[1][target_kind != "source"]
    if alias_kind != "direct":
        alias = tmp_path / "alias.json"
        if alias_kind == "hardlink":
            alias.hardlink_to(target)
        else:
            alias.symlink_to(target)
        target = alias
    before = target.read_bytes()
    assert main(["freeze", *arguments(pairs, rubric), "--out", str(target)]) == 2
    assert target.read_bytes() == before


def test_repeated_coverage_is_rejected_for_legacy_input(suite, capsys):
    pairs, rubric, _ = suite
    args = arguments(pairs, rubric)
    args.remove("--input-format")
    args.remove("openinference-otlp")
    assert main(["score", *args]) == 2
    assert "--coverage requires OTLP input" in capsys.readouterr().err
