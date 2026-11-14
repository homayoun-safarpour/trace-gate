# Reliability card: trace-gate

| Field | Boundary |
| --- | --- |
| Job | Check recorded tool-call policy and composite regressions against a reviewed pin |
| Inputs | Supported JSON trajectories, a deterministic rubric and baseline schema v1 |
| Signals | All parsed tool names, explicit forbidden names, four quality metrics, rubric SHA-256, exact case coverage |
| Gate | `check`: only `PASS` exits 0; documented refusals exit 2 |
| Diagnostics | `score` may exit 0 while reporting `policy_ok=false`; it is not the gate |
| Evidence | Synthetic unit cases and real installed CLI invocations; no production outcomes or competitor benchmark |
| Runtime dependencies | None; no model calls and no execution of recorded tools |
| Limits | No trace authenticity/completeness proof, tool argument checking, semantic grading, runtime enforcement or general safety guarantee |

The rubric hash detects a changed rubric relative to a pin, not unauthorized
changes to both files. Baselines do not pin scorer/parser versions or source
trace hashes. Reports supplied directly through Python are trusted caller
inputs. Legacy baseline metrics are historical diagnostics, not an independent
policy certificate. See [GATE_CONTRACT.md](GATE_CONTRACT.md).

The prepared package version is 0.2.0. Local distribution verification covers
Python 3.10, 3.11 and 3.12 on Linux x86-64. The configured CI matrix and public
badge are not evidence of a hosted run for these bytes. Consult the matching
verification report and exact revision checks before deployment.
