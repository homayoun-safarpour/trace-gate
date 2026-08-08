# Reliability card — trace-gate

| Field | Value |
| --- | --- |
| **Job** | Fail-closed CI gate on agent trajectory scores vs a frozen baseline |
| **Primary signals** | Deterministic trajectory scores + `rubric_sha256` pin |
| **Named verdicts** | `OK` (0), config/usage errors (1), `REGRESSION` / `RUBRIC_DRIFT` / `MISSING_BASELINE` / `UNKNOWN_TRAJECTORY` (2) |
| **Fixtures** | `examples/` support + regress trajectories (see README fail path) |
| **Runtime deps for core claim** | No LLM calls in the gate |
| **Claim** | Pytest can be green while tool-use regresses; this gate sees trajectory JSON |
| **Not claimed** | Full LLM-as-judge trajectory grading (use agentevals-class tools offline) |

## Field alignment (not affiliation)

Same job language as Ireland AI-first QA / agentic platform roles: **golden baseline + deterministic gate + fail closed**. Complements `judge-drift-sentinel` (judge instrument drift) with **agent behavior** drift.
