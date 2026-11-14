# trace-gate 0.2.0

Prepared release notes. Publication and hosted CI are separate steps; this file
does not claim that a tag, package or release has been published.

## Why 0.2.0

This is a pre-1.0 minor release, not a patch-only update. It adds an offline
telemetry adapter and a Promptfoo integration, and intentionally changes gate
and Python API behavior. A new minor version makes that migration visible.
The project is not declaring a stable 1.0 API or general OTLP conformance.

## Changes from 0.1.0 / public main 39168cd

- Forbidden tools veto `check` and `freeze`, independent of average quality or
  tolerance. Exact baseline case coverage and rubric fingerprints are required.
- Nested calls, including forbidden second calls and repeated calls, are retained.
  Ambiguous or malformed evidence is rejected instead of silently ignored.
- The narrow offline OTel/OpenInference profile can inspect supplied JSON and
  requires an explicit coverage declaration before scoring. It does not collect
  live telemetry or prove the declaration is complete.
- Parent-graph validation uses an iterative, linear pass instead of repeatedly
  walking every ancestor. Deep traces retain cycle and missing-parent checks
  without quadratic parent traversal or Python recursion-depth limits.
- An optional OpenTelemetry JavaScript SDK compatibility check creates original
  synthetic spans through a pinned SDK and its real OTLP JSON serializer, then
  checks the installed CLI. Recorded fixtures also run in the dependency-free
  Python suite; those recorded-fixture tests do not rerun the JavaScript SDK.
- The optional Promptfoo external Python assertion evaluates a complete recorded
  suite. Its local echo tests use no models; outer configuration can still weaken
  its result, so keep the documented positive weight and strict thresholds.
- JSON readers reject duplicate keys, non-finite/overflowing numbers and excessive
  nesting. Rubrics and baselines reject unknown fields. Freeze refuses to overwrite
  its input trajectory, coverage declaration or rubric through path aliases.
- Reports include the scoring rubric fingerprint. Python checks and freezes reject
  reports without the matching fingerprint using `REPORT_RUBRIC_MISMATCH`.
- Python checks and freezes reject incomplete metric sets and composites that
  do not match the four core metrics. Stale or malformed manually edited reports
  return `INVALID_REPORT`; rescore original traces instead of patching reports.
- Source distributions include runnable tests, fixtures, documentation and integration
  locks, but exclude installed Node dependencies. The core wheel has no runtime
  dependencies. Build/test pins and optional npm transitive overrides were updated.
- The distribution verifier rejects duplicate source-archive paths, including
  normalized aliases, before extracting files. This prevents last-entry-wins
  replacement from hiding ambiguous contents during local artifact checks.

## Migration

1. Keep the old executable and pins available while reviewing existing traces.
   Do not overwrite your only baseline or auto-freeze failures to make CI green.
2. Run the new parser and gate against the full reviewed suite. Expect refusals for
   forbidden calls, absent fingerprints, missing/unknown/duplicate cases and
   malformed evidence that older versions accepted.
3. Existing valid schema-v1 baselines and rubric fingerprints remain readable.
   Schema compatibility does not mean unchanged acceptance behavior. Follow
   [GATE_CONTRACT.md](GATE_CONTRACT.md#legacy-baseline-migration) for legacy pins.
4. Python callers should produce `ScoreReport` with `score_trajectory` using the
   reviewed rubric. Do not fabricate reports or relabel an old report's rubric.
5. Pin the reviewed executable as well as the rubric and baseline. Baselines do
   not pin parser/scorer versions. Review any deliberate re-freeze as a policy change.

## Boundaries

Verified locally on Linux x86-64 with Python 3.10–3.12 and the pinned optional
Promptfoo local-echo workload. Other platforms, Python 3.13+, live collectors,
real providers and production outcomes are not validated. Cross-major npm overrides
were exercised for this workload only. Dependency audits are dated checks for
known advisories, not a vulnerability-free guarantee.

Recorded calls show attempted tool use, not execution success. Hashes are
consistency checks, not authentication. A passing gate is not deployment approval
or a general safety guarantee. See [RELIABILITY_CARD.md](RELIABILITY_CARD.md) and
[THIRD_PARTY_REVIEW.md](THIRD_PARTY_REVIEW.md).

## Offline telemetry suites

`score`, `freeze` and `check` now accept several one-trace OTLP exports in one
invocation. Repeat `--coverage` once per export in the same order. Each source
hash is checked separately; missing/extra declarations and ineligible evidence
refuse the whole operation. Freeze protects every input and checks all cases
before replacement. Existing exact-case, rubric and forbidden-tool checks apply
to the complete suite. Single-export commands and baseline schema v1 are
unchanged; `inspect-otel` remains single-export. See [the suite workflow](OTEL_ADAPTER.md#gate-a-suite-of-exports).

## Tested loop-engine integration

The companion example now uses a bundled synthetic state file and an explicit
journal path. A pinned offline verifier checks the real installed CLI pair and
records gate exits separately from decision exits. The documentation makes clear
that loop-engine returns 0 for a repair decision and therefore cannot substitute
its process exit for trace-gate's CI gate. See the [integration guide](../integrations/loop-engine/README.md).
