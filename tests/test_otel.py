"""Original synthetic telemetry, not captured user or service data."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tracegate.cli import main
from tracegate.otel import PROFILE, ExportValidationError, load_export
from tracegate.score import Rubric, score_trajectory

TRACE = "0123456789abcdef0123456789ABCDEF"
ROOT = "0123456789ABCDEF"
LLM = "0123456789abcde1"
TOOL = "0123456789abcde2"


def attrs(**values):
    return [{"key": k, "value": {"stringValue": v}} for k, v in values.items()]


def sample():
    root = {
        "traceId": TRACE,
        "spanId": ROOT,
        "startTimeUnixNano": "1",
        "endTimeUnixNano": "900",
        "attributes": attrs(**{"openinference.span.kind": "AGENT"}),
    }
    llm = {
        "traceId": TRACE,
        "spanId": LLM,
        "parentSpanId": ROOT.lower(),
        "startTimeUnixNano": "10",
        "endTimeUnixNano": "100",
        "status": {"code": 0},
        "attributes": attrs(
            **{
                "openinference.span.kind": "LLM",
                "llm.output_messages.0.message.role": "assistant",
                "llm.output_messages.0.message.tool_calls.0.tool_call.id": "call-one",
                "llm.output_messages.0.message.tool_calls.0.tool_call.function.name": "search",
                "llm.output_messages.0.message.tool_calls.0.tool_call.function.arguments": "SECRET",
                "input.value": "SYNTHETIC_SECRET",
                "output.value": "__REDACTED__",
            }
        ),
    }
    tool = {
        "traceId": TRACE,
        "spanId": TOOL,
        "parentSpanId": ROOT,
        "startTimeUnixNano": "110",
        "endTimeUnixNano": "200",
        "status": {"code": 2, "message": "SYNTHETIC_SECRET"},
        "attributes": attrs(
            **{
                "openinference.span.kind": "TOOL",
                "tool.name": "search",
                "tool.id": "call-one",
                "output.value": "SYNTHETIC_SECRET",
            }
        ),
    }
    return {
        "resourceSpans": [
            {
                "resource": {"attributes": attrs(host="SYNTHETIC_SECRET")},
                "scopeSpans": [{"spans": [tool, root, llm]}],
            }
        ]
    }


def spans(data):
    return data["resourceSpans"][0]["scopeSpans"][0]["spans"]


def set_attr(span, key, value):
    span["attributes"] = [a for a in span["attributes"] if a["key"] != key] + attrs(**{key: value})


def files(tmp_path, data=None, coverage=True):
    source = tmp_path / "export.json"
    source.write_text(json.dumps(sample() if data is None else data))
    declaration = tmp_path / "coverage.json"
    declaration.write_text(
        json.dumps(
            {
                "profile": PROFILE,
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "trace_id": TRACE,
                "case_name": "synthetic-case",
                "span_coverage": "complete",
                "tool_call_coverage": "complete",
            }
        )
    )
    return source, declaration if coverage else None


def test_preserves_identity_and_states_without_payload_or_double_count(tmp_path):
    source, coverage = files(tmp_path)
    result = load_export(source, coverage)
    assert result.gate_eligible
    assert result.coverage == "declared_complete"
    assert result.spans[0].trace_id == TRACE
    assert result.spans[1].span_id == ROOT
    assert result.spans[2].parent_span_id == ROOT.lower()
    assert result.spans[0].status == "error"
    assert result.spans[1].status == "unknown"
    assert result.spans[2].status == "unset"
    assert result.spans[2].output_state == "redacted"
    assert result.spans[0].output_state == "omitted"
    assert "SYNTHETIC_SECRET" not in json.dumps(result.to_dict())
    trajectory = result.to_trajectory()
    assert trajectory.tools == ("search",)
    assert trajectory.tool_calls[0].id == "call-one"
    assert len(trajectory.steps) == 1


def test_external_completeness_unknown_without_declaration(tmp_path):
    source, _ = files(tmp_path)
    evidence = load_export(source)
    assert evidence.coverage == "unknown"
    assert not evidence.gate_eligible
    with pytest.raises(ExportValidationError):
        evidence.to_trajectory()


@pytest.mark.parametrize("state", ["incomplete", "unknown"])
def test_incomplete_or_unknown_declaration_cannot_gate(tmp_path, state):
    source, coverage = files(tmp_path)
    data = json.loads(coverage.read_text())
    data["tool_call_coverage"] = state
    coverage.write_text(json.dumps(data))
    assert load_export(source, coverage).coverage == state
    with pytest.raises(ExportValidationError):
        load_export(source, coverage).to_trajectory()


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_sha256", "0" * 64),
        ("trace_id", "a" * 32),
        ("profile", "future"),
        ("case_name", "SYNTHETIC_SECRET\n"),
        ("span_coverage", "probably"),
    ],
)
def test_bad_declaration_fails_closed(tmp_path, field, value):
    source, coverage = files(tmp_path)
    data = json.loads(coverage.read_text())
    data[field] = value
    coverage.write_text(json.dumps(data))
    with pytest.raises(ExportValidationError):
        load_export(source, coverage)


def test_coverage_digest_binds_exact_source_bytes(tmp_path):
    source, coverage = files(tmp_path)
    source.write_text(source.read_text() + "\n")
    with pytest.raises(ExportValidationError, match="hash mismatch"):
        load_export(source, coverage)


@pytest.mark.parametrize(
    "mutation,issue",
    [
        (lambda d: spans(d)[0].pop("endTimeUnixNano"), "incomplete_span_timing"),
        (lambda d: spans(d)[0].update(parentSpanId="f" * 16), "missing_parent_span"),
        (lambda d: spans(d)[0].update(droppedAttributesCount=1), "dropped_telemetry"),
        (lambda d: spans(d)[0].update(events=[{}]), "unsupported_span_events_or_links"),
        (lambda d: set_attr(spans(d)[0], "tool.name", "__REDACTED__"), "redacted_identity"),
        (lambda d: set_attr(spans(d)[1], "openinference.span.kind", "future"), "unknown_span_kind"),
        (
            lambda d: set_attr(spans(d)[2], "gen_ai.tool.name", "hidden"),
            "unsupported_genai_conventions",
        ),
        (
            lambda d: set_attr(spans(d)[2], "llm.function_call", "{}"),
            "unsupported_output_message_representation",
        ),
        (
            lambda d: set_attr(
                spans(d)[2], "llm.output_messages.0.message.contents.0.tool_call.id", "x"
            ),
            "unsupported_output_message_representation",
        ),
        (lambda d: spans(d)[0].update(startTimeUnixNano="99"), "inconsistent_call_timing"),
    ],
)
def test_problem_states_are_preserved_and_refuse_scoring(tmp_path, mutation, issue):
    data = sample()
    mutation(data)
    source, coverage = files(tmp_path, data)
    # Conflicting known/redacted names must not silently reconcile.
    try:
        result = load_export(source, coverage)
    except ExportValidationError:
        assert issue == "redacted_identity"
        return
    assert issue in result.issues
    assert not result.gate_eligible
    with pytest.raises(ExportValidationError):
        result.to_trajectory()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: spans(d).append(copy.deepcopy(spans(d)[0])),
        lambda d: spans(d)[0].update(traceId="invalid"),
        lambda d: spans(d)[0].update(traceId="0" * 32),
        lambda d: spans(d)[0].update(spanId="0" * 16),
        lambda d: spans(d)[0].update(traceId="a" * 32),
        lambda d: spans(d)[0].update(parentSpanId=TOOL),
        lambda d: spans(d)[0].update(startTimeUnixNano="201"),
        lambda d: spans(d)[0].update(startTimeUnixNano=True),
        lambda d: spans(d)[0].update(endTimeUnixNano=str(2**64)),
        lambda d: spans(d)[0].update(status={"code": True}),
        lambda d: spans(d)[0].update(status={"code": "STATUS_CODE_OK"}),
        lambda d: spans(d)[0].update(unknown="SYNTHETIC_SECRET"),
        lambda d: spans(d)[0]["attributes"].append(copy.deepcopy(spans(d)[0]["attributes"][0])),
        lambda d: spans(d)[0]["attributes"][0].update(value={"stringValue": "TOOL", "intValue": 1}),
        lambda d: set_attr(spans(d)[0], "tool.name", "different"),
    ],
)
def test_malformed_exports_fail_without_echo(tmp_path, mutation):
    data = sample()
    mutation(data)
    source, coverage = files(tmp_path, data)
    with pytest.raises(ExportValidationError) as error:
        load_export(source, coverage)
    assert "SYNTHETIC_SECRET" not in str(error.value)


@pytest.mark.parametrize(
    "content",
    [
        '{"resourceSpans":[],"resourceSpans":[]}',
        '{"resourceSpans": NaN}',
        '{"resourceSpans": Infinity}',
        '{"resourceSpans": []}',
        '{"spans": []}',
        "[]",
        "null",
        '{"SECRET_IN_BROKEN_JSON"',
    ],
)
def test_json_errors_fail_without_echo(tmp_path, content):
    path = tmp_path / "source.json"
    path.write_text(content)
    with pytest.raises(ExportValidationError) as error:
        load_export(path)
    assert "SECRET" not in str(error.value)


def test_multiple_generated_calls_preserve_order_repeat_names_and_ids(tmp_path):
    data = sample()
    llm = spans(data)[2]
    for field, value in [("id", "call-two"), ("function.name", "search")]:
        set_attr(llm, f"llm.output_messages.0.message.tool_calls.1.tool_call.{field}", value)
    source, coverage = files(tmp_path, data)
    trajectory = load_export(source, coverage).to_trajectory()
    assert trajectory.tools == ("search", "search")
    assert [c.id for c in trajectory.tool_calls] == ["call-one", "call-two"]
    assert len(trajectory.steps) == 1


def test_generated_unexecuted_forbidden_call_is_counted(tmp_path):
    data = sample()
    spans(data).pop(0)
    set_attr(
        spans(data)[1],
        "llm.output_messages.0.message.tool_calls.0.tool_call.function.name",
        "delete_database",
    )
    source, coverage = files(tmp_path, data)
    trajectory = load_export(source, coverage).to_trajectory()
    report = score_trajectory(trajectory, Rubric(forbidden_tools=("delete_database",)))
    assert not report.policy_ok


def test_input_history_and_advertised_definitions_are_not_calls(tmp_path):
    data = sample()
    set_attr(spans(data)[2], "llm.tools.0.tool.name", "delete_database")
    set_attr(
        spans(data)[2], "llm.input_messages.0.message.tool_calls.0.tool_call.function.name", "old"
    )
    source, coverage = files(tmp_path, data)
    assert load_export(source, coverage).to_trajectory().tools == ("search",)


def test_overlapping_uncorrelated_calls_refuse_order(tmp_path):
    data = sample()
    new = copy.deepcopy(spans(data)[0])
    new.update(spanId="0123456789abcde3", startTimeUnixNano="120", endTimeUnixNano="300")
    set_attr(new, "tool.id", "call-two")
    spans(data).append(new)
    # Existing execution is correlated and not an extra call; overlap with LLM instead.
    new["startTimeUnixNano"] = "50"
    source, coverage = files(tmp_path, data)
    assert "ambiguous_call_order" in load_export(source, coverage).issues


def test_cli_inspection_unknown_returns_two_but_emits_sanitized_evidence(tmp_path, capsys):
    source, _ = files(tmp_path)
    assert main(["inspect-otel", str(source)]) == 2
    output = capsys.readouterr()
    assert "SYNTHETIC_SECRET" not in output.out + output.err
    assert json.loads(output.out)["coverage"] == "unknown"


def test_cli_check_and_freeze_with_complete_coverage(tmp_path, capsys):
    source, coverage = files(tmp_path)
    rubric = tmp_path / "rubric.json"
    rubric.write_text(json.dumps({"required_tools": ["search"], "forbidden_tools": ["delete"]}))
    baseline = tmp_path / "baseline.json"
    flags = [
        str(source),
        "--rubric",
        str(rubric),
        "--input-format",
        "openinference-otlp",
        "--coverage",
        str(coverage),
    ]
    assert main(["freeze", *flags, "--out", str(baseline)]) == 0
    assert main(["check", *flags, "--baseline", str(baseline), "--json"]) == 0
    assert "SYNTHETIC_SECRET" not in capsys.readouterr().out


def test_cli_refusal_does_not_replace_baseline(tmp_path, capsys):
    source, coverage = files(tmp_path)
    rubric = tmp_path / "rubric.json"
    rubric.write_text("{}")
    baseline = tmp_path / "baseline.json"
    baseline.write_text("preserve me")
    for flags in [[], ["--coverage", str(coverage)]]:
        source.write_text(source.read_text() + " ")
        assert (
            main(
                [
                    "freeze",
                    str(source),
                    "--input-format",
                    "openinference-otlp",
                    "--rubric",
                    str(rubric),
                    "--out",
                    str(baseline),
                    *flags,
                ]
            )
            == 2
        )
    assert baseline.read_text() == "preserve me"
    assert not capsys.readouterr().out


def test_diagnostic_artifact_cannot_be_scored_as_trajectory(tmp_path, capsys):
    source, coverage = files(tmp_path)
    diagnostic = tmp_path / "inspection.json"
    rubric = tmp_path / "rubric.json"
    rubric.write_text("{}")
    assert (
        main(["inspect-otel", str(source), "--coverage", str(coverage), "--out", str(diagnostic)])
        == 0
    )
    assert main(["score", str(diagnostic), "--rubric", str(rubric)]) == 2
    assert "INVALID_TRAJECTORY" in capsys.readouterr().err


def test_inspection_never_replaces_its_inputs(tmp_path):
    source, coverage = files(tmp_path)
    original = source.read_bytes()
    assert main(["inspect-otel", str(source), "--out", str(source)]) == 2
    assert source.read_bytes() == original
    assert (
        main(["inspect-otel", str(source), "--coverage", str(coverage), "--out", str(coverage)])
        == 2
    )


def test_public_fixture_export_is_original_and_hash_bound():
    root = Path(__file__).resolve().parents[1] / "examples" / "otel"
    for name in ("support", "forbidden"):
        evidence = load_export(root / f"{name}.json", root / f"{name}-coverage.json")
        assert evidence.gate_eligible


def test_unsupported_nested_output_container_cannot_hide_forbidden_call(tmp_path):
    data = sample()
    spans(data)[2]["attributes"].append(
        {
            "key": "llm.output_messages.1.message",
            "value": {
                "kvlistValue": {
                    "values": attrs(
                        **{
                            "message.role": "assistant",
                            "message.function_call_name": "delete_database",
                        }
                    )
                }
            },
        }
    )
    source, coverage = files(tmp_path, data)
    evidence = load_export(source, coverage)
    assert "unsupported_output_message_representation" in evidence.issues
    with pytest.raises(ExportValidationError):
        evidence.to_trajectory()


def test_cli_rejects_message_step_bounds_on_call_projection(tmp_path, capsys):
    source, coverage = files(tmp_path)
    rubric = tmp_path / "rubric.json"
    rubric.write_text('{"max_steps": 1}')
    assert (
        main(
            [
                "score",
                str(source),
                "--rubric",
                str(rubric),
                "--input-format",
                "openinference-otlp",
                "--coverage",
                str(coverage),
            ]
        )
        == 2
    )
    assert not capsys.readouterr().out


def test_missing_output_message_index_refuses_scoring(tmp_path):
    data = sample()
    for attr in spans(data)[2]["attributes"]:
        attr["key"] = attr["key"].replace("llm.output_messages.0", "llm.output_messages.1")
    source, coverage = files(tmp_path, data)
    evidence = load_export(source, coverage)
    assert "incomplete_output_message_indexes" in evidence.issues
    assert not evidence.gate_eligible


def test_redacted_name_retains_state_in_diagnostic(tmp_path):
    data = sample()
    set_attr(spans(data)[0], "tool.name", "__REDACTED__")
    source, coverage = files(tmp_path, data)
    evidence = load_export(source, coverage)
    assert evidence.spans[0].calls[0].name_state == "redacted"
    assert evidence.spans[0].calls[0].name is None
    assert not evidence.gate_eligible


def test_message_payload_redaction_is_preserved_without_content(tmp_path):
    data = sample()
    set_attr(spans(data)[2], "llm.output_messages.0.message.content", "__REDACTED__")
    source, coverage = files(tmp_path, data)
    assert load_export(source, coverage).spans[2].output_message_states == {0: "redacted"}


@pytest.mark.parametrize(
    "value",
    [
        {"arrayValue": {"values": [], "unknown": "SECRET"}},
        {"kvlistValue": {"values": [], "unknown": "SECRET"}},
        {"bytesValue": "not valid base64!"},
        {"doubleValue": float("inf")},
        {"boolValue": 1},
        {"intValue": True},
        {"intValue": str(2**63)},
    ],
)
def test_malformed_anyvalue_refuses(tmp_path, value):
    data = sample()
    spans(data)[2]["attributes"].append({"key": "metadata", "value": value})
    source, coverage = files(tmp_path, data)
    with pytest.raises(ExportValidationError):
        load_export(source, coverage)


def test_duplicate_generated_ids_refuse(tmp_path):
    data = sample()
    set_attr(spans(data)[2], "llm.output_messages.0.message.tool_calls.1.tool_call.id", "call-one")
    set_attr(
        spans(data)[2],
        "llm.output_messages.0.message.tool_calls.1.tool_call.function.name",
        "search",
    )
    source, coverage = files(tmp_path, data)
    with pytest.raises(ExportValidationError, match="duplicate call ID"):
        load_export(source, coverage)


def test_duplicate_execution_ids_refuse(tmp_path):
    data = sample()
    extra = copy.deepcopy(spans(data)[0])
    extra["spanId"] = "abcd0123456789ef"
    spans(data).append(extra)
    source, coverage = files(tmp_path, data)
    with pytest.raises(ExportValidationError, match="duplicate call ID"):
        load_export(source, coverage)


def test_missing_call_id_is_unknown_not_generated(tmp_path):
    data = sample()
    spans(data).pop(0)
    spans(data)[1]["attributes"] = [
        a for a in spans(data)[1]["attributes"] if not a["key"].endswith("tool_call.id")
    ]
    source, coverage = files(tmp_path, data)
    evidence = load_export(source, coverage)
    assert evidence.spans[1].calls[0].call_id is None
    assert evidence.spans[1].calls[0].id_state == "unknown"
    assert "unknown_call_id" in evidence.issues
    assert not evidence.gate_eligible


def test_no_observed_calls_refuses_even_declared_complete(tmp_path):
    data = sample()
    spans(data)[:] = [spans(data)[1]]
    source, coverage = files(tmp_path, data)
    assert "no_observed_calls" in load_export(source, coverage).issues


def test_tool_only_span_is_a_recorded_attempt(tmp_path):
    data = sample()
    spans(data).pop(2)
    source, coverage = files(tmp_path, data)
    assert load_export(source, coverage).to_trajectory().tools == ("search",)


@pytest.mark.parametrize("target_input", ["source", "coverage"])
def test_inspection_hardlink_output_cannot_overwrite_inputs(tmp_path, target_input):
    source, coverage = files(tmp_path)
    target = source if target_input == "source" else coverage
    before = target.read_bytes()
    alias = tmp_path / "alias.json"
    alias.hardlink_to(target)
    assert (
        main(["inspect-otel", str(source), "--coverage", str(coverage), "--out", str(alias)]) == 2
    )
    assert target.read_bytes() == before


def test_diagnostic_retains_coverage_file_digest(tmp_path):
    source, coverage = files(tmp_path)
    result = load_export(source, coverage)
    assert result.to_dict()["coverage_sha256"] == hashlib.sha256(coverage.read_bytes()).hexdigest()
    assert load_export(source).to_dict()["coverage_sha256"] is None


@pytest.mark.parametrize(
    "key",
    [
        "llm.function_call.name", "llm.function_call.arguments",
        "tool_call.function.name", "tool_call",
    ],
)
def test_mixed_unsupported_call_attributes_block_scoring(tmp_path, key):
    data = sample()
    set_attr(spans(data)[2], key, "SYNTHETIC_SECRET_FORBIDDEN_CALL")
    evidence = load_export(*files(tmp_path, data))
    assert "unsupported_output_message_representation" in evidence.issues
    assert not evidence.gate_eligible
    assert "SYNTHETIC_SECRET" not in json.dumps(evidence.to_dict())
    with pytest.raises(ExportValidationError):
        evidence.to_trajectory()


@pytest.mark.parametrize("character", ["\u0085", "\u009b", "\u202e", "\ud800"])
@pytest.mark.parametrize("field", ["tool.name", "tool.id"])
def test_control_format_and_surrogate_identities_are_refused(tmp_path, character, field):
    data = sample()
    set_attr(spans(data)[0], field, "synthetic" + character)
    with pytest.raises(ExportValidationError, match="unsupported tool name or call ID"):
        load_export(*files(tmp_path, data))


@pytest.mark.parametrize("target_input", ["source", "coverage", "rubric"])
@pytest.mark.parametrize("alias", ["direct", "symlink", "hardlink"])
def test_freeze_never_replaces_otlp_inputs(tmp_path, target_input, alias):
    source, coverage = files(tmp_path)
    rubric = tmp_path / "rubric.json"
    rubric.write_text("{}")
    targets = {"source": source, "coverage": coverage, "rubric": rubric}
    target = targets[target_input]
    before = {key: path.read_bytes() for key, path in targets.items()}
    output = target
    if alias != "direct":
        output = tmp_path / "alias.json"
        if alias == "symlink":
            output.symlink_to(target)
        else:
            output.hardlink_to(target)
    assert main([
        "freeze", str(source), "--input-format", "openinference-otlp",
        "--coverage", str(coverage), "--rubric", str(rubric), "--out", str(output),
    ]) == 2
    assert {key: path.read_bytes() for key, path in targets.items()} == before


@pytest.mark.parametrize("target_input", ["source", "rubric"])
def test_freeze_never_replaces_legacy_inputs(tmp_path, target_input):
    source = tmp_path / "trajectory.json"
    source.write_text('{"name": "synthetic", "steps": [{"tool": "search"}]}')
    rubric = tmp_path / "rubric.json"
    rubric.write_text("{}")
    target = source if target_input == "source" else rubric
    before = target.read_bytes()
    assert main(["freeze", str(source), "--rubric", str(rubric), "--out", str(target)]) == 2
    assert target.read_bytes() == before


@pytest.mark.parametrize(
    "rubric_json",
    ['{"forbidden_tools": ["search"], "forbidden_tools": []}', '{"ignored": 1e999}'],
)
def test_otlp_cli_strict_rubric_loading(tmp_path, capsys, rubric_json):
    source, coverage = files(tmp_path)
    rubric = tmp_path / "rubric.json"
    rubric.write_text(rubric_json)
    assert main([
        "score", str(source), "--input-format", "openinference-otlp",
        "--coverage", str(coverage), "--rubric", str(rubric),
    ]) == 2
    result = capsys.readouterr()
    assert not result.out
    assert "INVALID_RUBRIC" in result.err
