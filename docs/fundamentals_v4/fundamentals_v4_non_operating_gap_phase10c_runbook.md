# Fundamentals V4 Non-Operating Gap Phase 10C Runbook

Status: `PRODUCTION_GATE_IMPLEMENTED_NOT_YET_DEPLOYED`

Phase 10C deploys only candidate package
`0e269e52a63500342df8a08ee2f91552fdc8fb216fa68cfe469bafb6aa8e3c30`
from Phase 10B. The command is dry-run by default. Writes require exact regular
non-symlink production paths, all full model fingerprints, full-universe mode,
the exact expected active package, `--apply --confirm-production`, a clean Git
worktree, the shared Fundamentals maintenance lock, an available SQLite write
lock, sufficient disk space and a verified online backup.

The first deployment must expect rollback package `a36d6903...`. It persists
and reconciles the candidate before atomically changing the complete active
package pointer. A second command must expect the new package and return a
byte-identical `NO_CHANGE`.

The command is:

```text
python3 -m rawcandle.fundamentals.operating_income_v2.phase10c \
  --package-fingerprint <full candidate package fingerprint> \
  --expected-active-package <full expected active package fingerprint> \
  --score-fingerprint <full fingerprint> \
  --lifecycle-fingerprint <full fingerprint> \
  --valuation-fingerprint <full fingerprint> \
  --delta-fingerprint <full fingerprint> \
  --relative-fingerprint <full fingerprint> \
  --diagnostic-fingerprint <full fingerprint> \
  --snapshot-fingerprint <full fingerprint> \
  --full-universe [--apply --confirm-production]
```

Activation-only rollback must hold the same maintenance lock, call
`activate_package` with the complete archived package fingerprint, validate
`assert_v2_active` before commit, and leave all versioned histories in place.
For full restore, stop writers, retain the failed database, validate the
recorded backup hash, restore into a new regular file with
`sqlite3.Connection.backup()`, require `quick_check=ok`, zero foreign-key
violations and the rollback package manifest, then atomically replace the
production analysis database. Never use a live filesystem copy as the only
backup.
