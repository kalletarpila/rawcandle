# Fundamental Delta V1 Phase 5D Production Deployment

## Outcome

Fundamental Delta V1 was deployed successfully on 2026-09-02. The normalized V2 revised-history layout is active in `/home/kalle/projects/rawcandle/data/fundamentals_analysis.db`.

- deployment window start: `2026-09-02T10:08:27Z`
- final verification completed: `2026-09-02T10:27:50Z`

Production order is now:

```text
provider/canonical -> TTM -> Fundamental Score -> Lifecycle
-> Absolute Valuation at Filing -> Fundamental Delta V2
-> Relative Position current snapshot
```

No provider update and no push occurred. Rollback was not required.

## Git And Tests

- branch: `chore/ignore-backups`
- Phase 5C.2 commit: `f0794e78f2775d9c74f77c2617a0a972d1813d26`
- reviewed Phase 5D code commit: `dca34a9f41cdd016d1518095912da03dca63cee3`
- pre-deployment worktree: clean
- focused production, Delta persistence, and Relative Position tests: 43 passed
- complete Fundamentals V4 group: 520 passed in 51.42 seconds
- `compileall`: passed
- `git diff --check`: passed
- push: not performed

The code commit was created before the first production write.

## Authorization Contract

Production writes require all of the following:

- exact five absolute production paths;
- regular non-symlink files and distinct resolved paths;
- locked Score, Lifecycle, Valuation, and Delta model fingerprints;
- persistence `V4_FUNDAMENTAL_DELTA_REVISED_HISTORY_V2`;
- layout `001d4d86ff3f279b2c44f497d536883a8f63bf281ee34c9086881e14635997c0`;
- full-history scope;
- explicit `--apply` and `--confirm-production`;
- expected economic source and package fingerprints.

Relative paths, symlinks, normalized aliases, wrong fingerprints, partial history, and missing confirmation are rejected. Complete-company rebuild remains an internal supported persistence operation, but the Phase 5D production CLI authorizes only full history.

## Preflight

All paths resolved exactly as expected and were owned by `kalle`, mode `0644`, regular non-symlink SQLite files. SQLite headers, `quick_check`, and foreign keys passed. Analysis journal mode was `delete`, with no final or pre-deployment analysis WAL/SHM files.

Free space was `586,976,763,904` bytes. This covered the retained backup, enlarged analysis database, temporary journal growth, artifacts, and a large safety margin.

Pre-deployment analysis state:

| Metric | Value |
|---|---:|
| Size | 322,220,032 bytes |
| Page count | 78,667 |
| Freelist | 0 |
| Schema hash | `9f047307ea684956c86f209b0473380f01b1077b9c6c222dcbfc00ae2b791a5d` |
| SHA-256 | `3c56f082817584dedb4f4c5712380f646a960f802cd639fb879d37088b472ab7` |
| Score rows | 50,585 |
| Lifecycle rows | 50,585 |
| Valuation rows | 50,585 |
| Relative Position result rows | 13,737 |
| Delta objects | 0 |

No V1 Delta object existed.

## Backup And Restore

Retained online backup:

`/home/kalle/projects/rawcandle/backups/fundamentals_analysis_pre_delta_phase5d_20260902T100827Z.db`

- size: 322,220,032 bytes
- SHA-256: `7e9c84f6eca2e39e795066ee3404846402f7365d3c94f8bc2849cc596b34fb77`
- `quick_check`: `ok`
- foreign-key violations: 0
- Score/Lifecycle/Valuation rows: 50,585 each
- Relative Position result rows: 13,737
- Delta objects: 0

Verified restore staging commands:

```bash
sqlite3 /home/kalle/projects/rawcandle/backups/fundamentals_analysis_pre_delta_phase5d_20260902T100827Z.db \
  ".backup '/home/kalle/projects/rawcandle/data/fundamentals_analysis_phase5d_restore.db'"
sqlite3 /home/kalle/projects/rawcandle/data/fundamentals_analysis_phase5d_restore.db \
  "PRAGMA quick_check; PRAGMA foreign_key_check;"
sha256sum /home/kalle/projects/rawcandle/data/fundamentals_analysis_phase5d_restore.db
```

Writers must be stopped before restore. The independently verified staging database may replace production only through the reviewed atomic replacement procedure. The retained backup must not be overwritten or deleted.

## Locked Fingerprints

| Contract | Fingerprint |
|---|---|
| Delta model | `7cd5ff99c623f047940f296e4b2f7c504dd1f9b868b3079f6ef7d3a3f9b0d49d` |
| Layout | `001d4d86ff3f279b2c44f497d536883a8f63bf281ee34c9086881e14635997c0` |
| Fundamental source | `c9402322dc4ecc731a8c084e16471be03d0183fd55618a7faf696a61b02ce9ba` |
| Fundamental result | `6c811ee39d0fd6cc88873c6aec8b30743449e2ffda0348ed22b019bf8d338f2d` |
| Lifecycle source | `3be63bb8403e43bc383914bb3c7bd9ffff115691c2aef0fb7b83d6ddd303c689` |
| Lifecycle result | `24cd7ead3ba0e5e945355e0a203d2cb4dd31eb94f5bceca2180ed2cc70b4a7c0` |
| Valuation source | `9b09434e1baa094b62b11e9792f7b6e781cd79fa2a3d7bbbe8af31d451273d9f` |
| Valuation result | `cfb056f0f27e98c90fa11d908eb7af0bce6f749b11ecb4a0f7ff4573f2ba31f1` |
| Economic package | `c94b25c4a11195f2fdb7c021231187ae126143421b01e407cdcfcd9249453bb3` |
| Physical content | `f6beb12f7bf13f425b21a1031cf7cdc4cf41d63367c64878382c97f4b5cd639c` |

## Commands And Artifacts

All commands used these common exact arguments:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_delta_production \
  --analysis-db /home/kalle/projects/rawcandle/data/fundamentals_analysis.db \
  --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db \
  --provider-db /home/kalle/projects/rawcandle/data/fundamentals_provider.db \
  --market-db /home/kalle/projects/rawcandle/data/osakedata.db \
  --taxonomy-db /home/kalle/projects/rawcandle/data/analysis.db \
  --as-of-date 2026-09-01 \
  --score-model-fingerprint 6d12268b9b3c1b7da3d3b04b5b097afa1e6781a5c7cbc6dece3344a04e54be80 \
  --lifecycle-model-fingerprint db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f \
  --valuation-model-fingerprint 17a9c388647f9e810b9a88b5de1de764a1cb9f406c0f9e4f602da87b285ef62f \
  --delta-model-fingerprint 7cd5ff99c623f047940f296e4b2f7c504dd1f9b868b3079f6ef7d3a3f9b0d49d \
  --persistence-version V4_FUNDAMENTAL_DELTA_REVISED_HISTORY_V2 \
  --layout-fingerprint 001d4d86ff3f279b2c44f497d536883a8f63bf281ee34c9086881e14635997c0 \
  --fundamental-source-fingerprint c9402322dc4ecc731a8c084e16471be03d0183fd55618a7faf696a61b02ce9ba \
  --lifecycle-source-fingerprint 3be63bb8403e43bc383914bb3c7bd9ffff115691c2aef0fb7b83d6ddd303c689 \
  --valuation-source-fingerprint 9b09434e1baa094b62b11e9792f7b6e781cd79fa2a3d7bbbe8af31d451273d9f \
  --economic-package-fingerprint c94b25c4a11195f2fdb7c021231187ae126143421b01e407cdcfcd9249453bb3 \
  --full-universe --output-dir OUTPUT_DIR OPERATION_FLAGS
```

Operations were run in this order:

1. Dry-run: no operation flags.
2. Migration: `--apply --confirm-production --migrate-only`.
3. Migration idempotency: the identical migration flags again.
4. First apply: `--apply --confirm-production`.
5. Deep replay: `--deep-replay` without `--apply`.
6. Required second apply: `--apply --confirm-production`.
7. Pipeline smoke: `--apply --confirm-production --pipeline-smoke --relative-position-model-fingerprint 983dc38a2805806d4e2709a6956f51bf9cb06ebb61fdb3d9e78344bca58cd7e2`.

Deterministic JSON artifacts are under:

`/home/kalle/projects/rawcandle/temp/fundamentals_v4_delta_phase5d/20260902T100827Z/`

## Dry-Run

The complete dry-run took 50.57 seconds for package calculation. It produced zero changes to all five databases and matched Phase 5C.2 exactly:

- 50,585 total endpoints;
- 354,095 component rows;
- zero persisted Lifecycle and Valuation rows;
- physical content fingerprint `f6beb12f...639c`;
- all expected economic source/result/package fingerprints.

Readiness reconciliation:

| Scope | QoQ | 2Q | YoY |
|---|---:|---:|---:|
| Historical ready | 27,490 | 25,210 | 20,717 |
| Current-fresh ready | 2,187 | 2,179 | 2,149 |

Current-fresh endpoints were 2,441. Lifecycle 2Q context ready was 2,385 and Valuation 2Q diagnostic ready was 2,221. Maximum total reconciliation error was `3.907985046680551e-14`.

## Migration

The additive migration created only:

- `fundamental_delta_package`;
- `fundamental_delta_status`;
- `fundamental_delta_reason`;
- `fundamental_delta_component_type`;
- `fundamental_delta_result`;
- `fundamental_delta_component`;
- `idx_fundamental_delta_current`;
- `idx_fundamental_delta_cross_section`.

It removed no object, rebuilt no table, ran no `VACUUM`, and created no V1, Lifecycle-context, Valuation-diagnostic, cache, or JSON object. The identical second migration added and removed zero objects and left size, page count, mtime, schema hash, and SHA-256 unchanged.

## First Apply

The first apply completed in 12.16 seconds after package calculation:

- total inserted: 50,585;
- component inserted: 354,095;
- all update/delete counts: 0;
- Delta-owned Lifecycle/Valuation rows: 0;
- routine quick check: 5.35 seconds, no details;
- SQLite quick check: `ok`;
- foreign-key violations: 0.

The database grew by 68,038,656 bytes from pre-migration production to 390,258,688 bytes. Storage matched rehearsal:

| Object group | Bytes |
|---|---:|
| Components | 49,897,472 |
| Totals | 13,148,160 |
| Two indexes | 3,330,048 |
| Package and codebooks | 16,384 |

## Routine Check And Deep Replay

Routine daily validation is separate from the explicit deep replay. It checks the model/package/layout, codebooks, row fingerprints, seven-component relationship, finite ready values, NULL versus zero, 1/2/4-quarter endpoint references, arithmetic reconciliation, SQLite integrity, foreign keys, metadata, and physical content fingerprint. It does not rebuild authoritative economic results. Measured routine duration was 5.29-5.35 seconds.

The deployment deep replay rebuilt the package read-only in 49.69 seconds, then compared all persisted rows in 15.47 seconds:

- endpoints compared: 50,585;
- components compared: 354,095;
- mismatches: 0;
- maximum reconciliation error: `3.907985046680551e-14`;
- result writes: 0;
- all five before/after database fingerprints unchanged.

## Required Second Apply

The identical second apply returned `NO_CHANGE`:

- total inserts/updates/deletes: 0/0/0;
- component inserts/updates/deletes: 0/0/0;
- totals unchanged: 50,585;
- components unchanged: 354,095;
- size, page count, freelist, mtime, schema hash, SHA-256, fingerprints, and readers unchanged.

## Reader And Context Verification

The production reader checks verified current company, full history, one endpoint, current universe, fiscal-quarter cross-section, total plus seven components, all three independent horizons, exact zero versus NULL, deterministic ordering, and rejection of wrong Delta/Lifecycle/Valuation fingerprints.

Representative values matched exactly:

| Ticker | QoQ | 2Q | YoY |
|---|---:|---:|---:|
| CRMD | -2.4822450134938663 | -3.11564573300889 | -2.8940667320374303 |
| APD | -26.7023531089393 | 5.376062770577377 | -4.330330445282925 |

Both returned seven components and on-demand Lifecycle and Valuation contexts. CRMD also verified a YoY Lifecycle transition from `DISTRESSED` to `SCALING`.

Additional read-only examples:

- all three total horizons ready: company 2312, FY2026 Q2;
- QoQ/2Q ready and YoY unavailable: company 2104, FY2023 Q4;
- total unavailable but component diagnostic ready: company 888, FY2023 Q3, `BALANCE_SHEET_RESILIENCE`;
- exact-zero QoQ Delta: company 121, FY2024 Q4;
- invalid 2Q fiscal chain: company 858, FY2023 Q2;
- Lifecycle not-ready: `ABEO`, prior Lifecycle unavailable;
- Valuation not-ready: `AAT`, `VALUATION_FULL_REQUIRED`;
- price-dominated Valuation example: `ABNB`, 2Q score change -8.5067;
- fundamentals-dominated Valuation example: `A`, 2Q score change +1.9545.

Lifecycle and Valuation contexts remained on demand; no context cache or copy table was created.

## Pipeline Smoke

The no-provider smoke demonstrated:

```text
Absolute Valuation SOURCE_READY, zero writes
-> Fundamental Delta NO_CHANGE, zero total/component writes
-> Relative Position NO_CHANGE, zero result/coverage/snapshot writes
```

The Relative Position active snapshot remained `42efd2f3d42e019a21dee2fb03acf9b1cc698502b189e930ec83e24ac135c1ff`. One bounded Relative Position refresh-audit row was added, increasing that audit table from 3 to 4 rows. This changed analysis SHA-256 and mtime but did not change database size, page count, active snapshot, Score, Lifecycle, Valuation, Delta, or Relative Position bulk content. Deep replay was not invoked. No provider download occurred.

The pipeline implementation attempts Relative Position independently after a Delta failure, preserves the previous transactional Delta history, and reports the overall post-Valuation stage as failed. A Relative Position failure occurs after Delta's independent commit and cannot corrupt Delta.

## Final Integrity

Final analysis state:

| Metric | Value |
|---|---:|
| Size | 390,258,688 bytes |
| Page count | 95,278 |
| Freelist | 0 |
| Schema hash | `e0b484386fad4a643bd14c9a4a646e63954e34badfc6d2493c7edb5aab56b504` |
| SHA-256 after smoke audit | `55b22d0fa0357aff6b85d21fd5fac7af8961d7c46bc03d644487e02c5483d456` |
| Delta total rows | 50,585 |
| Delta component rows | 354,095 |

Final source SHA-256 values matched preflight:

| Database | SHA-256 |
|---|---|
| Canonical | `2e4bc3d99c1eca1d1b28eaacffe581fad61f6a2ef7ead7dee2eeae1a0338ee10` |
| Provider | `17660df9f00837fbb52668aff17144d1b167aae4458dfa1a3c057701924b6d9c` |
| Market/osakedata | `a09ef0c20c0c159f722037276903ad891948755bf6de244c4b4bf2f0d00ef57b` |
| Taxonomy | `16614df785ea1d4a497bcca495298d61dba8e65fe322bbf236d80d85a714736c` |

All production databases and the retained backup returned `quick_check=ok` and zero foreign-key violations. No analysis WAL/SHM remained. Score, Lifecycle, and Valuation stayed at 50,585 rows with their original fingerprints. The final schema contains only normalized V2 Delta data and no V1 or persisted context objects.

## Rollback Decision And Remaining Risks

Rollback criteria were not met, so production was not restored.

Remaining operational facts:

- history is currently revised, not PIT;
- taxonomy/sector classification is current-state, not PIT-versioned;
- a full daily package build measured about 50 seconds and routine integrity about 5.3 seconds;
- Relative Position intentionally appends one bounded audit row per refresh check;
- only the analysis database is writable in this stage; provider, canonical, market, and taxonomy remain read-only inputs.

The retained backup remains available for rollback.
