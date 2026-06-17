# dc_dashboard Legacy Removal Audit

## Executive summary

Assessment: `ACTIVE_AND_ENTANGLED_CURRENT_DASHBOARD_ENRICHMENT`.

The `dc_dashboard_*` name is not a safe remove-by-prefix target. Repository evidence shows five current `dc_dashboard_*_daily` analysis-layer enrichment tables, active migrations for them, write-capable dev_tools, read-only audit/dev_tools, a dashboard input builder that reads them, scheduler configuration for `reports` versus `enrichment` dashboard source modes, and scheduler tests that enforce the current dashboard/enrichment compatibility surface.

Phase F note: `rawcandle/cli/preflight_dc_dashboard_legacy_db_cleanup.py` now provides a read-only preflight CLI for an explicitly supplied SQLite DB path. It distinguishes the five current `_daily` enrichment tables from old snapshot-style dashboard tables, does not modify DBs, and does not approve cleanup. Actual cleanup still requires explicit DB path confirmation, reviewed preflight output, verified backup, rollback plan, and approved drop plan.

Analysis DB preflight note: read-only preflight for `/home/kalle/projects/rawcandle/data/analysis.db` is documented in `docs/dc_dashboard_legacy_db_preflight_analysis_db.md`. Assessment: `NO_DASHBOARD_SNAPSHOT_CLEANUP_NEEDED`; no old snapshot-style dashboard tables or unknown `dc_dashboard%` tables were found, and the five current `_daily` enrichment tables were present.

Need audit follow-up: [dc_dashboard_enrichment_need_audit.md](/home/kalle/projects/rawcandle/docs/dc_dashboard_enrichment_need_audit.md) assesses whether the five current `_daily` enrichment tables are still needed. Assessment: `AMBIGUOUS_NEEDS_UI_DECISION`, with interim recommendation `PRESERVE_FOR_NOW`. They are not required by default reports-mode scheduler operation, but they are still an implemented opt-in/manual dashboard enrichment path and cannot be removed as cleanup without a separate dashboard source decision.

Decision follow-up: [dc_dashboard_ui_enrichment_retirement_decision.md](/home/kalle/projects/rawcandle/docs/dc_dashboard_ui_enrichment_retirement_decision.md) records the user decision `RETIRE_DASHBOARD_UI_HTML_AND_ENRICHMENT`. Runtime neutralization and DB cleanup remain separate later phases.

Phase 1 status: scheduler/config/dashboard hooks for dashboard UI/HTML/enrichment have now been neutralized. Scheduler config, scheduler runner, scheduler CLI output, and scheduler UI settings no longer expose the retired dashboard/enrichment path. No DB cleanup was done; migrations `002`/`003`, current `dc_*`, current legacy Datacenter reports, current `ec_*`, and `ec_source_layer` were preserved.

Phase 2 status: dashboard/enrichment dev_tools, builders, exporters, diagnostics, UI/HTML code, and their direct tests have now been removed. Active dashboard/enrichment docs were moved to `docs/archive/dashboard_ui_enrichment/`. The read-only `preflight_dc_dashboard_legacy_db_cleanup` CLI/test remain preserved for later DB validation. No DB cleanup was done; migrations `002`/`003`, current `dc_*`, current legacy Datacenter reports, current `ec_*`, and `ec_source_layer` were preserved.

Phase 3-prestep status: the active `DatabaseManager` hook that applied dashboard enrichment migrations during general analysis DB initialization has been neutralized, and the write-capable dashboard enrichment migration helper has been removed. Migrations `002`/`003` remain unchanged for a later migration-policy decision. No DB cleanup was done; current `dc_*`, current legacy Datacenter reports, current `ec_*`, and `ec_source_layer` were preserved.

Phase 3 status: read-only DB/migration cleanup strategy and `analysis.db` preflight are documented in [dc_dashboard_enrichment_db_cleanup_strategy.md](/home/kalle/projects/rawcandle/docs/dc_dashboard_enrichment_db_cleanup_strategy.md). Assessment: `DASHBOARD_ENRICHMENT_DB_CLEANUP_CANDIDATE_WITH_BACKUP_REQUIRED`. No DB cleanup was done and migrations `002`/`003` remain unchanged.

Phase 4 status: the five retired dashboard enrichment `_daily` tables were dropped from `/home/kalle/projects/rawcandle/data/analysis.db` after verified backup. Details are documented in [dc_dashboard_enrichment_db_cleanup_analysis_db.md](/home/kalle/projects/rawcandle/docs/dc_dashboard_enrichment_db_cleanup_analysis_db.md). No `VACUUM` was run; migrations `002`/`003`, current `dc_*`, current legacy Datacenter reports, current `ec_*`, and `ec_source_layer` were preserved.

Runtime hook removal is no longer blocked because the retirement decision has been made and Phase 1 has neutralized scheduler/config hooks. DB removal for `/home/kalle/projects/rawcandle/data/analysis.db` is complete for the five retired `dc_dashboard_*_daily` tables; other DBs still require separate preflight, backup, rollback plan, and explicit approval.

This audit does not affect current `dc_*` source facts, current legacy Datacenter reports, current `ec_*`, or `ec_source_layer`.

## Scope and preserve boundary

This audit is for `dc_dashboard_*` legacy objects only.

It is not for current `dc_*` source facts:

- `dc_ticker_swing_signal_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`
- `dc_group_index_daily`
- `dc_pipeline_watermark`

It is not for:

- Current Datacenter swing pipeline.
- Current legacy Datacenter reports over current `dc_*`.
- Current `ec_*` sidecar.
- `ec_source_layer`.
- Active dashboard/enrichment behavior unless that behavior is separately proven to rely only on obsolete `dc_dashboard_*` objects and a later approved change removes it.

## Evidence scope

Searches run:

- `git status --short`
- `git diff --stat`
- `rg -n "dc_dashboard|dc_dashboard_|CREATE TABLE.*dc_dashboard|INSERT INTO dc_dashboard|FROM dc_dashboard|JOIN dc_dashboard|DROP TABLE.*dc_dashboard" rawcandle analysis tests docs dev_tools`
- `rg -n "dashboard.*dc_|dc_.*dashboard|dashboard_enrichment|enrichment|dashboard.*migration|dashboard.*readmodel|read_model|readmodel" rawcandle analysis tests docs dev_tools`
- `find rawcandle/sqlite/migrations -maxdepth 1 -type f | sort`
- `rg -n "dc_ticker_swing_signal_daily|dc_group_swing_signal_daily|dc_group_synthetic_ohlc_daily|dc_group_index_daily|dc_pipeline_watermark" rawcandle analysis tests docs`
- `rg -n "ec_source_layer|ec_ticker_signal_daily|ec_group_signal_daily|ec_group_synthetic_ohlc_daily|ec_group_index_daily|ec_pipeline_watermark" rawcandle analysis tests docs`
- `rg -n "dashboard|enrichment" rawcandle/scheduler rawcandle/cli tests docs`
- `rg -n "apply_datacenter_dashboard_enrichment_migration|datacenter_enrichment_apply_migrations|datacenter_enrichment_enabled|datacenter_dashboard_source_mode|run_datacenter_dashboard_enrichment_write|build_datacenter_dashboard_input_from_analysis_db" rawcandle/scheduler/runner.py rawcandle/cli/run_stock_update_scheduler.py tests/test_stock_update_scheduler_runner.py tests/test_stock_update_scheduler_cli.py`
- `rg -n "dc_dashboard_ticker_enrichment_daily|dc_dashboard_group_enrichment_daily|dc_dashboard_action_summary_daily|dc_dashboard_decision_trace_daily|dc_dashboard_enrichment_run_daily" tests rawcandle dev_tools`

Files inspected:

- `rawcandle/sqlite/migrations/002_create_datacenter_dashboard_enrichment.sql`
- `rawcandle/sqlite/migrations/003_add_high_exit_risk_days_count_to_ticker_enrichment.sql`
- `rawcandle/datacenter_dashboard_enrichment_migration.py`
- `rawcandle/scheduler/config.py`
- `dev_tools/run_datacenter_dashboard_enrichment_write.py`
- `dev_tools/datacenter_dashboard_analysis_db_builder.py`
- `dev_tools/run_datacenter_dashboard_enrichment_audit.py`
- `docs/DATACENTER_DASHBOARD_ANALYSIS_DB_ENRICHMENT_SPEC.md`
- `docs/DATACENTER_DASHBOARD_MANUAL_PRODUCTION_ENRICHMENT_RUNBOOK.md`

Excluded areas:

- Generated reports.
- DB files.
- WAL/SHM files.
- Backups.
- Exports.
- Temp artifacts.
- Logs.

No DB contents were inspected in this audit. No scheduler, stock update, refresh, backfill, recovery, report generation, dashboard generation, or DB-writing command was run.

## Schema/table inventory

| Table name | Migration/file | Role | Category |
|---|---|---|---|
| `dc_dashboard_ticker_enrichment_daily` | `002_create_datacenter_dashboard_enrichment.sql`, patched by `003_add_high_exit_risk_days_count_to_ticker_enrichment.sql` | Current ticker-level dashboard-ready enrichment table in `analysis.db`. | PRESERVE |
| `dc_dashboard_group_enrichment_daily` | `002_create_datacenter_dashboard_enrichment.sql` | Current group/market-map enrichment table. | PRESERVE |
| `dc_dashboard_action_summary_daily` | `002_create_datacenter_dashboard_enrichment.sql` | Current precomputed action summary derived from ticker enrichment rows. | PRESERVE |
| `dc_dashboard_decision_trace_daily` | `002_create_datacenter_dashboard_enrichment.sql` | Current decision trace rows for dashboard enrichment. | PRESERVE |
| `dc_dashboard_enrichment_run_daily` | `002_create_datacenter_dashboard_enrichment.sql` | Current enrichment run metadata. | PRESERVE |
| `dc_dashboard_runs` | No current migration found in inspected files; listed as `OLD_SNAPSHOT_TABLES` in `dev_tools/run_datacenter_dashboard_enrichment_audit.py`. | Old snapshot-style dashboard table if present in a DB. | DB_CLEANUP_LATER |
| `dc_dashboard_source_reports` | No current migration found in inspected files; listed as `OLD_SNAPSHOT_TABLES`. | Old snapshot-style dashboard table if present in a DB. | DB_CLEANUP_LATER |
| `dc_dashboard_market_map` | No current migration found in inspected files; listed as `OLD_SNAPSHOT_TABLES`. | Old snapshot-style dashboard table if present in a DB. | DB_CLEANUP_LATER |
| `dc_dashboard_watchlist_status` | No current migration found in inspected files; listed as `OLD_SNAPSHOT_TABLES`. | Old snapshot-style dashboard table if present in a DB. | DB_CLEANUP_LATER |
| `dc_dashboard_ticker_status` | No current migration found in inspected files; listed as `OLD_SNAPSHOT_TABLES`. | Old snapshot-style dashboard table if present in a DB. | DB_CLEANUP_LATER |
| `dc_dashboard_decision_trace` | No current migration found in inspected files; listed as `OLD_SNAPSHOT_TABLES`. | Old snapshot-style dashboard table if present in a DB. | DB_CLEANUP_LATER |

## Categorized inventory

| Path | Symbol/table/pattern | Reference type | Category | Reason | Suggested next action |
|---|---|---|---|---|---|
| `rawcandle/sqlite/migrations/002_create_datacenter_dashboard_enrichment.sql` | five `dc_dashboard_*_daily` tables | Migration/schema | PRESERVE | Creates the current dashboard-ready enrichment layer documented as analysis-side intermediate state. | Do not remove in a legacy cleanup. |
| `rawcandle/sqlite/migrations/003_add_high_exit_risk_days_count_to_ticker_enrichment.sql` | `dc_dashboard_ticker_enrichment_daily` | Migration/schema patch | PRESERVE | Patches current ticker enrichment table. | Do not remove unless current enrichment is retired in a separate decision. |
| `rawcandle/datacenter_dashboard_enrichment_migration.py` | `apply_datacenter_dashboard_enrichment_migration` | Migration helper | AMBIGUOUS | Applies current enrichment migrations when explicitly configured. Active surface, but default scheduler config does not apply migrations automatically. | Preserve for now; decision required before any neutralization. |
| `rawcandle/scheduler/config.py` | `datacenter_dashboard_source_mode`, `datacenter_enrichment_*` | Scheduler config | PRESERVE | Current scheduler supports `reports` and `enrichment` source modes and keeps enrichment disabled by default. | Preserve. |
| `rawcandle/scheduler/runner.py` | dashboard/enrichment post-step logic | Scheduler runtime | PRESERVE | Current scheduler has dashboard and enrichment orchestration guarded by config. | Preserve. |
| `rawcandle/cli/run_stock_update_scheduler.py` | dashboard/enrichment summary output | CLI output | PRESERVE | Current CLI reports dashboard/enrichment status fields. Tests enforce this surface. | Preserve. |
| `dev_tools/run_datacenter_dashboard_enrichment_write.py` | writes five `dc_dashboard_*_daily` tables | Write-capable dev_tool | AMBIGUOUS | Manual/current enrichment writer; production runbook documents this path. Not safe to remove as legacy. | Preserve pending separate dashboard/enrichment retirement decision. |
| `dev_tools/run_datacenter_dashboard_ticker_enrichment_write.py` | `dc_dashboard_ticker_enrichment_daily` | Write-capable dev_tool | AMBIGUOUS | Component writer for current enrichment layer. | Preserve pending decision. |
| `dev_tools/run_datacenter_dashboard_group_enrichment_write.py` | `dc_dashboard_group_enrichment_daily` | Write-capable dev_tool | AMBIGUOUS | Component writer for current enrichment layer. | Preserve pending decision. |
| `dev_tools/run_datacenter_dashboard_action_summary_write.py` | `dc_dashboard_action_summary_daily` | Write-capable dev_tool | AMBIGUOUS | Component writer for current enrichment layer. | Preserve pending decision. |
| `dev_tools/run_datacenter_dashboard_decision_trace_write.py` | `dc_dashboard_decision_trace_daily` | Write-capable dev_tool | AMBIGUOUS | Component writer for current enrichment layer. | Preserve pending decision. |
| `dev_tools/datacenter_dashboard_analysis_db_builder.py` | `_ENRICHMENT_REQUIRED_TABLES` | Dashboard input builder | PRESERVE | Builds dashboard input from current enrichment tables when `source_mode="enrichment"`. | Preserve. |
| `dev_tools/run_datacenter_dashboard_enrichment_audit.py` | `EXPECTED_TABLES`, `OLD_SNAPSHOT_TABLES` | Read-only audit tool | PRESERVE | Distinguishes current expected `_daily` enrichment tables from old snapshot table names. | Preserve; use for later read-only DB preflight if approved. |
| `dev_tools/run_datacenter_dashboard_*_diagnosis.py` and related audit scripts | `dc_dashboard_ticker_enrichment_daily` / current enrichment tables | Diagnostics/dev_tools | AMBIGUOUS | Diagnostics read current enrichment tables and compare dashboard behavior. Not safe to delete under this audit. | Preserve pending dashboard tooling policy. |
| `tests/test_stock_update_scheduler_runner.py` | dashboard/enrichment scheduler behavior | Tests | PRESERVE | Tests enforce current dashboard/enrichment behavior, including enrichment source mode and migration gating. | Preserve. |
| `tests/test_stock_update_scheduler_cli.py` | dashboard/enrichment summary output | Tests | PRESERVE | Tests enforce CLI summary fields. | Preserve. |
| `docs/DATACENTER_DASHBOARD_ANALYSIS_DB_ENRICHMENT_SPEC.md` | `dc_dashboard_*_daily` | Current design doc | DOCS_ONLY | Describes current analysis-side enrichment tables and warns not to recreate old snapshot tables. | Preserve; update only if dashboard strategy changes. |
| `docs/DATACENTER_DASHBOARD_MANUAL_PRODUCTION_ENRICHMENT_RUNBOOK.md` | manual production enrichment | Current runbook | DOCS_ONLY | Documents a write-capable production path using the current enrichment tables. | Preserve until superseded. |
| Current `dc_*` source fact builders/loaders/docs | named current `dc_*` tables | Runtime/docs | PRESERVE | Source facts feed Datacenter reports, dashboard enrichment, and `ec_*`. | Preserve. |
| Current `ec_*` and `ec_source_layer` paths | current sidecar | Runtime/CLI/tests | PRESERVE | Independent current sidecar; not part of `dc_dashboard_*` cleanup. | Preserve. |

## Active runtime assessment

| Question | Assessment |
|---|---|
| Is anything in scheduler using `dc_dashboard_*`? | The scheduler has active dashboard/enrichment configuration and runner paths. Enrichment is guarded by `datacenter_dashboard_source_mode`, `datacenter_enrichment_enabled`, and `datacenter_enrichment_apply_migrations`. |
| Is any current dashboard/enrichment path using it? | Yes. Current dev_tools write and read the five `dc_dashboard_*_daily` enrichment tables; the analysis DB builder reads them for `source_mode="enrichment"`. |
| Is any current Datacenter pipeline using it? | The core swing source-fact pipeline is separate, but dashboard enrichment consumes current `dc_*` source facts and writes `dc_dashboard_*_daily`. |
| Is any current legacy report using it? | No direct evidence that legacy daily/rolling reports read `dc_dashboard_*`; they read current `dc_*` source facts. |
| Is `ec_source_layer` using it? | No evidence found. `ec_source_layer` uses current `dc_*` source facts and current `ec_*` tables. |
| Is any current CLI/dev_tool using it? | Yes. Multiple dev_tools write, audit, diagnose, or build from `dc_dashboard_*_daily`. |
| Is any test still enforcing it? | Scheduler tests enforce dashboard/enrichment config, status, and summary behavior. |

## Proposed phased removal plan

### Phase A: audit only

Status: complete in this document. No runtime, test, migration, DB, scheduler, `dc_*`, `ec_*`, or `ec_source_layer` changes were made.

### Phase B: neutralize active hooks if any exist

Active hooks exist. Do not neutralize them without a separate decision that answers whether dashboard enrichment is current or should be retired. If retirement is selected later, start with scheduler/config/dev_tools neutralization, not DB drops.

### Phase C: remove old `dc_dashboard_*` code/tests if no active blockers remain

Not ready. Current `_daily` enrichment tables have active code and tests. Only old snapshot table references such as `dc_dashboard_runs`, `dc_dashboard_source_reports`, `dc_dashboard_market_map`, `dc_dashboard_watchlist_status`, `dc_dashboard_ticker_status`, and `dc_dashboard_decision_trace` look like DB-cleanup candidates if present in a DB.

### Phase D: archive old docs

Do not archive current dashboard enrichment docs. Archive only documents proven to describe retired snapshot-style dashboard tables as current.

### Phase E: migration strategy if migrations exist

Migrations `002` and `003` exist for current `_daily` enrichment tables and should be preserved. No migration strategy is recommended unless dashboard enrichment itself is retired.

### Phase F: read-only DB preflight for explicit DB path

Recommended before any DB cleanup. The preflight should separately report:

- current expected `dc_dashboard_*_daily` tables
- old snapshot-style `dc_dashboard_runs`, `dc_dashboard_source_reports`, `dc_dashboard_market_map`, `dc_dashboard_watchlist_status`, `dc_dashboard_ticker_status`, `dc_dashboard_decision_trace`
- row counts
- related indexes/triggers/views
- `PRAGMA integrity_check`
- `PRAGMA foreign_key_check`
- current `dc_*` source fact and `ec_*` table presence

### Phase G: backup-confirmed DB cleanup only after preflight

Only old snapshot-style tables should be considered for later DB cleanup, and only after explicit approval, verified backup, reviewed drop list, rollback plan, and post-cleanup checks. Do not drop the five current `_daily` enrichment tables under a generic `dc_dashboard_*` cleanup.

## Safeguards

- Never remove current `dc_*` source facts under a `dc_dashboard_*` cleanup label.
- Never remove current `ec_*` or `ec_source_layer`.
- Do not break active dashboard/enrichment behavior unless separately approved.
- Do not drop the current five `dc_dashboard_*_daily` enrichment tables unless dashboard enrichment is explicitly retired.
- No DB cleanup without explicit DB path, read-only preflight, backup, and confirmation.
- No `VACUUM` or `VACUUM INTO` without separate approval.
- Keep runtime cleanup, migration strategy, and DB table cleanup as separate phases.
- Do not infer live DB table presence from migration files or repository references.

## Recommended next Codex step

Create a read-only DB preflight for an explicit DB path that distinguishes current `dc_dashboard_*_daily` enrichment tables from old snapshot-style `dc_dashboard_*` tables. Do not remove code, migrations, tests, or DB tables before deciding whether current dashboard enrichment is preserved or retired.

## Things not touched

- No runtime code changed.
- No tests changed.
- No migrations changed.
- No DBs inspected or modified.
- No DB tables dropped.
- No dashboard generation command run.
- No scheduler behavior changed.
- No `scheduler_config.json` changed.
- No current `dc_*` source fact generation changed.
- No current legacy Datacenter reports changed.
- No current `ec_*` sidecar behavior changed.
- No `ec_source_layer` behavior changed.
