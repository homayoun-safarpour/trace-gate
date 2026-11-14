# trace-gate consequence bench — local interaction bench

This extends the existing real-checker local workbench, rather than drawing another decorative scene. Three connected functional areas explain the repository, run its actual core check, then inspect/compare/export evidence.

1. Enter a synthetic recorded tool trace (no tool is executed).
2. Run the pinned actual trace-gate Python checker, observing real emitted stages.
3. Pin completed run A, change one field, run and pin B. Inspect changed fields and actual verdict/score. Export a receipt tied to the submitted input and exact events.

A deliberately high-scoring forbidden call is refused; changing `deny_0` to `read` produces a new actual PASS on this narrow fixture. PASS is not a safety certificate. Unknown case/missing fingerprint controls expose separate gate failures. Multiple changed fields receive an attribution warning, not a causal claim. This is useful for explaining/debugging why a score did not determine permission.

## Run and verify

Python 3.10+ standard library, no model keys or paid requests:

```
python app.py
# Open http://127.0.0.1:8765 on that same computer
python -m unittest -v test_live.py
node test_receipt.cjs
node test_ui.cjs
node --check static/app.js
```

`real-check-evidence.json` contains two actual local checker runs made during implementation; it feeds regression tests only. The UI does not replay this file. Every click calls the local checker again.

## Evidence boundaries

The vendored unchanged checker is pinned at d4178b8afe98387fecbb5bbbcd380bd7b174a268; SOURCE-MANIFEST.json preserves per-file hashes and vendor/LICENSE preserves licensing. The UI validates exact stage order, same run identity, monotonic timestamps, submitted-input binding and completion shape before enabling pin/export. Edits or failed requests invalidate the current receipt. Historical pinned runs remain explicitly historical. Receipt integrity is structural only: it is not signed/remote attestation. JavaScript timestamps are display/order values, not nanosecond precision evidence.

Loopback-only HTTP service, strict Host/Origin/fixed routes/schema/length restrictions, one check at a time. Fixed local subprocess only; user strings never enter a shell. Do not expose publicly; no authentication or production hardening. No arbitrary repo/skill scanning, no runtime permission enforcement, and no LLM is consulted by this candidate.

## Verification and limits

13 real localhost HTTP/backend tests pass. 13 receipt/comparison assertions use two actual checker runs. 14 mock-DOM UI assertions cover pin, export, stale invalidation, changed-input late responses and refusal. Source manifest hashes verified unchanged. No actual browser/device test, screenshot, deployment or public commit was performed. This is a local candidate, not the requested directly accessible final page. Original workbench and public repositories were not edited.

Review correction: receipt sealing now rejects unknown verdicts and contradictory verdict/`ok`/exit-code triples. PASS requires `ok=true` and exit 0; all known refusals require `ok=false` and exit 2. Composite must be within [0,1]. Additional regression checks reject 12 contradictory triples, accept four consistent triples, and reject an unknown verdict and two invalid score ranges. This structural validation is not independent recomputation of the checker or cryptographic attestation.
