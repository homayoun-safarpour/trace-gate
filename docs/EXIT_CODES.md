# Exit-code contract

Use `trace-gate check` as the CI gate. Only `PASS` exits 0. All documented
refusals exit 2; calling code should block on **any nonzero** status.

| Verdict | Meaning |
| --- | --- |
| `PASS` | Current recorded traces meet the configured checks |
| `POLICY_VIOLATION` | At least one forbidden-tool signal, regardless of tolerance |
| `REGRESSION` | A composite is below `pinned - tolerance` |
| `RUBRIC_DRIFT` | Rubric absent from the Python check call or different from the pin |
| `MISSING_RUBRIC_FINGERPRINT` | Hashless legacy pin requires review and re-freeze |
| `MISSING_BASELINE` | Baseline has no scores |
| `UNKNOWN_TRAJECTORY` | At least one supplied parsed case name is absent from the pin |
| `MISSING_TRAJECTORY` | At least one pinned case was not supplied |
| `DUPLICATE_TRAJECTORY` | A case name appears more than once |
| `INVALID_BASELINE` | Unsupported version, malformed fingerprint or invalid numeric values |
| `INVALID_REPORT` | Missing/invalid policy metric, invalid composite or case name in Python API |
| `REPORT_RUBRIC_MISMATCH` | Python reports lack provenance or were scored with another rubric |

`check --json` emits `verdict`, `ok` and `details` for completed gate checks,
including refusals. Bad/missing input files and malformed JSON/structure emit
`INVALID_RUBRIC`, `INVALID_TRAJECTORY` or `INVALID_BASELINE` to **stderr**, with
no partial stdout result, and exit 2. Argument errors also exit 2.

`score` exits 0 when it can produce diagnostics, **even if policy_ok is false**.
`freeze` exits 0 only after a valid baseline is written; validation or I/O errors
produce `FREEZE_REFUSED` on stderr and exit 2. A policy-violating freeze cannot
create or overwrite a pin. See [the full contract](GATE_CONTRACT.md) for failure
precedence, compatibility and migration.

This is a recorded-evidence gate. A passing exit code is not authorization to
deploy or proof that an agent is safe. The CI consumer must preserve the code:

```bash
trace-gate check case-a.json case-b.json --rubric rubric.json --baseline baseline.json
```

Do not add `|| true` or `continue-on-error`. Unexpected crashes and environment
failures may use other nonzero codes and must block too.
