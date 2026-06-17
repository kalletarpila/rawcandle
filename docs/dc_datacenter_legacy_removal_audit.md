# dc_datacenter Legacy Removal Audit

## Executive summary

Assessment: `NO_REPOSITORY_REFERENCES_FOUND`.

Targeted searches did not find `dc_datacenter_*` or `dc_datacenter...` table, code, test, migration, CLI, scheduler, dev_tools, or documentation references in the inspected repository areas. Based on repository evidence only, there is no active `dc_datacenter_*` runtime surface to retire and no migration-backed `dc_datacenter_*` schema to plan for removal.

Removal is not ready because there is currently nothing concrete in the repository to remove. The correct next step is not deletion by name, but a read-only DB preflight against an explicitly approved DB path if the concern is that old `dc_datacenter_*` tables may still exist in a local database.

This audit does not affect current `dc_*` source facts, current legacy Datacenter reports, current `ec_*`, or `ec_source_layer`.

## Scope and preserve boundary

This audit is for `dc_datacenter_*` / `dc_datacenter...` legacy objects only.

It is not for current `dc_*` source facts:

- `dc_ticker_swing_signal_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`
- `dc_group_index_daily`
- `dc_pipeline_watermark`

It is not for:

- Current Datacenter swing pipeline.
- Current legacy Datacenter reports over current `dc_*`.
- Dashboard enrichment paths over current `dc_*`.
- Current `ec_*` sidecar.
- `ec_source_layer`.
- Scheduler stock update, Datacenter, dashboard, or `ec_source_layer` behavior.

## Evidence scope

Searches run:

- `git status --short`
- `git diff --stat`
- `rg -n "dc_datacenter|dc_datacenter_|datacenter_.*dc_|CREATE TABLE.*dc_datacenter|INSERT INTO dc_datacenter|FROM dc_datacenter|JOIN dc_datacenter|DROP TABLE.*dc_datacenter" rawcandle analysis tests docs dev_tools`
- `rg -n "datacenter.*canonical|canonical.*datacenter|datacenter.*readmodel|read_model|readmodel|datacenter.*v1|datacenter.*legacy" rawcandle analysis tests docs dev_tools`
- `find rawcandle/sqlite/migrations -maxdepth 1 -type f | sort`
- `rg -n "dc_ticker_swing_signal_daily|dc_group_swing_signal_daily|dc_group_synthetic_ohlc_daily|dc_group_index_daily|dc_pipeline_watermark" rawcandle analysis tests docs`
- `rg -n "ec_source_layer|ec_ticker_signal_daily|ec_group_signal_daily|ec_group_synthetic_ohlc_daily|ec_group_index_daily|ec_pipeline_watermark" rawcandle analysis tests docs`
- `rg -n "dc_datacenter" rawcandle analysis tests docs dev_tools`
- `rg -n "CREATE TABLE[^\n]*dc_datacenter|INSERT INTO dc_datacenter|FROM dc_datacenter|JOIN dc_datacenter|DROP TABLE[^\n]*dc_datacenter" rawcandle analysis tests docs dev_tools`
- `rg -n "dc_datacenter" rawcandle/sqlite/migrations`
- `rg -n "dc_datacenter" rawcandle/scheduler rawcandle/cli analysis/datacenter_indices dev_tools tests`

Files inspected:

- `docs/datacenter_dc_tables_reference.md`
- `docs/datacenter_legacy_report_generation_reference.md`
- `docs/legacy_migration_policy_decision.md`

Excluded areas:

- Generated reports.
- DB files.
- WAL/SHM files.
- Backups.
- Exports.
- Temp artifacts.
- Logs.

No DB contents were inspected. No scheduler, stock update, refresh, backfill, recovery, report generation, or DB-writing command was run.

## Schema/table inventory

No `dc_datacenter_*` schema or migration references were found.

| Table name | Migration/file | Role | Category |
|---|---|---|---|
| `dc_datacenter_*` | none found | no repository schema evidence | UNKNOWN |

Near-name note: `docs/datacenter_dc_tables_reference.md` documents `dc_ecosystem_membership` as an unclear or possibly unused schema placeholder, but that table is not named `dc_datacenter_*` and is outside this audit target. It should not be removed or reclassified by this audit.

## Categorized inventory

| Path | Symbol/table/pattern | Reference type | Category | Reason | Suggested next action |
|---|---|---|---|---|---|
| `rawcandle/sqlite/migrations/**` | `dc_datacenter` | Migration/schema | UNKNOWN | Exact search found no migration references creating or patching `dc_datacenter_*`. | No migration action. Revisit only if a later DB preflight finds matching live tables. |
| `rawcandle/**` | `dc_datacenter` | Runtime code | UNKNOWN | Exact search found no runtime references. | No runtime action. |
| `analysis/**` | `dc_datacenter` | Datacenter builders/reporting | UNKNOWN | Exact search found no builder, loader, query, or report references. | No code action. |
| `rawcandle/scheduler/**` | `dc_datacenter` | Scheduler | UNKNOWN | Exact scheduler search found no references. | Preserve scheduler behavior. |
| `rawcandle/cli/**` and `dev_tools/**` | `dc_datacenter` | CLI/dev_tools | UNKNOWN | Exact search found no CLI or dev_tools references. | No CLI action. |
| `tests/**` | `dc_datacenter` | Tests | UNKNOWN | Exact search found no test references enforcing this surface. | No test action. |
| `docs/**` | `dc_datacenter` | Documentation | UNKNOWN | Exact search found no docs that describe `dc_datacenter_*` as current. | No docs cleanup beyond this audit. |
| `docs/datacenter_dc_tables_reference.md` | current `dc_*` source facts | Documentation | PRESERVE | Documents active `dc_*` pipeline tables and explicitly distinguishes them from removed legacy systems. | Preserve. |
| `docs/datacenter_legacy_report_generation_reference.md` | legacy Datacenter reports over current `dc_*` | Documentation | PRESERVE | Documents active legacy reports reading `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily`, and `dc_group_synthetic_ohlc_daily`. | Preserve. |
| `rawcandle/ec_*`, `rawcandle/cli/plan_ec_source_layer_*`, `rawcandle/cli/run_ec_source_layer_*` | current `ec_*` and `ec_source_layer` | Runtime/CLI | PRESERVE | Current sidecar paths consume current `dc_*` source facts, not `dc_datacenter_*`. | Preserve. |

## Active runtime assessment

| Question | Assessment |
|---|---|
| Is anything in scheduler using `dc_datacenter_*`? | No repository evidence found. |
| Is any current Datacenter pipeline using it? | No repository evidence found. |
| Is any current legacy report using it? | No repository evidence found; current legacy reports use named current `dc_*` source facts. |
| Is `ec_source_layer` using it? | No repository evidence found; current `ec_source_layer` paths use current `dc_*` source facts and current `ec_*` tables. |
| Is any current CLI/dev_tool using it? | No repository evidence found. |
| Is any test still enforcing it? | No repository evidence found. |

## Proposed phased removal plan

### Phase A: audit only

Status: complete in this document. No runtime, test, migration, DB, scheduler, `dc_*`, `ec_*`, or `ec_source_layer` changes were made.

### Phase B: neutralize active hooks if any exist

No active hooks were found. If a future search or DB preflight identifies a concrete `dc_datacenter_*` code path, neutralize that hook first before deleting code.

### Phase C: remove old `dc_datacenter_*` code/tests

No code or tests were found. Do not remove current `dc_*` source fact builders, legacy reports, dashboard enrichment, or `ec_source_layer` code under this phase.

### Phase D: archive old docs

No active or archive docs containing `dc_datacenter` were found. No documentation archive action is currently needed.

### Phase E: migration strategy

No `dc_datacenter_*` migrations were found. If later evidence finds such migrations, treat them as `MIGRATION_STRATEGY_LATER` and decide separately; do not modify migration files during this audit.

### Phase F: read-only DB preflight for explicit DB path

If the concern is live table residue rather than repository references, run a later read-only preflight against an explicitly approved DB path. The preflight should list tables matching `dc_datacenter*`, row counts, related indexes/triggers/views, `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, and confirm current `dc_*` and `ec_*` table presence. This audit did not inspect DB contents.

### Phase G: backup-confirmed DB cleanup

Only if Phase F finds approved old tables, prepare a separate backup-confirmed cleanup plan. Do not drop tables without explicit approval, verified backup, reviewed drop list, rollback plan, and post-cleanup checks.

## Safeguards

- Never remove current `dc_*` source facts under a `dc_datacenter_*` cleanup label.
- Never remove current legacy Datacenter reports under this audit.
- Never remove current `ec_*` or `ec_source_layer`.
- No DB cleanup without explicit DB path, read-only preflight, backup, and confirmation.
- No `VACUUM` or `VACUUM INTO` without separate approval.
- Keep repository-code cleanup, migration strategy, and DB table cleanup as separate phases.
- Do not infer live DB table presence from repository search results.

## Recommended next Codex step

No code-removal or migration-removal step is recommended from repository evidence.

If `dc_datacenter_*` is suspected to exist in `analysis.db` or another local database, the next step should be a read-only DB preflight for an explicit DB path. If no live DB tables are found, close this cleanup target as `NO_REPOSITORY_OR_DB_SURFACE_FOUND`.

## Things not touched

- No runtime code changed.
- No tests changed.
- No migrations changed.
- No DBs inspected or modified.
- No DB tables dropped.
- No scheduler behavior changed.
- No `scheduler_config.json` changed.
- No current `dc_*` source fact generation changed.
- No current legacy Datacenter reports changed.
- No current `ec_*` sidecar behavior changed.
- No `ec_source_layer` behavior changed.
