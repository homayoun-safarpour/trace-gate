# trace-gate

**Unit tests pass while your agent starts calling forbidden tools, because pytest never sees trajectory JSON.**

[![CI](https://github.com/homayoun-safarpour/trace-gate/actions/workflows/ci.yml/badge.svg)](https://github.com/homayoun-safarpour/trace-gate/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Fail CI when agent trajectory scores regress against a frozen baseline (exit 0 or 2).

```bash
git clone https://github.com/homayoun-safarpour/trace-gate
cd trace-gate && pip install -e .
trace-gate check examples/trajectories/support_regress.json --rubric examples/rubric.json --baseline examples/baselines/support_v1.json
```

```text
verdict: REGRESSION
  rubric_sha256 OK (1d90a2ae91e6...)
  support-agent-good: REGRESSION composite=0.5000 < floor=0.9500 (pinned=1.0000, tol=0.05)
```

That command exits 2. The same check on `examples/trajectories/support_good.json` exits 0.

## Use this when

| Situation | Use trace-gate? |
| --- | --- |
| You export agent runs as JSON (tool calls / messages) and want a CI check | Yes |
| You need exit code `0` / `2` so GitHub Actions or [agent-loop-engine](https://github.com/homayoun-safarpour/agent-loop-engine) can fail closed | Yes |
| You want LLM-as-judge trajectory grading out of the box | No; use [langchain-ai/agentevals](https://github.com/langchain-ai/agentevals). This repo stays deterministic |
| You need OpenTelemetry / Jaeger ingest | No; point a converter at JSON first |

Not on PyPI yet. `pip install git+https://github.com/homayoun-safarpour/trace-gate` is the other path.

The limit: deterministic scorers only. It does not grade free-text replies.

## The problem

Agent eval libraries can score a trajectory once. CI still needs a regression verdict: did this PR make the agent worse than the last known-good run? Without a pinned baseline, every score is a one-off number nobody can gate on. Without a rubric fingerprint, a teammate can greenlight a failing agent by deleting `forbidden_tools` from the rubric file.

## Threat model (when production loops go wrong)

| Failure | What it looks like | What trace-gate does |
|---|---|---|
| Silent gate skip | Rubric edited so bad tool use still scores 1.0 | `RUBRIC_DRIFT` if `rubric_sha256` no longer matches the pin |
| Unbounded "looks fine" | Scores printed in a log, never fail the job | `check` exit `2` on `REGRESSION` |
| Flaky CI via LLM judge | Same trajectory, different grade tomorrow | Deterministic scorers only; no model calls |
| Journal / baseline loss | Baseline deleted, check skipped in the script | Empty baseline -> `MISSING_BASELINE` -> exit `2` |
| Name mismatch hide | Fixture renamed, old pin never compared | `UNKNOWN_TRAJECTORY` -> exit `2` (fail closed, not silent pass) |

## Compared to what people already try

| Approach | Scores tool-use behavior | Pins last-known-good | Blocks merge/loop on drop | Rubric tamper check | LLM cost in CI |
|---|---|---|---|---|---|
| Cron + "print the score" | Maybe | No | No | No | Often |
| LangGraph / agent toy demo | Ad hoc | No | Rarely | No | Yes |
| [langchain-ai/agentevals](https://github.com/langchain-ai/agentevals) | Yes (rich) | Not as a deploy gate | You wire it | N/A | Optional judges |
| **trace-gate** | Yes (deterministic subset) | `freeze` | `check` exit `2` | `rubric_sha256` | None |

Honest: agentevals is deeper for offline LLM judges and graph matchers. This instrument is the deploy gate layer those scores still need.

## Quickstart

Interview pack: [docs/INTERVIEW.md](docs/INTERVIEW.md).

Claim boundaries: [docs/RELIABILITY_CARD.md](docs/RELIABILITY_CARD.md).

```bash
trace-gate score examples/trajectories/support_good.json --rubric examples/rubric.json

trace-gate freeze examples/trajectories/support_good.json \
  --rubric examples/rubric.json \
  --out examples/baselines/support_v1.json \
  --tolerance 0.05

trace-gate check examples/trajectories/support_good.json \
  --rubric examples/rubric.json \
  --baseline examples/baselines/support_v1.json
```

Good-path output:

```text
support-agent-good: composite=1.0000
verdict: PASS
```

## How we did it

1. **Chose upstream.** [langchain-ai/agentevals](https://github.com/langchain-ai/agentevals) (MIT) proved demand for trajectory-level agent eval. A full monorepo fork (Python + JS + LangChain) breaks the under-30-minute install bar.
2. **Restyled into one instrument.** MIT package `trace-gate`: JSON in, deterministic scorers, no LLM calls, CLI shaped like the rest of this stack.
3. **Sharp improvements.** (a) Frozen-baseline regression gate with exit `0`/`2`. (b) `rubric_sha256` pin so criteria cannot drift under the gate without a deliberate re-freeze. Named tests: `test_check_detects_regression_below_floor`, `test_check_refuses_when_rubric_fingerprint_mismatches`, `test_readme_first_screen_matches_top100_craft`.
4. **Reproduce committed artifacts:**

```bash
trace-gate freeze examples/trajectories/support_good.json \
  --rubric examples/rubric.json \
  --out examples/baselines/support_v1.json \
  --tolerance 0.05
trace-gate check examples/trajectories/support_good.json \
  --rubric examples/rubric.json \
  --baseline examples/baselines/support_v1.json
pytest -q
```

## Worked example: loop + quality gate

Treat an agent trajectory like a test-suite artifact a loop can refuse to advance past.

```bash
loop-engine tick --state LOOP_STATE.md \
  --gate "trace=trace-gate check examples/trajectories/support_good.json --rubric examples/rubric.json --baseline examples/baselines/support_v1.json"
```

Red gate -> loop policy prefers repair over new backlog work. Exit contract: [`docs/EXIT_CODES.md`](docs/EXIT_CODES.md).

The first-screen command is the fail-closed path (`support_regress.json`). Inflating the pin or editing the rubric without re-freeze (`RUBRIC_DRIFT`) must also exit non-zero.

## What is in the box

| Module | What it does | Use it when |
|---|---|---|
| `tracegate.trajectory` | Load JSON runs; extract tools (incl. OpenAI-style `tool_calls`) | Exporter already writes messages |
| `tracegate.score` | Deterministic rubric scorers -> composite | CI without an LLM judge bill |
| `tracegate.baseline` | Freeze / load / check + rubric fingerprint | Regression verdict that resists criterion drift |
| `tracegate.cli` | `score` / `freeze` / `check` | Scripts, Actions, loop gates |

## Failure modes and limitations

- Deterministic scorers only. No semantic grading of free-text replies.
- Minimal trajectory schema. OTel / Jaeger need a converter first.
- Baseline keys by `trajectory.name`. Rename without updating the pin -> `UNKNOWN_TRAJECTORY`.
- Fingerprint covers rubric fields that affect scores, not every comment in the JSON file.
- Not a full fork of agentevals; see attribution.

## Upstream attribution

Trajectory-eval framing comes from **[langchain-ai/agentevals](https://github.com/langchain-ai/agentevals)** (MIT, Copyright LangChain et al.). This repo is a separate MIT instrument: smaller surface, no LangChain runtime dependency, plus frozen-baseline + rubric-fingerprint deploy gates. Use agentevals for offline LLM judges; keep `trace-gate` for the CI pin.

## Design commitments

- Zero runtime dependencies; Python 3.10+
- Every central claim has a named test under `tests/`
- Exit codes: `0` = PASS, `2` = fail closed (see `docs/EXIT_CODES.md`)

## Field alignment

AI-first QA / agentic platform jobs ask for golden sets and fail-closed eval gates. This package is the trajectory deploy gate (deterministic; no LLM in CI). Claim boundaries: [docs/RELIABILITY_CARD.md](docs/RELIABILITY_CARD.md).

## Related instruments

- [agent-loop-engine](https://github.com/homayoun-safarpour/agent-loop-engine) - state, gates, decide, journal
- [judge-drift-sentinel](https://github.com/homayoun-safarpour/judge-drift-sentinel) - judge vs system drift
- [judge-field-guide](https://github.com/homayoun-safarpour/judge-field-guide) - link-checked map of the LLM-judge ecosystem

## Interview notes

[`docs/INTERVIEW.md`](docs/INTERVIEW.md): three questions + two-minute demo.

## Citation

```bibtex
@software{safarpour2026tracegate,
  author = {Homayoun Safarpour},
  title  = {trace-gate: gate deploys on frozen agent-trajectory baselines},
  year   = {2026},
  url    = {https://github.com/homayoun-safarpour/trace-gate}
}
```

Author: Homayoun Safarpour. [LinkedIn](https://www.linkedin.com/in/homayoun-safarpour/)

## License

MIT. See [`LICENSE`](LICENSE).
