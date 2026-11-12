> Historical report: the later private readiness review corrected the drift
> fixture collision and patched the optional npm lock. Current re-test results
> are in [README.md](README.md#private-readiness-re-test-corrections) and
> `evidence/readiness/`; the original records below are retained for comparison.

# Private integration verification, 2026-11-09

## Result

The trace-gate candidate works through the real Promptfoo 0.125.1 external Python
assertion interface. The complete-suite envelope preserves exact case coverage,
matching rubric fingerprints, quality floors and forbidden-tool vetoes.

The integration is private and unpublished. The original candidate was preserved.
No repository was pushed and no package or site was published.

## Actual CLI comparison

Each row is a complete synthetic suite snapshot. `PASS` means that particular
configuration accepted it, not that the underlying agent is safe.

| Fixture | trace-gate assertion | Native policy assertion |
| --- | --- | --- |
| Good suite | PASS | PASS |
| Forbidden second nested call | FAIL | FAIL |
| Malformed nested tool calls | FAIL | FAIL |
| Missing baseline case | FAIL | PASS |
| Additional unknown case | FAIL | PASS |
| Duplicate case | FAIL | PASS |
| Quality regression | FAIL | PASS |
| Rubric changed since pin | FAIL | PASS |
| Missing rubric fingerprint | FAIL | PASS |
| Invalid JSON | FAIL | FAIL |

Both sides correctly enforce their configured tool policy. The six differences
are explicitly unconfigured features in the native comparator, not capability
limits of Promptfoo. Promptfoo custom assertions can implement the full contract.
No universal superiority, benchmark accuracy or performance claim is supported.

The forbidden fixture's affected trajectory composite is **0.9875**, above its
**0.95** quality floor. Across its two cases the diagnostic mean is **0.99375**.
It still returns `pass: false`, `score: 0`, `POLICY_VIOLATION`.

## Checks performed

- Clean locked npm reinstall: 398 packages installed with lifecycle scripts
  disabled; all CLI checks below were rerun successfully afterward.
- Real Promptfoo CLI: 20 comparison rows matched expectations, zero runtime errors.
- Positive and negative single-suite smoke runs: exit 0 and exit 2 respectively.
- Two real CLI misconfiguration tests: zero assertion weight and zero aggregate
  threshold each overrode a forbidden-fixture failure. These are documented risks,
  not success cases for safe gating.
- Standard-library adapter tests: 12 passed, including structured output,
  duplicate keys/IDs, non-finite JSON, missing configuration, unchanged inputs,
  unrelated working directories and no input-selected file access.
- Existing core tests: 110 passed.
- Built source archive and wheel: clean distribution verifier passed, including
  110 packaged unit tests and 16 real console checks with a wheel-only environment.
- Ruff checks passed for core, tests, scripts and the integration.
- Actual runtime: Linux x86-64, Python 3.12.14, Node 24.22.1, Promptfoo 0.125.1.
  No other Python/Node/OS compatibility is claimed.
- All evaluation providers were local `echo`, costs and model tokens were zero.
  Telemetry, update checks, cache, sharing and result persistence were disabled;
  evaluation ran with sanitized environment variables. This does not claim
  OS-level network isolation. npm installation used the public registry.

Raw results, terminal logs and summarized outcomes are in `evidence/`. The verifier
checks individual rows, exact scenario coverage, errors, CLI exits, provider and
zero token usage. It returns success because intentional failures occurred.

## Provenance and limits

The official repository was cloned read-only at
`b3603fab85bb331da98a8b68ca442e1f4af7e368`. Its MIT license was verified and retained.
The optional published npm runtime is pinned separately by version and integrity.
Its Python wrapper and LICENSE hashes match the inspected clone. We did not build
all of upstream or run its complete test suite, and did not audit every npm
transitive dependency. The install skipped lifecycle scripts and unrelated
optional packages, adding only the matching SQLite binding needed by the CLI.

Fixtures are synthetic and deliberately small. There is no live model benchmark,
production trace validation, real tool execution, runtime blocking, argument
policy, trace authentication or semantic output evaluation here. Output is a
recorded suite JSON bundle, not an OpenTelemetry ingestion bridge. Protect both
reviewed policy files and the outer Promptfoo configuration.
