# Private offline OpenInference / OTLP adapter

This candidate adds an **offline reader for a narrow JSON export profile**.
It does not run an exporter, install instrumentation, contact a collector, or
execute tools. It adds no runtime dependencies. It retains the completed
Promptfoo integration unchanged.

## Try the original synthetic fixtures

```bash
# Emits a sanitized diagnostic, but returns 2: coverage is unknown by default.
trace-gate inspect-otel examples/otel/support.json

# The supplied declaration is valid only for this synthetic fixture's exact bytes.
trace-gate inspect-otel examples/otel/support.json \
  --coverage examples/otel/support-coverage.json --out inspection.json

trace-gate freeze examples/otel/support.json \
  --input-format openinference-otlp --coverage examples/otel/support-coverage.json \
  --rubric examples/otel/rubric.json --out /tmp/otel-baseline.json
trace-gate check examples/otel/support.json \
  --input-format openinference-otlp --coverage examples/otel/support-coverage.json \
  --rubric examples/otel/rubric.json --baseline /tmp/otel-baseline.json

# Returns 2 / POLICY_VIOLATION, including an unexecuted generated forbidden call.
trace-gate check examples/otel/forbidden.json \
  --input-format openinference-otlp --coverage examples/otel/forbidden-coverage.json \
  --rubric examples/otel/rubric.json --baseline /tmp/otel-baseline.json
```

`inspect-otel` returns 0 only when evidence is eligible for this profile's scoring.
That is **not a policy verdict**: a forbidden-call export can be eligible.
It returns 2 for unknown/incomplete coverage, unsupported evidence, or malformed
input. For structurally readable but ineligible evidence it still emits a useful
diagnostic with states/issues. Malformed input emits only a fixed error, without
partial scores or a diagnostic file. A diagnostic is not a trajectory and cannot
be accidentally fed to the legacy trajectory loader. Inspection output cannot
replace its source or declaration, including through hardlink aliases. Baseline
freeze also refuses outputs aliasing any source, coverage declaration or rubric,
for both OTLP and legacy input formats.

`score` remains diagnostic and can return 0 for a policy violation; use `check`
to enforce the hard forbidden-tool gate. `freeze` never writes a new baseline
from ineligible or policy-violating evidence. Existing baseline, parser, hard
policy, fingerprint and complete-case checks remain unchanged.

## Gate a suite of exports

A single baseline can cover several OTLP test cases. Supply all export paths
first, then repeat `--coverage` once per file in the same order:

```bash
trace-gate freeze case-a.json case-b.json \
  --input-format openinference-otlp \
  --coverage case-a-coverage.json --coverage case-b-coverage.json \
  --rubric rubric.json --out baseline.json

trace-gate check case-a.json case-b.json \
  --input-format openinference-otlp \
  --coverage case-a-coverage.json --coverage case-b-coverage.json \
  --rubric rubric.json --baseline baseline.json
```

These are project-local filenames, not bundled production attestations. Review
each export and its coverage declaration as described below. Each file still
contains one trace, each declaration binds that file's exact bytes, and its
stable `case_name` identifies the test case. All cases use the same rubric.
Reorder export/declaration pairs together; a mismatched declaration fails its
source hash check. Missing or extra declarations are refused, never broadcast,
guessed or silently ignored. `inspect-otel` remains a one-file diagnostic.

`score` prints the full set of diagnostics only after every export is eligible.
`freeze` validates the whole suite before replacing the baseline, and refuses
outputs aliasing any export, declaration or rubric. `check` requires every
baseline case exactly once: one omitted, unknown, duplicate, forbidden or
regressing case refuses the whole check. A valid case cannot hide another
case's failure. Existing one-file commands are unchanged.

This does not combine multiple traces within a file, merge trace identities,
accept partial suites, infer completeness or add new OpenInference conventions.
Per-file size/span limits remain in effect; callers should bound suite size
and use normal CI process limits for large batches.

## Supported profile

- One trace per file in a camelCase OTLP JSON `resourceSpans` envelope, containing
  `scopeSpans` and `spans`. Explicit `--input-format openinference-otlp` prevents
  format guessing. Batch exports with multiple trace IDs are refused.
- Nonzero 32-hex trace IDs and 16-hex span/parent IDs. Original letter case is
  preserved, while identity comparisons are case-insensitive for OTLP hex IDs.
  Arbitrary provider call IDs are exact, case-sensitive strings. No ID is invented.
- Flattened OpenInference generated calls under
  `llm.output_messages.N.message.tool_calls.M.tool_call.{id,function.name,...}`
  and `TOOL` spans with `tool.name` and `tool.id`.
- Generated and execution observations with the same call ID/name represent one
  recorded attempt; **both original span records remain in the diagnostic**.
  Duplicate generated IDs or execution IDs, conflicting names, invalid IDs and
  cyclic parents are errors. Unicode control, formatting and surrogate characters
  in tool names/call IDs are refused rather than echoed or normalized. Different
  IDs preserve repeated tool names.
- Tool definitions (`llm.tools`) and input-message history are not new attempts.
  Historical tool results do not establish matching execution or success.
- Known OpenInference kinds are retained. Unknown kinds, missing parents/roots,
  missing/zero timestamps, dropped counts, missing/redacted call identities,
  gapped call/message indexes, ambiguous ordering, events/links and unsupported
  output-message shapes block scoring. Mixed legacy `llm.function_call.*` and
  standalone `tool_call.*` attributes are also refused, never silently dropped.
  No call observations also blocks scoring.
- Span statuses retain `unknown`, `unset`, `ok`, or `error`. Status is not an
  action-success receipt. Errors and unset statuses are not silently converted
  to success, but do not erase the recorded attempt.

This is deliberately **not a full OTLP or OpenInference conformance layer**.
Jaeger, Phoenix/SDK console JSON, protobuf, JSONL, snake_case fields, symbolic
OTLP enum values, legacy function-call attributes, ordered content-part calls,
GenAI semantic conventions, unknown envelope fields, events and linked traces
need a separately reviewed adapter. Valid telemetry outside this narrow profile
can therefore be refused. No claims of interoperability with every exporter.

## Coverage is an explicit trust boundary

The export alone cannot prove that instrumentation captured every call. By
default coverage is `unknown` and scoring/check/freeze refuse it. For a reviewed
export, the caller supplies a separate declaration containing exactly:

```json
{
  "profile": "openinference-otlp-v1",
  "source_sha256": "<SHA-256 of the exact original export bytes>",
  "trace_id": "<exact trace ID spelling from the first exported span>",
  "case_name": "reviewed-stable-case-name",
  "span_coverage": "complete",
  "tool_call_coverage": "complete"
}
```

The two coverage fields also accept `unknown` and `incomplete`, which remain
ineligible. Both must be `complete` for scoring, and observed problems still
block scoring. The case name is explicit and stable across trace IDs; allowed
characters are letters, digits, underscore, dot and hyphen, up to 128 characters.
The declaration's own hash is retained alongside the source hash in diagnostics.

**A declaration is caller attestation, not verified completeness or authenticity.**
Only author it after reviewing instrumentation, sampling, truncation and export
boundaries. Never fabricate a completeness declaration just to get a green gate.
A source hash detects mismatch, not malicious changes to both files. Protect the
export, declaration, rubric, baseline and package version in your review process.
No automatic production-declaration generator is supplied.

## Ordering and score compatibility

Calls are ordered by non-overlapping source-span timestamps; call arrays inside
one LLM span retain message/call index order. Overlapping unrelated call-bearing
spans are refused, rather than using export arrival order or a guessed tie-break.
A generated array order represents **recorded request order, not execution order**.
The profile does not detect a tool that executed later than a subsequent request.

The Python projection creates one Step per call-bearing output message or
uncorrelated TOOL span. This is not the full conversation or span count. The CLI
therefore refuses nondefault `min_steps`/`max_steps`; message step-band policies
cannot be transferred to this profile. Tool-presence/order metrics and forbidden
policy are supported. Freeze a separately reviewed baseline for this profile;
do not reuse a legacy message-trajectory pin merely because case names match.
Baseline schema v1 does not pin adapter versions or source provenance.

Direct Python callers of `to_trajectory()` get the call projection and are
responsible for rubric compatibility, just as direct Trajectory construction
bypasses loader guarantees. The diagnostic includes provenance; the compact
ScoreReport retains its existing schema and does not include provenance hashes.
Keep inspection results with the original export and coverage declaration.

## Data minimization and limits

Diagnostics allowlist trace/span/parent/call IDs, tool names, timestamp values,
known kinds/statuses, coverage provenance and state labels. They do **not** copy
arguments, input/output bodies, reasoning signatures, resource metadata, span
names, status messages, arbitrary attribute names or arbitrary attribute values.
Payload states are `unknown` (absent), `redacted` (OpenInference's explicit
`__REDACTED__` marker), or `omitted` (present but deliberately not copied).
Identity states are `known`, `unknown`, or `redacted`.

This is payload minimization, **not a general secret detector**. Required tool
names and IDs remain exact for matching and can themselves contain sensitive
information; the caller must keep identifiers free of secrets. Other redaction
conventions are not inferred. In particular, a missing field cannot tell us
whether an exporter omitted or redacted it. No raw inputs from users/services
were used in these tests; every fixture is original and synthetic.

Input is bounded to 16 MiB and 10,000 items per collection / spans per export.
Parent-graph validation is iterative and visits each span's parent edge once,
so a deeply nested trace does not require repeated walks over all its ancestors.
This change preserves duplicate-ID, cycle, missing-parent and root checks. It
does not infer trace completeness or bound every other part of import processing.
JSON duplicate keys, non-finite values, malformed AnyValue encodings, invalid
numeric fields and unsupported layouts fail closed. This is not a hostile-input
service or an adversarial authenticity boundary. Use ordinary filesystem access
controls and process limits when reading untrusted exports.

## Read-only source evidence

The OpenInference sources listed below were inspected statically and were not
executed or copied into runtime code. A separate optional
[OpenTelemetry JavaScript compatibility check](../integrations/opentelemetry-js/README.md)
now creates synthetic spans with the real SDK and serializes them using its
OTLP JSON serializer. It sets OpenInference attributes explicitly; it does not
execute an OpenInference auto-instrumentation package or a collector.

Source and fixture implementation are original. OpenInference Apache-2.0 source
was reviewed at commit `6be7118f789c9cd3c71b3375810fe9250050fe31`:

- [Tool calling conventions](https://github.com/Arize-ai/openinference/blob/6be7118f789c9cd3c71b3375810fe9250050fe31/spec/tool_calling.md)
- [Semantic attributes and tool.id](https://github.com/Arize-ai/openinference/blob/6be7118f789c9cd3c71b3375810fe9250050fe31/spec/semantic_conventions.md)
- [OTLP JSON envelope/ID interfaces in upstream tests](https://github.com/Arize-ai/openinference/blob/6be7118f789c9cd3c71b3375810fe9250050fe31/js/packages/openinference-instrumentation-mcp/test/collector.ts)
- [Explicit redaction marker](https://github.com/Arize-ai/openinference/blob/6be7118f789c9cd3c71b3375810fe9250050fe31/python/openinference-instrumentation/src/openinference/instrumentation/config.py)

File hashes and the compatibility scope are recorded in
[`otel-source-lock.json`](otel-source-lock.json). The existing MIT license and
attribution remain intact. No upstream package was installed for this adapter.
