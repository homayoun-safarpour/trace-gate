# trace-gate

**Unit tests pass while your agent starts calling forbidden tools, because pytest never reads the recorded run.**

[![CI](https://github.com/homayoun-safarpour/trace-gate/actions/workflows/ci.yml/badge.svg)](https://github.com/homayoun-safarpour/trace-gate/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Fail CI when agent trajectory scores regress against a frozen baseline (exit 0 or 2).

trace-gate is a small command-line check that reads the recorded run of an AI agent (its messages and tool calls) and compares it with a run that a person has already approved. We built it because a test suite checks the code of an agent, whereas the failures we care about appear in what the agent did during a run, such as calling a tool that the rules forbid. Given a rubric and a frozen baseline, trace-gate scores each new run with fixed rules, keeps the sha256 fingerprint of the rubric beside the stored score, and returns exit 0 or 2, so that a CI job or an agent loop can stop a change that makes the agent worse.

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

## What each result means

| Verdict | Exit | Meaning |
|---|---|---|
| `PASS` | 0 | The run used only the tools the rubric allows, and its score is within the tolerance of the pinned baseline. |
| `REGRESSION` | 2 | The score fell below the pinned baseline minus the tolerance. |
| `RUBRIC_DRIFT` | 2 | The rubric file no longer matches the fingerprint stored with the baseline. |
| `MISSING_BASELINE` | 2 | The baseline is empty or absent, so there is nothing to compare against. |
| `UNKNOWN_TRAJECTORY` | 2 | The run's name is not in the baseline. |

A `PASS` shows that the recorded tool use matches the reviewed rubric and has not become worse. It does not show that the reply was correct or helpful. The exit contract is in [`docs/EXIT_CODES.md`](docs/EXIT_CODES.md), and the limits of each claim are in [`docs/RELIABILITY_CARD.md`](docs/RELIABILITY_CARD.md).

## Use this when

| Situation | Use trace-gate? |
| --- | --- |
| Your agent's runs are exported as JSON (messages and tool calls) and you want a CI check | Yes |
| You need exit code `0` or `2` so GitHub Actions or [agent-loop-engine](https://github.com/homayoun-safarpour/agent-loop-engine) can stop on failure | Yes |
| You want a language-model judge to grade the run | No. Use [langchain-ai/agentevals](https://github.com/langchain-ai/agentevals); this tool uses fixed rules only |
| Your traces are in OpenTelemetry or Jaeger format | Not directly. Convert them to JSON first |

The package is not on PyPI yet. `pip install git+https://github.com/homayoun-safarpour/trace-gate` is the other way to install it.

## The problem

An evaluation library can score one run. A build needs a different answer: did this change make the agent worse than the last approved run? Without a pinned baseline, a score is a single number that nothing can gate on. Without a fingerprint of the rubric, a teammate can make a failing agent pass by deleting a forbidden tool from the rubric file.

## How it works

1. `trace-gate score` reads a run and scores it against the rubric.
2. `trace-gate freeze` stores the score of an approved run as the baseline, with a tolerance and the sha256 fingerprint of the rubric.
3. `trace-gate check` scores a new run, compares it with the baseline, and exits 0 or 2.

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

Output of the last command, on the approved run:

```text
verdict: PASS
  rubric_sha256 OK (1d90a2ae91e6...)
  support-agent-good: PASS composite=1.0000 >= floor=0.9500 (pinned=1.0000)
```

| Module | What it does |
|---|---|
| `tracegate.trajectory` | Loads a run from JSON and extracts the tool calls, including OpenAI-style `tool_calls` |
| `tracegate.score` | Scores the run against the rubric with fixed rules and no model calls |
| `tracegate.baseline` | Freezes, loads and checks a baseline together with the rubric fingerprint |
| `tracegate.cli` | The `score`, `freeze` and `check` commands |

Interview pack: [docs/INTERVIEW.md](docs/INTERVIEW.md), three questions and a two-minute demo.

## Limits

- It is not a language-model judge. It scores tool use only and does not judge the meaning of a reply.
- The run format is minimal, so other trace formats need a converter first.
- A baseline is keyed by the run's name. If a run is renamed and the baseline is not updated, the verdict is `UNKNOWN_TRAJECTORY`.
- The fingerprint covers the rubric fields that change a score. It does not cover comments in the file.
- It has no runtime dependencies and needs Python 3.10 or later. Every central claim has a named test under `tests/`.

## Use it as a gate in a loop

[agent-loop-engine](https://github.com/homayoun-safarpour/agent-loop-engine) can run this check before it lets an agent continue. A failed gate makes the loop repair before it adds new work.

```bash
loop-engine tick --state LOOP_STATE.md \
  --gate "trace=trace-gate check examples/trajectories/support_good.json --rubric examples/rubric.json --baseline examples/baselines/support_v1.json"
```

## How we did it

1. **Chose the upstream.** [langchain-ai/agentevals](https://github.com/langchain-ai/agentevals) (MIT) showed that teams want to evaluate whole agent runs. Forking its full monorepo (Python, JavaScript and LangChain) would break the aim of an install in under 30 minutes.
2. **Built one small tool.** The MIT package `trace-gate` takes JSON in, scores it with fixed rules, makes no model calls, and has a command line shaped like the rest of this stack.
3. **Added two gates.** A frozen baseline with exit `0` or `2`, and a `rubric_sha256` pin, so that the criteria cannot change under the gate without a deliberate new freeze. Named tests: `test_check_detects_regression_below_floor`, `test_check_refuses_when_rubric_fingerprint_mismatches`, `test_readme_first_screen_matches_top100_craft`.

## Related tools

- [agent-loop-engine](https://github.com/homayoun-safarpour/agent-loop-engine): state, gates, the next-step decision and a journal for agent loops.
- [judge-drift-sentinel](https://github.com/homayoun-safarpour/judge-drift-sentinel): tells a change in the system from a change in the judge.
- [judge-field-guide](https://github.com/homayoun-safarpour/judge-field-guide): a link-checked map of tools for language-model judges.

## Credit

The idea of evaluating a whole agent run comes from **[langchain-ai/agentevals](https://github.com/langchain-ai/agentevals)** (MIT, Copyright LangChain and contributors). trace-gate is a separate MIT tool with a smaller surface and no LangChain dependency, and it adds the frozen baseline and the rubric fingerprint. Use agentevals for language-model judges, and trace-gate for the CI pin.

## Citation

Use the "Cite this repository" button on GitHub, or:

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
