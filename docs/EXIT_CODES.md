# Exit-code contract (composition)

`trace-gate check` is meant to plug into CI and into
[agent-loop-engine](https://github.com/homayoun-safarpour/agent-loop-engine) as a named gate.

| Exit | Meaning | What a consumer should do |
| --- | --- | --- |
| `0` | `PASS` | Proceed (merge, or allow the loop to advance) |
| `2` | Fail closed | Block new work / fail the job |

Verdicts that map to exit `2`:

- `REGRESSION` — composite below `pinned - tolerance`
- `RUBRIC_DRIFT` — rubric SHA-256 no longer matches the pin (criteria were edited)
- `MISSING_BASELINE` — empty scores object
- `UNKNOWN_TRAJECTORY` — no overlap between run names and baseline keys

`score` and `freeze` return `0` on success and `2` on bad arguments / missing files
(via argparse / load errors).

## Stack composition (Type C hint, not a platform)

| Instrument | Role | Shared contract |
| --- | --- | --- |
| `trace-gate check` | Agent *behavior* regression on trajectories | exit `0`/`2` |
| `drift-sentinel check` | Judge *measurement* drift on frozen anchors | exit `0`/`2` (remap docs in that repo) |
| `loop-engine tick --gate …` | Prefer repair when any gate is red | consumes shell exit codes |

Example loop-engine gate line:

```bash
--gate "trace=trace-gate check path/to/run.json --rubric rubric.json --baseline baseline.json"
```
