# dc_dashboard Enrichment DB Cleanup Strategy

## Executive summary

Dashboard UI/HTML/enrichment is retired by `RETIRE_DASHBOARD_UI_HTML_AND_ENRICHMENT`.

Scheduler/config hooks were neutralized in Phase 1, dashboard/enrichment tooling was removed in Phase 2, and the remaining analysis DB initialization migration hook was neutralized in Phase 3-prestep. The remaining cleanup candidates are the five retired `dc_dashboard_*_daily` tables in `analysis.db` and historical migrations `002`/`003`.

This step is read-only. No database files were modified, no tables were dropped, no backup was created, and no `VACUUM` or `VACUUM INTO` was run.

Assessment: `DASHBOARD_ENRICHMENT_DB_CLEANUP_CANDIDATE_WITH_BACKUP_REQUIRED`.

The read-only preflight shows the five retired `_daily` tables are present, old snapshot-style dashboard tables are absent, no unknown `dc_dashboard%` tables are present, `PRAGMA integrity_check` is `ok`, and `PRAGMA foreign_key_check` reports 0 violations. A later cleanup can be planned for the five `_daily` tables only after an explicit backup-confirmed DB cleanup prompt.

## Current removal state

| Phase | State |
|---|---|
| Phase 1 | Scheduler/config dashboard UI/HTML/enrichment hooks neutralized. |
| Phase 2 | Dashboard/enrichment dev_tools, builders, exporters, diagnostics, UI/HTML paths, and direct tests removed. |
| Phase 3-prestep | `DatabaseManager` no longer applies dashboard enrichment migrations; write-capable migration helper removed. |
| Read-only preflight CLI | Preserved as `rawcandle/cli/preflight_dc_dashboard_legacy_db_cleanup.py`. |
| DB cleanup | Not yet performed. |
| Migrations `002`/`003` | Unchanged historical migration files. |

## Remaining reference classification

| Path / pattern | Category | Action |
|---|---|---|
| `rawcandle/sqlite/migrations/002_create_datacenter_dashboard_enrichment.sql` | `MIGRATION_ONLY` | Keep unchanged for now as a historical inert migration pending a later migration-history decision. |
| `rawcandle/sqlite/migrations/003_add_high_exit_risk_days_count_to_ticker_enrichment.sql` | `MIGRATION_ONLY` | Keep unchanged for now as a historical inert migration pending a later migration-history decision. |
| `rawcandle/cli/preflight_dc_dashboard_legacy_db_cleanup.py` | `PREFLIGHT_TOOL_ONLY` | Preserve read-only inventory/preflight tooling for DB cleanup planning. |
| `tests/test_preflight_dc_dashboard_legacy_db_cleanup_cli.py` | `PREFLIGHT_TOOL_ONLY` | Preserve tests for read-only preflight behavior. |
| `docs/archive/dashboard_ui_enrichment/**` | `ARCHIVE_DOC_ONLY` | Leave archived historical dashboard/enrichment specs and runbooks unchanged. |
| `docs/dc_dashboard_ui_enrichment_retirement_decision.md` | `RETIREMENT_STATUS_DOC_ONLY` | Keep status trail and link to this strategy. |
| `docs/dc_dashboard_enrichment_need_audit.md` | `RETIREMENT_STATUS_DOC_ONLY` | Keep as historical evidence; status notes supersede older preserve-for-now sections. |
| `docs/dc_dashboard_legacy_removal_audit.md` | `RETIREMENT_STATUS_DOC_ONLY` | Keep as historical audit; status notes supersede older active/ambiguous sections. |
| `docs/dc_dashboard_legacy_db_preflight_analysis_db.md` | `RETIREMENT_STATUS_DOC_ONLY` | Keep earlier snapshot-table preflight as historical evidence; this strategy reinterprets `_daily` tables under the later retirement decision. |
| `docs/eco_legacy_*analysis_db.md` | `RETIREMENT_STATUS_DOC_ONLY` | Leave historical analysis DB inventories unchanged. |

No current runtime blocker was found after Phase 3-prestep. Active runtime/dev_tools/test references to `apply_datacenter_dashboard_enrichment_migration` or `rawcandle.datacenter_dashboard_enrichment_migration` are absent.

## Migration strategy for `002`/`003`

Options:

- Keep `002`/`003` as historical inert migrations.
- Archive/remove them after a separate migration-history decision.
- Tombstone/no-op them after a separate migration-history decision.

Recommendation: keep `002`/`003` as historical inert migrations for now, matching previous legacy migration policy, unless a later migration-history decision explicitly chooses archive/remove or tombstone/no-op handling.

Do not infer current table existence from these migration files. The authoritative cleanup target must come from an explicit DB preflight against the exact DB path.

## Read-only `analysis.db` preflight result

| Field | Value |
|---|---|
| DB path | `/home/kalle/projects/rawcandle/data/analysis.db` |
| DB size | `4,609,642,496` bytes |
| CLI status | `NO_LEGACY_DASHBOARD_SNAPSHOT_TABLES_FOUND` |
| legacy snapshot table count | `0` |
| total legacy snapshot rows | `0` |
| unknown `dc_dashboard%` table count | `0` |
| related legacy indexes/triggers/views | none |
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` violations | `0` |
| `page_count` | `1,125,401` |
| `freelist_count` | `8,877` |

Current retired `_daily` table inventory:

| Table | Present | Row count |
|---|---:|---:|
| `dc_dashboard_action_summary_daily` | yes | `32` |
| `dc_dashboard_decision_trace_daily` | yes | `34,383` |
| `dc_dashboard_enrichment_run_daily` | yes | `9` |
| `dc_dashboard_group_enrichment_daily` | yes | `486` |
| `dc_dashboard_ticker_enrichment_daily` | yes | `2,124` |

The existing preflight CLI still labels these as current dashboard tables because it was originally written for legacy snapshot cleanup. Under the later retirement decision, this output is used as inventory only. It is not by itself approval to drop tables.

## Later backup-confirmed DB cleanup plan

Exact target tables:

- `dc_dashboard_decision_trace_daily`
- `dc_dashboard_action_summary_daily`
- `dc_dashboard_group_enrichment_daily`
- `dc_dashboard_ticker_enrichment_daily`
- `dc_dashboard_enrichment_run_daily`

Suggested drop order:

1. `dc_dashboard_decision_trace_daily`
2. `dc_dashboard_action_summary_daily`
3. `dc_dashboard_group_enrichment_daily`
4. `dc_dashboard_ticker_enrichment_daily`
5. `dc_dashboard_enrichment_run_daily`

Backup requirements:

- Confirm exact DB path: `/home/kalle/projects/rawcandle/data/analysis.db`.
- Create a SQLite backup API backup before any drop.
- Verify backup `PRAGMA integrity_check`.
- Record backup path and size.
- Confirm the backup still contains the five target tables before cleanup.

Rollback:

- Stop using the modified DB.
- Restore the verified backup over the target DB only after explicit approval.
- Re-run integrity and preflight checks after restore.

Post-checks after a later cleanup:

- Verify the five target `_daily` tables are absent.
- Verify no `ec_*` tables were dropped.
- Verify current `dc_*` source fact tables remain present.
- Verify `PRAGMA integrity_check` returns `ok`.
- Verify `PRAGMA foreign_key_check` reports 0 violations.
- Re-run scheduler, Datacenter, and `ec_source_layer` targeted tests.

Do not run `VACUUM` or `VACUUM INTO` unless separately approved with disk-space and backup checks.

## Safeguards

- Preserve current `dc_*` source facts.
- Preserve current `ec_*` sidecar behavior.
- Preserve `ec_source_layer`.
- Preserve legacy Datacenter Markdown/CSV reports.
- Preserve read-only preflight tooling until DB cleanup is complete.
- Do not infer table existence from migrations.
- Do not perform DB cleanup without a verified backup, rollback plan, explicit DB path, and approved drop list.

## Things not touched

- No DB tables were dropped.
- No DB files, WAL files, or SHM files were modified intentionally.
- No backup was created.
- No `VACUUM` or `VACUUM INTO` was run.
- Migrations `002`/`003` were not modified or deleted.
- Runtime code was not changed in this step.
- Tests were not modified.
- `scheduler_config.json` was not modified.
- Current `dc_*`, current `ec_*`, and `ec_source_layer` behavior were not changed.

## Recommended next step

Proceed to Phase 4: backup-confirmed DB cleanup for the five retired `dc_dashboard_*_daily` tables, if the explicit DB path and backup requirements are accepted.
