# Build and verify a clean installation

The runtime has no third-party dependencies. Python 3.10, 3.11 and 3.12 are the
CI target versions. CI configuration is not evidence that every target has run;
see the accompanying verification report for the versions actually tested.

## Reproduce the distribution checks

Use a fresh checkout or extracted source archive, with an empty `dist/`
directory, and a disposable virtual environment. On Linux/macOS:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-ci.txt
python -m ruff check src tests scripts integrations
python -m build --no-isolation
python -m pip install --no-index --no-deps --force-reinstall dist/*.whl
python scripts/verify_distribution.py --dist-dir dist
```

`build` first creates a source archive, then builds the wheel from that archive.
The pinned requirements are build/test tools, not runtime dependencies. The
build-system requirement in `pyproject.toml` stays a compatible lower bound;
`--no-isolation` makes this verification use the explicitly installed tool pins.
These version pins are not cryptographic hashes or a supply-chain guarantee.

The verifier:

1. Extracts the source archive into a new temporary directory, rejecting path
   traversal, link members and duplicate paths (including `./` or repeated-separator
   aliases). It validates archive headers before writing any extracted files.
2. Confirms that the source archive and wheel contain identical Python package
   files, then checks that the installed package is non-editable, has no declared runtime
   dependencies, and its Python files match the supplied wheel by SHA-256.
3. Runs the source archive's pytest suite with isolated Python, importlib import
   mode, no `PYTHONPATH`, and automatic pytest plugin loading disabled. Tests and
   example fixtures must actually be present in the source archive.
4. Creates a second virtual environment, installs only the local wheel using
   `--no-index --no-deps`, and repeats the installed-code check.
5. Runs the core and offline-telemetry console-script tests from unrelated
   temporary working directories, using synthetic trajectories and the standard
   library only.
6. Runs the packaged Promptfoo Python wrapper tests against the same isolated
   wheel installation. This does not execute the optional Promptfoo Node runtime;
   use its separate integration verifier for that compatibility check.

Those CLI tests cover help, JSON scoring, freeze/pass, a forbidden second nested
call, rubric drift, unknown trajectory, an empty baseline, malformed evidence,
duplicate call IDs, and avoiding baseline creation/overwrite on invalid input.
They execute recorded JSON checks, not the named tools or any model calls.
Policy, coverage and legacy-baseline behavior is intentionally stricter in 0.2.0;
see [GATE_CONTRACT.md](GATE_CONTRACT.md) before migrating existing pins.

Installed optional Promptfoo dependencies are explicitly excluded from the
source archive. Only its adapter, fixtures, lockfile, notices and evidence are
packaged; the core wheel still declares no runtime dependencies.

The separate Linux x86-64 Promptfoo CI job installs the pinned optional Node
runtime with lifecycle scripts disabled, audits that lock, and runs the real
local-echo verifier against the built wheel. It requires registry access and is
not part of the dependency-free core runtime. Its hosted run must be checked on
the exact commit before claiming publication readiness.

The distribution verifier itself does not fetch packages. The initial tooling install needs
registry access. No OS-level network isolation is claimed.

## Use the installed CLI in another CI job

Place the reviewed wheel in your build artifacts, install it, and run the gate
as an ordinary shell step. A regression is expected to fail that step:

```yaml
- name: Install reviewed trace-gate artifact
  run: python -m pip install --no-index --no-deps artifacts/trace_gate-*.whl
- name: Check agent trajectory
  run: >-
    trace-gate check examples/trajectories/support_good.json
    --rubric examples/rubric.json
    --baseline examples/baselines/support_v1.json
```

The wheel contains the Python package and console entry point, not project
examples. Keep your trajectory, rubric and pinned baseline in your own project.
The source archive includes this repository's examples and documentation.
Do not add `|| true` or `continue-on-error` to the gate. Exit `0` means the
configured score checks passed, not that a trace is authentic or an agent safe.
Exit `2` means a documented gate refusal; see [EXIT_CODES.md](EXIT_CODES.md).

## Troubleshooting

- **Command not found:** activate the environment used for installation, or run
  its `bin/trace-gate` directly (`Scripts/trace-gate.exe` on Windows).
- **Import or source mismatch:** install the exact wheel being checked with
  `--force-reinstall --no-deps`. Editable installs and stale same-version wheels
  intentionally fail verification.
- **More than one distribution found:** move old artifacts aside and build in a
  clean checkout. The verifier refuses to guess between wheels or archives.
- **Missing examples/tests:** use the source archive produced with `MANIFEST.in`.
  The previous packaging omitted examples even while including tests.
- **Rubric or baseline errors:** first reproduce with the supplied synthetic
  examples. Only change/freeze a baseline deliberately after reviewing behavior.

Windows-specific smoke support is included but is not part of the Linux CI
matrix. A local run on one interpreter does not validate the other interpreters.
The isolated runtime uses the platform default venv layout (symlinked Python on
POSIX, copied executables on Windows), including relocatable Python builds.
The prepared package version is 0.2.0. A built version number alone is not proof
of publication or hosted verification. See [RELEASING.md](RELEASING.md) for the
exact-revision review and release procedure.
