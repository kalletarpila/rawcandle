# Relative Position V1 Phase 4D Deployment Runbook

## Hard gate

Do not deploy from Phase 4C alone. Its CLI deliberately rejects every production destination and has no production-confirmation flag. Phase 4D must first add and test a narrow production wrapper around `ensure_schema`, `apply_snapshot`, readers, and `quick_check`. Do not invent or substitute an unreviewed SQL or Python one-liner.

Required production sequence:

```text
provider/canonical update
-> TTM
-> Fundamental Score
-> Lifecycle
-> Absolute Valuation at Filing
-> Relative Position full current snapshot
```

Relative Position runs at most once after a completed daily Fundamentals cycle, in its own transaction. A failure must be visible operationally and must not roll back already committed upstream stages.

## Preflight

1. Require a clean worktree and reviewed Phase 4D commit: `git status --short` and `git rev-parse HEAD`.
2. Resolve and record all production paths with `realpath`. Reject symlinks and aliases.
3. Record SHA-256, size, nanosecond mtime, schema hash, page count, freelist, and Score/Lifecycle/Valuation row counts.
4. Create timestamped SQLite online backups of every writable production database. Open each backup read-only and require `PRAGMA quick_check='ok'` and zero `PRAGMA foreign_key_check` rows.
5. Keep the Phase 4C evidence directory and commit hash in the deployment record.

## Verified rehearsal command

This command shape is verified against the implemented `--help`. It remains non-production and is the final mandatory rehearsal before Phase 4D authorization:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_relative_position_phase4c \
  --analysis-source /home/kalle/projects/rawcandle/data/fundamentals_analysis.db \
  --canonical-source /home/kalle/projects/rawcandle/data/fundamentals_v4.db \
  --market-source /home/kalle/projects/rawcandle/data/osakedata.db \
  --taxonomy-source /home/kalle/projects/rawcandle/data/analysis.db \
  --analysis-destination /home/kalle/projects/rawcandle/temp/fundamentals_v4_relative_position_phase4d_preflight/fundamentals_analysis_rehearsal.db \
  --as-of-date YYYY-MM-DD \
  --model-fingerprint 983dc38a2805806d4e2709a6956f51bf9cb06ebb61fdb3d9e78344bca58cd7e2 \
  --full-universe --apply --create-online-backup --verify-idempotency \
  --exercise-changed-source --exercise-failures \
  --output-json /home/kalle/projects/rawcandle/temp/fundamentals_v4_relative_position_phase4d_preflight/report.json
```

Require Phase 4B fingerprints/counts, a zero-write second apply, all rollback checks, bounded retention, CRMD values, and unchanged source evidence.

## Production execution

After the Phase 4D production wrapper exists, verify its exact command against its own `--help` and add that captured output plus the exact invocation to the deployment record before execution. The wrapper must require exact production paths, the locked model fingerprint, full-universe scope, an explicit apply flag, and a separate production confirmation token. Until those controls exist, stop here.

The authorized run must perform, in order:

1. read-only full calculation and fingerprint comparison;
2. Relative Position schema migration in its own transaction;
3. first full snapshot apply;
4. reusable `quick_check`;
5. identical second apply requiring zero result inserts/deletes and zero pointer changes;
6. CRMD and representative reader checks;
7. production database quick/foreign-key checks and post-deployment evidence capture.

Only after those checks pass may the daily hook be enabled after Absolute Valuation. Run one scheduler smoke cycle and verify that unchanged input is a bulk no-op.

## Rollback

Before pipeline activation, rollback means disable the new wrapper/hook and restore the verified online backup if schema or active data is invalid. After a successful schema deployment, a failed refresh normally requires no database restore because atomic activation preserves the previous active snapshot.

Restore from backup only for failed integrity checks, unexpected changes outside Relative Position objects, or an invalid active snapshot that cannot be corrected by reactivating the retained previous complete snapshot. Stop upstream writers, preserve the failed database and logs, restore with SQLite online backup, reopen read-only, and rerun quick/foreign-key checks before service resumption.

Retain the pre-deployment backup until at least one successful daily cycle and explicit owner acceptance. The deployment record must contain commands, commit, operator, timestamps, before/after evidence, backup evidence, fingerprints, row counts, durations, reader checks, idempotency result, hook status, and rollback decision.
