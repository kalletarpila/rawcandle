# eco legacy migration cleanup strategy

## Executive summary

This is a planning-only step for old `eco_*` legacy migration and database cleanup. No migration files, runtime code, tests, scheduler behavior, `ec_*`/`dc_*` paths, `scheduler_config.json`, or database files were changed.

Recommendation: keep migrations `015`-`018` in place for now as historical inert migrations. Do not delete, archive, or neutralize them until a separate migration-runner compatibility decision is approved. The current `ec_*` sidecar migration path is already independent from `015`-`018`, so there is no immediate technical pressure to remove the old files.

Existing database `eco_*` tables should be handled later through a separate approved DB cleanup phase with explicit backups, read-only preflight counts, a reviewed drop order, integrity checks, and rollback instructions.

Phase 3B note: `rawcandle/cli/preflight_eco_legacy_db_cleanup.py` now provides a read-only preflight CLI for an explicitly supplied SQLite DB path. It inventories `eco_*` tables, row counts, related schema objects, integrity status, foreign-key violations, and page/freelist counts. It does not modify DBs, create backups, drop tables, run VACUUM, or approve cleanup; actual cleanup still requires a separate backup-confirmed prompt.

Phase 3C note: read-only preflight was run against `/home/kalle/projects/rawcandle/data/analysis.db` and documented in `docs/eco_legacy_db_preflight_analysis_db.md`. The DB contains 16 old `eco_*` tables with 72,931 rows; integrity and foreign-key checks were clean. No DB cleanup was performed.

Phase 3D note: backup-confirmed old `eco_*` table cleanup was completed for `/home/kalle/projects/rawcandle/data/analysis.db` and documented in `docs/eco_legacy_db_cleanup_analysis_db.md`. A verified backup was created at `/home/kalle/projects/rawcandle/temp/analysis__before_eco_legacy_cleanup__20260617T132223Z.sqlite`; no `VACUUM` was run, and migrations remain unchanged.

## Current removal state

- Old V3/eco scheduler execution was neutralized.
- Old V3/eco CLI entrypoints and direct CLI tests were removed.
- Old V3/eco core modules and direct core tests were removed.
- Old V3/eco docs were archived under `docs/archive/old_v3_eco/`.
- Remaining old V3/eco references are expected in migrations `015`-`018`, archive docs, audit/status docs, and allowed `v3_reports_*` scheduler compatibility fields.
- Current `ec_*` sidecar, `ec_source_layer`, `dc_*` source facts, and legacy Datacenter reports remain current paths.

## Migration System Findings

The current `ec_*` sidecar migration runner is `rawcandle/ec_sidecar_migration.py`.

Findings:

- `ec_sidecar_migration.py` does not discover migrations by globbing every file in `rawcandle/sqlite/migrations`.
- It uses an explicit `MIGRATION_SQL_PATHS` tuple containing only `019_create_ec_sidecar_schema.sql` through `024_patch_ec_group_index_counts.sql`.
- No `schema_migrations` table or `PRAGMA user_version` tracking was found in the inspected `ec_*` migration path.
- Numbering is used in filenames for ordering and readability, but the active `ec_*` runner order is defined by the explicit Python tuple.
- Removing migrations `015`-`018` would not affect `apply_ec_sidecar_migration(...)` directly, because that runner does not reference them.
- Removing migrations `015`-`018` would remove fresh-DB bootstrap ability for the old `eco_*` schema, which may still matter for historical reproduction or any undiscovered manual workflows.
- Migrations `019`-`024` do not depend on `eco_*` tables. They create or patch `ec_*` tables and foreign keys reference `ec_*` tables only.
- Tests exercise the `ec_*` migration path through `apply_ec_sidecar_migration(...)` and `_apply_ec_sidecar_migration_to_connection(...)`; they do not require migrations `015`-`018`.
- The write-capable `run_ec_source_layer_build` path applies `ec_*` migrations after creating a backup. The refresh path intentionally does not import or run `apply_ec_sidecar_migration`.

## Migration Inventory

| Migration file | Tables created/modified | Current status | Later recommended action |
|---|---|---|---|
| `015_create_eco_base_dimensions_v3.sql` | Creates `eco_ecosystem`, `eco_taxonomy_version`, `eco_entity`, `eco_taxonomy_entity_relation`, `eco_watchlist`, `eco_watchlist_member`, `eco_report_window`; seeds `eco_report_window`. | Old `eco_*` legacy schema only. | Keep for now; later archive/remove only after compatibility decision. |
| `016_create_eco_core_facts_v3.sql` | Creates `eco_report_run`, `eco_entity_window_snapshot`, `eco_entity_metric_value`, `eco_entity_coverage`, `eco_quality_summary`. | Old `eco_*` legacy schema only. | Keep for now; later archive/remove only after DB cleanup strategy is approved. |
| `017_create_eco_signal_event_facts_v3.sql` | Creates `eco_signal_observation`, `eco_signal_relevance`, `eco_entity_event`. | Old `eco_*` legacy schema only. | Keep for now; later archive/remove with `015`-`018` set. |
| `018_create_eco_classification_decision_v3.sql` | Creates `eco_classification_decision`. | Old `eco_*` legacy schema only. | Keep for now; later archive/remove with `015`-`018` set. |
| `019_create_ec_sidecar_schema.sql` | Creates `ec_ecosystem`, `ec_taxonomy_version`, `ec_entity`, `ec_entity_alias`, `ec_membership`, `ec_watchlist`, `ec_watchlist_member`. | Current `ec_*` sidecar. | Preserve. |
| `020_harden_ec_sidecar_schema.sql` | Creates `ec_signal_run`, `ec_signal_calendar`; additional hardening is applied in Python. | Current `ec_*` sidecar. | Preserve. |
| `021_patch_ec_signal_calendar_p0_fields.sql` | SQL file is a marker/comment; SQLite-safe additive column/index patching is in `ec_sidecar_migration.py`. | Current `ec_*` sidecar patch. | Preserve. |
| `022_create_ec_fact_tables.sql` | Creates `ec_ticker_signal_daily`, `ec_group_signal_daily`, `ec_group_synthetic_ohlc_daily`, `ec_group_index_daily`, `ec_pipeline_watermark`. | Current `ec_*` sidecar. | Preserve. |
| `023_patch_ec_fact_schema_for_dc_parity.sql` | SQL file is a marker/comment; additive fact-column patching is in `ec_sidecar_migration.py`. | Current `ec_*` sidecar patch. | Preserve. |
| `024_patch_ec_group_index_counts.sql` | SQL file is a marker/comment; additive `ec_group_index_daily` count patching is in `ec_sidecar_migration.py`. | Current `ec_*` sidecar patch. | Preserve. |

## Remaining Reference Classification

| Path/pattern | Category | Action |
|---|---|---|
| `rawcandle/sqlite/migrations/015_create_eco_base_dimensions_v3.sql` through `018_create_eco_classification_decision_v3.sql` | MIGRATION_ONLY | Keep unchanged until a separate migration-file cleanup decision. |
| `docs/archive/old_v3_eco/**` | ARCHIVE_DOC_ONLY | Keep as historical context; not current architecture. |
| `docs/eco_legacy_removal_audit.md` | AUDIT_STATUS_ONLY | Keep as audit trail and phase status. |
| `rawcandle/scheduler/runner.py`, `rawcandle/scheduler/config.py`, `rawcandle/cli/run_stock_update_scheduler.py` `v3_reports_*` / `datacenter_v3_reports_*` fields | COMPATIBILITY_FIELD_ONLY | Keep until a separate config/summary compatibility removal decision. |
| `tests/test_stock_update_scheduler_runner.py`, `tests/test_stock_update_scheduler_cli.py` `v3_reports` assertions | COMPATIBILITY_FIELD_ONLY | Keep while scheduler compatibility fields remain. |
| `docs/datacenter_legacy_report_generation_reference.md` `v3_reports.*` summary mentions | COMPATIBILITY_FIELD_ONLY | Update only if compatibility fields are later removed. |

No unexpected ACTIVE_RUNTIME reference to old `eco_*` builders, query layer, report renderer, or CLIs was found in this planning step.

## Migration 015-018 Decision Options

### Option A: keep as historical inert migrations

Keep `015`-`018` in `rawcandle/sqlite/migrations` unchanged. They are no longer used by active `ec_*` sidecar migration code, but they preserve historical schema bootstrap capability and avoid changing migration history.

Pros:

- Lowest immediate risk.
- No migration-runner behavior change.
- Preserves old database reproduction capability for audit/history.
- Avoids ambiguity around numbered migration gaps.

Cons:

- Fresh databases can still get old `eco_*` tables if someone manually applies all SQL files by filename.
- The repository still contains obsolete schema files until a later cleanup.

### Option B: archive/remove migrations 015-018 and adjust runner/tests if needed

Move old migration files to an archive or delete them after confirming no workflow applies `rawcandle/sqlite/migrations/*.sql` wholesale.

Pros:

- Removes stale schema files from the active migrations directory.
- Prevents accidental old `eco_*` bootstrap by broad migration tooling.

Cons:

- Requires a compatibility decision for any manual/full-directory migration workflow.
- Could break historical fresh-DB reproduction.
- Requires tests/checks that no tooling expects contiguous numbered files.

### Option C: replace with explicit tombstone/no-op migrations

Replace `015`-`018` with no-op/tombstone files that document removal while preserving filenames/order.

Pros:

- Keeps filename continuity if a broad migration runner is introduced later.
- Makes removal intent explicit.

Cons:

- Modifies migration history.
- Existing databases with old tables would not be cleaned up by no-op files.
- Requires careful documentation so tombstones are not mistaken for DB cleanup.

Recommended decision: choose Option A now. Defer Option B or C until after DB preflight confirms where old `eco_*` tables still exist and after a separate decision about whether historical bootstrap from `015`-`018` should remain possible.

## Later DB Cleanup Plan

Do not run DB cleanup until separately approved.

Preconditions:

- Confirm exact target DB path and environment.
- Confirm the DB is not production unless there is explicit production approval.
- Confirm no running scheduler, refresh, backfill, stock update, or report process is using the DB.
- Confirm current `ec_*` sidecar and `dc_*` legacy reporting tests/checks pass before cleanup.
- Confirm old `eco_*` code paths remain removed and no ACTIVE_RUNTIME references reappear.

Backup requirements:

- Create a full filesystem copy of the DB before any writes.
- Preserve related WAL/SHM state correctly by stopping writers first or using SQLite backup APIs.
- Record source DB path, backup path, timestamp, file sizes, and checksums.
- Verify the backup can be opened read-only before modifying the source DB.

Read-only preflight checks:

- List old tables with `SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'eco_*' ORDER BY name`.
- Count rows for every `eco_*` table.
- List indexes/triggers/views that reference `eco_*`.
- Check `PRAGMA foreign_key_check`.
- Check `PRAGMA integrity_check`.
- Record `page_count`, `freelist_count`, and database file size.

Drop-table plan:

- Do not disable safety controls implicitly; run only from an approved SQL script.
- Drop dependent old fact tables before dimensions. A conservative order is:
  - `eco_signal_relevance`
  - `eco_signal_observation`
  - `eco_entity_event`
  - `eco_classification_decision`
  - `eco_entity_window_snapshot`
  - `eco_entity_metric_value`
  - `eco_entity_coverage`
  - `eco_quality_summary`
  - `eco_report_run`
  - `eco_watchlist_member`
  - `eco_watchlist`
  - `eco_taxonomy_entity_relation`
  - `eco_report_window`
  - `eco_entity`
  - `eco_taxonomy_version`
  - `eco_ecosystem`
- Use `DROP TABLE IF EXISTS` only after backup and preflight are complete.

Post-cleanup integrity checks:

- Re-run old-table list and confirm no `eco_*` tables remain.
- Re-run `PRAGMA foreign_key_check`.
- Re-run `PRAGMA integrity_check`.
- Run targeted `ec_*` and `dc_*` smoke checks.
- Run scheduler summary tests without running scheduler jobs against production.

Rollback plan:

- Stop all writers.
- Replace modified DB with verified backup.
- Restore WAL/SHM handling according to the chosen backup method.
- Re-run read-only integrity checks against restored DB.

VACUUM warning:

- Dropping tables may not reduce file size immediately.
- `VACUUM` rewrites the database, requires additional disk space, and is a separate high-risk operation that should require explicit approval.
- Consider `VACUUM INTO` a new file only after backup and disk-space checks.

## Checks Before Actual Migration-File Cleanup

- `rg -n "015_create_eco|016_create_eco|017_create_eco|018_create_eco|eco_" rawcandle tests docs`
- `rg -n "MIGRATION_SQL_PATHS|sqlite/migrations|glob|schema_migrations|user_version" rawcandle tests`
- `pytest -q tests/test_ec_sidecar_schema.py tests/test_ec_fact_schema.py`
- `pytest -q tests/test_plan_ec_source_layer_build_cli.py tests/test_plan_ec_source_layer_refresh_cli.py tests/test_plan_ec_source_layer_backfill_cli.py`
- `pytest -q tests/test_run_ec_source_layer_build_cli.py`
- Fresh temporary DB smoke using `apply_ec_sidecar_migration` only, not production DBs.

## Checks Before Actual DB Table Cleanup

- Read-only old-table inventory and row counts.
- Read-only `PRAGMA integrity_check` and `PRAGMA foreign_key_check`.
- Confirm backup exists and opens read-only.
- `pytest -q tests/test_stock_update_scheduler_runner.py -k "v3_reports or ec_source_layer or datacenter_pipeline"`
- `pytest -q tests/test_stock_update_scheduler_cli.py -k "v3_reports or summary or datacenter"`
- `pytest -q tests/test_plan_ec_source_layer_build_cli.py tests/test_plan_ec_source_layer_refresh_cli.py tests/test_plan_ec_source_layer_backfill_cli.py`
- Targeted `ec_*` loader/schema tests against temp DBs only.

## Things Not Touched In This Step

- Migrations `015`-`018`.
- Migrations `019`-`024`.
- Runtime code.
- Tests.
- Scheduler runtime behavior.
- Scheduler config shape.
- `ec_*` sidecar files.
- `dc_*` legacy Datacenter report files.
- Production DBs and local DB files.
- `scheduler_config.json`.

## Recommended Next Codex Step

Run the read-only preflight CLI against an explicitly chosen DB path, review the reported `eco_*` table row counts and integrity status, then decide whether to prepare a separate backup-confirmed cleanup prompt. Do not execute cleanup or table drops until that preflight output is reviewed and a separate cleanup prompt is approved.
