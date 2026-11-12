# Promptfoo integration: recorded suite assertion

Optional integration for trace-gate 0.2.0. It uses
Promptfoo's documented external Python assertion interface: `get_assert(output,
context)` returns `pass`, `score`, and `reason`. There are no model calls in this
example. Promptfoo is optional; trace-gate's runtime stays dependency-free.

## What is integrated

The provider output must be one complete recorded suite:

```json
{"trajectories": [{"name": "case-a", "steps": []}, {"name": "case-b", "steps": []}]}
```

Each trajectory uses trace-gate's existing supported JSON formats. This envelope
is important: checking one Promptfoo test at a time against a multi-case baseline
would lose the intended whole-suite coverage or incorrectly fail every test.
Here each Promptfoo test is a **complete suite snapshot**, not one baseline case.

Trusted assertion configuration points at reviewed rubric and baseline files:

```yaml
assert:
  - type: python
    value: file://trace_gate_assert.py
    weight: 1
    config:
      rubric_path: fixtures/rubric.json
      baseline_path: fixtures/baseline.json
```

Paths are relative to `trace_gate_assert.py`, even from another working directory.
Provider output never selects files, supplies a replacement policy, or runs tools.
Malformed input and missing files fail. Duplicate JSON keys and non-finite JSON
constants are rejected. The adapter calls the existing parser, scorer, and
baseline checker rather than maintaining a second scoring implementation.

A passing gate returns score 1; **every refusal returns score 0**, including a
forbidden call with a high quality composite. Quality remains available as the
`quality_mean` named diagnostic metric. It is not the approval score.

## Reproduce the tested setup

Verified on Linux x86-64, Node **24.22.1**, Python **3.12.14**, Promptfoo **0.125.1**.
The inspected source requires Node >=22.22.0; its `.nvmrc` requests 24.22.2. We did
not claim that exact patch version or other operating systems were tested.

A clean locked `npm ci` reinstall completed with install scripts disabled, then
the full CLI verifier passed again. The lock installed 398 packages, including
the matching SQLite platform binding.

Start from this source archive/check-out. Install the reviewed wheel in a fresh
Python environment, then install the pinned optional Promptfoo tooling:

```sh
python3 -m venv .venv-promptfoo
.venv-promptfoo/bin/pip install --no-index --no-deps dist/trace_gate-0.2.0-py3-none-any.whl
cd integrations/promptfoo/runtime-lock
npm ci --ignore-scripts --omit=optional --no-audit --no-fund
cd ../../..
.venv-promptfoo/bin/python -I -m unittest discover -s integrations/promptfoo/tests -v
.venv-promptfoo/bin/python -I integrations/promptfoo/verify_integration.py \
  --cli integrations/promptfoo/runtime-lock/node_modules/promptfoo/dist/src/entrypoint.js
```

A source archive normally does not include a built wheel; build it using
[the main installation guide](../../docs/INSTALLATION.md) or use the accompanying
reviewed wheel. `runtime-lock` is deliberately **Linux x86-64-specific**: the CLI
loads a SQLite native dependency even when evaluation persistence is disabled.
The lock includes matching `@libsql/linux-x64-gnu` 0.5.29 explicitly, so dependency
lifecycle scripts and other optional providers need not run. Other platforms need
their matching binding and a separately verified installation.

The verifier checks the installed Promptfoo version; runs local `echo` evaluations
from a fresh temporary directory; uses this Python interpreter; disables sharing,
telemetry, update checks, result persistence and cache; strips inherited API keys;
and enforces a 100% pass-rate threshold and exit 2 for failed evaluations. It
checks exported per-case results and zero model tokens, not just process status.
This is not an OS-level network sandbox. Initial npm installation requires network.

The verifier itself exits zero when its **expected pass and expected fail tests**
all behave correctly. It is a compatibility test, **not a deployment gate**.
`pass-config.json` is a passing smoke test; `fail-config.json` must exit 2 with the
same environment/flags. `promptfooconfig.json` intentionally contains nine
negative tests and must also exit 2. The native comparison must exit 2 too.

## Do not weaken the containing gate

- Keep this as a positive `python` assertion, with positive weight (examples use 1).
- Do not use `not-python`, `weight: 0`, a test/assertion-set aggregate threshold,
  a reduced evaluation pass-rate threshold, or a CI step that ignores failure.
- Protect the configuration, adapter, rubric, baseline and CI invocation in review.
- Run each complete baseline suite. For sharding, use a reviewed baseline per shard.
- Keep a standalone `trace-gate check` CI step if you cannot enforce the surrounding
  Promptfoo configuration.

The real CLI tests deliberately demonstrate that `weight: 0` and test `threshold:
0` can each make a forbidden fixture pass at the Promptfoo aggregate level. Those
misconfigurations are generated only in temporary directories, and their results
are recorded under `evidence/`. The adapter cannot overrule its caller's policies.
Rubric hashes detect mismatches; they do not authenticate the policy or evidence.

## Configured comparison, not a leaderboard

`native_policy_assert.py` is a separate Python assertion with no trace-gate import.
It checks the supplied forbidden-tool list and basic trace structure. It sees
**every nested call**, including the forbidden second call. Both configurations
reject that action and malformed nested tool calls. No forbidden-tool detection
advantage is claimed.

The native comparator intentionally has no baseline, fingerprint, case-coverage,
or quality-floor code. It therefore passes those six mutations, while the
trace-gate integration refuses them. This measures these **two configurations**,
not Promptfoo's maximum capabilities. Native Python/JavaScript assertions can
implement all of these checks; the integration's contribution is reuse of the
reviewed gate and baseline contract with Promptfoo's result/report workflow.

Ten synthetic suite snapshots are provided. They do not estimate production
accuracy, safety, speed, adoption or model quality. No live agent, paid API,
OpenTelemetry pipeline, tool argument checker or runtime interceptor was tested.
See [REPORT.md](REPORT.md) and the machine-readable [comparison](evidence/comparison.json).

## Source pin and attribution

Official repository: <https://github.com/promptfoo/promptfoo>.
Inspected commit: `b3603fab85bb331da98a8b68ca442e1f4af7e368`.
The [Python assertion contract](https://github.com/promptfoo/promptfoo/blob/b3603fab85bb331da98a8b68ca442e1f4af7e368/site/docs/configuration/expected-outputs/python.md)
was checked against source and the actual published 0.125.1 CLI.

Source revision and npm release are pinned separately in `upstream-lock.json`.
We do not claim the npm bundle was built from that commit. The Python wrapper and
LICENSE bytes match between the clone and installed npm package. Package integrity
and exact transitive resolution are in `runtime-lock/package-lock.json`.

Promptfoo is MIT, Copyright (c) Promptfoo 2025. Its unmodified license is included
in `licenses/PROMPTFOO-MIT.txt`. No Promptfoo implementation source is vendored into
the adapter; its optional npm runtime retains its own notices. This is independent
interoperability work, not an official Promptfoo integration or endorsement.
The full npm dependency tree's licensing/security was not comprehensively audited.

## Private readiness re-test corrections

The drift fixture generator previously reused `rubric-drift.json` for both policy
and evidence, overwriting the policy with trajectories. That caused refusal for
the wrong reason. The policy now has its own `rubric-drift-policy.json`, and a
regression test checks its shape and path separation. Unknown rubric fields are
rejected rather than becoming an empty policy. The adapter also shares core's
strict JSON decoder, including rejection of overflowing numbers such as `1e999`.

See [core migration notes](../../docs/CORE_HARDENING.md) for report-rubric binding.
The existing `evidence/` CLI records are historical, not proof of the corrected
candidate's runtime behavior; fresh readiness evidence is kept separately under
`evidence/readiness/`.

The original lockfile audit found eight affected package nodes (five high and
three moderate, zero critical), rooted in `basic-ftp`, `glob`, and `minimatch`.
The integration runtime now explicitly overrides those to **6.2.6**, **14.0.4**,
and **11.0.5**, respectively, while retaining Promptfoo **0.125.1**. No patched
same-major versions satisfied the advisory ranges. The resulting lock also moves
`path-scurry` to 3.0.0 and adds `@isaacs/nonrecursive-glob-match` 1.1.0.

A clean script-disabled reinstall succeeded (399 packages). The corrected
candidate passed the real CLI verifier again: 20 comparison rows, separate
pass/fail exits, and two aggregation hazards, all with zero model tokens. The
post-change registry audit reports **zero known advisories**. Records include
[original audit](evidence/readiness/npm-audit.json),
[post-change audit](evidence/readiness/npm-audit.after.json),
[exact lock diff](evidence/readiness/package-lock.diff), and
[fresh CLI comparison](evidence/readiness/comparison.json).

These cross-major transitive overrides were verified only for this local echo
integration on Node 24.22.1, not all Promptfoo providers. The FTP, cancellation and
glob-amplification exploit paths were not exercised. Zero audit findings are
neither comprehensive security clearance nor a licensing audit. Core trace-gate
still has no runtime dependencies.
