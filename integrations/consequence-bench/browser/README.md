# Browser-local trace-gate fixture port: fixed-fixture interaction bench

Three connected interactions retained: change the synthetic input, calculate the bounded gate, compare/export exact input-bound receipts. Every check is a fresh local JavaScript calculation. No server call, uploaded material, user authentication data, model API, arbitrary tools or repository execution.

This is **not the original Python CLI**, not a generic checker port, and not a repository/skill scanner. Reference source is the existing unchanged pinned trace-gate checker d4178b8afe98387fecbb5bbbcd380bd7b174a268. Supported domain is exactly three controls: a 0–40-character ASCII tool name, unknown-case boolean, missing-fingerprint boolean. The fixed rubric forbids deny_0 through deny_19, fixes a read baseline and 0.05 tolerance. UI and exported events identify the browser port. Event timestamps are display ordering, not timing benchmarks. Baseline/trace byte hashes use JS serialization and are not Python file-byte hashes.

## Verify
- `python test_parity.py` compares actual pinned Python calls against the JS engine: exact result, details, score, fingerprint, reference exit code. It covers all flag combinations, all forbidden names, boundary/unforbidden representatives and seeded random inputs. It does not claim exhaustive arbitrary string/general checker verification.
- `node test_engine.cjs` validates input refusal and coherent fresh receipts.
- `node --check dist/engine.js` and `node --check dist/app.js`.

The bench is buildless static content in dist. No hosting configuration is included. CI exercises engine/parity regressions, not real-browser end-to-end behavior. No actual Python execution or remote attestation should be claimed by the hosted port.
