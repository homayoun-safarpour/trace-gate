# Transactional baseline writes

Private follow-up to the prepared 0.2.0 candidate. No baseline schema, scoring,
rubric fingerprint, or gate verdict changes are introduced by this patch.

`freeze` and the Python `write_baseline` function no longer truncate the target
file before writing. They serialize the complete JSON, create a private temporary
file in the destination directory, write/flush/sync and close it, then use an
atomic filesystem replacement of the named baseline entry. Readers see the old
complete file or the new complete file on filesystems providing atomic replace.

## Failure behavior

- Serialization, staging-file creation, write, flush, file sync, close or replace
  errors before commit leave the previous baseline bytes intact. A new baseline
  is not installed on those errors. The CLI returns 2 with `FREEZE_REFUSED` and
  does not print a success message.
- Temporary cleanup is attempted on ordinary exceptions and Python-level
  `KeyboardInterrupt`. Cleanup failures or a force-killed process can leave a `.trace-gate-*.tmp`
  staging file. Review that file before removing it; it is not a valid committed
  baseline merely because it exists.
- New parent directories may remain if a later step fails.
- JSON non-finite values fail serialization before filesystem changes. This is
  not a substitute for using `freeze_baseline` to validate a direct API input.

## Linked files and permissions

- Existing symlink outputs, including dangling symlinks, are refused. Select the
  intended real baseline path explicitly. Directories, FIFOs and other nonregular
  destinations are also refused without opening or replacing them.
  This check applies to the final output entry; symlinked parent directories
  follow the operating system's normal path resolution.
- Replacing a hardlink output updates only that named directory entry. Other
  hardlinks retain their original bytes. The CLI's existing protection against
  output aliases of its inputs remains in force.
- The committed file inherits the staging file's private creation permissions
  (owner read/write, `0600`, on POSIX). Old permission bits, ACLs and extended
  attributes are not copied. This deliberately avoids making a new pin more
  broadly readable based on the old file; users sharing generated baselines must
  review the resulting permissions through their normal process.
- The operation needs permission to create and replace entries in the destination
  directory, not just permission to write the old file. A read-only old file can
  be replaced when the directory allows it, following ordinary rename semantics.

## Boundaries

This protects an individual write transaction, not the authenticity of the pin.
It is not locking or compare-and-swap: simultaneous valid writers can replace
each other, with the last completed replacement winning. Keep policy files and
their directories protected and coordinate writers in CI.

The staging file is synced before replacement, but the parent directory is not
synced. Sudden power loss, network-filesystem behavior and hostile concurrent
directory changes are not guaranteed here. There is no attempt to defend against
an attacker who can replace parent directories or control the running process.

Fault-injection and link regressions are in `tests/test_baseline_atomic.py`.
Separate installed-wheel console tests are in `tests/installed_smoke.py`.
