# Fundamentals V4 current-state audit

Audit date: 2026-09-19

## Current V4 architecture

RawCandle owns the active Fundamentals stack. The production databases are:

- `data/fundamentals_provider.db`: provider runs, observations, and Sharadar source data.
- `data/fundamentals_v4.db`: company/security identity, canonical quarters, field provenance, TTM values, structural context, and the operational universe.
- `data/fundamentals_analysis.db`: Score, revised Lifecycle and Valuation, Delta, diagnostics, Relative Position V2, Relative Valuation, and active model/package metadata.

Read-only inputs owned outside Fundamentals are:

- `data/osakedata.db`, including authoritative Sector/Industry data in `ticker_meta`.
- `data/analysis.db`, including the active `dc_ecosystem` taxonomy.

The main current paths are the Fundamentals Administration commands and UI, the V4 provider/canonical bootstrap and TTM commands, `operating_income_v2.full_rebuild`, Relative Position V2, Relative Valuation, and the company snapshot UI service. Administration reads `ticker_meta` and the active taxonomy; it does not own either source.

## Active tables

`fundamentals_provider.db` contains `provider_run`, `provider_observation`, `sharadar_fundamental_observation`, `sharadar_ticker_metadata`, `sharadar_action_metadata`, and `schema_version`.

`fundamentals_v4.db` contains company/security identity and aliases, CIK and fiscal-calendar identity, canonical V4 quarters and financials, field and working-capital provenance, TTM contract/input/value tables, structural event/regime tables, operational-universe tables, `phase13g2_applied_plan`, and `schema_version`.

`fundamentals_analysis.db` contains model runs; Score; revised Lifecycle and Valuation; Delta; eight-flag diagnostics; the current `operating_income_v2` package manifest/evidence; Relative Position V2 snapshots, coverage, taxonomy dependency, audit and active snapshot; Relative Valuation snapshots/results/history/audit and active snapshot; active model-family metadata; and `schema_version`.

The `operating_income_v2_*` and `relative_position_v2_*` names identify current analytical models inside the V4 architecture. They are not legacy V2 databases or compatibility tables.

## Removed legacy artifacts

- Removed the scheduler's SwingMaster Fundamentals post-step, configuration, summaries, log parsing, and tests. RawCandle no longer invokes an external V1/V2 Fundamentals runtime.
- Removed the orphan Yahoo quarter-state writer and its `fundamentals_fin.db` / `fundamentals_usa.db` paths, service callback, recovery counters, and tests. No RawCandle reader consumed that state.
- Removed TTM's read-only SwingMaster V3 parity path and artifacts.
- Removed the V3 CIK schema-prototype reader, prototype CLI, retired V3 fixture tests, pytest exclusion marker, and Phase 13D retired-test audit machinery.
- Removed the completed V1 schema-cleanup utility and its tests; production already satisfies the final schema.
- Removed unused Phase 10B and Phase 11C rehearsal modules and the obsolete Phase 11C CLI.
- Removed zero-byte stray files named `fundamentals_analysis.db`, `data/fundamentals.db`, `data/fundamentals_analysis_2.db`, `data/fundamentals_canonical.db`, and `data/fundamentals_taxonomy.db`.
- Removed all `temp/` files dated 2026-09-18 or earlier with explicit operator approval. `temp/` decreased from approximately 121 GB to 30 MB; only current-day artifacts remain.

## Preserved shared components

- `rawcandle.fundamentals.operating_income_v2` is the current V4 analysis model and full-rebuild implementation.
- Relative Valuation's internal V1 rule/version labels describe the current RV model and are still consumed by V4.
- `schema/prototype.py` retains shared provider-ingest, canonicalization, validation, hashing, CSV, and JSON helpers imported by current V4 bootstrap and rebuild code. Its direct V3 database path and prototype runner were removed.
- Phase-named modules directly imported by the Administration/full-rebuild path remain required even though their names record implementation history.
- `data/osakedata.db.ticker_meta` remains the sole Sector/Industry authority, and `data/analysis.db` remains the active taxonomy authority.

## Database verification

All three production Fundamentals databases returned `ok` from `PRAGMA quick_check`. Their `schema_version` rows are `v4_6a2_operating_working_capital`. Direct schema inventory found no retired `lifecycle_result` or `valuation_result` tables and no V1/V3 Fundamentals tables. `data/osakedata.db.ticker_meta` exists, contains 5,035 rows, and its database also passed `PRAGMA quick_check`.

Repository-wide legacy-reference searches were run across production code, tests, configuration, scripts, and database paths. A focused suite covering all changed Fundamentals, scheduler, stock-update, and recovery contracts passed 393 tests. Full-suite collection succeeded with 2,580 tests and no import or collection errors. A broader 707-test Fundamentals run was stopped after it proved to be an unnecessarily expensive database-copy integration run; the focused suite covers the changed boundaries.

## Retained recovery material

Historical rollback databases under `backups/` are ignored, non-runtime artifacts. They remain on disk because the operator approved age-based `temp/` cleanup, not destruction of production rollback history. The newest Administration rollback is `backups/fundamentals_admin_production/20260919T113359Z_add_tickers_8bbcda32e218_production_38f7bfac`.

## Classification

- `CURRENT_V4`: the three production databases, their listed tables, Administration, provider/canonical/TTM processing, current analysis models, snapshot serving, and their tests.
- `SHARED_REQUIRED`: `osakedata.db`, `analysis.db`, shared schema helpers, and phase-named modules reached by current full rebuilds.
- `HISTORICAL_DOCUMENTATION`: phase reports under `docs/fundamentals_v4` that do not affect runtime.
- `AMBIGUOUS`: historical rollback retention policy. No backup was deleted without explicit approval.

## Final state

The active RawCandle runtime, active database schemas, configuration, commands, and tests now use only the current Fundamentals V4 architecture plus the explicitly identified shared components. This is not an unqualified repository-wide deletion claim because ignored historical rollback databases remain under `backups/` pending a separate retention decision; they are not referenced by active runtime code.
