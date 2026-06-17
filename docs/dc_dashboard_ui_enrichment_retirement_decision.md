# dc_dashboard UI/HTML and Enrichment Retirement Decision

## Executive summary

DECISION: `RETIRE_DASHBOARD_UI_HTML_AND_ENRICHMENT`.

Dashboard UI is not needed. Dashboard HTML output is not needed. Dashboard enrichment is not needed as a long-term path.

This decision retires the dashboard UI/HTML/enrichment direction while preserving current non-dashboard Datacenter outputs. Reports-mode and non-dashboard report outputs remain separate from this retirement decision.

Current `dc_*` source facts, current `ec_*` sidecar tables/loaders, and `ec_source_layer` remain preserved.

No code, tests, migrations, scheduler behavior, scheduler config, or DB contents are changed by this decision document.

Phase 1 status: scheduler/config/dashboard hooks for dashboard UI/HTML/enrichment have now been neutralized in code. The scheduler no longer exposes dashboard/enrichment source-mode config, enrichment migration toggles, dashboard post-step result fields, or dashboard/enrichment CLI summary output. This intentionally breaks compatibility with scheduler config files that still contain retired dashboard/enrichment keys; `scheduler_config.json` was not edited in this step.

Phase 1 did not perform DB cleanup. Migrations `002` and `003` remain unchanged. Current `dc_*` source facts, current legacy Datacenter Markdown/CSV reports, current `ec_*`, and `ec_source_layer` remain preserved.

Phase 2 status: dashboard/enrichment dev_tools, builders, exporters, diagnostics, UI/HTML paths, and their direct tests have been removed. Active dashboard/enrichment runbooks/specs were moved under `docs/archive/dashboard_ui_enrichment/`. The read-only DB cleanup preflight `rawcandle/cli/preflight_dc_dashboard_legacy_db_cleanup.py` and its test remain preserved for later DB validation. No DB cleanup was done; migrations `002`/`003`, current `dc_*`, legacy Datacenter Markdown/CSV reports, current `ec_*`, and `ec_source_layer` remain preserved.

Phase 3-prestep status: the `DatabaseManager` dashboard enrichment migration hook has been neutralized, and the write-capable dashboard enrichment migration helper has been removed. General analysis DB initialization no longer applies dashboard enrichment migrations `002`/`003`. Migrations `002`/`003` remain unchanged as historical migration files. No DB cleanup was done; current `dc_*`, legacy Datacenter Markdown/CSV reports, current `ec_*`, and `ec_source_layer` remain preserved.

## Scope

Retirement target:

- Dashboard UI / HTML output paths.
- Dashboard/enrichment source mode.
- The five `dc_dashboard_*_daily` enrichment tables.
- Dashboard/enrichment writers, builders, diagnostics, acceptance tools, and runbooks.
- Dashboard/enrichment scheduler/config/UI hooks.
- Dashboard/enrichment tests and docs after corresponding code paths are retired.

Preserve boundary:

- Current `dc_*` source facts:
  - `dc_ticker_swing_signal_daily`
  - `dc_group_swing_signal_daily`
  - `dc_group_synthetic_ohlc_daily`
  - `dc_group_index_daily`
  - `dc_pipeline_watermark`
- Current Datacenter swing pipeline.
- Current legacy Datacenter Markdown/CSV reports over current `dc_*`, if still active.
- Current `ec_*` sidecar.
- `ec_source_layer`.
- Scheduler stock update, Datacenter, and `ec_source_layer` behavior.
- Non-dashboard Markdown/CSV reports if still active.

## Current facts

- Scheduler dashboard source mode defaults to `reports`.
- Dashboard enrichment is opt-in/manual, not required by the default scheduler path.
- `datacenter_enrichment_enabled` defaults to disabled.
- `datacenter_enrichment_apply_migrations` defaults to disabled.
- Five current `_daily` enrichment tables exist in `analysis.db` according to the earlier read-only preflight:
  - `dc_dashboard_ticker_enrichment_daily`
  - `dc_dashboard_group_enrichment_daily`
  - `dc_dashboard_action_summary_daily`
  - `dc_dashboard_decision_trace_daily`
  - `dc_dashboard_enrichment_run_daily`
- Old snapshot-style dashboard tables were not found in `analysis.db` in the earlier read-only preflight.
- Enrichment still has repository hooks: code, tests, docs, scheduler/config fields, UI settings, dev_tools, diagnostics, and builder/export consumers.
- No DB cleanup is done in this step.

## Alternatives considered

| Alternative | Assessment |
|---|---|
| Preserve dashboard enrichment | Technically possible, but rejected because dashboard UI/HTML/enrichment is no longer needed. |
| Retire dashboard UI/HTML/enrichment and keep non-dashboard reports | Selected. This preserves Datacenter source facts and legacy non-dashboard report outputs while removing an unnecessary derived dashboard readmodel direction. |
| Replace dashboard input with direct `dc_*` | Rejected for now. Direct `dc_*` dashboard input is not currently complete and dashboard output itself is not needed. |
| Replace dashboard input with `ec_*` | Rejected for now. No current direct `ec_*` dashboard builder was found, and dashboard output itself is not needed. |
| Keep selected derived fields | Not selected as part of this decision. If a future non-dashboard workflow needs selected derived fields, it should be specified as a separate source-fact or report requirement, not retained via dashboard enrichment by default. |

## Decision and rationale

Selected decision: retire dashboard UI/HTML/enrichment.

Rationale:

- User has no need for dashboard UI.
- User has no need for dashboard HTML output.
- Dashboard enrichment is not required by the default scheduler path.
- Dashboard enrichment adds an extra derived readmodel and operational path.
- Current source of truth should remain current `dc_*` source facts and current `ec_*` sidecar outputs.
- Simplification is consistent with prior legacy cleanup work: remove unneeded optional/derived systems only after documenting preserve boundaries and sequencing DB cleanup behind preflight and backup.

## Required phased retirement plan

Phase 1: neutralize scheduler/config/UI hooks.

- Neutralize or remove dashboard/enrichment scheduler/config/UI hooks.
- Remove or lock out `datacenter_dashboard_source_mode="enrichment"` support.
- Remove or neutralize `datacenter_enrichment_enabled`.
- Remove or neutralize `datacenter_enrichment_apply_migrations`.
- Preserve stock update, Datacenter, and `ec_source_layer` behavior.
- Do not perform DB cleanup in this phase.

Phase 2: remove dashboard UI / HTML output paths.

- Remove dashboard UI / HTML output paths and export builders if present.
- Remove dashboard/enrichment dev_tools writers, builders, diagnostics, and acceptance tools after scheduler hooks are neutralized.
- Preserve non-dashboard reports.

Phase 3: remove dashboard/enrichment-only tests.

- Remove or update tests that only enforce dashboard/enrichment/UI/HTML behavior.
- Preserve scheduler tests for stock update, Datacenter, and `ec_source_layer`.
- Preserve Datacenter source-fact and legacy report tests.

Phase 4: archive or update dashboard/enrichment docs.

- Archive or mark dashboard/enrichment specs, runbooks, switch plans, parity reports, and diagnostics docs as retired history.
- Keep docs that explain current `dc_*`, current `ec_*`, `ec_source_layer`, and non-dashboard report behavior.

Phase 5: migration strategy for migrations `002` and `003`.

- Keep migrations `002` and `003` as historical inert migrations unless a separate migration-policy decision says otherwise.
- Do not edit migration history as part of scheduler/config/UI neutralization.

Phase 6: read-only DB preflight for the five `_daily` tables.

- Run a read-only preflight against an explicit DB path only after code no longer creates, writes, reads, audits, or tests the five `_daily` tables.
- Confirm related indexes, triggers, views, row counts, `PRAGMA integrity_check`, and `PRAGMA foreign_key_check`.

Phase 7: backup-confirmed DB cleanup.

- Drop only the five `dc_dashboard_*_daily` enrichment tables after explicit approval.
- Require explicit DB path, verified backup, reviewed drop list, rollback plan, and post-cleanup checks.
- Do not run `VACUUM` unless separately approved.

## Safeguards

- Do not remove current `dc_*` source facts.
- Do not remove current `ec_*`.
- Do not remove `ec_source_layer`.
- Do not remove current non-dashboard legacy Datacenter reports.
- Do not drop DB tables before preflight and backup.
- Do not run dashboard/enrichment write commands during retirement planning.
- Keep runtime neutralization, docs cleanup, migration policy, and DB cleanup as separate phases.
- Do not change `scheduler_config.json` as part of this documentation decision.

## Immediate next technical step

Recommended next step: Phase 1 implementation prompt.

Phase 1 should:

- remove or neutralize `datacenter_dashboard_source_mode="enrichment"` support
- remove or neutralize `datacenter_enrichment_enabled`
- remove or neutralize `datacenter_enrichment_apply_migrations`
- remove dashboard/UI/HTML scheduler hooks only if scoped and verified
- ensure scheduler continues stock update, Datacenter, and `ec_source_layer`
- perform no DB cleanup

## Things not touched

- No runtime changes.
- No tests changed.
- No migrations changed.
- No DBs inspected or modified.
- No scheduler behavior changed.
- No scheduler config changed.
- No dashboard/enrichment write commands run.
- No current `dc_*` source facts changed.
- No current `ec_*` sidecar behavior changed.
- No `ec_source_layer` behavior changed.
