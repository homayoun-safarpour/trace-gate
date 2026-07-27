# trace-gate — live project state

Type R (restyle-improve) ship. Upstream inspiration: langchain-ai/agentevals (MIT).
Sharp improvement: frozen-baseline regression gate with exit 0/2.

## Decision (2026-08-04)

**Strategy A** — clone-improve of agentevals-class trajectory scoring into a
deploy gate. Rejected full git fork of langchain-ai/agentevals: dual python/js
tree + LangChain deps break the <30 min stranger install bar. New MIT repo with
honest attribution + one named improvement (freeze/check baseline).

**W1 note:** `judge-drift-sentinel` W8 PyPI remains Boss-token blocked; this Type R
does not replace that close — it is the week's fork-engineering lane ship.

## Interview gate

See `docs/INTERVIEW.md`.

### Three questions (short)

1. Frozen baseline vs one-off score?
2. Why deterministic scorers for CI?
3. Exit 0/2 composition with agent-loop-engine?

### Two-minute demo

```bash
pip install -e . pytest -q
trace-gate check examples/trajectories/support_good.json \
  --rubric examples/rubric.json \
  --baseline examples/baselines/support_v1.json
pytest -q
```

## Backlog

- [x] W1 Trajectory JSON loader + tool extraction (cost: S) (touched: 2026-08-04)
- [x] W2 Deterministic rubric scorers + composite (cost: S) (touched: 2026-08-04)
- [x] W3 `freeze` / `check` baseline + exit codes (cost: M) (touched: 2026-08-04)
- [x] W4 Worked examples + committed baseline output (cost: S) (touched: 2026-08-04)
- [x] W5 Tests + ruff + CI on 3.10/3.11/3.12 (cost: S) (touched: 2026-08-04)
- [x] W6 Type R README: How we did it + Tutorial + attribution (cost: M) (touched: 2026-08-04)
- [ ] W7 Adapter: convert agentevals trajectory dumps → our JSON schema (cost: M)
- [ ] W8 PyPI publish when Boss provides token (cost: M)

## NEXT TICK

W7 adapter for agentevals-shaped dumps, or leave until a real consumer appears.
