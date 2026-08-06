# Interview talking points : trace-gate

Five CLI-backed points for a technical screen (no resume recap).

- **`trace-gate score TRAJECTORY.json --rubric rubric.json`** : deterministic scorers only (no LLM calls in CI); prints composite scores you can log before gating.
- **`trace-gate freeze TRAJECTORY.json --rubric rubric.json -o baseline.json`** : writes last-known-good composites plus `rubric_sha256` so later checks detect rubric edits, not just score drops.
- **`trace-gate check TRAJECTORY.json --rubric rubric.json --baseline baseline.json`** : exit `0` on `PASS`, exit `2` on `REGRESSION`, `RUBRIC_DRIFT`, `MISSING_BASELINE`, or `UNKNOWN_TRAJECTORY` (see `docs/EXIT_CODES.md`).
- **Rubric tamper is a first-class failure** : `test_check_refuses_when_rubric_fingerprint_mismatches` proves softening `forbidden_tools` cannot greenwash a bad run without re-freezing.
- **Compose with `loop-engine tick --gate "trace=trace-gate check ..."`** : same exit contract as other stack gates so repair runs before new agent work when behavior regresses.