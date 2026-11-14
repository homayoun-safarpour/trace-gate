# Historical evidence path normalization

These are retained historical run records, not new executions. Absolute checkout
and installation prefixes were replaced with reproducible placeholders:

- `/ORIGINAL_REPO_ROOT`: checkout used for the original verification.
- `/READINESS_REPO_ROOT`: checkout used for the later readiness verification.
- `/INSTALL_ROOT`: installation-test root containing the recorded virtualenv.

To reproduce commands, substitute your own corresponding absolute directories.
A `file:///ORIGINAL_REPO_ROOT/...` entry is a normalized recorded reference,
not a currently accessible file URL. Results, case identifiers, timestamps, assertion outcomes and exit codes are
unchanged. Configuration is unchanged except for normalized paths, including
paths in assertion values. File bytes and checksums necessarily
change when paths are normalized; these copies are not byte-identical raw logs.
This does not remove earlier Git history or retract already published copies.
