# Fundamentals V4 Phase 13C Production Migration

Outcome: **PHASE 13C COMPLETE — UNIVERSE AND DEPENDENCY FOUNDATION ACTIVE IN PRODUCTION**.

Phase 13C deployed the Phase 13B operational-universe and dependency foundation to production on 2026-09-11. The migration was explicitly limited to additive foundation schema and dependency metadata. It did not add tickers, change taxonomy content, fetch provider data, recalculate scores, refresh Relative Position or Relative Valuation economics, regenerate production reports, or change Scheduler behavior.

Primary artifact directory:

`temp/fundamentals_v4_phase13c_production/20260911T164127Z_APPLY`

## Production Scope

Production writes were limited to:

- `/home/kalle/projects/rawcandle/data/fundamentals_v4.db`
- `/home/kalle/projects/rawcandle/data/fundamentals_analysis.db`

The provider, market and taxonomy databases were backed up and verified but not logically changed:

- `/home/kalle/projects/rawcandle/data/fundamentals_provider.db`
- `/home/kalle/projects/rawcandle/data/osakedata.db`
- `/home/kalle/projects/rawcandle/data/analysis.db`

The Phase 13C preflight recorded Git HEAD `e4c1238240b25d6151d7568258b7282be808ba79` on branch `chore/ignore-backups`, with clean worktree and upstream state `ahead 2`. Production apply was run only after the dry-run outcome `PHASE 13C BLOCKED — NO PRODUCTION WRITE PERFORMED`.

## Baseline Verification

The production baseline matched the Phase 12E and Phase 13B contract before the write:

- Active Operating-Income V2 package: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- Active Relative Valuation snapshot date: `2026-09-10`
- Active Relative Valuation snapshot: `7edd6226bd9cc0346f24c1f92d3d4c1dabb67df18e9d4f3210550530daf68324`
- Canonical TTM rows: `87319`
- Diagnostic evaluations: `698552`
- Provider-disabled pipeline smoke outcome: `NO_CHANGE`

## Backups and Rollback

Verified online backups were created under:

`/home/kalle/projects/rawcandle/backups/fundamentals_v4_phase13c_20260911T164256Z`

| Role | Backup | Size | SHA-256 | quick_check |
| --- | --- | ---: | --- | --- |
| canonical | `fundamentals_v4.before_phase13c.db` | 636272640 | `c217dfeb3c16ebfd0091e4977d0458e69271846ab0f1d06ebfd8920942496236` | ok |
| analysis | `fundamentals_analysis.before_phase13c.db` | 1534025728 | `94a9c219a7caeeb4f27282b4de14cc7dc53a5d6c5f49259c96461739765ef2e7` | ok |
| provider | `fundamentals_provider.before_phase13c.db` | 922521600 | `cbb2387479cb36aec563fe2a43b2ab5cf3059427a82cf5ca8c5481dda4bce44a` | ok |
| market | `osakedata.before_phase13c.db` | 1970778112 | `c89d6e85eb693d0c5cf22db42bc004c89b421a77b40ce13a88fa5b343dd83702` | ok |
| taxonomy | `analysis.before_phase13c.db` | 10674839552 | `524f3357a17aa6d3529db902dc350726e6353c7dfb5ccecc80f836bf24814c90` | ok |

Rollback rehearsal restored every backup into safe copy files, verified `quick_check=ok`, and reported `logical_equal=true` for canonical, analysis, provider, market and taxonomy databases.

## Operational Universe

The authoritative production operational universe is now active in `fundamentals_v4.db`.

- Members: `2458`
- Active securities represented: `2453`
- Zero-active companies retained for historical continuity: `16`
- Multi-active companies requiring later explicit selection: `11`
- Universe version id: `7f50deaa1eb83a536ae7152a759b185a`
- Universe economic fingerprint: `d21fff93d3f01a4056c0f6ed765f2e5f6169aafdb5f1e708b026d6c5ec7d4bdb`

The count relationship remains exactly explained: 2,458 companies minus 16 zero-active companies equals 2,442 companies with at least one active security; the 11 multi-active companies add one extra represented active security each, yielding 2,453 active securities.

## Dependency Foundation

The migration installed and populated the additive foundation tables rehearsed in Phase 13B:

- `fundamentals_operational_universe_version`
- `fundamentals_operational_universe_active_version`
- `fundamentals_operational_universe_member`
- `fundamentals_operational_universe_member_alias`
- `fundamentals_result_dependency`
- `relative_valuation_snapshot_dependency`

The first apply recorded dependency outcome `APPLIED`, `rows_changed=7`, `rv_snapshots=2`, `rp_snapshots=2`, `packages=1`, and status `COMPATIBLE`.

Taxonomy dependency identity remained:

- Source version: `DC_TAXONOMY_FULL_V2_1`
- Source fingerprint: `97847c7a7237070b195c476b742753c24e89804ac78ac2e8522bd92feeedd8bc`
- Economic fingerprint: `6f1e167ceafd77b0c50fa68c41c38020cfcd67381319ccd2b70c48f432fde975`
- Presentation fingerprint: `f7b3dfe7e78de922ef452bbeadd61ccecb436f586ac7831de5dc0d93aa176686`

## Compatibility Evidence

Reader compatibility checks after migration:

- Active 2026-09-10 Relative Valuation snapshot `7edd6226bd9cc0346f24c1f92d3d4c1dabb67df18e9d4f3210550530daf68324`: `COMPATIBLE`
- Wrong operational universe fingerprint: `OPERATIONAL_UNIVERSE_MISMATCH`
- Wrong taxonomy economic fingerprint: `ECONOMIC_TAXONOMY_MISMATCH`
- Phase 11E non-future guard for report date `2026-09-09`: selected 2026-09-08 snapshot `b7f786edfa7632a320df5281182761471a15281ca1c518d2d729bbfab36dc5df`, state `COMPATIBLE`

Snapshot/UI smoke completed for NVDA, AMZN, CRMD, APD, BTAI and HLX. Each first generation returned `CREATED`, each repeated generation returned `NO_CHANGE`, and the batch status was `COMPLETED`.

## Stability Evidence

The required second apply passed with `second_no_change=true`. Schema, universe and dependencies all reported `NO_CHANGE`, and canonical/analysis fingerprints were unchanged after the second run.

Economic immutability passed. The monitored economic tables and production reports fingerprint were unchanged before and after the migration. The provider-disabled pipeline smoke returned:

- Outcome: `NO_CHANGE`
- Logical changes: `0`
- Economic fingerprint: `3fdd93b6fedcdf7384728016c55fd955a2c44dfbc03c4618a758fd1601c84b27`
- Physical fingerprint: `63fb7191889c22835ebef895dd1afbca455998345b7d4495a1382a9b747324fa`

Measured rollback-journal/WAL peak during apply:

- Maximum any sidecar: `49760` bytes
- canonical-journal: `49760` bytes
- analysis-journal: `29240` bytes
- WAL files: `0` bytes

## Test Diagnosis

The full suite after production apply initially had two failures, both stale test expectations rather than production reader defects.

First, `test_presentation_identity_is_separate_from_active_economic_bundle` still expected the old Phase 10B package fingerprint. Production correctly uses the Phase 12E ten-year operational package `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`.

Second, `test_future_report_uses_active_snapshot_without_refresh_or_database_write` generated a report for `2026-09-09`, which correctly selected the non-future 2026-09-08 Relative Valuation snapshot `b7f786edfa7632a320df5281182761471a15281ca1c518d2d729bbfab36dc5df`. The test then compared the result against `company_by_ticker()` without a snapshot id, which reads the active 2026-09-10 snapshot `7edd6226bd9cc0346f24c1f92d3d4c1dabb67df18e9d4f3210550530daf68324`. The expectation was corrected to fetch the persisted company row using the same snapshot id selected by `report_snapshot_metadata("2026-09-09")`.

No production data was modified for the test corrections.

## Deferred Work

Phase 13C intentionally did not implement Add Tickers or Fundamentals Taxonomy Update. Those remain Phase 13D backend/CLI work and must use the now-active dependency foundation rather than treating `security.active` or limited taxonomy coverage as sufficient authority.
