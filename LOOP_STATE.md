# trace-gate — live project state

Type R (restyle-improve) + advanced bar (2026-08-04).
Upstream inspiration: langchain-ai/agentevals (MIT).
Sharp contributions: frozen-baseline regression gate (exit 0/2) + rubric_sha256 anti-tamper.

## Decision

**Strategy A** — clone-improve of agentevals-class trajectory scoring into a deploy gate.
Not a full git fork (LangChain/js tree too heavy for <30 min install).

**W1 note:** `judge-drift-sentinel` W8 PyPI remains Boss-token blocked; this ship does not replace that close.

## Interview gate

See `docs/INTERVIEW.md` and `docs/EXIT_CODES.md`.

## Backlog

- [x] W1 Trajectory JSON loader + tool extraction (cost: S) (touched: 2026-08-04)
- [x] W2 Deterministic rubric scorers + composite (cost: S) (touched: 2026-08-04)
- [x] W3 `freeze` / `check` baseline + exit codes (cost: M) (touched: 2026-08-04)
- [x] W4 Worked examples + committed baseline (cost: S) (touched: 2026-08-04)
- [x] W5 Tests + ruff + CI on 3.10/3.11/3.12 (cost: S) (touched: 2026-08-04)
- [x] W6 Type R README + Tutorial + attribution (cost: M) (touched: 2026-08-04)
- [x] W7 Advanced: threat model, comparison table, rubric fingerprint, EXIT_CODES (cost: M) (touched: 2026-08-04)
- [ ] W8 Adapter: convert agentevals-shaped dumps → our JSON schema (cost: M)
- [ ] W9 PyPI publish when Boss provides token (cost: M)

## NEXT TICK

W8 adapter, or leave until a real agentevals dump consumer appears.
