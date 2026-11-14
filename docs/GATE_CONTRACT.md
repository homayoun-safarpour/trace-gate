# Gate contract and compatibility

`check` requires all configured conditions to pass. A quality average cannot
cancel a forbidden call. This contract applies to supported recorded JSON,
not to a live agent or a guarantee of safe deployment.

## Hard policy versus quality

`score_trajectory` preserves the four original metrics and their arithmetic
mean. It additionally emits `forbidden_tools_used` in first-observed order,
without repeated names, and `policy_ok`. All nested calls remain available in
the parsed trajectory. Score JSON gains these two fields; old keys are retained.

`score` intentionally exits 0 for successfully scored evidence even when
`policy_ok` is false. It is a diagnostic command. Use `check` to enforce policy.

`check` refuses when either explicit forbidden names are present or the
`forbidden_tools` metric is below 1. The fallback supports Python reports from
the older API. Missing or invalid policy metrics and non-finite/out-of-range
composites produce `INVALID_REPORT`. A score of 0.9875 can still be a
`POLICY_VIOLATION`, even when the floor is 0.95. Tolerance never waives policy.

`freeze` rejects policy-violating, duplicate, empty or invalid reports before
writing any file. It requires a rubric or a valid explicit rubric fingerprint.
If both are supplied they must match. CLI validation refusals neither create
nor replace the target baseline. Filesystem write failures are reported, but
writes are not transactional against process interruption or disk failure.

## Complete case coverage

The parsed report names must match baseline score keys exactly, once each.

- Any unknown report name produces `UNKNOWN_TRAJECTORY`, even alongside a pass.
- Any omitted baseline case produces `MISSING_TRAJECTORY`.
- Repeated report names produce `DUPLICATE_TRAJECTORY`; `freeze` never silently
  collapses them into one dictionary entry.
- An empty report list cannot pass a populated baseline.

The legacy parser still derives a name from `name`, then `id`, then `unnamed`
and stringifies that value. This is not strict validation of source case IDs.
Use explicit stable string names. For intentional subsets or CI shards, freeze
and review distinct baseline files for the exact case set in each invocation.
There is no implicit subset mode.

## Rubric and numeric validity

`required_tools`, `forbidden_tools` and `ordered_tools` must be JSON lists of
non-empty strings when present. Bare strings, null values and invalid entries
are refused. Step bounds must be non-negative integers, with min <= max.
Omitted tool lists mean no constraint; an omitted min is 0 and max is unbounded.
Additional annotation fields are allowed but are not fingerprinted or scored.

Baseline scores and tolerance must be finite numbers in [0, 1], not numeric
strings or booleans. Only baseline schema version 1 is supported. The rubric
fingerprint must be a 64-character lowercase SHA-256 hex string and must match
the supplied rubric. Original schema-v1 fingerprints use the same canonical
rubric fields and remain unchanged.

Checks return the first failing category in this order: baseline structure and
fingerprint presence, rubric mismatch, report validity/duplicates and policy,
case coverage, then quality regression. They are not an exhaustive list of all
problems in one run. A policy refusal can therefore precede a coverage refusal.
Within coverage checks, unknown names take verdict priority while missing names
are also listed in the details.

## Legacy-baseline migration

This intentionally changes previously permissive behavior. There is no flag
that treats a missing fingerprint as success.

1. Preserve the old baseline for review. It can still be loaded for inspection.
2. Recover and review the original traces and rubric. A score-only file cannot
   prove which rubric generated it; do not invent or paste in a hash as proof.
3. Run `score` on those traces using the reviewed rubric. Inspect changes from
   the parser's full nested-call handling and any new policy violations.
4. Once acceptable, run `freeze` to a **new** baseline path, then `check` with
   the same complete case set. Review the diff before replacing the CI pin.

```bash
trace-gate freeze reviewed-a.json reviewed-b.json \
  --rubric reviewed-rubric.json --out baseline-reviewed.json --tolerance 0.05
trace-gate check reviewed-a.json reviewed-b.json \
  --rubric reviewed-rubric.json --baseline baseline-reviewed.json
```

If the original evidence is unavailable, regenerate and review it. Do not
silently treat the current candidate as last-known-good just to make CI green.

Existing fingerprinted v1 baselines remain usable when their score values,
case sets and rubric are valid. Stored baseline metrics are diagnostic history;
policy is enforced on the **current** reports. An older bad pin cannot waive a
current forbidden call, but a clean current report may pass against a low old
score. Review those pins rather than treating compatibility as certification.

Baseline files do not pin parser/scorer versions or trace hashes. They are not
signed. Protect baseline/rubric changes with code review, pin the installed
package artifact, and review/re-freeze after meaningful parser upgrades.

## Python API trust boundary

A caller constructing `Trajectory` or `ScoreReport` directly is responsible
for its integrity. Reports are not authenticated or cryptographically linked
to the rubric passed to `check_against_baseline`. Use the loader and scorer
with the same rubric, as the CLI does. This library is not a boundary against
malicious Python code, forged logs or someone able to edit both baseline and
rubric. Validation does not establish external instrumentation completeness.

## Report and schema consistency

Reports carry the `rubric_sha256` set by `score_trajectory`. Freeze and check
require it to match the pinned rubric and refuse missing/mismatched provenance
with `REPORT_RUBRIC_MISMATCH`. Rescore original evidence rather than attaching
a hash to old report data. The hash is not authentication against a malicious
caller that can fabricate report fields. See [migration notes](CORE_HARDENING.md).

Unknown rubric/baseline fields and duplicate/non-finite JSON values are rejected.
Malformed evidence at the CLI yields a controlled refusal (exit 2), including
JSON nesting deeper than the decoder supports.
