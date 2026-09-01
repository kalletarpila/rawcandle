# Valuation V1 Phase 3D Production Runbook

## Authorization boundary

This runbook is evidence for a future explicitly authorized Phase 3D. Do not execute it during Phase 3C. The Phase 3C CLI deliberately rejects every resolved production destination, including symlink aliases.

Set a timestamp and create a private backup directory with sufficient free space:

```bash
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP="temp/fundamentals_v4_valuation_phase3d/${STAMP}"
mkdir -p "$BACKUP"
```

## Backup and verification

Use SQLite online backup, not filesystem copy of an open database:

```bash
sqlite3 data/fundamentals_v4.db ".backup '$BACKUP/fundamentals_v4.before.db'"
sqlite3 data/fundamentals_analysis.db ".backup '$BACKUP/fundamentals_analysis.before.db'"
sqlite3 "$BACKUP/fundamentals_v4.before.db" "PRAGMA quick_check;"
sqlite3 "$BACKUP/fundamentals_analysis.before.db" "PRAGMA quick_check; PRAGMA foreign_key_check;"
stat -c '%n %s %Y' data/fundamentals_provider.db data/fundamentals_v4.db data/fundamentals_analysis.db data/osakedata.db > "$BACKUP/production.before.stat"
```

## Mandatory pre-deployment rehearsal command

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_valuation_rehearsal \
  --canonical-source data/fundamentals_v4.db \
  --provider-source data/fundamentals_provider.db \
  --analysis-source data/fundamentals_analysis.db \
  --market-source data/osakedata.db \
  --canonical-destination "$BACKUP/fundamentals_v4.rehearsal.db" \
  --analysis-destination "$BACKUP/fundamentals_analysis.rehearsal.db" \
  --output-dir "$BACKUP/rehearsal" \
  --apply
```

Require 50,585 first-run inserts, zero second-run inserts/deletes, source fingerprint `e552cf0b...`, result fingerprint `46bdde9b...`, both quick checks `ok`, exact-zero gate pass and exact Phase 3A bridge pass.

## Staged production sequence

Phase 3D must add a narrow exact-path authorization surface before any following production write. It must expose the same tested functions and preserve these checkpoints:

1. Stage A-B: authorize the tested additive `migrate_canonical_valuation_copy` only for exact `data/fundamentals_v4.db`, with provider opened read-only. It must add scalar columns plus `v4_common_earnings_provenance`; it must never rebuild, drop, rename, or copy `v4_field_provenance`.
2. Stage C: verify 50,171 canonical common-income rows and 42,596 common-income-ready TTM rows; rerun must change zero rows.
3. Stage D: dry-run `load_canonical_source` and require the rehearsed source fingerprint before analysis migration.
4. Stage E-F: create `valuation_revised_result`, then call `replace_results` for the exact model fingerprint in one analysis-local transaction.
5. Stage G: repeat the same apply and require zero writes plus the rehearsed result fingerprint.
6. Run `quick_check`, reader smoke tests, current distribution and exact-zero audit.
7. Only then add valuation refresh after Score/Lifecycle in the normal pipeline. Pipeline activation code and command do not exist in Phase 3C and must not be invented or executed before Phase 3D review.

Before Stage D require canonical schema version `v4_3c2_additive_provenance`, zero material freelist, a final size close to the rehearsed 288,563,200 bytes, 50,171 common-earnings provenance rows in the dedicated table, and zero logical changes/file growth on an identical second canonical migration. `VACUUM` is neither part of deployment nor rollback.

## Post-deployment checks

```bash
sqlite3 data/fundamentals_v4.db "PRAGMA quick_check; SELECT COUNT(net_income_common) FROM v4_quarter_financials; SELECT SUM(net_income_common_4q_ready) FROM v4_ttm_values;"
sqlite3 data/fundamentals_analysis.db "PRAGMA quick_check; PRAGMA foreign_key_check; SELECT valuation_status,COUNT(*) FROM valuation_revised_result WHERE model_fingerprint='17a9c388647f9e810b9a88b5de1de764a1cb9f406c0f9e4f602da87b285ef62f' GROUP BY valuation_status;"
```

Reader checks must explicitly pass the model fingerprint. Confirm that O is NOT_APPLICABLE, NVDA is FULL and a current NOT_READY row is not replaced by older FULL history.

## Independent rollback

Do not treat the two databases as one transaction. Restore only the failed or rejected stage after stopping writers:

```bash
sqlite3 "$BACKUP/fundamentals_v4.before.db" ".backup 'data/fundamentals_v4.db'"
sqlite3 data/fundamentals_v4.db "PRAGMA quick_check;"
```

```bash
sqlite3 "$BACKUP/fundamentals_analysis.before.db" ".backup 'data/fundamentals_analysis.db'"
sqlite3 data/fundamentals_analysis.db "PRAGMA quick_check; PRAGMA foreign_key_check;"
```

After either restore, rerun production row/fingerprint checks. Do not delete backups until the canonical and analysis checkpoints, second apply and pipeline smoke test are accepted.

The canonical and analysis databases remain independent transactions. Canonical rollback restores its online backup; it does not attempt to reverse additive DDL in place.

## Authorized production CLI

Phase 3D uses `rawcandle.cli.run_fundamentals_v4_valuation_production`. It defaults to dry-run and accepts only the four exact absolute production paths. Every apply requires `--apply`, `--confirm-production`, `--full-universe`, and the locked model fingerprint. Before any database write, the CLI prints the resolved paths and persists them as `<stage>_production_preflight.json` in the output directory. The Score production entrypoint applies the same gate and writes `production_preflight.json` to its artifact directory before its first database write.

Canonical apply:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_valuation_production \
  --stage canonical \
  --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db \
  --provider-db /home/kalle/projects/rawcandle/data/fundamentals_provider.db \
  --analysis-db /home/kalle/projects/rawcandle/data/fundamentals_analysis.db \
  --market-db /home/kalle/projects/rawcandle/data/osakedata.db \
  --model-fingerprint 17a9c388647f9e810b9a88b5de1de764a1cb9f406c0f9e4f602da87b285ef62f \
  --full-universe --apply --confirm-production --output-dir "$BACKUP/canonical-apply"
```

Valuation dry-run uses the same command with `--stage valuation` and without the two write flags. First and second production applies add `--apply --confirm-production`. The CLI persists resolved paths and before/after database evidence for every stage.

The established operational hook remains the Score production path. After Score commits, Lifecycle refresh completes and commits, then Valuation refresh runs with `FULL_UNIVERSE_FALLBACK`. Valuation owns its analysis-local transaction; failure preserves the previous valuation rows and is raised as `POST_LIFECYCLE_VALUATION_REFRESH_FAILED` without undoing Score or Lifecycle.
