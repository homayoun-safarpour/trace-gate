# OpenTelemetry JavaScript compatibility check

Generate six original synthetic traces with the real OpenTelemetry JavaScript
SDK and its OTLP JSON serializer, then check them with the installed trace-gate
wheel. The workload uses an in-memory span exporter. It does not create an HTTP
exporter, register global instrumentation, contact a collector or call a model.

## What this establishes

The checked runtime is Node 24.22.1, OpenTelemetry API 1.9.1, SDK/resource packages
2.12.1 and OTLP transformer 0.223.1. The generator checks those installed versions
against the existing npm lockfile before loading them. Its provenance record
contains the lock hash, package versions, declared registry integrity values,
entry-module hashes, generator hash and exact serialized fixture hashes.

OpenInference attributes are set by this fixture generator. This verifies one
SDK/serializer combination against the supported offline profile. It does not
validate an OpenInference auto-instrumentation library, Phoenix, a network
collector, every exporter version, or real instrumentation completeness. A lock
entry and module hash are not an independent audit of every installed dependency.

## Run against an existing optional runtime

Use an environment with the reviewed trace-gate wheel installed. The existing
[Promptfoo runtime lock](../promptfoo/runtime-lock/package-lock.json) contains the
OpenTelemetry packages used by this check. Reuse that runtime or follow its
separate installation procedure; this verifier performs no installation.

```sh
python -I integrations/opentelemetry-js/verify_integration.py \
  --runtime-root /absolute/path/to/runtime-lock \
  --evidence /absolute/path/to/new-sdk-evidence
```

The runtime directory must contain package.json, package-lock.json and its
matching node_modules. The verifier fails rather than fetching a missing package
or accepting a different top-level SDK version. It runs Node with a temporary
home and a small environment, then uses isolated Python for actual CLI checks.
No installed Node dependency is included in the trace-gate wheel or source archive.

## Cases and expected results

- **Good:** a generated search call and its correlated execution become one
  recorded attempt. The SDK execution has ERROR status; that state stays visible
  and is not a successful-action receipt. The configured tool-policy check passes.
- **Forbidden generated call:** an extra delete_database request is counted even
  though it has no execution span. The gate returns POLICY_VIOLATION and freeze
  cannot replace the existing baseline.
- **Repeated tool name:** distinct request IDs retain two search attempts.
- **Span event, dropped attributes, missing call ID:** the SDK produces valid
  telemetry outside the gate-eligible profile. Inspection retains the relevant
  issue, scoring refuses and the existing baseline is preserved.
- **Missing declaration or changed source hash:** coverage remains unknown or
  fails validation rather than being silently trusted.
- **Payload minimization:** synthetic input/output, argument, resource, span-name,
  event and status-message markers must not appear in inspection/CLI output.

The verifier authors completeness declarations only for its own freshly generated
synthetic fixtures. It is not a production declaration generator. Inspection
eligibility is not a policy pass: the forbidden-call fixture is eligible to score
and correctly fails the policy gate.

## Recorded fixtures and core tests

The fixtures directory stores the serializer's exact output plus provenance.
`tests/test_sdk_fixtures.py` checks those bytes and their behavior without Node.
Those tests are recorded-fixture tests, not new SDK executions. The optional
verifier regenerates fixtures with the actual installed SDK each time.
Regenerated fixture hashes must also match the recorded outputs; a difference
requires review rather than silently replacing the compatibility evidence.

The generators and tests are original project code. OpenTelemetry packages are
Apache-2.0; see [NOTICE.md](NOTICE.md). No upstream runtime code is vendored.

## Multi-export suite checks

The verifier also runs the installed CLI against several freshly generated
exports in one baseline suite. It checks complete/reordered suites, omitted and
duplicate cases, a forbidden second export, an ineligible second export, swapped
or missing declarations, unknown cases and protection of the second declaration
from baseline replacement. These remain synthetic, explicitly attested fixtures;
no production coverage declaration is inferred or generated.
