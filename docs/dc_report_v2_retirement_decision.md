# Canonical Report V2 retirement decision

## Executive summary

Decision: `RETIRE_CANONICAL_REPORT_V2`.

Canonical Report V2 and the `dc_report_*_v2` readmodel/output workflow are retired as a supported target for future work. The retirement target is the transitional Canonical Report V2 stack: manual V2 build/output/publish tooling, V2 readmodel tables, V2 migration application path, V2 builders/writers/formatter loaders/parity code, V2-only tests, and V2-only documentation.

This decision does not retire current `dc_*` source facts, current `ec_*` sidecar tables/loaders, `ec_source_layer`, legacy Datacenter reports over `dc_*`, dashboard enrichment over current `dc_*`, or scheduler stock update/Datacenter/dashboard/`ec_source_layer` behavior.

No code, tests, migrations, runtime behavior, scheduler config, or databases were changed by this decision document.

Phase B status: DatabaseManager no longer applies Canonical Report V2 migrations during general analysis DB initialization, and `dev_tools/run_report_canonical_v2_*.py` entrypoints are retired/disabled with a deterministic non-zero exit. No DB cleanup was performed. Migrations `004`-`014` remain unchanged. Current `dc_*`, `ec_*`, `ec_source_layer`, scheduler, and legacy Datacenter paths are preserved.

Phase C status: Canonical Report V2 core modules and direct non-CLI V2 tests were removed. Retired `dev_tools/run_report_canonical_v2_*.py` stubs remain and still exit non-zero. No DB cleanup was performed. Migrations `004`-`014` remain unchanged. Current `dc_*`, `ec_*`, `ec_source_layer`, scheduler, and legacy Datacenter paths are preserved.

Phase D status: V2-only documents were archived under `docs/archive/canonical_report_v2/`. Retired `dev_tools/run_report_canonical_v2_*.py` stubs remain intentionally for compatibility and discoverability. Stub policy: return exit code `2`, do not access DBs, do not write outputs, do not import V2 core modules, and point users to this retirement decision. Full deletion of retired stubs is a later optional step after consumers have had time to discover the retirement behavior.

Phase E status: migration and database retirement strategy is documented in `docs/dc_report_v2_migration_db_retirement_strategy.md`. Recommendation: keep migrations `004`-`014` temporarily as historical inert migrations; handle any `dc_report_*_v2` DB cleanup later through explicit read-only preflight, verified backup, and approved drop plan.

Phase F status: read-only preflight CLI `rawcandle/cli/preflight_dc_report_v2_db_cleanup.py` was added for explicit DB paths. It inventories known `dc_report_*_v2` tables and preserved current `dc_*` / `ec_*` table presence without modifying DBs; cleanup still requires a separate backup-confirmed prompt.

Phase G status: read-only preflight against `/home/kalle/projects/rawcandle/data/analysis.db` is documented in `docs/dc_report_v2_db_preflight_analysis_db.md`. Result: `CLEANUP_CANDIDATE_WITH_BACKUP_REQUIRED`; 17 known V2 tables and 2,341 rows were found, with clean integrity and FK checks. No DB cleanup was performed.

Phase H status: backup-confirmed cleanup of the 17 known `dc_report_*_v2` tables from `/home/kalle/projects/rawcandle/data/analysis.db` is documented in `docs/dc_report_v2_db_cleanup_analysis_db.md`. Post-cleanup result: `NO_DC_REPORT_V2_TABLES_FOUND`, integrity `ok`, FK violations `0`. No `VACUUM` was run.

## Scope boundary

Targeted for later retirement:

- `dc_report_*_v2` readmodel tables.
- `rawcandle/report_canonical_v2_migration.py` and automatic V2 migration application.
- `analysis/datacenter_indices/report_canonical_v2_*.py` V2 builders, writers, formatter loaders, and parity code.
- `dev_tools/run_report_canonical_v2_*.py` manual V2 build, output, smoke, parity, and publish CLIs.
- `tests/test_report_canonical_v2_*.py` V2-only tests.
- `docs/report_canonical_v2_*.md` and `docs/datacenter_report_canonical_v2_architecture*.md` V2-only operational/design documentation.

Explicitly preserved:

- `dc_ticker_swing_signal_daily`.
- `dc_group_swing_signal_daily`.
- `dc_group_synthetic_ohlc_daily`.
- `dc_group_index_daily`.
- `dc_pipeline_watermark`.
- Current Datacenter swing pipeline and legacy Datacenter reports that read `dc_*` source facts.
- Dashboard enrichment over current `dc_*` source facts.
- Current `ec_*` sidecar tables/loaders/planners/migrations.
- `ec_source_layer`.
- Scheduler stock update, legacy Datacenter, dashboard, and `ec_source_layer` behavior.

## Rationale

Canonical Report V2 is a transitional readmodel/output layer. It materializes report-specific `dc_report_*_v2` tables from current `dc_*` source facts and then renders Canonical V2 outputs. The current direction is to preserve `dc_*` source facts, preserve the `ec_*` sidecar, and make future reporting/ESS decisions separately.

Keeping Canonical V2 active would continue maintaining duplicate schema, builders, CLIs, docs, and tests around a manual output family that is not currently wired into the scheduler. The accepted `2026-05-29` manual production publish baseline remains useful historical evidence, but it should be archived rather than kept as an active operational path.

The scheduler search evidence in `docs/dc_report_v2_removal_audit.md` did not find active Canonical V2 scheduler wiring. That makes retirement separable from current scheduler runtime, provided the DB initialization migration hook and manual V2 CLIs are neutralized before code deletion.

## Alternatives considered

| Option | Decision | Consequence |
|---|---|---|
| Preserve manual Canonical V2 output/publish workflow | Rejected | Stop this removal track; keep `analysis/database_manager.py` V2 migration application, V2 dev_tools CLIs, V2 builders, V2 tests, V2 docs, and any existing `dc_report_*_v2` DB tables. |
| Retire Canonical V2 | Selected | Proceed through phased retirement: neutralize active V2 init/manual hooks first, then remove V2 code/tests/docs, then handle migrations and DB cleanup only after explicit preflight and backup. |

## Required phased retirement plan

### Phase B: neutralize active init and manual hooks

Stop `analysis/database_manager.py` from applying `apply_report_canonical_v2_migration(conn)` automatically during general analysis DB initialization.

Neutralize or remove write-capable V2 build/smoke CLIs that can apply V2 migrations or populate `dc_report_*_v2` rows. Decide whether read-only output/publish CLIs are removed immediately or retained temporarily as archived-output inspection tools. No DB cleanup belongs in this phase.

Required checks before and after Phase B:

- Targeted `rg` for `apply_report_canonical_v2_migration`, `report_canonical_v2`, and `dc_report_.*_v2`.
- Scheduler-focused tests/checks that prove current stock update, Datacenter, dashboard, and `ec_source_layer` behavior is unchanged.
- `py_compile` for touched runtime modules.

### Phase C: remove V2 code and tests

After active hooks are neutralized, remove V2-only code and direct tests:

- `analysis/datacenter_indices/report_canonical_v2_*.py`.
- `rawcandle/report_canonical_v2_migration.py`, after all imports/references are gone.
- `dev_tools/run_report_canonical_v2_*.py`.
- `tests/test_report_canonical_v2_*.py`.

Required checks:

- Targeted search confirms no remaining runtime imports of removed modules.
- Current `dc_*` source fact tests, `ec_*` sidecar tests, and scheduler compatibility tests still pass.

### Phase D: archive V2 docs

Archive or remove V2-only docs after code removal:

- `docs/report_canonical_v2_*.md`.
- `docs/datacenter_report_canonical_v2_architecture*.md`.

Preserve current `dc_*`, `ec_*`, scheduler, dashboard, and legacy Datacenter report docs.

Required checks:

- Targeted docs search confirms active docs no longer instruct users to run retired V2 CLIs.
- Historical references are clearly marked as archived if retained.

### Phase E: decide migration strategy

Decide whether migrations `004`-`014` remain as historical inert migrations or are archived/removed. Do not modify these migrations until fresh-DB compatibility consequences are explicit and tested.

Required checks:

- Fresh temporary DB initialization behavior is understood without touching production databases.
- No current runtime path expects `dc_report_*_v2` tables after Phase B/C.

### Phase F: read-only DB preflight

For each explicit DB path, run a separate read-only preflight for `dc_report_*_v2` table presence, row counts, related indexes/triggers/views, `PRAGMA integrity_check`, and `PRAGMA foreign_key_check`.

Do not infer live DB state from code, docs, or migrations.

### Phase H: backup-confirmed DB cleanup

Only after code/runtime removal and DB preflight:

- Create and verify a backup.
- Drop only approved `dc_report_*_v2` tables.
- Preserve current `dc_*` source facts and all `ec_*` tables.
- Do not run `VACUUM` unless separately approved.

## Immediate next technical step

Prepare Phase B implementation: neutralize the Canonical V2 migration application in `analysis/database_manager.py` and neutralize/remove manual V2 CLIs that can create or mutate V2 readmodel state. This next step must not perform DB cleanup.

## Risks and safeguards

| Risk | Safeguard |
|---|---|
| Accidentally deleting current `dc_*` source facts instead of V2 readmodels | Treat only `dc_report_*_v2` and `report_canonical_v2` paths as the retirement target. Preserve named current `dc_*` source fact tables. |
| Breaking manual Canonical V2 users unexpectedly | This document records the support decision before runtime changes. Archive baseline docs instead of silently deleting evidence. |
| Changing fresh DB bootstrap behavior accidentally | Phase B must test DB initialization implications in a temporary DB only, not production DBs. |
| Losing rollback path before DB cleanup | Keep DB tables until after code/runtime removal, read-only preflight, and verified backup. |
| Confusing V2 retirement with `ec_*` sidecar work | Preserve `ec_*`, `ec_source_layer`, and all scheduler `ec_source_layer` behavior. |

## Things not touched in this step

- Runtime code.
- Tests.
- Migrations `004`-`014` or any later migrations.
- Scheduler behavior.
- `scheduler_config.json`.
- Production databases or local DB files.
- Generated reports, exports, backups, temp artifacts, logs, or output directories.
- Current `dc_*` source fact generation.
- Current `ec_*` sidecar generation.
