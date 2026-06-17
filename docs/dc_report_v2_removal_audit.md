# dc_report_*_v2 removal audit

## Executive summary

This audit is for removing old/transitional `dc_report_*_v2` readmodel/reporting code, not current `dc_*` source facts.

Assessment: `REMOVAL_NOT_READY_ACTIVE_MANUAL_V2_PATHS_EXIST`.

Decision status: `DECISION: RETIRE_CANONICAL_REPORT_V2` is documented in `docs/dc_report_v2_retirement_decision.md`. That decision step made no runtime, code, test, migration, scheduler, config, or DB changes.

Phase B status: Canonical V2 hook neutralization is complete. `DatabaseManager` no longer installs V2 migrations automatically, and V2 dev_tools entrypoints are retired/disabled. No DB cleanup was performed.

Phase C status: Canonical V2 core modules and direct non-CLI V2 tests were removed. Retired dev_tools entrypoint stubs remain. No DB cleanup was performed.

The repository still contains historical Canonical Report V2 documentation, migrations `004`-`014`, retired dev_tools CLI stubs, and DB cleanup references around `dc_report_*_v2`. It does not appear wired into the current scheduler path. The original audit found that `analysis/database_manager.py` applied the Canonical V2 migrations during general analysis DB initialization; Phase B neutralized that hook. Phase C removed the V2 builders/writers/formatter loaders/parity code and their direct non-CLI tests. Docs still record an accepted manual production publish baseline for `2026-05-29`.

The safe next step is not DB cleanup. Archive/remove V2-only documentation in Phase D, then handle migration and DB cleanup strategy separately.

No code, tests, migrations, runtime behavior, scheduler config, or databases were changed in this audit.

## Preserve boundary

Preserve these current paths unless a separate audit proves otherwise:

- `dc_ticker_swing_signal_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`
- `dc_group_index_daily`
- `dc_pipeline_watermark`
- Current Datacenter swing pipeline.
- Current legacy Datacenter reports that read `dc_*` source facts.
- Dashboard enrichment paths that read current `dc_*` source facts.
- Current `ec_*` sidecar tables/loaders/planners/migrations.
- `ec_source_layer`.
- Scheduler stock update, legacy Datacenter, dashboard, and `ec_source_layer` behavior.

`dc_report_*_v2` must not be confused with the current `dc_*` source facts above.

## Evidence scope

Searches run:

```bash
git status --short
rg -n "dc_report_.*_v2|dc_report|report_v2|classification_v2|canonical_v2|readmodel|read_model|reporting_v2|v2_report|daily_report_v2|rolling.*v2" rawcandle tests docs dev_tools
rg -n "dc_report_ticker|dc_report_group|dc_report_classification|dc_report_signal|dc_report_context|dc_report_run|dc_report_window|dc_report_read" rawcandle tests docs dev_tools
rg -n "CREATE TABLE.*dc_report|INSERT INTO dc_report|FROM dc_report|JOIN dc_report|DROP TABLE.*dc_report" rawcandle tests docs dev_tools
find rawcandle/sqlite/migrations -maxdepth 1 -type f | sort
rg -n "dc_ticker_swing_signal_daily|dc_group_swing_signal_daily|dc_group_synthetic_ohlc_daily|dc_group_index_daily|dc_pipeline_watermark" rawcandle tests docs
rg -n "ec_source_layer|ec_ticker_signal_daily|ec_group_signal_daily|ec_group_synthetic_ohlc_daily|ec_group_index_daily|ec_pipeline_watermark" rawcandle tests docs
find analysis/datacenter_indices -maxdepth 1 -type f \( -name 'report_canonical_v2*' -o -name '*canonical_v2*' \) | sort
rg -n "dc_report_|report_canonical_v2|apply_report_canonical_v2_migration|INSERT INTO|FROM dc_|JOIN dc_|DELETE FROM" analysis/datacenter_indices/report_canonical_v2*.py
rg --files tests | rg 'canonical_v2|report_canonical_v2|dc_report'
rg -n "report_canonical_v2|dc_report_.*_v2|canonical_v2" rawcandle/scheduler rawcandle/cli tests/test_stock_update_scheduler_runner.py tests/test_stock_update_scheduler_cli.py dev_tools/stock_update_scheduler_ui.py
rg -n "apply_report_canonical_v2_migration|report_canonical_v2|dc_report_run_v2|004_create_datacenter_report_canonical_v2" rawcandle tests/test_report_canonical_v2_schema.py
rg -n "report_canonical_v2_migration|apply_report_canonical_v2_migration" rawcandle analysis dev_tools tests docs
python3 -m py_compile rawcandle/scheduler/runner.py rawcandle/scheduler/config.py rawcandle/cli/run_stock_update_scheduler.py
```

Files inspected:

- `rawcandle/report_canonical_v2_migration.py`
- `analysis/database_manager.py`
- `analysis/datacenter_indices/report_canonical_v2_orchestrator.py`
- `analysis/datacenter_indices/report_canonical_v2_*.py` by targeted `rg`
- `dev_tools/run_report_canonical_v2_output.py`
- `dev_tools/run_report_canonical_v2_publish_outputs.py`
- `tests/test_report_canonical_v2_schema.py`
- `docs/report_canonical_v2_production_rollout_checkpoint.md`
- Migration table definitions in `rawcandle/sqlite/migrations/004` and `009`-`014` by targeted `rg`

Excluded areas:

- DB contents.
- Generated reports.
- DB files, backups, exports, temp artifacts, and logs.
- Broad unrelated Datacenter implementation areas.
- Scheduler execution, stock update, refresh, backfill, recovery, report generation, and DB-writing commands.

## Schema inventory

Migration files that create or patch `dc_report_*_v2`:

| Migration file | Role | Category | Suggested next action |
|---|---|---|---|
| `rawcandle/sqlite/migrations/004_create_datacenter_report_canonical_v2.sql` | Creates `dc_report_run_v2`, `dc_report_context_group_v2`, `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_classification_v2`. | DB_CLEANUP_LATER | Keep until Canonical V2 migration/apply path is neutralized or explicitly preserved. |
| `rawcandle/sqlite/migrations/005_add_daily_trigger_inputs_to_report_context_daily_v2.sql` | Patches `dc_report_context_daily_v2`. | DB_CLEANUP_LATER | Keep with V2 schema set until migration strategy decision. |
| `rawcandle/sqlite/migrations/006_add_rolling2_classifier_inputs_to_report_context_window_v2.sql` | Patches `dc_report_context_window_v2`. | DB_CLEANUP_LATER | Keep with V2 schema set until migration strategy decision. |
| `rawcandle/sqlite/migrations/007_add_daily_distance_to_ema10_to_report_context_daily_v2.sql` | Patches `dc_report_context_daily_v2`. | DB_CLEANUP_LATER | Keep with V2 schema set until migration strategy decision. |
| `rawcandle/sqlite/migrations/008_add_daily_formatter_source_fields_to_report_context_v2.sql` | Patches context V2 tables; also mirrored in Python idempotent column logic. | DB_CLEANUP_LATER | Keep with V2 schema set until migration strategy decision. |
| `rawcandle/sqlite/migrations/009_create_report_window_metadata_v2.sql` | Creates `dc_report_valid_signal_date_v2`. | DB_CLEANUP_LATER | Include in later DB preflight/drop plan if V2 is retired. |
| `rawcandle/sqlite/migrations/010_create_report_ticker_coverage_v2.sql` | Creates `dc_report_watchlist_ticker_v2`, `dc_report_taxonomy_ticker_coverage_v2`. | DB_CLEANUP_LATER | Include in later DB preflight/drop plan if V2 is retired. |
| `rawcandle/sqlite/migrations/011_create_report_relevance_quality_v2.sql` | Creates `dc_report_technical_relevance_context_v2`, `dc_report_data_quality_summary_v2`. | DB_CLEANUP_LATER | Include in later DB preflight/drop plan if V2 is retired. |
| `rawcandle/sqlite/migrations/012_create_report_group_progression_v2.sql` | Creates group progression readmodel tables. | DB_CLEANUP_LATER | Include in later DB preflight/drop plan if V2 is retired. |
| `rawcandle/sqlite/migrations/013_create_report_timing_freshness_v2.sql` | Creates timing, MA-break, and freshness V2 readmodel tables. | DB_CLEANUP_LATER | Include in later DB preflight/drop plan if V2 is retired. |
| `rawcandle/sqlite/migrations/014_create_report_synthetic_event_history_v2.sql` | Creates synthetic event history V2 readmodel table. | DB_CLEANUP_LATER | Include in later DB preflight/drop plan if V2 is retired. |

## Categorized inventory

| Path | Reference type | Category | Reason | Suggested next action |
|---|---|---|---|---|
| `analysis/database_manager.py` | DB initialization hook | SAFE_REMOVE_LATER after Phase B | Phase B removed the import/call to `apply_report_canonical_v2_migration(conn)`, so general analysis DB initialization no longer installs V2 schema automatically. | Keep current non-V2 initialization behavior preserved; no further V2 hook action needed here unless cleanup removes stale docs/tests. |
| `rawcandle/report_canonical_v2_migration.py` | Migration applier | REMOVED_PHASE_C | Removed after Phase B neutralized `DatabaseManager` and V2 dev_tools entrypoints. Migrations `004`-`014` remain on disk unchanged. | No code action; handle migration files separately in Phase E. |
| `analysis/datacenter_indices/report_canonical_v2_orchestrator.py` | V2 builder orchestrator | REMOVED_PHASE_C | Removed with the rest of the retired Canonical V2 core implementation. | No further action until docs/archive and DB cleanup phases. |
| `analysis/datacenter_indices/report_canonical_v2_group_context_builder.py` | V2 context builder | REMOVED_PHASE_C | Removed V2 writer while preserving current `dc_group_swing_signal_daily` and `dc_group_synthetic_ohlc_daily` source facts. | Preserve current source fact pipeline. |
| `analysis/datacenter_indices/report_canonical_v2_daily_context_builder.py` | V2 context builder | REMOVED_PHASE_C | Removed V2 writer while preserving `dc_ticker_swing_signal_daily`. | Preserve current source fact pipeline. |
| `analysis/datacenter_indices/report_canonical_v2_window_context_builder.py` | V2 context builder | REMOVED_PHASE_C | Removed V2 writer while preserving current `dc_*` source facts. | Preserve current source fact pipeline. |
| `analysis/datacenter_indices/report_canonical_v2_*_classification_writer.py` | V2 classification writers | REMOVED_PHASE_C | Removed V2 readmodel classification writers. | No further action until docs/archive and DB cleanup phases. |
| `analysis/datacenter_indices/report_canonical_v2_*_formatter_loader.py` | V2 formatter/query/readmodel loaders | REMOVED_PHASE_C | Removed V2 formatter loaders after dev_tools entrypoints were retired. | No further action until docs/archive phase. |
| `analysis/datacenter_indices/report_canonical_v2_parity_audit.py` | V2 parity/audit code | REMOVED_PHASE_C | Removed V2 parity code after manual V2 workflow retirement. | No further action until docs/archive phase. |
| `dev_tools/run_report_canonical_v2_output.py` | Retired manual render CLI stub | PRESERVE_UNTIL_LATER | Phase B replaced executable behavior with a retired entrypoint that exits non-zero and does not open DBs or import V2 formatter modules. | Keep until a later docs/stub cleanup phase explicitly deletes retired entrypoints. |
| `dev_tools/run_report_canonical_v2_publish_outputs.py` | Retired manual publish CLI stub | PRESERVE_UNTIL_LATER | Phase B replaced executable behavior with a retired entrypoint that exits non-zero and does not publish outputs. | Keep until a later docs/stub cleanup phase explicitly deletes retired entrypoints. |
| `dev_tools/run_report_canonical_v2_daily_markdown_smoke.py` and `run_report_canonical_v2_all_outputs_smoke.py` | Retired build/smoke CLI stubs | PRESERVE_UNTIL_LATER | Phase B removed build/smoke behavior from these entrypoints; they no longer apply V2 migrations or write DB/output state. | Keep until a later docs/stub cleanup phase explicitly deletes retired entrypoints. |
| `dev_tools/run_report_canonical_v2_*_{markdown,csv}.py` | Retired manual output CLI stubs | PRESERVE_UNTIL_LATER | Phase B replaced render behavior with retired entrypoints that exit non-zero. | Keep until a later docs/stub cleanup phase explicitly deletes retired entrypoints. |
| `dev_tools/run_report_canonical_v2_parity_audit.py` | Retired manual parity CLI stub | PRESERVE_UNTIL_LATER | Phase B replaced parity behavior with a retired entrypoint that exits non-zero and does not import V2 parity code. | Keep until a later docs/stub cleanup phase explicitly deletes retired entrypoints. |
| `tests/test_report_canonical_v2_*.py` | Test suite | REMOVED_OR_PRESERVED_PHASE_C | Direct non-CLI V2 tests were removed. `tests/test_report_canonical_v2_retired_cli.py` remains to validate retired stubs. | Keep retired-stub test until stubs are deleted later. |
| `docs/report_canonical_v2_*.md` | Canonical V2 docs | AMBIGUOUS | Docs record accepted production baseline and manual publish workflow, not merely historical notes. | Archive only after V2 manual workflow is explicitly obsolete. |
| `docs/datacenter_report_canonical_v2_architecture*.md` | V2 architecture docs | AMBIGUOUS | Design docs for V2 readmodel and report outputs; still relevant if manual V2 is kept. | Archive only after V2 is retired. |
| `rawcandle/scheduler/*`, `rawcandle/cli/run_stock_update_scheduler.py` | Scheduler/current CLI | PRESERVE | Targeted search found no active `report_canonical_v2` or `dc_report_*_v2` references in scheduler paths. | Preserve; no Phase B scheduler neutralization appears needed from current evidence. |
| `rawcandle/ec_*_loader.py`, `rawcandle/cli/plan_ec_source_layer_*.py`, `tests/test_*ec_source_layer*` | Current `ec_*` sidecar | PRESERVE | Current sidecar consumes `dc_*` source facts and writes `ec_*`; unrelated to V2 readmodel removal target. | Preserve. |
| Current `dc_*` source fact docs/tests/builders | Current Datacenter source facts | PRESERVE | `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily`, `dc_group_synthetic_ohlc_daily`, `dc_group_index_daily`, and `dc_pipeline_watermark` are active sources for legacy reports, dashboard, and `ec_*`. | Preserve. |
| Existing DB tables named `dc_report_*_v2` | DB tables | DB_CLEANUP_LATER | Actual presence/row counts were not inspected in this audit. | Separate read-only DB preflight against explicit DB path, then backup-confirmed cleanup if approved. |

## Current-source preserve evidence

The following paths use current `dc_*` source facts and should not be removed as part of `dc_report_*_v2` cleanup:

- `rawcandle/ec_ticker_signal_daily_loader.py` reads `dc_ticker_swing_signal_daily`.
- `rawcandle/ec_group_signal_daily_loader.py` reads `dc_group_swing_signal_daily`.
- `rawcandle/ec_group_synthetic_ohlc_daily_loader.py` reads `dc_group_synthetic_ohlc_daily`.
- `rawcandle/ec_group_index_daily_loader.py` reads `dc_group_index_daily`.
- `rawcandle/ec_pipeline_watermark_loader.py` reads `dc_pipeline_watermark` and source fact tables.
- `rawcandle/ec_dc_coverage_audit.py` and `rawcandle/ec_dc_fact_parity_audit.py` validate current `dc_*` to `ec_*` coverage/parity.
- `rawcandle/cli/plan_ec_source_layer_build.py`, `plan_ec_source_layer_refresh.py`, and `plan_ec_source_layer_backfill.py` inspect current `dc_*` source fact readiness.
- `docs/datacenter_legacy_report_generation_reference.md` records current legacy Datacenter reports as reading `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily`, and `dc_group_synthetic_ohlc_daily`.
- `docs/datacenter_dc_tables_reference.md` classifies these source fact tables as active Datacenter pipeline tables.

## Removal blockers and open questions

Blockers before removal:

- `analysis/database_manager.py` still applies the V2 migration set for new analysis DB initialization.
- Production docs describe Canonical V2 as an accepted manual/publish baseline, not archived history.
- `dev_tools/run_report_canonical_v2_publish_outputs.py` is explicitly read-only against DB but writes output files and is documented as a manual publish workflow.
- Extensive tests validate V2 behavior; removing them without a policy decision would remove coverage for an apparently accepted manual output path.

Open questions:

- Is Canonical Report V2 still a supported manual output family, or has it been superseded by current legacy reports plus `ec_*` sidecar/dashboard work?
- If it is obsolete, should the first runtime change be to stop `DatabaseManager` from applying migrations `004`-`014`?
- Should existing `docs/report_canonical_v2_*` be archived as historical evidence or kept as an accepted manual baseline?
- Should V2 migrations `004`-`014` remain as historical inert migrations after code removal, or be archived after compatibility analysis?
- Which explicit DB paths should be preflighted later for `dc_report_*_v2` table presence and row counts?

## Proposed phased removal plan

### Phase A: audit only

This document. No code, runtime, migration, test, or DB changes.

### Phase B: neutralize active runtime/init/report hooks

If Canonical V2 is approved for retirement, first remove or neutralize active hooks:

- `analysis/database_manager.py` automatic `apply_report_canonical_v2_migration(conn)` call.
- Manual build/smoke CLIs that apply V2 migrations or populate V2 rows.
- Manual output/publish CLIs only after delivery policy is changed.

Current evidence does not show scheduler hooks for `dc_report_*_v2`, so scheduler neutralization may not be needed.

### Phase C: remove old V2 CLIs/builders/query/readmodel code and direct tests

After active hooks are gone:

- Remove `analysis/datacenter_indices/report_canonical_v2_*.py`.
- Remove `rawcandle/report_canonical_v2_migration.py` if no longer needed.
- Remove `dev_tools/run_report_canonical_v2_*.py`.
- Remove `tests/test_report_canonical_v2_*.py`.

Preserve current `dc_*` source fact builders/loaders/pipeline and all `ec_*` sidecar code.

### Phase D: archive/remove obsolete docs

Archive or remove docs that only describe the retired Canonical V2 path:

- `docs/report_canonical_v2_*.md`
- `docs/datacenter_report_canonical_v2_architecture*.md`

Keep current `dc_*`, `ec_*`, scheduler, dashboard, and legacy Datacenter report docs.

### Phase E: migration strategy

Decide whether migrations `004`-`014` stay as historical inert migrations or are archived/removed. Do not change migrations until compatibility and fresh-DB initialization consequences are explicit.

### Phase F: read-only DB preflight

For each explicit DB path, run a separate read-only preflight that lists:

- `dc_report_*_v2` table names.
- Row counts.
- Related indexes/triggers/views.
- `PRAGMA integrity_check`.
- `PRAGMA foreign_key_check`.

No DB contents were inspected in this audit. Do not infer actual table presence from code or migrations.

### Phase G: backup-confirmed DB cleanup

Only after code/runtime removal and DB preflight:

- Create and verify a backup.
- Drop only approved `dc_report_*_v2` tables.
- Preserve all current `dc_*` source facts and `ec_*` tables.
- Do not run `VACUUM` unless separately approved.

## Recommended next Codex step

Prepare a no-runtime-change decision note for Canonical Report V2 support status:

- Option 1: preserve manual Canonical V2 output/publish workflow and stop this removal track.
- Option 2: retire Canonical V2, starting with a Phase B plan to neutralize `analysis/database_manager.py` migration application and manual V2 build/publish CLIs.

Do not remove files or drop `dc_report_*_v2` tables until that decision is explicit.
