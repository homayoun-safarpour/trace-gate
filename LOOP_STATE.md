# trace-gate : project backlog

Type R (restyle-improve) instrument.
Upstream inspiration: langchain-ai/agentevals (MIT).
Focus: frozen-baseline regression gate (exit 0/2) + `rubric_sha256` anti-tamper.

## Decision

Clone-improve of agentevals-class trajectory scoring into a deploy gate.
Not a full git fork of the LangChain tree (too heavy for a short install path).

## Interview notes

See `docs/INTERVIEW.md` and `docs/EXIT_CODES.md`.

## Backlog

- [x] W1 Trajectory JSON loader + tool extraction (cost: S) (touched: 2026-08-04)
- [x] W2 Deterministic rubric scorers + composite (cost: S) (touched: 2026-08-04)
- [x] W3 `freeze` / `check` baseline + exit codes (cost: M) (touched: 2026-08-04)
- [x] W4 Worked examples + committed baseline (cost: S) (touched: 2026-08-04)
- [x] W5 Tests + ruff + CI on 3.10/3.11/3.12 (cost: S) (touched: 2026-08-04)
- [x] W6 Type R README + worked example + attribution (cost: M) (touched: 2026-08-04)
- [x] W7 Threat model, comparison table, rubric fingerprint, EXIT_CODES (cost: M) (touched: 2026-08-04)
- [ ] W8 Adapter: convert agentevals-shaped dumps to this JSON schema (cost: M)
- [ ] W9 PyPI publish (`pip install trace-gate`) (cost: M)

## Next

W8 adapter when a real agentevals dump consumer is needed; otherwise W9 when packaging is ready.
