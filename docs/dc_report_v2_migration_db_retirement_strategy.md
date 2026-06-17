# dc_report_*_v2 migration and DB retirement strategy

## Executive summary

This is a planning-only step for Canonical Report V2 / `dc_report_*_v2` migration and database retirement. No migration files, runtime code, tests, scheduler behavior, `dc_*` source fact paths, `ec_*` sidecar paths, `ec_source_layer`, `scheduler_config.json`, or database files were changed.

Canonical Report V2 is retired. The V2 hooks are neutralized, the V2 core modules are removed, V2-only documentation is archived, and the temporary retired dev_tools stubs were removed in R2. Migrations `004`-`014` remain unchanged pending a separate migration-history decision.

Recommended default: keep migrations `004`-`014` temporarily as historical inert migrations unless a later compatibility check proves they can be archived, removed, or replaced by tombstones safely.

Phase F note: `rawcandle/cli/preflight_dc_report_v2_db_cleanup.py` now provides a read-only preflight CLI for an explicitly supplied SQLite DB path. It inventories known retired `dc_report_*_v2` tables, row counts, related schema objects, integrity status, foreign-key violations, and preserved current `dc_*` / `ec_*` table presence. It does not modify DBs, create backups, drop tables, run `VACUUM`, or approve cleanup; actual cleanup still requires a separate backup-confirmed prompt.

Phase G note: read-only preflight was run against `/home/kalle/projects/rawcandle/data/analysis.db` and documented in `docs/dc_report_v2_db_preflight_analysis_db.md`. The DB contains 17 known `dc_report_*_v2` tables with 2,341 total rows; integrity and foreign-key checks were clean. No DB cleanup was performed.

Phase H note: backup-confirmed cleanup of the 17 known `dc_report_*_v2` tables from `/home/kalle/projects/rawcandle/data/analysis.db` was completed and documented in `docs/dc_report_v2_db_cleanup_analysis_db.md`. Backup path: `/home/kalle/projects/rawcandle/temp/analysis__before_dc_report_v2_cleanup__20260617T143742Z.sqlite`. No `VACUUM` was run; migrations and runtime code remain unchanged.

Final verification note: combined read-only verification for old `eco_*` and retired `dc_report_*_v2` cleanup is documented in `docs/analysis_db_legacy_cleanup_final_verification.md`. Assessment: `LEGACY_CLEANUP_VERIFIED`.

R2 note: Canonical Report V2 retired dev_tools stubs and their retired-stub test were removed. No migration files, DB files, current `dc_*`, current `ec_*`, `ec_source_layer`, scheduler, dashboard, or legacy Datacenter behavior was changed.

## Current state summary

- Phase B neutralized V2 hooks: `analysis/database_manager.py` no longer applies Canonical Report V2 migrations during general analysis DB initialization, and `dev_tools/run_report_canonical_v2_*.py` entrypoints returned a deterministic retirement error until R2 removed them.
- Phase C removed Canonical Report V2 core modules and direct non-CLI V2 tests.
- Phase D archived V2-only docs under `docs/archive/canonical_report_v2/`.
- Retired dev_tools stubs were removed in R2. Running `dev_tools/run_report_canonical_v2_*` is no longer supported because those files no longer exist.
- Migrations `004`-`014` remain present under `rawcandle/sqlite/migrations/`.
- DB cleanup for `/home/kalle/projects/rawcandle/data/analysis.db` was completed in Phase H after verified backup.

## Migration system findings

Current evidence:

- No current code path was found that applies migrations `004`-`014`.
- `analysis/database_manager.py` now applies only technical signal relevance and Datacenter dashboard enrichment migrations during analysis DB initialization.
- No active migration runner was found that globs every file in `rawcandle/sqlite/migrations`.
- The current `ec_*` sidecar migration runner, `rawcandle/ec_sidecar_migration.py`, uses an explicit `MIGRATION_SQL_PATHS` tuple for `019_create_ec_sidecar_schema.sql` through `024_patch_ec_group_index_counts.sql`.
- No inspected current migration path uses a `schema_migrations` table or `PRAGMA user_version` convention that requires numbered files to be contiguous.
- Migrations `019`-`024` are independent of `004`-`014`; they create or patch current `ec_*` sidecar tables and do not reference `dc_report_*_v2`.
- No current `dc_*` source fact builder/loader reference to `dc_report_*_v2` was found in the targeted searches.
- Tests no longer reference Canonical V2 retired stubs after R2.

## Migration inventory

| Migration file | V2 tables created/modified | Status | Later recommendation |
|---|---|---|---|
| `004_create_datacenter_report_canonical_v2.sql` | Creates `dc_report_run_v2`, `dc_report_context_group_v2`, `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_classification_v2`; creates V2 indexes. | V2-only migration. | Keep unchanged for now; include all created tables in later DB preflight and cleanup planning. |
| `005_add_daily_trigger_inputs_to_report_context_daily_v2.sql` | Alters `dc_report_context_daily_v2`. | V2-only patch migration. | Keep unchanged for now; archive/remove only after migration compatibility decision. |
| `006_add_rolling2_classifier_inputs_to_report_context_window_v2.sql` | Alters `dc_report_context_window_v2`. | V2-only patch migration. | Keep unchanged for now; archive/remove only after migration compatibility decision. |
| `007_add_daily_distance_to_ema10_to_report_context_daily_v2.sql` | Alters `dc_report_context_daily_v2`. | V2-only patch migration. | Keep unchanged for now; archive/remove only after migration compatibility decision. |
| `008_add_daily_formatter_source_fields_to_report_context_v2.sql` | Alters `dc_report_context_group_v2` and `dc_report_context_daily_v2`. | V2-only patch migration. | Keep unchanged for now; archive/remove only after migration compatibility decision. |
| `009_create_report_window_metadata_v2.sql` | Creates `dc_report_valid_signal_date_v2`; creates V2 index. | V2-only migration. | Keep unchanged for now; include table in later DB preflight/drop plan. |
| `010_create_report_ticker_coverage_v2.sql` | Creates `dc_report_watchlist_ticker_v2`, `dc_report_taxonomy_ticker_coverage_v2`; creates V2 indexes. | V2-only migration. | Keep unchanged for now; include tables in later DB preflight/drop plan. |
| `011_create_report_relevance_quality_v2.sql` | Creates `dc_report_technical_relevance_context_v2`, `dc_report_data_quality_summary_v2`; creates V2 indexes. | V2-only migration. | Keep unchanged for now; include tables in later DB preflight/drop plan. |
| `012_create_report_group_progression_v2.sql` | Creates `dc_report_ecosystem_window_change_v2`, `dc_report_group_overheat_progression_v2`, `dc_report_group_relative_change_v2`; creates V2 indexes. | V2-only migration. | Keep unchanged for now; include tables in later DB preflight/drop plan. |
| `013_create_report_timing_freshness_v2.sql` | Creates `dc_report_group_timing_persistence_v2`, `dc_report_ma_break_status_v2`, `dc_report_signal_freshness_v2`; creates V2 indexes. | V2-only migration. | Keep unchanged for now; include tables in later DB preflight/drop plan. |
| `014_create_report_synthetic_event_history_v2.sql` | Creates `dc_report_synthetic_event_history_v2`; creates V2 indexes. | V2-only migration. | Keep unchanged for now; include table in later DB preflight/drop plan. |

## Remaining reference classification

| Path/pattern | Category | Action |
|---|---|---|
| `rawcandle/sqlite/migrations/004_create_datacenter_report_canonical_v2.sql` through `014_create_report_synthetic_event_history_v2.sql` | MIGRATION_ONLY | Keep unchanged until a separate migration-file cleanup decision. |
| `docs/archive/canonical_report_v2/**` | ARCHIVE_DOC_ONLY | Keep as historical context; do not treat as current architecture or runnable runbook. |
| `dev_tools/run_report_canonical_v2_*.py` and `dev_tools/report_canonical_v2_retired.py` | REMOVED_R2 | Removed after compatibility/discoverability window. |
| `tests/test_report_canonical_v2_retired_cli.py` | REMOVED_R2 | Removed with retired stubs. |
| `docs/dc_report_v2_retirement_decision.md` and `docs/dc_report_v2_removal_audit.md` | RETIREMENT_DOC_ONLY | Keep as status and audit trail. |
| `docs/eco_legacy_*` references to `dc_report_*_v2` | RETIREMENT_DOC_ONLY | Keep as historical DB cleanup context; not current V2 runtime evidence. |
| Current `dc_*` source fact tables and docs: `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily`, `dc_group_synthetic_ohlc_daily`, `dc_group_index_daily`, `dc_pipeline_watermark` | CURRENT_PRESERVE | Preserve. These are not Canonical Report V2 readmodels. |
| Current `ec_*` sidecar and `ec_source_layer` paths | CURRENT_PRESERVE | Preserve. They are independent of V2 migrations `004`-`014`. |
| Active runtime code path applying `004`-`014` or writing `dc_report_*_v2` | ACTIVE_RUNTIME_BLOCKER | None found in this planning step. Re-check before any migration-file or DB cleanup. |

## Recommended migration-file policy

### Option A: keep as historical inert migrations

Keep `004`-`014` in `rawcandle/sqlite/migrations` unchanged. They are no longer used by active initialization paths found in this audit, but they preserve historical schema bootstrap ability and avoid changing migration history.

Pros:

- Lowest immediate risk.
- No migration-runner behavior change.
- Preserves historical reproduction capability.
- Avoids ambiguity around numbered migration gaps.

Cons:

- A future or manual full-directory migration workflow could still create obsolete `dc_report_*_v2` tables.
- Obsolete schema files remain in the active migrations directory.

### Option B: archive/remove migrations 004-014 after compatibility checks

Move old migration files to an archive or delete them after confirming no workflow applies `rawcandle/sqlite/migrations/*.sql` wholesale and no bootstrap process expects the historical files.

Pros:

- Removes obsolete V2 schema files from the active migration directory.
- Prevents accidental V2 table creation by broad migration tooling.

Cons:

- Requires a compatibility decision for any manual/full-directory migration workflow.
- Could break historical fresh-DB reproduction.
- Requires targeted tests to confirm no tooling expects numbered-file continuity.

### Option C: replace with tombstone/no-op migrations

Replace `004`-`014` with explicit no-op/tombstone files if filename continuity is needed but V2 schema creation must be prevented.

Pros:

- Keeps filename continuity.
- Makes retirement intent explicit to future readers and broad migration tooling.

Cons:

- Modifies migration history.
- Does not clean up existing DB tables.
- Requires clear documentation so tombstones are not mistaken for DB cleanup.

Recommended decision: choose Option A now. Revisit Option B or C only after DB cleanup planning is complete and after a final broad reference check confirms no active runtime, test, or bootstrap dependency on `004`-`014`.

## Later DB preflight plan

Do not inspect or modify DBs in this planning step. A later read-only preflight must use an explicit DB path and record:

- Target DB path and environment.
- `dc_report_*_v2` table list from SQLite schema metadata.
- Row count for each `dc_report_*_v2` table.
- Indexes, triggers, and views referencing `dc_report_*_v2`.
- `PRAGMA integrity_check`.
- `PRAGMA foreign_key_check`.
- Current `dc_*` source fact table presence, including `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily`, `dc_group_synthetic_ohlc_daily`, `dc_group_index_daily`, and `dc_pipeline_watermark`.
- Current `ec_*` table presence.
- Database file size, `page_count`, and `freelist_count`.
- Confirmation that no scheduler, stock update, refresh, backfill, recovery, report generation, or V2 build/publish/smoke process is running against the target DB.

## Later backup-confirmed DB cleanup plan

Do not run DB cleanup until separately approved.

Backup requirements:

- Use a verified backup method appropriate for SQLite, preferably SQLite backup API or a filesystem copy only after all writers are stopped.
- Record source DB path, backup path, timestamp, file sizes, and verification results.
- Open the backup read-only and run `PRAGMA integrity_check` before modifying the source DB.
- Keep WAL/SHM handling explicit; do not ignore active WAL state.

Rollback plan:

- Stop all writers.
- Replace the modified DB with the verified backup using the same WAL/SHM assumptions documented for the backup.
- Re-run read-only integrity and foreign-key checks after restore.

Drop plan:

- Drop only explicitly approved V2 tables discovered by the preflight.
- Preserve current `dc_*` source fact tables.
- Preserve current `ec_*` sidecar tables.
- Preserve legacy Datacenter reports and scheduler behavior.
- Do not run `VACUUM` or `VACUUM INTO` unless separately approved.

Post-cleanup checks:

- Confirm no approved `dc_report_*_v2` tables remain.
- Re-run `PRAGMA integrity_check`.
- Re-run `PRAGMA foreign_key_check`.
- Verify current `dc_*` source fact table presence.
- Verify current `ec_*` table presence.
- Run targeted scheduler and `ec_source_layer` tests without running scheduler jobs or DB-writing production commands.

## Things not touched

- Migrations `004`-`014`.
- Migrations `019`-`024`.
- Runtime code.
- Tests.
- Scheduler runtime behavior.
- `scheduler_config.json`.
- Current `dc_*` source fact builders/loaders.
- Current legacy Datacenter reports.
- Current `ec_*` sidecar files.
- `ec_source_layer`.
- Database files, WAL/SHM files, exports, temp artifacts, or backups.

## Recommended next Codex step

Phase H: prepare a separate backup-confirmed cleanup prompt only if the user approves table removal. Do not drop tables without verified backup, explicit drop list, rollback plan, and post-cleanup checks.

## Searches and files inspected

Searches run:

- `rg -n "004_create_datacenter_report_canonical_v2|005_add_daily_trigger_inputs|006_add_rolling2|007_add_daily_distance|008_add_daily_formatter|009_create_report_window_metadata|010_create_report_ticker_coverage|011_create_report_relevance_quality|012_create_report_group_progression|013_create_report_timing_freshness|014_create_report_synthetic_event_history" rawcandle analysis tests docs dev_tools`
- `rg -n "dc_report_.*_v2|dc_report_run_v2|dc_report_context|dc_report_classification|dc_report_valid_signal_date|dc_report_watchlist|dc_report_taxonomy|dc_report_technical|dc_report_data_quality|dc_report_group|dc_report_timing|dc_report_synthetic" rawcandle analysis tests docs dev_tools`
- `rg -n "sqlite/migrations|migrations|migration|schema_migrations|PRAGMA user_version|MIGRATION_SQL_PATHS|glob" rawcandle analysis tests docs`
- `find rawcandle/sqlite/migrations -maxdepth 1 -type f | sort`

Files inspected:

- `analysis/database_manager.py`
- `rawcandle/ec_sidecar_migration.py`
- `dev_tools/report_canonical_v2_retired.py`
- `dev_tools/run_report_canonical_v2_daily_markdown_smoke.py`
- `dev_tools/run_report_canonical_v2_all_outputs_smoke.py`
- `tests/test_report_canonical_v2_retired_cli.py`
- `rawcandle/sqlite/migrations/004_create_datacenter_report_canonical_v2.sql`
- `rawcandle/sqlite/migrations/005_add_daily_trigger_inputs_to_report_context_daily_v2.sql`
- `rawcandle/sqlite/migrations/006_add_rolling2_classifier_inputs_to_report_context_window_v2.sql`
- `rawcandle/sqlite/migrations/007_add_daily_distance_to_ema10_to_report_context_daily_v2.sql`
- `rawcandle/sqlite/migrations/008_add_daily_formatter_source_fields_to_report_context_v2.sql`
- `rawcandle/sqlite/migrations/009_create_report_window_metadata_v2.sql`
- `rawcandle/sqlite/migrations/010_create_report_ticker_coverage_v2.sql`
- `rawcandle/sqlite/migrations/011_create_report_relevance_quality_v2.sql`
- `rawcandle/sqlite/migrations/012_create_report_group_progression_v2.sql`
- `rawcandle/sqlite/migrations/013_create_report_timing_freshness_v2.sql`
- `rawcandle/sqlite/migrations/014_create_report_synthetic_event_history_v2.sql`
