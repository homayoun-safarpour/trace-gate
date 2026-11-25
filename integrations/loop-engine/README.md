# Run trace-gate as a loop-engine quality gate

This example connects the real trace-gate CLI to the real
[agent-loop-engine](https://github.com/homayoun-safarpour/agent-loop-engine)
decision CLI. A clean trace permits an `advance` decision; a forbidden call,
quality regression, malformed input or invalid baseline produces `repair`.
Neither package executes the backlog item or invokes the tools recorded in a trace.

## Try it from an extracted trace-gate source archive

Install the reviewed trace-gate wheel and a reviewed agent-loop-engine checkout
in the same disposable Python environment. The tested companion revision is
[`75992043ec9ae1cee04295d25846a53435f3b4fb`](https://github.com/homayoun-safarpour/agent-loop-engine/commit/75992043ec9ae1cee04295d25846a53435f3b4fb),
version 0.1.0. It is not bundled into the trace-gate wheel or source archive.
With the pinned build tools already installed:

```sh
python -m pip install --no-index --no-deps /path/to/trace_gate-0.2.0-py3-none-any.whl
python -m pip install --no-deps --no-build-isolation /path/to/reviewed/agent-loop-engine
```

Activate that environment and run from the **trace-gate source root**. The state
file below is bundled, synthetic and intentionally contains one unfinished item.
Choose a new, separate journal path that does not alias any input file.

```sh
loop-engine tick --state integrations/loop-engine/LOOP_STATE.md \
  --journal /tmp/trace-gate-loop-demo-journal.md \
  --gate 'trace=trace-gate check examples/trajectories/support_regress.json --rubric examples/rubric.json --baseline examples/baselines/support_v1.json'
```

Expected decision: `action : repair`, `target : trace`. Repeat with
`support_good.json` and the decision is `action : advance`. The journal gains
one entry per tick; the demonstration backlog is not changed or executed.
These shell examples target POSIX environments, not Windows shells.

## Do not use tick's exit code as the trace gate

**At the pinned revision, `loop-engine tick` exits 0 for both `advance` and
`repair`.** Zero means it produced a decision, not that its gates passed.
For CI refusal, run `trace-gate check` directly and preserve its exit code:
0 for PASS, 2 for a refusal. If orchestrating the decision engine, inspect its
`action` field and act accordingly. Do not interpret a successful tick process
as permission to advance, publish or deploy.

Gate commands are trusted operator code executed by a shell. Never interpolate
untrusted trace, state, tool argument or model-output text into them. The
verifier below constructs only fixed, quoted commands. Configure the journal
as a separate output: the companion package does not protect against a journal
path aliasing your state, trace, rubric or baseline.

The decision JSON and journal contain a decision and gate status, not the
complete trace-gate report. The companion captures only the last 2,000 characters
of gate output and does not put that output into either artifact. Keep direct
trace-gate output when detailed diagnostics matter.

## Verify the installed pair

```sh
python -I integrations/loop-engine/verify_integration.py --evidence /tmp/trace-gate-loop-evidence
```

The verifier checks the companion's version and all six Python source-module
hashes against `upstream-lock.json` before launching its CLI. It executes nine
positive/negative scenarios and a two-tick repair-to-advance sequence, checks the
journal appended without changing the demo state, and records both direct gate
and decision CLI outcomes. Working paths include spaces and an apostrophe to
exercise argument quoting. All state, traces and journals are synthetic and local.

It does not download/install packages, read a real task queue, schedule work,
call a model or contact a service. The hash pin checks these reviewed source
files, not a universal supply-chain guarantee. A different companion revision
must be reviewed and its compatibility rerun. The core pytest suite does not
execute the companion; use this separate verifier for the end-to-end claim.

## Attribution

agent-loop-engine is MIT licensed, Copyright (c) 2026 Homayoun Safarpour. Its
upstream runtime is used unchanged and is not vendored here. Source URLs, Git
blob identities and SHA-256 values are recorded in `upstream-lock.json`. This
integration harness and example state are original trace-gate code.
