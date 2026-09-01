# Fundamentals V4 Valuation V1 Phase 3D Deployment

## Outcome

Phase 3D deployed `ABSOLUTE_VALUATION_SCORE_V1` on 2026-09-01. The additive canonical common-earnings contract, TTM common earnings, `valuation_revised_result`, full revised history, readers, and the Score -> Lifecycle -> Valuation production hook are active. No provider update ran, osakedata remained read-only, no rollback was needed, and no commit was pushed.

The code gate commit is `6dc8127fc10246d0bc00e7eaa6c001681b5c256b`. Deployment evidence is retained under `temp/fundamentals_v4_valuation_phase3d/20260901T160342Z/`.

## Production Paths

| Role | Resolved path | Pre size / mtime ns | Post size / mtime ns |
|---|---|---:|---:|
| Canonical destination | `/home/kalle/projects/rawcandle/data/fundamentals_v4.db` | 269,901,824 / 1,788,161,831,846,195,291 | 288,563,200 / 1,788,278,801,036,152,326 |
| Analysis destination | `/home/kalle/projects/rawcandle/data/fundamentals_analysis.db` | 253,874,176 / 1,788,265,476,181,173,290 | 302,678,016 / 1,788,279,035,957,180,642 |
| Provider read-only source | `/home/kalle/projects/rawcandle/data/fundamentals_provider.db` | 546,754,560 / 1,788,157,472,860,058,036 | unchanged |
| Osakedata read-only source | `/home/kalle/projects/rawcandle/data/osakedata.db` | 1,963,397,120 / 1,788,241,471,425,823,593 | unchanged |

All paths were exact, absolute, distinct, non-symlink paths. The CLIs printed and persisted resolved-path preflight evidence before each apply. Available disk was 623,094,894,592 bytes against a conservative 2,000,000,000-byte peak requirement. `lsof` found no active handles on the four database files.

## Verified Backups

| Database | Retained backup | Bytes | SHA-256 | Check |
|---|---|---:|---|---|
| Canonical | `/home/kalle/projects/rawcandle/backups/fundamentals_v4.phase3d.20260901T160342Z.db` | 269,901,824 | `86214043559060aaab319aa8448b16b7227df428a1c45fd8e41e2111b35990ff` | independent open, `quick_check=ok`, FK 0 |
| Analysis | `/home/kalle/projects/rawcandle/backups/fundamentals_analysis.phase3d.20260901T160342Z.db` | 253,874,176 | `15c80c124c95964cb283cdf8daa8d2d66e2d7b8254f29e9a7ed1267a0172afa1` | independent open, `quick_check=ok`, FK 0 |

After stopping writers, the exact authorized restore commands are:

```bash
python3 -c 'from pathlib import Path; from rawcandle.fundamentals.valuation.phase3c import sqlite_backup; sqlite_backup(Path("/home/kalle/projects/rawcandle/backups/fundamentals_v4.phase3d.20260901T160342Z.db"), Path("/home/kalle/projects/rawcandle/data/fundamentals_v4.db"))'
python3 -c 'from pathlib import Path; from rawcandle.fundamentals.valuation.phase3c import sqlite_backup; sqlite_backup(Path("/home/kalle/projects/rawcandle/backups/fundamentals_analysis.phase3d.20260901T160342Z.db"), Path("/home/kalle/projects/rawcandle/data/fundamentals_analysis.db"))'
```

## Commands Used

Every production stage used these exact paths and gates:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_valuation_production \
  --stage canonical \
  --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db \
  --provider-db /home/kalle/projects/rawcandle/data/fundamentals_provider.db \
  --analysis-db /home/kalle/projects/rawcandle/data/fundamentals_analysis.db \
  --market-db /home/kalle/projects/rawcandle/data/osakedata.db \
  --model-fingerprint 17a9c388647f9e810b9a88b5de1de764a1cb9f406c0f9e4f602da87b285ef62f \
  --full-universe --apply --confirm-production \
  --output-dir /home/kalle/projects/rawcandle/temp/fundamentals_v4_valuation_phase3d/20260901T160342Z/canonical-first
```

The identical second canonical apply changed only `--output-dir` to `canonical-second`. Valuation dry-run changed `--stage` to `valuation`, used output `valuation-dry-run`, and omitted both write flags. The first and second valuation applies used outputs `valuation-first` and `valuation-second` with both write flags.

## Canonical Migration

The first apply added one canonical column and two TTM columns, backfilled 50,171 canonical common-earnings rows, inserted 50,171 restricted provenance rows, and changed 42,596 TTM rows. Schema version is `v4_3c2_additive_provenance`, applied at `2026-09-01T16:06:38Z`.

| Stage | Bytes | Pages | Freelist | Elapsed seconds |
|---|---:|---:|---:|---:|
| Before | 269,901,824 | 65,894 | 0 | 0 |
| Schema | 269,901,824 | 65,898 | 0 | 0.048 |
| Canonical backfill | 287,531,008 | 70,225 | 0 | 0.734 |
| TTM rebuild | 288,509,952 | 70,450 | 0 | 0.278 |
| Clean close | 288,563,200 | 70,450 | 0 | 0 |

The second canonical apply added zero columns and made zero canonical, provenance, or TTM changes. Size, page count, freelist, schema timestamp, and mtime remained unchanged. The legacy `v4_field_provenance` retained rootpage 24, its SQL, 602,940 rows, and hash `bfdb79d65aea59b7e5f4846eaa18b709c66ab83d41d07150f2a48c064c2fbd53`. Existing `net_income` and `ttm_net_income` hashes were unchanged. No table rebuild or `VACUUM` occurred.

## Valuation Apply

The dry-run left analysis size and mtime unchanged and produced the locked source and result fingerprints. The first analysis-local transaction created the revised table and indexes and inserted 50,585 rows. Schema version is `V4_VALUATION_REVISED_HISTORY_V1`, applied at `2026-09-01T16:10:20Z`.

The mandatory second apply reported:

```text
rows before:  50,585
rows after:   50,585
inserted:          0
deleted:           0
unchanged:    50,585
```

Analysis stayed at 302,678,016 bytes, 73,896 pages, freelist 0, and the same mtime. The old `valuation_result` remains unchanged and empty. Logical duplicates are zero.

## Locked Results

```text
Model fingerprint:  17a9c388647f9e810b9a88b5de1de764a1cb9f406c0f9e4f602da87b285ef62f
Source fingerprint: e552cf0b01a1e649d6269a968c4ea7e96b903acccce9c8b73d21d7c6cd230e47
Result fingerprint: 46bdde9bd6711180b9bc1b75462c42c39e2ff5498ee93ad0c711cbbf88e69a18
```

Historical status counts are 39,117 FULL, 2,903 NOT_APPLICABLE, and 8,565 NOT_READY from 50,585 observations and 2,451 companies. FULL score mean is 28.7020; P10/P25/P50/P75/P90 are 0 / 0 / 24.1677 / 48.3320 / 70.9997. Score bands `[0,20) / [20,40) / [40,60) / [60,80) / [80,100]` contain 17,949 / 8,301 / 6,357 / 4,001 / 2,509 rows. Exact zero is 11,595 and exact 100 is 382.

Current universe at 2026-09-01 with 180-day freshness contains 2,431 companies: 2,246 FULL, 139 NOT_APPLICABLE, and 46 NOT_READY. Mean is 27.7606; P10/P25/P50/P75/P90 are 0 / 0 / 24.6288 / 46.3136 / 65.7706. Bands contain 1,003 / 521 / 413 / 213 / 96 rows. Exact zero is 631 and exact 100 is 6.

The zero-score hard invariant passed: all 11,595 exact-zero observations have nonpositive EBIT, FCF, and common earnings. Component score distribution details and all reason distributions are in `postdeployment_validation.json`.

## Readers And Regressions

Reader spots passed for NVDA (FULL, 29.5989), AAOI zero-score operating company (FULL, 0), Agilent mature profitable and leveraged (FULL, 29.1396), AIP growth (FULL, 1.0883), AAOI net cash, Realty Income `O` (NOT_APPLICABLE, `UNSUPPORTED_REIT_MODEL`), AEI non-REIT Real Estate (FULL), CME Financial Data & Stock Exchanges (FULL, 29.7819), and ACXP NOT_READY (`ENTERPRISE_VALUE_NONPOSITIVE`). NVDA history returned 21 rows; fiscal-quarter lookup returned 2027 Q2; a wrong fingerprint returned zero rows.

Persisted Score remained 50,585 rows and 354,095 components with fingerprint `47add84845743b33bc9e43d35296871890c1e850d0c9ca23b10e3b10c861f7bc`. A read-only Score recalculation had identical result values, statuses, and all component scores. Its full audit fingerprint differed only because four FTFT dilution evidence rows now include the 2023-02-01 split event added to osakedata after the persisted Score run; split evidence is evidence-only and production Score was not rewritten. This reconciliation is in `score_recalculation_reconciliation.json`.

Lifecycle read-only replay planned zero deletes and zero inserts with all 50,585 rows unchanged. Model fingerprint remains `db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f`, and result fingerprint remains `43fee8da28ea454236263c93a09f2a3fe089473509fc4d926b7cc3aae811729c`.

Canonical and analysis `quick_check` returned `ok`; both FK checks returned zero rows. Provider and osakedata byte size and mtime stayed unchanged throughout deployment.

## Pipeline Activation

The established Score entrypoint is dry-run by default and requires the exact production paths, valuation fingerprint, full-universe flag, `--apply`, and `--confirm-production`. On apply, Score commits first, Lifecycle refresh runs and commits second, then Valuation runs with `FULL_UNIVERSE_FALLBACK` in its own transaction. Focused tests verify ordering, unchanged-input zero writes, schema inclusion, and rollback of Valuation schema/data on an injected failure. A Valuation failure is raised as `POST_LIFECYCLE_VALUATION_REFRESH_FAILED`; it preserves the previous Valuation set and does not undo already committed upstream models. No scheduler or live provider run was added.

## Verification And Risk

Before production, 383 Fundamentals V4 tests passed, focused tests passed, `compileall` passed, and `git diff --check` passed. The same gates are rerun after this record is written. The full repository suite was not run because the complete Fundamentals V4 group covers the changed schema, migration, Score, Lifecycle, Valuation, reader, and pipeline surface.

Rollback was not needed. Backups are retained. The remaining operational limitation is deliberate full-universe Valuation refresh until the pipeline exposes a reliable changed-company set. Current Valuation is filing-date revised history; no daily snapshot or relative ranking is active.
