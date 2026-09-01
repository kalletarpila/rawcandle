# Lifecycle V1 Revised-History Runbook

## Semantics

Lifecycle V1 answers what each company's lifecycle path looks like under the currently accepted canonical and TTM history. Every row is labeled `REVISED_HISTORY`. Restatements can revise older classifications; this dataset is not an investor-knowable historical record.

The source of truth is `fundamentals_v4.db`. Company replay follows canonical fiscal sequence and uses the exact four quarterly inputs linked by TTM. The pipeline neither reads Score components nor changes Score.

## Phase 2C commands

Plan the full universe without writes:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_lifecycle_revised \
  --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db \
  --full-universe
```

Create a temporary SQLite-safe clone and run the full apply twice:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_lifecycle_revised \
  --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db \
  --destination-db /tmp/rawcandle_lifecycle_phase2c_rehearsal.db \
  --rehearsal-source-analysis-db /home/kalle/projects/rawcandle/data/fundamentals_analysis.db \
  --full-universe --apply \
  --output-json /tmp/rawcandle_lifecycle_phase2c_rehearsal.json
```

The rehearsal checks both rebuild fingerprints, requires zero writes on the second rebuild, runs lifecycle and SQLite quick checks, compares Score fingerprints before/after, and verifies that the read-only production analysis source metadata did not change.

## Schema And Readers

`lifecycle_revised_result` is unique by company, fiscal year, fiscal quarter, model fingerprint and `REVISED_HISTORY`. Replacement computes and validates all rows first, then deletes and inserts only the selected model fingerprint in one transaction. Full rebuild removes obsolete universe rows; filtered refresh replaces only the selected companies' complete histories. Rows for other fingerprints remain.

`RevisedLifecycleRepository` provides `current_company`, `current_universe`, `history` and `fiscal_quarter`. Every call requires `model_fingerprint`. A latest `UNCLASSIFIED` row is returned as `LIFECYCLE_NOT_READY`; readers do not substitute an older state.

## Phase 2D Production Authorization

Production apply requires all of the following guards:

- exact canonical path `/home/kalle/projects/rawcandle/data/fundamentals_v4.db`;
- exact destination `/home/kalle/projects/rawcandle/data/fundamentals_analysis.db`;
- both paths must be ordinary non-symlink paths;
- `--full-universe`;
- `--model-fingerprint db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f`;
- `--apply` and `--confirm-production`.

The confirmation flag fails closed for every other destination. Temporary rehearsal apply remains available without production confirmation. The authorized procedure must:

1. Verify a clean worktree and the approved commit.
2. Record database sizes, mtimes, `PRAGMA quick_check`, Score fingerprint and row counts.
3. Create and validate a timestamped SQLite `backup()` of `fundamentals_analysis.db`.
4. Run the full plan command above and review distributions and fingerprints.
5. Apply the lifecycle schema and full transactional rebuild to the explicit production path.
6. Repeat the identical rebuild and require an unchanged fingerprint with zero row writes.
7. Exercise all four readers and run lifecycle plus SQLite quick checks.
8. Recompute a source sample and reconcile it to persisted rows.
9. Verify the Score fingerprint, rows and representative component values are unchanged.
10. Record final metadata, logs and backup location.

The production command is:

```bash
cd /home/kalle/projects/rawcandle
git status --short
git rev-parse HEAD
stat -c '%n %s %Y' data/fundamentals_v4.db data/fundamentals_analysis.db
sqlite3 -readonly data/fundamentals_v4.db 'PRAGMA quick_check;'
sqlite3 -readonly data/fundamentals_analysis.db 'PRAGMA quick_check;'
sqlite3 -readonly data/fundamentals_analysis.db \
  "SELECT COUNT(*) AS score_rows FROM score_result WHERE model_version='SIMPLE_FUNDAMENTAL_SCORE_V1';"

BACKUP="/home/kalle/projects/rawcandle/backups/fundamentals_analysis.phase2d.$(date -u +%Y%m%dT%H%M%SZ).db"
python3 -c "import sqlite3,sys; s=sqlite3.connect('file:/home/kalle/projects/rawcandle/data/fundamentals_analysis.db?mode=ro',uri=True); d=sqlite3.connect(sys.argv[1]); s.backup(d); d.commit(); d.close(); s.close()" "$BACKUP"
sqlite3 -readonly "$BACKUP" 'PRAGMA quick_check;'

python3 -m rawcandle.cli.run_fundamentals_v4_lifecycle_revised \
  --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db \
  --full-universe \
  --model-fingerprint db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f \
  --output-json /tmp/rawcandle_lifecycle_phase2d_plan.json

python3 -m rawcandle.cli.run_fundamentals_v4_lifecycle_revised \
  --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db \
  --destination-db /home/kalle/projects/rawcandle/data/fundamentals_analysis.db \
  --full-universe \
  --model-fingerprint db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f \
  --apply --confirm-production \
  --output-json /tmp/rawcandle_lifecycle_phase2d_production.json

sqlite3 -readonly data/fundamentals_analysis.db 'PRAGMA quick_check;'
stat -c '%n %s %Y' data/fundamentals_v4.db data/fundamentals_analysis.db
```

Restore on validation failure only after stopping every process that can open the analysis database. Preserve the failed database and restore the verified backup into a new file before an atomic swap:

```bash
cd /home/kalle/projects/rawcandle
mv data/fundamentals_analysis.db "data/fundamentals_analysis.failed.$(date -u +%Y%m%dT%H%M%SZ).db"
python3 -c "import sqlite3,sys; s=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.commit(); d.close(); s.close()" "$BACKUP" data/fundamentals_analysis.restored.db
sqlite3 -readonly data/fundamentals_analysis.restored.db 'PRAGMA quick_check;'
mv data/fundamentals_analysis.restored.db data/fundamentals_analysis.db
```

## Continuous Refresh

The existing Score V1 production run is the final established Fundamentals V4 processing stage. After Score commits and passes integrity checks, it invokes lifecycle revised-history refresh. Canonical and TTM processing therefore precede Score, and lifecycle runs last. Because the current path does not expose a reliable changed-company set, the operational hook uses a deterministic full-universe rebuild. An unchanged source produces zero lifecycle writes.

Lifecycle failure is recorded as `lifecycle_refresh.status=FAILED` in `score_v1_summary.json` and raised as `POST_SCORE_LIFECYCLE_REFRESH_FAILED`. It does not undo the already committed Score result and its own replacement transaction preserves the previously committed lifecycle dataset.

The process stop and restore execution require explicit authorization. Keep the verified backup until the user authorizes removal.
