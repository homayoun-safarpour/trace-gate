# Interview gate — trace-gate

## Three questions an interviewer can ask

1. **What problem does a frozen baseline solve that a one-off trajectory score does not?**  
   A single score has no deploy meaning. The baseline pins last-known-good composites; `check` fails when a new run drops below `pinned - tolerance`, so CI can block merges the same way unit tests do.

2. **Why stay deterministic instead of calling an LLM judge?**  
   Gate flakiness is worse than a slightly weaker scorer. Tool presence / order / forbidden-tool checks are stable across machines and cost nothing. Semantic judges belong in offline eval (e.g. langchain-ai/agentevals); the deploy gate should be boring.

3. **How does this compose with an agent loop?**  
   `trace-gate check` returns exit `0` or `2`. [agent-loop-engine](https://github.com/homayoun-safarpour/agent-loop-engine) treats any non-zero gate as “repair before advance,” so a trajectory regression blocks new backlog work until the agent (or human) fixes tool use.

## Two-minute demo (copy-paste)

```bash
git clone https://github.com/homayoun-safarpour/trace-gate
cd trace-gate
pip install -e . pytest -q
trace-gate score examples/trajectories/support_good.json --rubric examples/rubric.json
trace-gate check examples/trajectories/support_good.json \
  --rubric examples/rubric.json \
  --baseline examples/baselines/support_v1.json
pytest -q
```

Expect: composite `1.0000`, verdict `PASS`, `13 passed`.
