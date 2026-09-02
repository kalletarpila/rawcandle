# Fundamental Delta V1 Phase 5D Deployment Runbook

## Current Production Status

Phase 5D completed on 2026-09-02. Fundamental Delta V1 is active with normalized V2 persistence. The production wrapper is `rawcandle.cli.run_fundamentals_v4_delta_production`; it defaults to dry-run and requires exact paths, locked fingerprints, full history, `--apply`, and `--confirm-production` for writes. The verified deployment record is `fundamentals_v4_delta_v1_phase5d_deployment.md`.

The only authorized future layout is persistence version `V4_FUNDAMENTAL_DELTA_REVISED_HISTORY_V2`, layout fingerprint `001d4d86ff3f279b2c44f497d536883a8f63bf281ee34c9086881e14635997c0`. V1 was never deployed. Production must receive the additive V2 schema directly; do not create, migrate or drop V1 Delta tables.

The following Phase 5C command remains the historical final-rehearsal command:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_delta_phase5c \
  --analysis-db /home/kalle/projects/rawcandle/data/fundamentals_analysis.db \
  --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db \
  --provider-db /home/kalle/projects/rawcandle/data/fundamentals_provider.db \
  --market-db /home/kalle/projects/rawcandle/data/osakedata.db \
  --taxonomy-db /home/kalle/projects/rawcandle/data/analysis.db \
  --destination /home/kalle/projects/rawcandle/temp/fundamentals_v4_delta_phase5d_preflight.db \
  --as-of-date 2026-09-01 \
  --score-model-fingerprint 6d12268b9b3c1b7da3d3b04b5b097afa1e6781a5c7cbc6dece3344a04e54be80 \
  --lifecycle-model-fingerprint db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f \
  --valuation-model-fingerprint 17a9c388647f9e810b9a88b5de1de764a1cb9f406c0f9e4f602da87b285ef62f \
  --delta-model-fingerprint 7cd5ff99c623f047940f296e4b2f7c504dd1f9b868b3079f6ef7d3a3f9b0d49d \
  --full-universe --apply --create-online-copy --verify-idempotency \
  --exercise-company-rebuilds --exercise-failures \
  --output-dir /home/kalle/projects/rawcandle/temp/fundamentals_v4_delta_phase5d_preflight
```

## Preflight And Backup

1. Require clean worktree, reviewed Phase 5D commit and exact branch/HEAD in the deployment record:

```bash
cd /home/kalle/projects/rawcandle
git status --short
git rev-parse HEAD
python3 -m pytest -q tests/test_fundamentals_v4_*.py
```

2. Resolve every path and verify no symlink:

```bash
readlink -f data/fundamentals_analysis.db
test ! -L data/fundamentals_analysis.db
sqlite3 data/fundamentals_analysis.db "PRAGMA quick_check; PRAGMA foreign_key_check;"
```

3. Stop all writers. Create the retained online backup outside `temp` and verify it independently:

```bash
mkdir -p /home/kalle/projects/rawcandle/backups
sqlite3 /home/kalle/projects/rawcandle/data/fundamentals_analysis.db ".backup '/home/kalle/projects/rawcandle/backups/fundamentals_analysis_pre_delta_phase5d.db'"
sha256sum /home/kalle/projects/rawcandle/backups/fundamentals_analysis_pre_delta_phase5d.db
sqlite3 /home/kalle/projects/rawcandle/backups/fundamentals_analysis_pre_delta_phase5d.db "PRAGMA quick_check; PRAGMA foreign_key_check;"
```

Record production size, mtime, SHA-256, schema hash, page/freelist counts and key table counts before proceeding.

## Phase 5D Authorization Gate

Phase 5D added a production command with these hard requirements: exact five production paths, locked four model fingerprints, `--full-universe`, explicit `--apply`, explicit `--confirm-production`, no symlink/alias, no provider call, its own transaction and an artifact directory. Use its actual `--help`; do not substitute a manually edited Phase 5C command.

The authorized command sequence must expose distinct operations for dry-run, additive migration/apply, required identical second apply, quick check and reader spot checks. Run full-history fallback unless a trustworthy upstream changed-company set is proven. Never perform quarter-only replacement.

## Required Deployment Checks

After the first authorized apply:

- persisted row counts must be 50,585 total / 354,095 component / zero Delta-owned Lifecycle / zero Delta-owned Valuation unless upstream source fingerprints changed and the difference is explained;
- Fundamental/Lifecycle/Valuation result fingerprints must match the same-run source package;
- persistence/layout fingerprints must match the locked V2 values and no Valuation JSON may exist;
- every quick-check detail must be empty;
- CRMD and APD must return seven persisted components plus on-demand Lifecycle and Valuation context and exact engine values;
- SQLite quick check must be `ok` and foreign-key violations zero;
- first apply storage growth must be reviewed against the Phase 5C.2 68,038,656-byte rehearsal result and approximately 65 MB design target.

Run the identical apply immediately. It must report zero inserted, deleted and updated total/component rows, unchanged size/page count and the same content fingerprint. Validate one-company and 20-company on-demand context readers separately; they must not create rows or cache tables.

Activate the pipeline only after both applies pass. Insert Delta after Valuation and before Relative Position. Delta failure must leave previous Delta history active, surface pipeline failure, avoid provider calls and leave already committed Score/Lifecycle/Valuation untouched. Relative Position behavior after Delta failure must be explicit in the Phase 5D code review.

Run a no-provider-update pipeline smoke and record every stage, transaction outcome, fingerprint and reader check in `fundamentals_v4_delta_v1_phase5d_deployment.md`.

## Rollback

Rollback criteria include migration/apply exception, quick-check or FK failure, fingerprint mismatch, wrong row counts, any persisted context/JSON, failed idempotency, unexplained storage growth or reader mismatch.

Stop all writers before restoring. Retain the failed production database for diagnosis, then restore through SQLite:

```bash
sqlite3 /home/kalle/projects/rawcandle/backups/fundamentals_analysis_pre_delta_phase5d.db ".backup '/home/kalle/projects/rawcandle/data/fundamentals_analysis_phase5d_restore.db'"
sqlite3 /home/kalle/projects/rawcandle/data/fundamentals_analysis_phase5d_restore.db "PRAGMA quick_check; PRAGMA foreign_key_check;"
```

Only after independent verification may the operator atomically replace the stopped production database using the repository's reviewed deployment procedure. Do not delete or overwrite the retained backup. Record rollback hashes and the final restored production metrics.
