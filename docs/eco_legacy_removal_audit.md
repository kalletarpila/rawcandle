# eco_* legacy removal audit

## Executive summary

This audit is for removing old eco_* legacy code, not the new ec_* sidecar.

The repository contains two similarly named systems that must be kept separate:

- `eco_*`: old Canonical V3 ecosystem tables, builders, query layer, Markdown report generation, and related tests. This is the later removal target.
- `ec_*`: current sidecar/source-layer system. This must be preserved, including `ec_source_layer`, `ec_*` loaders, `ec_*` migrations, and `dc_*` source facts used by legacy Datacenter reporting.

The original audit found the main old `eco_*` implementation in `rawcandle/report_canonical_v3_*.py`, `rawcandle/reporting_v3_*.py`, V3 CLI modules, migrations `015`-`018`, and matching tests. Later cleanup removed the old V3/eco runtime code, old DB tables from `analysis.db`, and the retired V3 scheduler/config/output compatibility surface. Migrations `015`-`018` remain as historical migration files until a separate migration-history decision.

No runtime code, tests, config, schema, reports, or database files were changed in this step.

Phase 1B status: old V3/eco CLI entrypoints and their direct CLI tests were removed after scheduler imports were neutralized in Phase 1A. Core `report_canonical_v3_*`, `reporting_v3_*`, and migrations `015`-`018` remain for later phases.

Phase 2A status: old V3/eco core modules `report_canonical_v3_*`, `reporting_v3_query.py`, `reporting_v3_markdown.py`, and their direct core tests were removed. Migrations `015`-`018`, historical docs, scheduler compatibility fields, `ec_*`, and `dc_*` paths remain for later phases.

Phase 2B status: old V3/eco historical docs were archived under `docs/archive/old_v3_eco/`. Runtime code, migrations `015`-`018`, production DBs, scheduler compatibility fields, `ec_*`, and `dc_*` paths were not changed; DB cleanup remains a separate later phase.

Phase 3A planning status: migration and database cleanup strategy was documented in `docs/eco_legacy_migration_cleanup_strategy.md`. Migrations `015`-`018`, runtime code, production DBs, scheduler compatibility fields, `ec_*`, and `dc_*` paths were not changed.

Phase 3B status: read-only DB cleanup preflight CLI `rawcandle/cli/preflight_eco_legacy_db_cleanup.py` was added. No DB cleanup was performed; migrations `015`-`018`, runtime scheduler behavior, `ec_*`, and `dc_*` paths were not changed.

Phase 3C status: read-only analysis DB preflight completed and documented in `docs/eco_legacy_db_preflight_analysis_db.md`. No DB cleanup was performed; no tables were dropped; migrations `015`-`018`, runtime scheduler behavior, `ec_*`, and `dc_*` paths were not changed.

Phase 3D status: analysis DB old `eco_*` table cleanup completed and documented in `docs/eco_legacy_db_cleanup_analysis_db.md`. Backup path: `/home/kalle/projects/rawcandle/temp/analysis__before_eco_legacy_cleanup__20260617T132223Z.sqlite`. No `VACUUM` was run; migrations `015`-`018`, migrations `019`-`024`, runtime scheduler behavior, `ec_*`, and `dc_*` paths were not changed.

Phase 3E status: post-cleanup read-only verification completed and documented in `docs/eco_legacy_post_cleanup_verification_analysis_db.md`. Assessment: `POST_CLEANUP_READINESS_OK`. No `VACUUM` was run; migrations `015`-`024`, runtime scheduler behavior, `ec_*`, and `dc_*` paths were not changed.

Final verification status: combined read-only verification for old `eco_*` and retired `dc_report_*_v2` cleanup is documented in `docs/analysis_db_legacy_cleanup_final_verification.md`. Assessment: `LEGACY_CLEANUP_VERIFIED`.

R1 compatibility cleanup status: retired V3 scheduler/config/output compatibility fields were removed and documented in `docs/retired_compatibility_surface_audit.md`. Canonical Report V2 retired dev_tools stubs remain for a later R2 decision.

## Evidence scope

Read-only checks used targeted `rg` searches for:

- `eco_`
- `eco.`
- `EcosystemSwing`
- `eco_entity`
- `eco_entity_metric_value`
- `eco_pipeline`
- `eco_source`
- `datacenter_v3`
- retired V3 scheduler summary fields

The audit intentionally excluded generated reports, DB files, exports, backups, temp artifacts, and logs. It did not inspect production DB contents and did not run scheduler, stock update, refresh, backfill, recovery, or DB-mutating commands.

## Active configuration assumptions from repo files

- `ec_source_layer` is represented as the current sidecar path in scheduler config and scheduler runner fields.
- R1 later removed retired V3 scheduler/config/output compatibility from `rawcandle/scheduler/config.py`, `rawcandle/scheduler/runner.py`, and `rawcandle/cli/run_stock_update_scheduler.py`.
- `scheduler_config.json` was not edited by this cleanup track.
- The audit does not rely on `data/analysis.db` or any other production DB content.

## Categorized inventory

| Path | Reference type | Category | Reason | Suggested next action |
|---|---|---|---|---|
| `rawcandle/report_canonical_v3_*.py` | Builders/importers | SAFE_REMOVE_LATER | Modules read/write `eco_*` tables and implement the old Canonical V3 build path. | Remove after scheduler and CLI references are removed. |
| `rawcandle/reporting_v3_query.py` | Query layer | SAFE_REMOVE_LATER | Reads `eco_report_run`, `eco_entity_metric_value`, `eco_classification_decision`, and related old `eco_*` facts. | Remove with V3 Markdown report generation. |
| `rawcandle/reporting_v3_markdown.py` | Report renderer | SAFE_REMOVE_LATER | Renders old V3 Markdown reports from old `eco_*` query data. | Remove with V3 Markdown report generation. |
| `rawcandle/cli/run_canonical_v3_latest_build.py` | CLI | SAFE_REMOVE_LATER | Orchestrates old `eco_*` builders and target tables. | Delete once no operational scripts call it. |
| `rawcandle/cli/plan_canonical_v3_latest_build.py` | CLI/planner | SAFE_REMOVE_LATER | Plans old `eco_*` Canonical V3 build steps. | Delete with old build CLI. |
| `rawcandle/cli/inspect_canonical_v3.py` | CLI/inspection | SAFE_REMOVE_LATER | Inspects old `eco_*` tables only. | Delete once old tables are retired. |
| `rawcandle/cli/write_latest_v3_markdown_reports.py` | CLI/report writer | SAFE_REMOVE_LATER | Resolves latest `eco_report_run` and invokes V3 Markdown writer. | Delete after scheduler no longer imports it. |
| `rawcandle/cli/write_v3_markdown_prototypes.py` | CLI/report writer | SAFE_REMOVE_LATER | Uses `reporting_v3_query` and `reporting_v3_markdown`. | Delete with V3 report renderer. |
| `rawcandle/sqlite/migrations/015_create_eco_base_dimensions_v3.sql` | Schema migration | SAFE_REMOVE_LATER | Creates base old `eco_*` dimension tables. | Stop applying, then delete or archive. |
| `rawcandle/sqlite/migrations/016_create_eco_core_facts_v3.sql` | Schema migration | SAFE_REMOVE_LATER | Creates old `eco_*` report/fact tables. | Stop applying, then delete or archive. |
| `rawcandle/sqlite/migrations/017_create_eco_signal_event_facts_v3.sql` | Schema migration | SAFE_REMOVE_LATER | Creates old `eco_*` signal/event tables. | Stop applying, then delete or archive. |
| `rawcandle/sqlite/migrations/018_create_eco_classification_decision_v3.sql` | Schema migration | SAFE_REMOVE_LATER | Creates old `eco_classification_decision`. | Stop applying, then delete or archive. |
| `tests/test_canonical_v3_*.py` | Tests | SAFE_REMOVE_LATER | Test old `eco_*` schema, importers, builders, and decisions. | Remove with corresponding modules. |
| `tests/test_reporting_v3_*.py` | Tests | SAFE_REMOVE_LATER | Test old V3 query/Markdown output over `eco_*`. | Remove with V3 report renderer. |
| `tests/test_write_v3_markdown_prototypes_cli.py` | Tests | SAFE_REMOVE_LATER | Tests old V3 Markdown CLI. | Remove with CLI. |
| `tests/test_write_latest_v3_markdown_reports_cli.py` | Tests | SAFE_REMOVE_LATER | Tests latest `eco_report_run` resolver and report writer. | Remove with CLI and scheduler hook. |
| `tests/test_inspect_canonical_v3_cli.py` | Tests | SAFE_REMOVE_LATER | Tests old `eco_*` inspect CLI. | Remove with CLI. |
| `tests/test_plan_canonical_v3_latest_build_cli.py` | Tests | SAFE_REMOVE_LATER | Tests old Canonical V3 planner. | Remove with planner CLI. |
| `tests/test_run_canonical_v3_latest_build_cli.py` | Tests | SAFE_REMOVE_LATER | Tests old Canonical V3 build orchestration. | Remove with build CLI. |
| `docs/ecosystem_v3_eco_tables_reference.md` | Documentation | SAFE_REMOVE_LATER | Documents old `eco_*` table model. | Archive or delete after removal plan is accepted. |
| `docs/ecosystem_v3_report_generation_reference.md` | Documentation | SAFE_REMOVE_LATER | Documents old V3 reports sourced from `eco_*`. | Archive or delete with V3 reporting. |
| `docs/canonical_v3_ecosystem_entity_model_design.md` | Documentation | SAFE_REMOVE_LATER | Design document for old Canonical V3 `eco_*` model. | Archive as historical context or delete. |
| `docs/canonical_v3_classification_report_state_design.md` | Documentation | SAFE_REMOVE_LATER | Design document for old `eco_classification_decision`. | Archive or delete with classification table removal. |
| `docs/datacenter_v3_replacement_decision_plan.md` | Documentation | SAFE_REMOVE_LATER | Describes old V3 replacement/parity direction. | Archive or delete after replacement decision is superseded by `ec_*`. |
| `docs/datacenter_legacy_vs_v3_report_parity.md` | Documentation | SAFE_REMOVE_LATER | Compares legacy reports to old `eco_*` V3 reports. | Archive or delete after old V3 report path is retired. |
| `rawcandle/ec_sidecar_migration.py` | Schema migration runner | PRESERVE | Owns current `ec_*` sidecar migrations `019`-`024`. | Keep. |
| `rawcandle/sqlite/migrations/019_create_ec_sidecar_schema.sql` | Schema migration | PRESERVE | Creates current `ec_*` sidecar dimensions. | Keep. |
| `rawcandle/sqlite/migrations/020_harden_ec_sidecar_schema.sql` | Schema migration | PRESERVE | Hardens current `ec_*` sidecar schema. | Keep. |
| `rawcandle/sqlite/migrations/021_patch_ec_signal_calendar_p0_fields.sql` | Schema migration | PRESERVE | Patches current `ec_signal_calendar`. | Keep. |
| `rawcandle/sqlite/migrations/022_create_ec_fact_tables.sql` | Schema migration | PRESERVE | Creates current `ec_*` fact tables. | Keep. |
| `rawcandle/sqlite/migrations/023_patch_ec_fact_schema_for_dc_parity.sql` | Schema migration | PRESERVE | Adds current `ec_*` parity columns. | Keep. |
| `rawcandle/sqlite/migrations/024_patch_ec_group_index_counts.sql` | Schema migration | PRESERVE | Patches current `ec_group_index_daily`. | Keep. |
| `rawcandle/ec_*_loader.py` | Loaders | PRESERVE | Current sidecar loaders for `ec_*` data. | Keep. |
| `rawcandle/cli/run_ec_source_layer_refresh.py` | CLI | PRESERVE | Current sidecar refresh orchestration. | Keep. |
| `rawcandle/cli/plan_ec_source_layer_build.py` | CLI/planner | PRESERVE | Current no-write planner for `ec_*` build. Contains old `eco_*` schema inventory text only. | Keep; later update wording if old table inventory is removed. |
| `rawcandle/cli/plan_ec_source_layer_refresh.py` | CLI/planner | PRESERVE | Current no-write planner for `ec_*` refresh. Contains old `eco_*` schema inventory text only. | Keep; later update wording if old table inventory is removed. |
| `rawcandle/cli/plan_ec_source_layer_backfill.py` | CLI/planner | PRESERVE | Current no-write planner for `ec_*` backfill. Contains old `eco_*` schema inventory text only. | Keep; later update wording if old table inventory is removed. |
| `rawcandle/ec_dc_coverage_audit.py` | Audit | PRESERVE | Current `ec_*` coverage/parity support. | Keep. |
| `tests/test_ec_*.py` | Tests | PRESERVE | Validate current sidecar loaders, migrations, coverage, and pipeline watermarks. | Keep. |
| `tests/test_plan_ec_source_layer_*.py` | Tests | PRESERVE | Validate current `ec_source_layer` planners. | Keep; update only if planner output intentionally changes later. |
| `tests/test_run_ec_source_layer_build_cli.py` | Tests | PRESERVE | Current `ec_*` source-layer CLI coverage. | Keep. |
| `docs/datacenter_dc_tables_reference.md` | Documentation | PRESERVE | Documents `dc_*` source facts and legacy Datacenter report dependencies. | Keep; remove old V3 references only in a later doc cleanup pass. |
| `docs/datacenter_legacy_report_generation_reference.md` | Documentation | PRESERVE | Documents legacy Datacenter reports over `dc_*`. | Keep; remove old V3 comparison references only later. |
| `rawcandle/scheduler/runner.py` | Scheduler | REMOVED_LATER | R1 later removed retired V3 scheduler result fields and helper call paths while preserving scheduler, Datacenter, dashboard, and `ec_source_layer`. | No further R1 action. |
| `rawcandle/scheduler/config.py` | Config | REMOVED_LATER | R1 later removed retired V3 config fields and old keys are no longer accepted by the strict parser. | No further R1 action. |
| `rawcandle/cli/run_stock_update_scheduler.py` | CLI summary output | REMOVED_LATER | R1 later removed retired V3 summary output lines. | No further R1 action. |
| `scheduler_config.json` | Local config | NOT_TOUCHED | Local config was intentionally not edited in this cleanup track. | Handle separately if needed; do not stage local config in cleanup commits. |
| `rawcandle/cli/plan_ec_source_layer_build.py` lines mentioning `eco_tables` | Planner inventory | AMBIGUOUS | Uses `eco_tables = _glob_table_names(conn, "eco_*")` as read-only old-schema visibility, while preserving `ec_*`. | Keep for now; later remove inventory output after old schema cleanup. |
| `rawcandle/cli/plan_ec_source_layer_refresh.py` lines mentioning `eco_tables` | Planner inventory | AMBIGUOUS | Same read-only old-schema visibility. | Keep for now; later remove inventory output after old schema cleanup. |
| `rawcandle/cli/plan_ec_source_layer_backfill.py` lines mentioning `eco_tables` | Planner inventory | AMBIGUOUS | Same read-only old-schema visibility. | Keep for now; later remove inventory output after old schema cleanup. |

## Proposed phased removal plan

### Phase 1: disable/delete unused old eco_* CLIs and builders

Goal: remove runtime import and execution paths for old `eco_*` code while preserving scheduler, legacy Datacenter reports, `dc_*`, and `ec_source_layer`.

Suggested actions:

- Remove unconditional imports of `write_latest_v3_markdown_reports` and `write_v3_markdown_prototypes` from scheduler.
- Replace `_run_v3_datacenter_report_generation` with a removed/deprecated no-op, or remove the function and all callers if summary compatibility is not required.
- Delete old Canonical V3 builder/importer modules once no imports remain.
- Delete old Canonical V3 CLIs once no tests or scheduler paths import them.

Checks before and after:

- `rg -n "report_canonical_v3|write_latest_v3|write_v3_markdown|reporting_v3" rawcandle tests`
- Scheduler unit tests covering skipped/default post-step behavior.
- `ec_source_layer` tests to confirm current sidecar path remains intact.

### Phase 2: remove old eco_* report generation paths/tests

Goal: remove old V3 Markdown report generation, query layer, renderer, and tests.

Suggested actions:

- Delete `rawcandle/reporting_v3_query.py`.
- Delete `rawcandle/reporting_v3_markdown.py`.
- Delete V3 Markdown CLI tests and reporting V3 query/Markdown tests.
- Delete generated-output expectations tied to `datacenter_v3_*` filenames from tests.

Checks before and after:

- targeted search for old V3 runtime/reporting references in `rawcandle` and `tests`
- Datacenter legacy report tests to ensure `dc_*`-based reports still work.
- Dashboard tests if dashboard report references consume scheduler summaries.

### Phase 3: remove obsolete config/dashboard hooks if safe

Goal: remove compatibility surface for disabled old V3 reports without breaking active scheduler/dashboard consumers.

R1 decision completed later: remove the retired V3 scheduler/config/output compatibility surface immediately. Old retired V3 config keys are no longer accepted by the strict scheduler config parser.

Checks before and after:

- targeted search for retired V3 scheduler/config/output strings in `rawcandle`, `tests`, and relevant docs
- Scheduler CLI tests.
- Scheduler UI tests if they display old retired V3 fields.

### Phase 4: optional schema cleanup strategy for old eco_* tables

Goal: remove old `eco_*` tables from databases only after code no longer depends on them.

Do not run this as part of code cleanup without separate confirmation. Production DB table drops require a fresh backup, explicit confirmation of target DB path, and enough free disk for SQLite cleanup.

Suggested table-drop order for a separately approved DB cleanup:

```sql
PRAGMA foreign_keys = OFF;

DROP TABLE IF EXISTS eco_signal_relevance;
DROP TABLE IF EXISTS eco_signal_observation;
DROP TABLE IF EXISTS eco_entity_event;
DROP TABLE IF EXISTS eco_entity_window_snapshot;
DROP TABLE IF EXISTS eco_entity_metric_value;
DROP TABLE IF EXISTS eco_classification_decision;
DROP TABLE IF EXISTS eco_entity_coverage;
DROP TABLE IF EXISTS eco_quality_summary;
DROP TABLE IF EXISTS eco_report_run;
DROP TABLE IF EXISTS eco_watchlist_member;
DROP TABLE IF EXISTS eco_watchlist;
DROP TABLE IF EXISTS eco_taxonomy_entity_relation;
DROP TABLE IF EXISTS eco_report_window;
DROP TABLE IF EXISTS eco_entity;
DROP TABLE IF EXISTS eco_taxonomy_version;
DROP TABLE IF EXISTS eco_ecosystem;

PRAGMA foreign_keys = ON;
PRAGMA integrity_check;
```

Run `VACUUM` only after confirming disk space. `DROP TABLE` makes pages reusable inside SQLite; it does not necessarily shrink the file until vacuuming.

Checks before and after:

- `rg -n "eco_" rawcandle tests`
- Read-only schema query against the target DB:
  `SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'eco_%' ORDER BY name;`
- `PRAGMA integrity_check;`
- `ec_*` row-count smoke checks if a DB cleanup is performed.

## Tests/checks recommended before later removal phases

- `pytest tests/test_ec_ticker_signal_daily_loader.py tests/test_ec_group_signal_daily_loader.py tests/test_ec_group_synthetic_ohlc_daily_loader.py tests/test_ec_datacenter_taxonomy_loader.py tests/test_ec_datacenter_watchlist_loader.py`
- `pytest tests/test_plan_ec_source_layer_build_cli.py tests/test_plan_ec_source_layer_refresh_cli.py tests/test_plan_ec_source_layer_backfill_cli.py`
- `pytest tests/test_run_ec_source_layer_build_cli.py tests/test_run_datacenter_swing_pipeline_cli.py`
- `pytest tests/test_stock_update_scheduler_cli.py tests/test_run_datacenter_swing_pipeline_cli.py`
- `rg -n "eco_|datacenter_v3|v3_reports|report_canonical_v3|reporting_v3" rawcandle tests docs dev_tools scheduler_config.json`

These are recommendations for later phases. They were not run in this audit step.

## Things not touched in this step

- No runtime behavior was changed.
- No code files were edited.
- No tests were edited.
- No scheduler/config/report fields were renamed or removed.
- No old `eco_*` tables were dropped.
- No `ec_*` sidecar tables, migrations, loaders, planners, or tests were changed.
- No `dc_*` source facts or legacy Datacenter report paths were changed.
- No production DBs were opened for write or modified.
- No scheduler, stock update, refresh, backfill, or recovery command was run.

## Files inspected

Targeted search results were reviewed for these areas:

- `rawcandle/report_canonical_v3_*.py`
- `rawcandle/reporting_v3_query.py`
- `rawcandle/reporting_v3_markdown.py`
- `rawcandle/cli/run_canonical_v3_latest_build.py`
- `rawcandle/cli/plan_canonical_v3_latest_build.py`
- `rawcandle/cli/inspect_canonical_v3.py`
- `rawcandle/cli/write_latest_v3_markdown_reports.py`
- `rawcandle/cli/write_v3_markdown_prototypes.py`
- `rawcandle/cli/plan_ec_source_layer_build.py`
- `rawcandle/cli/plan_ec_source_layer_refresh.py`
- `rawcandle/cli/plan_ec_source_layer_backfill.py`
- `rawcandle/scheduler/runner.py`
- `rawcandle/scheduler/config.py`
- `rawcandle/cli/run_stock_update_scheduler.py`
- `rawcandle/sqlite/migrations/015_create_eco_base_dimensions_v3.sql`
- `rawcandle/sqlite/migrations/016_create_eco_core_facts_v3.sql`
- `rawcandle/sqlite/migrations/017_create_eco_signal_event_facts_v3.sql`
- `rawcandle/sqlite/migrations/018_create_eco_classification_decision_v3.sql`
- `rawcandle/sqlite/migrations/019_create_ec_sidecar_schema.sql`
- `rawcandle/sqlite/migrations/020_harden_ec_sidecar_schema.sql`
- `rawcandle/sqlite/migrations/021_patch_ec_signal_calendar_p0_fields.sql`
- `rawcandle/sqlite/migrations/022_create_ec_fact_tables.sql`
- `rawcandle/sqlite/migrations/023_patch_ec_fact_schema_for_dc_parity.sql`
- `rawcandle/sqlite/migrations/024_patch_ec_group_index_counts.sql`
- `docs/*v3*`
- `tests/test_canonical_v3_*.py`
- `tests/test_reporting_v3_*.py`
- `tests/test_write_v3_markdown_prototypes_cli.py`
- `tests/test_write_latest_v3_markdown_reports_cli.py`
- `tests/test_inspect_canonical_v3_cli.py`
- `tests/test_plan_canonical_v3_latest_build_cli.py`
- `tests/test_run_canonical_v3_latest_build_cli.py`

## Recommended next Codex step

Prepare a no-runtime-change implementation plan for Phase 1 that removes scheduler imports of old V3 report modules and decides how to handle `v3_reports_*` result/config compatibility. Do not delete old files or drop tables until that compatibility decision is explicit.
