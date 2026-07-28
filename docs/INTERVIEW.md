# Interview gate — trace-gate

## Three questions

1. **What does a frozen baseline add that a one-off trajectory score does not?**  
   A score is a measurement. A baseline is a contract: last-known-good composites plus tolerance. `check` fails the job when a new run drops below the floor, so CI and agent loops can treat behavior like a unit test.

2. **Why pin `rubric_sha256`?**  
   Without it, someone softens `forbidden_tools` or drops required tools, the same bad trajectory scores 1.0, and the gate looks green. Fingerprint mismatch → `RUBRIC_DRIFT` → exit 2 until someone deliberately re-freezes.

3. **How does this compose with an agent loop or a judge-drift sentinel?**  
   Shared exit contract (`0` / `2`). `loop-engine tick --gate "trace=trace-gate check …"` prefers repair when the gate is red. Judge drift (sentinel) and agent tool-use drift (trace-gate) are different objects; both fail closed the same way. See `docs/EXIT_CODES.md`.

## Two-minute demo

```bash
git clone https://github.com/homayoun-safarpour/trace-gate
cd trace-gate
pip install -e . pytest -q
trace-gate check examples/trajectories/support_good.json \
  --rubric examples/rubric.json \
  --baseline examples/baselines/support_v1.json
pytest -q
```

Expect: `verdict: PASS`, tests green (including `test_check_refuses_when_rubric_fingerprint_mismatches`).
