# Release procedure

## Public-review checkpoint

The prepared target is 0.2.0. Keep the release archive private until the owner
authorizes publishing the source to a public branch and draft pull request.
Never treat local tests or an existing main-branch badge as hosted verification.

1. Recheck the intended base and inspect the complete diff. The preparation base
   is `39168cdbae749413542ff5d778c407c203adc568`. If main changes, review the new
   diff and rerun affected checks; do not silently overwrite remote work.
2. With authorization, push the reviewed source to `release/0.2.0` and open a
   draft PR. Do not commit `dist/`, caches, virtual environments or `node_modules/`.
3. Record the exact branch commit SHA. The workflow's push event tests the branch
   commit; a pull-request event can instead test GitHub's synthetic merge commit.
   Verify the recorded `Checked revision` and run `head_sha`, not only a green name.
4. Require all three `test` matrix jobs, `promptfoo`, `loop-engine`, `action`, and the aggregate
   `Release readiness` check to succeed. The aggregate cannot pass when a dependency
   fails, is skipped or is cancelled. Keep the run links and artifact checksums.
5. Re-review any new changes after the checks. A green earlier commit does not
   validate a later edit, rebase, merge or workflow change.

Main was unprotected at preparation time. Configuring branch protection or
required checks is a separate repository-settings decision; the workflow does
not enforce those settings. Recommended required check: `Release readiness`.

## Final publication checkpoint

Merging and publishing a GitHub release are separate actions requiring the
owner's approval of their destination and scope. A draft PR is not approval to
perform them. Publishing a final GitHub release is also the request to upload to
PyPI: `.github/workflows/publish.yml` starts on it (see below). A pre-release
uploads nothing.

After an authorized merge, check CI on the exact final commit on main. If the
final tree differs from the reviewed tree, repeat review and the full checks.

Only then create the approved `v0.2.0` tag/release pointing to that commit. Do not
move or overwrite `v0.1.0`. Include the migration notes.

`publish.yml` refuses to build unless the release tag equals `v` plus the version
in `pyproject.toml`, the tagged commit is on `main`, and the CI check
`Release readiness` passed on that commit. It then builds the wheel and source
archive, repeats the distribution verification, prints SHA-256 checksums, and
uploads through PyPI trusted publishing (no stored password or token). The
build is not byte-reproducible, so a local build has other checksums: the
checksums of the published files are the ones in that workflow run and on PyPI.

Before the first release, the owner:
1. creates the environment `pypi` in the repository settings (Environments),
   with the owner as required reviewer, limited to tags matching `v*`;
2. adds the pending trusted publisher on PyPI: project name
   `agent-trace-gate` (from `pyproject.toml`), owner `homayoun-safarpour`,
   repository `trace-gate`, workflow `publish.yml`, environment `pypi`.

The upload job then waits for the owner's approval in the `pypi` environment.

The CI workflow never deploys, uploads to PyPI, creates a GitHub release or calls
a model/provider. CI does access registries for pinned test tooling and Promptfoo.
