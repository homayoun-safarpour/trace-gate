# Automatic evidence, not automatic trust

## Status correction 16 November 2026

The introductory candidate paragraph below is retained as a historical snapshot. The workflow and checker source is now published on `release/0.2.0` at `9b61dff26890c9ce551e7ea63f4d470e798fed9c`, after PR #4 merged into that release branch. Integration into `main` remains separate. Hosted outcomes must be checked against their exact revision; publication alone establishes no successful execution. If the trusted main/base checker is absent, retain `TRUSTED_CHECKER_UNAVAILABLE` and `NOT ASSESSED` rather than executing the candidate checker.

Integration candidate based on release/0.2.0 commit `d4178b8afe98387fecbb5bbbcd380bd7b174a268` for `homayoun-safarpour/trace-gate`. These files have not been pushed, merged, enabled, or run on GitHub. The existing ci.yml workflow definition is unchanged; this candidate also changes the optional runtime dependency lock and source-distribution manifest.

## What runs after reviewed integration

- **Recorded trace evidence:** the head of every remote branch push (including release branches) and each PR targeting main triggers the narrow trace-data check. PRs use the *base commit's* checker, rubric and baseline; pushes use the current trusted main branch's checker/policy, not code from the pushed feature or release branch. Actual checked-out trusted/candidate commit SHAs are recorded. This is not a historical comparison against the previous push. Local commits cannot trigger GitHub until pushed; intermediate commits bundled in one push are not individually checked. The checker consumes only `examples/trajectories/support_good.json` from the head commit, capped at 100,000 bytes. Sparse checkout can also materialize ancestor/root files; this job never executes or imports them. These guarantees describe the unchanged reviewed workflow, not malicious modifications to the workflow YAML itself. The expected happy-path example must still satisfy the existing frozen baseline. No PR Python/JavaScript/tests/package scripts are run by this job. Changes to other files are NOT assessed by this job.
- **Consequence bench evidence:** each main push, manual main dispatch, and daily 06:37 UTC schedule runs source-lock checks, real localhost backend tests, receipt checks, mocked DOM interactions, browser-engine regression, exact Python/JavaScript fixture parity and JavaScript syntax checks. Scheduled GitHub jobs can be delayed. This is not a continuous worker. Neither new workflow uses concurrency cancellation; GitHub queue/quota limits, manual cancellation and disabled Actions can still prevent completion.
- Reports are job summaries and 14-day Actions artifacts containing JSON and test logs. No comments, commits, deployments, model API calls, paid model credits, or repository write permissions. GitHub Actions quota/billing still applies.

The executable bench has a case-sensitive shell check for exact `refs/heads/main` before checkout or code execution; case-variant branch names fail with a NOT ASSESSED artifact. Both jobs use GitHub-hosted runners, `contents: read`, pinned official action commits, bounded timeout, and checkout without retained credentials. No secrets are referenced, and there is no `pull_request_target`, external action inputs from PR text, package install, candidate code import, or arbitrary command input. PR output omits raw trace text and raw diagnostics. JSON input is copied to a temporary fixed path before the trusted CLI is invoked with isolated Python imports.

## Installation/review order

Apply this change to a clean reviewed trace-gate 0.2.0 checkout. The older current main emits different verdict semantics and is not a compatible base. Preserve the existing `.github/workflows/ci.yml`; the two new workflows are additive. Run:

```
python -I scripts/verify_consequence_bench.py
python -m unittest discover -s integrations/consequence-bench -p test_pr_trace_ci.py -v
```

Review before merging into main. The PR checker script must first exist on the trusted base branch; an initial PR that introduces it cannot run that base-side script and reports `TRUSTED_CHECKER_UNAVAILABLE` with a failing status and artifact, not silently running its head copy. After integration, create controlled good, forbidden-call, invalid-JSON and symlink PRs; verify actual GitHub job outcomes and artifact contents. Only then consider making the check required via a separate reviewed repository setting change. No setting change is included here.

Protect workflow/checker/policy changes with reviewer approval and branch rules. This workflow is not immutable security policy: a contributor can propose changes to workflow YAML itself. A read-only workflow cannot enforce those repository controls. Existing CI also executes PR test/build code; this additive candidate does not harden or replace that separate pipeline. Do not claim all PR execution is data-only.

## Evidence boundaries

The browser integration is a fixed-fixture port of pinned Python trace-gate `d4178b8afe98387fecbb5bbbcd380bd7b174a268`; parity checks compare exact scores, results and exit codes for 172 generated cases, not timestamps or arbitrary full-checker inputs. Mocked DOM tests are not real-browser E2E. The main branch tests run trusted merged source and never run a submitted repository as a program.

This is a trace-regression gate and interactive-demo regression suite, NOT the separate skill-file/Cisco scanner. It does not ingest GitHub URLs, scan all repo files, classify licenses, deploy the private Site, enforce live agent permissions, automatically improve code, or certify that an agent or repository is safe.

Official references checked during preparation:
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- https://github.com/actions/upload-artifact/commit/ea165f8d65b6e75b540449e92b4886f43607fa02

Checkout/setup Python/setup Node pins are preserved from the existing trace-gate CI and independently resolved on their official commit pages. Upload-artifact v4.6.2 commit verified against the official release. Runtime versions are selected versions, not immutable runner/container images. GitHub-hosted execution is still unverified.

## Existing optional-runtime audit compatibility

The existing Promptfoo 0.125.1 runtime pins `@hono/node-server` 2.1.5. This change includes a scoped `overrides.promptfoo.@hono/node-server` pin to 2.1.6, the first patched 2.x version for GHSA-qv5m-9pm6-hqp3 and GHSA-jpvv-r467-5p4w. No other locked dependency version is changed. This deliberately overrides Promptfoo's exact transitive pin; it is not an upstream compatibility endorsement. Re-evaluate/remove the override when the upstream pin is fixed. Local CLI/SDK regressions and current npm audit are checked, not every Promptfoo server/UI feature or WebSocket race. No `npm audit fix --force` downgrade is used.
