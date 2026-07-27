# trace-gate

**Unit tests pass while your agent starts calling the wrong tools. This gates a deploy on trajectory scores pinned to a frozen baseline.**

[![CI](https://github.com/homayoun-safarpour/trace-gate/actions/workflows/ci.yml/badge.svg)](https://github.com/homayoun-safarpour/trace-gate/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## The problem

Agent eval libraries can score a trajectory once. CI still needs a **regression verdict**: did this PR make the agent worse than the last known-good run? Without a pinned baseline, every score is a one-off number nobody can gate on.

## Use this when

| Situation | Use trace-gate? |
| --- | --- |
| You export agent runs as JSON (tool calls / messages) and want a CI check | Yes |
| You need exit code `0` / `2` so GitHub Actions or [agent-loop-engine](https://github.com/homayoun-safarpour/agent-loop-engine) can fail closed | Yes |
| You want LLM-as-judge trajectory grading out of the box | No — use [langchain-ai/agentevals](https://github.com/langchain-ai/agentevals); this repo stays deterministic |
| You need OpenTelemetry / Jaeger ingest | No — point a converter at JSON first |

## Install

```bash
pip install git+https://github.com/homayoun-safarpour/trace-gate
# or from source
git clone https://github.com/homayoun-safarpour/trace-gate
cd trace-gate
pip install -e . pytest ruff
```

Python 3.10+. Zero runtime dependencies.

## Quickstart (< 5 min)

```bash
# 1) Score a known-good trajectory against a rubric
trace-gate score examples/trajectories/support_good.json --rubric examples/rubric.json

# 2) Freeze those scores as the deploy baseline
trace-gate freeze examples/trajectories/support_good.json \
  --rubric examples/rubric.json \
  --out examples/baselines/support_v1.json \
  --tolerance 0.05

# 3) Gate a new run (exit 0 = PASS, exit 2 = REGRESSION)
trace-gate check examples/trajectories/support_good.json \
  --rubric examples/rubric.json \
  --baseline examples/baselines/support_v1.json
```

Real output from this repository:

```
$ trace-gate score examples/trajectories/support_good.json --rubric examples/rubric.json
support-agent-good: composite=1.0000
  tool_presence=1.0000
  forbidden_tools=1.0000
  tool_order=1.0000
  step_band=1.0000

$ trace-gate check examples/trajectories/support_good.json \
    --rubric examples/rubric.json \
    --baseline examples/baselines/support_v1.json
verdict: PASS
  support-agent-good: PASS composite=1.0000 >= floor=0.9500 (pinned=1.0000)
```

## How we did it

1. **Chose upstream.** [langchain-ai/agentevals](https://github.com/langchain-ai/agentevals) (MIT, trajectory evaluators for agent runs) proved the market want: score *behavior*, not only final strings. A full monorepo fork pulls LangChain / dual JS packages — too heavy for a stranger to install in under 30 minutes.
2. **Restyled into a single instrument.** New MIT package `trace-gate`: JSON trajectories in, deterministic scorers (tool presence, order, forbidden tools, step band), no LLM calls, same CLI shape as the rest of this stack.
3. **One sharp improvement — frozen baseline gate.** `freeze` writes pinned composites; `check` compares a new run to that file with tolerance and returns exit `0` (PASS) or `2` (REGRESSION). That is the deploy gate agentevals-class scoring does not ship by itself.
4. **Commands that reproduce the committed baseline** (from repo root after `pip install -e .`):

```bash
trace-gate freeze examples/trajectories/support_good.json \
  --rubric examples/rubric.json \
  --out examples/baselines/support_v1.json \
  --tolerance 0.05
trace-gate check examples/trajectories/support_good.json \
  --rubric examples/rubric.json \
  --baseline examples/baselines/support_v1.json
# expect: verdict PASS, process exit 0
pytest -q
# expect: 13 passed
```

## Tutorial (15 min) — loop + quality gate

Read this once, then run the commands. Goal: treat an agent trajectory like a test suite artifact.

### 1. What a trajectory is here

A JSON object with a `name` and `steps`. Steps that called tools set `"tool": "..."`. See `examples/trajectories/support_good.json`.

### 2. What a rubric encodes

`examples/rubric.json` declares required tools, forbidden tools, expected order, and a step-count band. Scorers are pure functions in `[0, 1]`; the composite is their mean.

### 3. Score → freeze → check (the loop)

| Step | Command role | Why it exists |
| --- | --- | --- |
| Score | measure current behavior | You need a number before you can pin it |
| Freeze | write `baseline.json` | The last known-good becomes the contract |
| Check | compare + exit code | CI / [agent-loop-engine](https://github.com/homayoun-safarpour/agent-loop-engine) gates consume `0`/`2` |

Wire as a loop-engine gate:

```bash
loop-engine tick --state LOOP_STATE.md \
  --gate "trace=trace-gate check examples/trajectories/support_good.json --rubric examples/rubric.json --baseline examples/baselines/support_v1.json"
```

If the gate is red, the loop's decision policy prefers repair over new backlog work.

### 4. See a failure on purpose

Inflate the pinned score so the same good file fails:

```bash
python -c "import json; p='examples/baselines/support_v1.json'; d=json.load(open(p)); d['scores']['support-agent-good']=1.5; d['tolerance']=0.0; json.dump(d, open(p,'w'), indent=2)"
trace-gate check examples/trajectories/support_good.json \
  --rubric examples/rubric.json \
  --baseline examples/baselines/support_v1.json
echo Exit: $?
# restore: re-run the freeze command from Quickstart
```

You should see `verdict: REGRESSION` and a non-zero exit. That is the product.

## What is in the box

| Module | What it does | Use it when |
| --- | --- | --- |
| `tracegate.trajectory` | Load JSON runs; extract tool names (incl. OpenAI-style `tool_calls`) | Your exporter already writes messages |
| `tracegate.score` | Deterministic rubric scorers → composite | You want CI without an LLM judge bill |
| `tracegate.baseline` | Freeze / load / check pinned scores | You need a regression verdict, not a one-off score |
| `tracegate.cli` | `score` / `freeze` / `check` | Scripts, Actions, loop gates |

## Honest limitations

- Deterministic scorers only. No LLM judge, no semantic equivalence of free-text replies.
- Trajectory schema is minimal (steps + tools). Rich OTel / Jaeger graphs need a converter first.
- Baseline keys by `trajectory.name`. Rename a fixture without updating the baseline and `check` reports `UNKNOWN_TRAJECTORY` (exit 2), not a silent pass.
- Not a fork of the full agentevals tree — see attribution below.

## Upstream attribution

Trajectory-evaluation framing and the “score agent tool-use behavior” problem are established by **[langchain-ai/agentevals](https://github.com/langchain-ai/agentevals)** (MIT License, Copyright LangChain et al.). This repository is a separate MIT instrument: smaller surface, no LangChain runtime dependency, plus the frozen-baseline deploy gate described above. If you need upstream’s LLM judges and graph matchers, use agentevals directly and keep `trace-gate` for the CI pin.

## Design commitments

- Zero runtime dependencies; Python 3.10+
- Every README claim above has a named test under `tests/`
- Exit codes: `0` = PASS, `2` = REGRESSION / missing baseline / unknown trajectory

## Interview notes

See [`docs/INTERVIEW.md`](docs/INTERVIEW.md) for three questions and a two-minute demo path.

## License

MIT — see [`LICENSE`](LICENSE).
