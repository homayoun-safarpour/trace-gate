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
4. Require all three `test` matrix jobs, `promptfoo`, `loop-engine`, and the aggregate
   `Release readiness` check to succeed. The aggregate cannot pass when a dependency
   fails, is skipped or is cancelled. Keep the run links and artifact checksums.
5. Re-review any new changes after the checks. A green earlier commit does not
   validate a later edit, rebase, merge or workflow change.

Main was unprotected at preparation time. Configuring branch protection or
required checks is a separate repository-settings decision; the workflow does
not enforce those settings. Recommended required check: `Release readiness`.

## Final publication checkpoint

Merging, publishing a tag/GitHub release, and publishing to a package registry
are separate actions requiring the owner's approval of their destination and
scope. A draft PR is not approval to perform them.

After an authorized merge, check CI on the exact final commit on main. Build the
release assets from that revision using [INSTALLATION.md](INSTALLATION.md),
validate the wheel and source archive, and record SHA-256 checksums. If the final
tree differs from the reviewed tree, repeat review and the full checks.

Only then create the approved `v0.2.0` tag/release pointing to that commit. Do not
move or overwrite `v0.1.0`. Include the migration notes and matching checksums.
Package-registry publication is not configured by this repository; verify name
ownership, credentials, target registry and approval before adding it.

This workflow never deploys, uploads to PyPI, creates a GitHub release or calls
a model/provider. CI does access registries for pinned test tooling and Promptfoo.
