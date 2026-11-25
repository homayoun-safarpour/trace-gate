"""Offline, deliberately narrow OTLP JSON/OpenInference evidence adapter.

No SDK, collector, network calls, or telemetry payload values are emitted.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tracegate.trajectory import Step, ToolCall, Trajectory, TrajectoryValidationError

PROFILE = "openinference-otlp-v1"
MAX_BYTES = 16 * 1024 * 1024
MAX_ITEMS = 10000
MAX_UINT64 = 2**64 - 1
MAX_INTEGER_DIGITS = 20
MAX_LABEL_LENGTH = 256
MAX_INDEX_DIGITS = 4
REDACTED = "__REDACTED__"
KINDS = {
    "AGENT",
    "CHAIN",
    "LLM",
    "TOOL",
    "RETRIEVER",
    "RERANKER",
    "EMBEDDING",
    "GUARDRAIL",
    "EVALUATOR",
    "PROMPT",
    "DECISION",
}
CALL = re.compile(
    r"llm\.output_messages\.(0|[1-9][0-9]*)\.message\.tool_calls\."
    r"(0|[1-9][0-9]*)\.tool_call\.(id|function\.name|function\.arguments|reasoning_signature)"
)
MESSAGE = re.compile(
    r"llm\.output_messages\.(0|[1-9][0-9]*)\.message\.(role|content|name|tool_call_id)"
)


class ExportValidationError(TrajectoryValidationError):
    """Static messages never interpolate untrusted payloads, paths, or IDs."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExportValidationError(message)


def _object(value: Any) -> dict:
    _require(isinstance(value, dict), "expected an object")
    return value


def _list(value: Any) -> list:
    _require(isinstance(value, list) and len(value) <= MAX_ITEMS, "invalid or oversized list")
    return value


def _string(value: Any) -> str:
    _require(isinstance(value, str) and bool(value.strip()), "expected a non-empty string")
    return value


def _identity(value: Any, length: int) -> str:
    _require(
        isinstance(value, str) and bool(re.fullmatch(rf"[0-9a-fA-F]{{{length}}}", value)),
        "invalid trace or span ID",
    )
    _require(int(value, 16) != 0, "zero trace or span ID")
    return value  # Preserve original spelling; compare IDs case-insensitively.


def _uint(value: Any) -> int:
    valid = type(value) is int or (isinstance(value, str) and bool(re.fullmatch(r"[0-9]+", value)))
    _require(valid, "invalid unsigned integer")
    _require(len(str(value)) <= MAX_INTEGER_DIGITS, "unsigned integer out of range")
    number = int(value)
    _require(0 <= number <= MAX_UINT64, "unsigned integer out of range")
    return number


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, "duplicate JSON object key")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise ExportValidationError("non-finite JSON number")


def _read(path: str | Path) -> tuple[Any, str]:
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        _require(len(raw) <= MAX_BYTES, "export exceeds size limit")
        data = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, ExportValidationError):
            raise
        raise ExportValidationError("cannot read supported JSON evidence") from None
    return data, hashlib.sha256(raw).hexdigest()


def _any_value(raw: Any) -> Any:  # noqa: PLR0911 - OTLP tagged union
    value = _object(raw)
    _require(len(value) == 1, "invalid OTLP AnyValue")
    kind, item = next(iter(value.items()))
    if kind == "stringValue":
        _require(isinstance(item, str), "invalid OTLP stringValue")
        return item
    if kind == "boolValue":
        _require(type(item) is bool, "invalid OTLP boolValue")
        return item
    if kind == "intValue":
        _require(
            type(item) is int or (isinstance(item, str) and bool(re.fullmatch(r"-?[0-9]+", item))),
            "invalid OTLP intValue",
        )
        _require(
            len(str(item)) <= MAX_INTEGER_DIGITS and -(2**63) <= int(item) < 2**63,
            "OTLP intValue out of range",
        )
        return int(item)
    if kind == "doubleValue":
        _require(type(item) in {int, float} and math.isfinite(item), "invalid OTLP doubleValue")
        return item
    if kind == "arrayValue":
        _require(set(_object(item)) <= {"values"}, "unsupported OTLP array fields")
        return [_any_value(v) for v in _list(item.get("values", []))]
    if kind == "kvlistValue":
        _require(set(_object(item)) <= {"values"}, "unsupported OTLP key-value list fields")
        return _attributes(item.get("values", []))
    if kind == "bytesValue":
        _require(isinstance(item, str), "invalid OTLP bytesValue")
        try:
            base64.b64decode(item, validate=True)
        except (binascii.Error, ValueError):
            raise ExportValidationError("invalid OTLP bytesValue") from None
        return {"opaque_bytes": True}
    raise ExportValidationError("unsupported OTLP AnyValue")


def _attributes(raw: Any) -> dict:
    result = {}
    for raw_pair in _list(raw):
        pair = _object(raw_pair)
        _require(set(pair) == {"key", "value"}, "invalid OTLP attribute entry")
        key = _string(pair["key"])
        _require(key not in result, "duplicate OTLP attribute key")
        result[key] = _any_value(pair["value"])
    return result


def _state(value: Any) -> str:
    if value is None:
        return "unknown"
    return "redacted" if value == REDACTED else "omitted"


def _label_state(value: Any) -> str:
    return "known" if _state(value) == "omitted" else _state(value)


def _optional_label(value: Any, issues: set[str], missing: str) -> str | None:
    if value is None:
        issues.add(missing)
        return None
    label = _string(value)
    if label == REDACTED:
        issues.add("redacted_identity")
        return None
    # Names and call IDs must remain exact for policy matching. No guessing/scrubbing.
    _require(
        len(label) <= MAX_LABEL_LENGTH
        and not any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in label),
        "unsupported tool name or call ID",
    )
    return label


@dataclass
class CallEvidence:
    name: str | None
    call_id: str | None
    span_id: str
    representation: str
    message_index: int | None = None
    call_index: int | None = None
    arguments_state: str = "unknown"
    name_state: str = "unknown"
    id_state: str = "unknown"


@dataclass
class SpanEvidence:
    trace_id: str
    span_id: str
    parent_span_id: str | None
    start_ns: int | None
    end_ns: int | None
    kind: str | None
    status: str
    input_state: str
    output_state: str
    calls: list[CallEvidence] = field(default_factory=list)
    output_message_states: dict[int, str] = field(default_factory=dict)


@dataclass
class ExportEvidence:
    source_sha256: str
    spans: list[SpanEvidence]
    issues: set[str]
    coverage: str = "unknown"
    case_name: str | None = None
    coverage_sha256: str | None = None

    @property
    def gate_eligible(self) -> bool:
        return self.coverage == "declared_complete" and not self.issues

    def to_dict(self) -> dict:
        return {
            "format": "trace-gate.otel-evidence.v1",
            "profile": PROFILE,
            "source_sha256": self.source_sha256,
            "coverage_sha256": self.coverage_sha256,
            "coverage": self.coverage,
            "case_name": self.case_name,
            "gate_eligible": self.gate_eligible,
            "issues": sorted(self.issues),
            "spans": [asdict(span) for span in self.spans],
        }

    def to_trajectory(self) -> Trajectory:
        _require(
            self.gate_eligible, "OTLP evidence is not eligible for scoring; inspect its states"
        )
        groups = _call_groups(self.spans, self.issues)
        _require(not self.issues, "OTLP evidence has unresolved call identities or ordering")
        return Trajectory(
            name=self.case_name,
            steps=tuple(
                Step(role="assistant", tool_calls=tuple(ToolCall(c.name, c.call_id) for c in calls))
                for _, _, calls in groups
            ),
        )


def _status(raw: Any) -> str:
    status = _object(raw)
    _require(set(status) <= {"code", "message"}, "unsupported span status fields")
    if "message" in status:
        _require(isinstance(status["message"], str), "invalid status message")
    code = status.get("code", 0)
    _require(type(code) is int and code in {0, 1, 2}, "unsupported span status code")
    return {0: "unset", 1: "ok", 2: "error"}[code]


def _generated_calls(attrs: dict, span_id: str, issues: set[str]) -> list[CallEvidence]:
    groups: dict[tuple[int, int], dict] = {}
    message_indexes: set[int] = set()
    for key, value in attrs.items():
        match = CALL.fullmatch(key)
        if match:
            message, call = int(match[1]), int(match[2])
            _require(message < MAX_ITEMS and call < MAX_ITEMS, "tool call index out of range")
            _require(isinstance(value, str), "invalid tool call attribute type")
            groups.setdefault((message, call), {})[match[3]] = value
            message_indexes.add(message)
        elif key.startswith("llm.output_messages"):
            message_match = MESSAGE.fullmatch(key)
            if message_match:
                _require(
                    len(message_match[1]) <= MAX_INDEX_DIGITS and int(message_match[1]) < MAX_ITEMS,
                    "output message index out of range",
                )
                _require(isinstance(value, str), "invalid output message attribute type")
                message_indexes.add(int(message_match[1]))
            else:
                issues.add("unsupported_output_message_representation")
        elif (
            key == "llm.function_call"
            or key.startswith("llm.function_call.")
            or key == "tool_call"
            or key.startswith("tool_call.")
        ):
            issues.add("unsupported_output_message_representation")
        elif key.startswith("gen_ai."):
            issues.add("unsupported_genai_conventions")
    if sorted(message_indexes) != list(range(len(message_indexes))):
        issues.add("incomplete_output_message_indexes")
    calls = []
    for (message, call), values in sorted(groups.items()):
        role = attrs.get(f"llm.output_messages.{message}.message.role")
        if role != "assistant":
            issues.add("unknown_output_message_role")
        name = values.get("function.name")
        call_id = values.get("id")
        calls.append(
            CallEvidence(
                _optional_label(name, issues, "unknown_tool_name"),
                _optional_label(call_id, issues, "unknown_call_id"),
                span_id,
                "generated",
                message,
                call,
                _state(values.get("function.arguments")),
                _label_state(name),
                _label_state(call_id),
            )
        )
    for message in {m for m, _ in groups}:
        indexes = sorted(c for m, c in groups if m == message)
        if indexes != list(range(len(indexes))):
            issues.add("incomplete_call_indexes")
    return calls


def _span(raw: Any, issues: set[str]) -> SpanEvidence:  # noqa: PLR0912 - schema validation
    span = _object(raw)
    allowed = {
        "traceId",
        "spanId",
        "parentSpanId",
        "traceState",
        "flags",
        "name",
        "kind",
        "startTimeUnixNano",
        "endTimeUnixNano",
        "attributes",
        "droppedAttributesCount",
        "events",
        "droppedEventsCount",
        "links",
        "droppedLinksCount",
        "status",
    }
    _require(set(span) <= allowed, "unsupported span field")
    trace_id = _identity(span.get("traceId"), 32)
    span_id = _identity(span.get("spanId"), 16)
    parent = span.get("parentSpanId")
    if parent == "":
        parent = None
    if parent is not None:
        parent = _identity(parent, 16)
    for key in ("name", "traceState"):
        if key in span:
            _require(isinstance(span[key], str), "invalid span text metadata")
    if "kind" in span:
        _require(type(span["kind"]) is int and span["kind"] in range(6), "invalid OTLP span kind")
    if "flags" in span:
        _require(type(span["flags"]) is int and 0 <= span["flags"] < 2**32, "invalid span flags")
    for key in ("droppedAttributesCount", "droppedEventsCount", "droppedLinksCount"):
        count = span.get(key, 0)
        _require(type(count) is int and 0 <= count < 2**32, "invalid dropped item count")
        if count:
            issues.add("dropped_telemetry")
    for key in ("events", "links"):
        if _list(span.get(key, [])):
            issues.add("unsupported_span_events_or_links")
    start = _uint(span["startTimeUnixNano"]) if "startTimeUnixNano" in span else None
    end = _uint(span["endTimeUnixNano"]) if "endTimeUnixNano" in span else None
    if start is None or end is None or start == 0 or end == 0:
        issues.add("incomplete_span_timing")
    if start is not None and end is not None:
        _require(end >= start, "span ends before it starts")
    attrs = _attributes(span.get("attributes", []))
    for key in ("input.value", "output.value"):
        if key in attrs:
            _require(isinstance(attrs[key], str), "invalid OpenInference payload type")
    kind = attrs.get("openinference.span.kind")
    if kind is not None:
        _string(kind)
    if kind not in KINDS:
        issues.add("unknown_span_kind")
        kind = None  # Do not echo arbitrary metadata.
    calls = _generated_calls(attrs, span_id, issues)
    if calls and kind != "LLM":
        issues.add("unexpected_call_location")
    if kind == "TOOL":
        name, call_id = attrs.get("tool.name"), attrs.get("tool.id")
        calls.append(
            CallEvidence(
                _optional_label(name, issues, "unknown_tool_name"),
                _optional_label(call_id, issues, "unknown_call_id"),
                span_id,
                "execution",
                arguments_state=_state(attrs.get("input.value")),
                name_state=_label_state(name),
                id_state=_label_state(call_id),
            )
        )
    elif "tool.name" in attrs or "tool.id" in attrs:
        issues.add("unexpected_call_location")
    return SpanEvidence(
        trace_id,
        span_id,
        parent,
        start,
        end,
        kind,
        _status(span["status"]) if "status" in span else "unknown",
        _state(attrs.get("input.value")),
        _state(attrs.get("output.value")),
        calls,
        {
            int(match[1]): _state(value)
            for key, value in attrs.items()
            if (match := MESSAGE.fullmatch(key)) and match[2] == "content"
        },
    )


def _container(raw: Any, allowed: set[str], issues: set[str]) -> dict:
    value = _object(raw)
    _require(set(value) <= allowed, "unsupported OTLP container field")
    for key in ("name", "version", "schemaUrl"):
        if key in value:
            _require(isinstance(value[key], str), "invalid OTLP container metadata")
    if "attributes" in value:
        _attributes(value["attributes"])
    count = value.get("droppedAttributesCount", 0)
    _require(type(count) is int and 0 <= count < 2**32, "invalid dropped attribute count")
    if count:
        issues.add("dropped_telemetry")
    return value


def _spans(data: Any, issues: set[str]) -> list[SpanEvidence]:
    root = _container(data, {"resourceSpans"}, issues)
    _require("resourceSpans" in root, "expected OTLP resourceSpans envelope")
    spans = []
    for raw_resource in _list(root["resourceSpans"]):
        resource = _container(raw_resource, {"resource", "scopeSpans", "schemaUrl"}, issues)
        if "resource" in resource:
            _container(resource["resource"], {"attributes", "droppedAttributesCount"}, issues)
        for raw_scope in _list(resource.get("scopeSpans", [])):
            scope = _container(raw_scope, {"scope", "spans", "schemaUrl"}, issues)
            if "scope" in scope:
                _container(
                    scope["scope"],
                    {"name", "version", "attributes", "droppedAttributesCount"},
                    issues,
                )
            spans.extend(_span(raw, issues) for raw in _list(scope.get("spans", [])))
            _require(len(spans) <= MAX_ITEMS, "too many spans")
    _require(bool(spans), "empty OTLP span export")
    _require(len({s.trace_id.lower() for s in spans}) == 1, "multiple traces are unsupported")
    return spans


def _topology(spans: list[SpanEvidence], issues: set[str]) -> None:
    # Normalize each parent edge once, then finish each path only once. Walking
    # all ancestors separately for every span is quadratic on deep traces.
    parents: dict[str, str | None] = {}
    for span in spans:
        parent = span.parent_span_id
        parents[span.span_id.lower()] = parent.lower() if parent is not None else None
    _require(len(parents) == len(spans), "duplicate span ID")
    if sum(parent is None for parent in parents.values()) != 1:
        issues.add("incomplete_trace_roots")
    finished: set[str] = set()
    for start in parents:
        path: set[str] = set()
        current = start
        while current is not None and current not in finished:
            _require(current not in path, "cyclic span parents")
            if current not in parents:
                issues.add("missing_parent_span")
                break
            path.add(current)
            current = parents[current]
        finished.update(path)


def _call_groups(spans: list[SpanEvidence], issues: set[str]) -> list:  # noqa: PLR0912
    generated: dict[str, CallEvidence] = {}
    executed: dict[str, CallEvidence] = {}
    grouped: dict[tuple[str, int | None], list[CallEvidence]] = {}
    lookup = {s.span_id.lower(): s for s in spans}
    for span in spans:
        for call in span.calls:
            if call.call_id is None:
                continue
            target = generated if call.representation == "generated" else executed
            _require(call.call_id not in target, "duplicate call ID in one representation")
            target[call.call_id] = call
    for call_id, call in executed.items():
        if call_id in generated:
            if call.name is not None and generated[call_id].name is not None:
                _require(call.name == generated[call_id].name, "conflicting call ID names")
            gen_span = lookup[generated[call_id].span_id.lower()]
            tool_span = lookup[call.span_id.lower()]
            if (
                gen_span.end_ns is not None
                and tool_span.start_ns is not None
                and tool_span.start_ns < gen_span.end_ns
            ):
                issues.add("inconsistent_call_timing")
    for span in spans:
        for call in span.calls:
            if call.representation == "execution" and call.call_id in generated:
                continue  # One attempt, two observations, both preserved in evidence.
            grouped.setdefault((span.span_id, call.message_index), []).append(call)
    groups = [(lookup[sid.lower()], index, calls) for (sid, index), calls in grouped.items()]
    groups.sort(key=lambda g: (g[0].start_ns or 0, g[0].span_id.lower(), g[1] or 0))
    for previous, current in zip(groups, groups[1:], strict=False):
        left, right = previous[0], current[0]
        if left.span_id != right.span_id and (
            left.end_ns is None
            or right.start_ns is None
            or left.end_ns > right.start_ns
            or left.start_ns == right.start_ns
        ):
            issues.add("ambiguous_call_order")
    if not groups:
        issues.add("no_observed_calls")
    return groups


def _coverage(evidence: ExportEvidence, path: str | Path) -> None:
    data, coverage_hash = _read(path)
    data = _object(data)
    _require(
        set(data)
        == {
            "profile",
            "source_sha256",
            "trace_id",
            "case_name",
            "span_coverage",
            "tool_call_coverage",
        },
        "invalid coverage declaration",
    )
    _require(data["profile"] == PROFILE, "unsupported coverage profile")
    _require(data["source_sha256"] == evidence.source_sha256, "coverage source hash mismatch")
    _require(data["trace_id"] == evidence.spans[0].trace_id, "coverage trace ID mismatch")
    _require(
        data["span_coverage"] in {"complete", "incomplete", "unknown"}
        and data["tool_call_coverage"] in {"complete", "incomplete", "unknown"},
        "invalid coverage state",
    )
    name = _string(data["case_name"])
    _require(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name)), "unsupported case name")
    evidence.case_name = name
    evidence.coverage_sha256 = coverage_hash
    states = {data["span_coverage"], data["tool_call_coverage"]}
    evidence.coverage = (
        "declared_complete"
        if states == {"complete"}
        else "incomplete"
        if "incomplete" in states
        else "unknown"
    )


def load_export(path: str | Path, coverage_path: str | Path | None = None) -> ExportEvidence:
    """Read one trace. Declaration means caller attestation, never exporter verification."""
    data, source_hash = _read(path)
    try:
        issues: set[str] = set()
        spans = _spans(data, issues)
        _topology(spans, issues)
        _call_groups(spans, issues)
        evidence = ExportEvidence(source_hash, spans, issues)
        if coverage_path is not None:
            _coverage(evidence, coverage_path)
        return evidence
    except (RecursionError, TypeError, ValueError, OverflowError) as exc:
        if isinstance(exc, ExportValidationError):
            raise
        raise ExportValidationError("malformed or unsupported OTLP evidence") from None
