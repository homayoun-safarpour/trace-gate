# Gate hardening in 0.2.0

The gate now binds each `ScoreReport` to the rubric used by `score_trajectory`.
`freeze_baseline` and `check_against_baseline` reject reports with absent or
mismatched `rubric_sha256` using `REPORT_RUBRIC_MISMATCH`. Passing a different
rubric at check time cannot relabel an already scored report. Callers constructing
reports manually should instead rescore original trajectories with the reviewed
rubric. The report JSON includes this additional field. Existing version-1
baseline files and rubric fingerprints remain compatible.

Checks and freezes also require all four core metrics (`tool_presence`,
`forbidden_tools`, `tool_order`, `step_band`) and a composite equal to their mean,
within an absolute floating-point tolerance of 1e-12. Missing or additional
metrics, malformed forbidden-tool lists and stale composites produce
`INVALID_REPORT`. Report dictionaries are not automatically repaired. Rescore
the original trajectory instead of editing individual values or dropping fields.
Custom metrics belong in a separate record; they do not extend the core gate's
arithmetic. This is a stricter Python API contract for manually constructed
reports; unchanged results from `score_trajectory` remain compatible.

This is consistency checking, not cryptographic authentication: trusted Python
callers can mutate reports or fabricate hashes. Protect the scorer, recorded
inputs, baseline, policy and calling application in review. Baseline composite
floors still allow offsetting quality changes by design; the forbidden-tool veto
is independent and cannot be offset by quality or tolerance.

Rubric and baseline JSON objects reject unknown fields so misspelled policy keys
cannot silently become defaults. Rubric constructor tool lists are copied into
immutable tuples. JSON file loaders reject duplicate keys, non-finite constants
and overflowing floating-point numbers. Supplied trajectory names and IDs must
be nonempty strings; omitted identity retains the documented `unnamed` fallback.

Regression coverage is in `tests/test_core_adversarial.py`; Promptfoo adapter
coverage is in `integrations/promptfoo/tests/test_assertion.py`.

The private follow-up adds [transactional baseline writes](BASELINE_WRITES.md):
failed writes preserve the reviewed pin, symlink outputs are refused and hardlink
aliases are not modified. Its filesystem and permission boundaries are explicit.
