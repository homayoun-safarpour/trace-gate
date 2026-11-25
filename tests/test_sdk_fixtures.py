"""Read recorded SDK output; Node is exercised only by the optional integration run."""
import hashlib
import json
from pathlib import Path

import pytest

from tracegate.baseline import check_against_baseline, freeze_baseline
from tracegate.otel import ExportValidationError, load_export
from tracegate.score import Rubric, score_trajectory

FIXTURES = Path(__file__).resolve().parents[1] / "integrations/opentelemetry-js/fixtures"
PROVENANCE = json.loads((FIXTURES / "provenance.json").read_text())
RUBRIC = Rubric(required_tools=("search",), forbidden_tools=("delete_database",))


def evidence(tmp_path, name):
    source = FIXTURES / f"{name}.json"
    declaration = tmp_path / f"{name}-coverage.json"
    declaration.write_text(json.dumps({
        "profile": "openinference-otlp-v1",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "trace_id": "1" * 32, "case_name": "sdk-synthetic",
        "span_coverage": "complete", "tool_call_coverage": "complete",
    }))
    return load_export(source, declaration)


@pytest.mark.parametrize("name", PROVENANCE["fixtures"])
def test_recorded_sdk_fixture_matches_generation_hash(name):
    actual = hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()
    assert actual == PROVENANCE["fixtures"][name]


def test_real_serializer_output_preserves_failed_execution_and_minimizes_payloads(tmp_path):
    result = evidence(tmp_path, "good")
    assert result.gate_eligible
    assert len(result.spans) == 3
    assert any(s.status == "error" for s in result.spans)
    assert result.to_trajectory().tools == ("search",)
    assert "SYNTHETIC_PAYLOAD" not in json.dumps(result.to_dict())
    report = score_trajectory(result.to_trajectory(), RUBRIC)
    baseline = freeze_baseline([report], rubric=RUBRIC)
    assert check_against_baseline([report], baseline, rubric=RUBRIC).ok


def test_real_sdk_generated_forbidden_call_is_not_hidden_by_absent_execution(tmp_path):
    result = evidence(tmp_path, "forbidden-generated")
    assert result.gate_eligible
    assert result.to_trajectory().tools == ("search", "delete_database")
    report = score_trajectory(result.to_trajectory(), RUBRIC)
    with pytest.raises(ValueError, match="POLICY_VIOLATION"):
        freeze_baseline([report], rubric=RUBRIC)


def test_real_sdk_repeated_tool_names_retain_distinct_ids(tmp_path):
    trace = evidence(tmp_path, "repeated-name").to_trajectory()
    assert trace.tools == ("search", "search")
    assert [c.id for c in trace.tool_calls] == ["call-one", "call-two"]


@pytest.mark.parametrize("name,issue", [
    ("events", "unsupported_span_events_or_links"),
    ("dropped-attributes", "dropped_telemetry"),
    ("missing-call-id", "unknown_call_id"),
])
def test_real_sdk_unsupported_evidence_refuses_scoring(tmp_path, name, issue):
    result = evidence(tmp_path, name)
    assert issue in result.issues
    assert not result.gate_eligible
    with pytest.raises(ExportValidationError):
        result.to_trajectory()


def test_sdk_fixture_still_needs_explicit_coverage():
    result = load_export(FIXTURES / "good.json")
    assert result.coverage == "unknown"
    assert not result.gate_eligible
