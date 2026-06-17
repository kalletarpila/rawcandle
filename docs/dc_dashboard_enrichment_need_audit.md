# dc_dashboard Enrichment Need Audit

## Executive summary

Decision assessment: `AMBIGUOUS_NEEDS_UI_DECISION`, with interim recommendation `PRESERVE_FOR_NOW`.

Decision follow-up: [dc_dashboard_ui_enrichment_retirement_decision.md](/home/kalle/projects/rawcandle/docs/dc_dashboard_ui_enrichment_retirement_decision.md) now records the user decision `RETIRE_DASHBOARD_UI_HTML_AND_ENRICHMENT`. This supersedes the interim preserve-for-now stance for future work, while preserving current `dc_*`, current `ec_*`, and `ec_source_layer` boundaries.

Phase 1 status: scheduler/config/dashboard hooks for dashboard UI/HTML/enrichment have been neutralized after that decision. The scheduler and scheduler CLI no longer keep the enrichment source-mode path active. No DB tables were dropped, migrations `002`/`003` were not changed, and this audit remains historical evidence for why DB cleanup must stay behind a separate preflight/backup step.

The current `dc_dashboard_*_daily` tables are not required by the default scheduler dashboard path: `datacenter_dashboard_source_mode` defaults to `reports`, and `datacenter_enrichment_enabled` defaults to `False`. The production-safe reference path documented in the repository remains `.md reports` -> parser / decision logic -> `EcosystemDashboardInput` -> `ecosystem_dashboard.db` -> HTML.

They are still not safe to delete as a pure cleanup. Repository evidence shows an implemented opt-in/manual enrichment path, scheduler/source-mode hooks, scheduler UI fields, tests, diagnostics, acceptance checks, and a builder/export path that consume these five `_daily` tables.

The direct `dc_*` builder path exists only as `source_mode="raw-v0"` and is explicitly partial: it cannot emit dashboard-ready watchlist, action summary, decision trace, or window-status semantics. No direct `ec_*` dashboard builder was found. Retiring `dc_dashboard_*_daily` therefore requires an explicit UI/operator decision and replacement design, not just table deletion.

## Scope

This audit answers whether the current dashboard enrichment tables are still needed, or whether they can be replaced by current `dc_*` / `ec_*` data.

In scope:

- `dc_dashboard_ticker_enrichment_daily`
- `dc_dashboard_group_enrichment_daily`
- `dc_dashboard_action_summary_daily`
- `dc_dashboard_decision_trace_daily`
- `dc_dashboard_enrichment_run_daily`
- Repository code, tests, CLI/dev_tools, scheduler/config, and docs that reference the current enrichment path.

Out of scope:

- DB contents.
- DB cleanup.
- Runtime behavior changes.
- Migration deletion.
- Scheduler config changes.
- Current `dc_*` source facts.
- Current `ec_*` / `ec_source_layer`.

No DB files were inspected. No scheduler, stock update, refresh, backfill, recovery, report generation, dashboard generation, or DB-writing command was run.

## Current dependency map

| Area | Evidence | Assessment |
|---|---|---|
| Scheduler defaults | `rawcandle/scheduler/config.py` defaults `datacenter_dashboard_source_mode="reports"`, `datacenter_enrichment_enabled=False`, `datacenter_enrichment_apply_migrations=False`. | Enrichment is not required for default operation. |
| Scheduler opt-in path | `rawcandle/scheduler/runner.py` has enrichment planning and `_run_datacenter_dashboard_enrichment_post_step(...)`, guarded by config. | Removal would break an implemented opt-in path. |
| Scheduler UI | `dev_tools/stock_update_scheduler_ui.py` exposes source mode and enrichment settings. | Removal requires UI/config cleanup, not just DB cleanup. |
| Migration/init | `analysis/database_manager.py` calls `apply_datacenter_dashboard_enrichment_migration(conn)` during analysis DB initialization. | Schema helper is still wired into initialization. |
| Analysis DB builder | `dev_tools/datacenter_dashboard_analysis_db_builder.py` requires the five `_daily` tables for `source_mode="enrichment"`. | Active consumer found. |
| Raw current source fallback | The same builder supports `source_mode="raw-v0"` over `dc_ticker_swing_signal_daily` and `dc_group_swing_signal_daily`. | Replacement exists only for partial dashboard input. |
| Manual production path | `docs/DATACENTER_DASHBOARD_MANUAL_PRODUCTION_ENRICHMENT_RUNBOOK.md` documents production writes through enrichment dev_tools. | Current operator runbook depends on this layer. |
| Switch plan | `docs/DATACENTER_DASHBOARD_SCHEDULER_SWITCH_PLAN.md` describes eventual controlled source-mode switch to enrichment. | Future-facing path, not dead code. |
| Tests | `tests/test_stock_update_scheduler_runner.py`, `tests/test_stock_update_scheduler_cli.py`, and dashboard enrichment tests assert enrichment behavior and table semantics. | Removal requires targeted test strategy. |

## Table-by-table assessment

| Table | Current purpose | Producers | Consumers | Replaceability |
|---|---|---|---|---|
| `dc_dashboard_ticker_enrichment_daily` | Ticker-level dashboard-ready row source with action, severity, primary reason, pullback validity, entry readiness, candidate priority, status windows, watchlist marker, and source metadata. | `dev_tools/run_datacenter_dashboard_ticker_enrichment_write.py`, then `dev_tools/run_datacenter_dashboard_ticker_decision_enrichment_write.py`. | `dev_tools/datacenter_dashboard_analysis_db_builder.py`, action summary writer, decision trace writer, diagnostics, acceptance/audit tools. | `UNIQUE_DERIVED_FIELDS_NEED_REIMPLEMENTATION`. Some inputs come from `dc_ticker_swing_signal_daily` / `dc_group_swing_signal_daily`, but dashboard decision fields are derived and would need to move into a direct builder or another table. |
| `dc_dashboard_group_enrichment_daily` | Dashboard market-map/group enrichment rows for ecosystem/layer/subindustry hierarchy and current group status. | `dev_tools/run_datacenter_dashboard_group_enrichment_write.py`. | Analysis DB builder, diagnostics, acceptance/audit tools. | `PARTIALLY_REPLACEABLE_FROM_DC_WITH_WORK`. It reads current group/ticker source facts and taxonomy, but dashboard-ready market-map semantics would need to be rebuilt elsewhere. |
| `dc_dashboard_action_summary_daily` | Precomputed action counts for dashboard action summary. | `dev_tools/run_datacenter_dashboard_action_summary_write.py`, derived from ticker enrichment. | Analysis DB builder and dashboard input export. | `REPLACEABLE_IF_COMPUTED_AT_BUILD_TIME`. It can be removed only if action summary generation is moved into the direct builder or final dashboard build path. |
| `dc_dashboard_decision_trace_daily` | Dashboard decision trace rows derived from ticker enrichment fields. | `dev_tools/run_datacenter_dashboard_decision_trace_write.py`. | Analysis DB builder, diagnostics, acceptance/audit tools. | `UNIQUE_DERIVED_FIELDS_NEED_REIMPLEMENTATION`. Direct `dc_*` does not currently provide this ready-made trace. |
| `dc_dashboard_enrichment_run_daily` | Enrichment run metadata/readiness for a signal date and taxonomy version. | `dev_tools/run_datacenter_dashboard_enrichment_write.py`. | Analysis DB builder and audit/acceptance tooling. | `REPLACEABLE_WITH_NEW_RUN_METADATA_IF_RETIRING_LAYER`. Existing tools expect this table today. |

## Can current `dc_*` replace it?

Not as-is.

Current `dc_*` source facts are the right durable calculation sources and must be preserved, but the implemented direct dashboard path is `raw-v0`. It emits partial `EcosystemDashboardInput` and explicitly warns that action summary, decision trace, watchlist, and window status are unavailable from the direct analysis DB export.

A direct-`dc_*` replacement is plausible, but it is a new implementation task. It would need to move the ticker decision adapter, watchlist derivation, action aggregation, decision trace generation, group market-map enrichment, and run/readiness metadata into either:

- a direct builder that computes everything without persisted `_daily` enrichment tables, or
- a new current table/model explicitly chosen as the dashboard input layer.

## Can current `ec_*` replace it?

No implemented direct replacement was found.

The `ec_*` sidecar and `ec_source_layer` must be preserved, but this audit did not find a dashboard builder that reads `ec_ticker_signal_daily`, `ec_group_signal_daily`, `ec_group_synthetic_ohlc_daily`, `ec_group_index_daily`, or `ec_pipeline_watermark` directly into `EcosystemDashboardInput`.

Using `ec_*` as the dashboard source may be architecturally reasonable later, but it requires an explicit design and parity plan. It is not a cleanup-only change.

## Recommendation options

| Option | Meaning | Repository fit | Recommendation |
|---|---|---|---|
| `PRESERVE_FOR_NOW` | Keep the five `_daily` tables and related code while reports mode remains default. | Matches current tests, docs, scheduler hooks, and manual runbook. | Safe interim position. |
| `RETIRE_DASHBOARD_ENRICHMENT` | Remove enrichment source mode, writers, migrations, tests, UI fields, and later DB tables. | Possible only if the operator/product decision is to keep dashboard publishing on reports mode or another source. | Requires separate approved phase plan. |
| `REPLACE_WITH_DIRECT_DC_OR_EC_INPUT` | Replace persisted enrichment tables with a direct builder from current `dc_*` or `ec_*`. | Not currently implemented. | Requires design, parity tests, and scheduler/UI migration. |
| `AMBIGUOUS_NEEDS_UI_DECISION` | Current evidence cannot decide product direction. | Best fit: layer is optional but active enough that deletion is unsafe. | Selected decision assessment. |

## Proposed phased plan if retirement is chosen later

Phase 1: decide dashboard source strategy.

- Choose one explicit target: keep reports mode, implement direct `dc_*`, implement direct `ec_*`, or keep enrichment.
- Define whether dashboard UI/operator workflows still need action summary, decision trace, watchlist, readiness, and acceptance reports.

Phase 2: neutralize runtime hooks before deleting schema.

- Remove or hide scheduler UI fields only after replacement behavior is defined.
- Remove scheduler source-mode `enrichment` handling only with targeted scheduler tests.
- Keep reports-mode fallback intact until replacement parity is proven.

Phase 3: replace or remove dev_tools.

- If direct `dc_*` / `ec_*` input is chosen, move decision/watchlist/action/trace logic into the direct builder and add parity tests.
- If reports mode is chosen permanently, remove enrichment writers, audits, diagnostics, and runbooks in a controlled docs/code phase.

Phase 4: migration and DB cleanup strategy.

- Preserve migrations until new DB bootstrap behavior is defined.
- Drop `_daily` tables only after code no longer creates, writes, reads, audits, or tests them.
- Any production DB table drop needs separate explicit DB path, backup, reviewed drop list, rollback plan, integrity checks, and confirmation.

## Recommended checks before any later removal

- `pytest -q tests/test_stock_update_scheduler_runner.py -k "datacenter_dashboard or enrichment"`
- `pytest -q tests/test_stock_update_scheduler_cli.py -k "datacenter_dashboard or enrichment or summary"`
- `pytest -q tests/test_datacenter_dashboard_analysis_db_builder.py`
- `pytest -q tests/test_datacenter_dashboard_enrichment_schema.py tests/test_datacenter_dashboard_enrichment_write_cli.py`
- Targeted `py_compile` for scheduler/config/CLI/dev_tools touched by the later phase.
- Read-only grep proving no remaining `source_mode="enrichment"` or `_ENRICHMENT_REQUIRED_TABLES` consumers before DB cleanup.

## Files inspected

- `analysis/database_manager.py`
- `rawcandle/scheduler/config.py`
- `rawcandle/scheduler/runner.py`
- `dev_tools/datacenter_dashboard_analysis_db_builder.py`
- `dev_tools/run_datacenter_dashboard_analysis_db_export.py`
- `dev_tools/run_datacenter_dashboard_enrichment_write.py`
- `dev_tools/run_datacenter_dashboard_ticker_enrichment_write.py`
- `dev_tools/run_datacenter_dashboard_group_enrichment_write.py`
- `dev_tools/run_datacenter_dashboard_action_summary_write.py`
- `dev_tools/run_datacenter_dashboard_decision_trace_write.py`
- `dev_tools/run_datacenter_dashboard_ticker_decision_enrichment_write.py`
- `dev_tools/datacenter_dashboard_enrichment_decision_adapter.py`
- `docs/dc_dashboard_legacy_removal_audit.md`
- `docs/DATACENTER_DASHBOARD_ANALYSIS_DB_ENRICHMENT_SPEC.md`
- `docs/DATACENTER_DASHBOARD_MANUAL_PRODUCTION_ENRICHMENT_RUNBOOK.md`
- `docs/DATACENTER_DASHBOARD_SCHEDULER_SWITCH_PLAN.md`
- targeted test references found under `tests/test_stock_update_scheduler_runner.py`, `tests/test_stock_update_scheduler_cli.py`, `tests/test_datacenter_dashboard_analysis_db_builder.py`, and `tests/test_datacenter_dashboard_enrichment*`.

## Things not touched

- No runtime code changed.
- No tests changed.
- No migrations changed.
- No DB files inspected or modified.
- No DB tables dropped.
- No scheduler, stock update, refresh, backfill, recovery, report generation, or dashboard generation command run.
- No `scheduler_config.json` changed.
- No current `dc_*` source facts changed.
- No current `ec_*` or `ec_source_layer` behavior changed.
