# dc_dashboard Legacy DB Preflight: analysis.db

## Executive summary

Read-only preflight was completed for dashboard legacy table cleanup decisions against `/home/kalle/projects/rawcandle/data/analysis.db`.

Assessment: `NO_DASHBOARD_SNAPSHOT_CLEANUP_NEEDED`.

No old snapshot-style `dc_dashboard_*` tables were found, and no unknown `dc_dashboard%` tables were found. The five current `_daily` dashboard/enrichment tables were present and must be preserved. `PRAGMA integrity_check` returned `ok`, and `PRAGMA foreign_key_check` reported 0 violations.

No DB writes were performed. No tables were dropped. No backup was created. No `VACUUM` or `VACUUM INTO` was run.

## Scope

| Field | Value |
|---|---|
| DB path | `/home/kalle/projects/rawcandle/data/analysis.db` |
| Mode | read-only preflight |
| CLI | `rawcandle.cli.preflight_dc_dashboard_legacy_db_cleanup` |
| Assessment | `NO_DASHBOARD_SNAPSHOT_CLEANUP_NEEDED` |
| DB size | `4,609,642,496` bytes |
| WAL file observed | `/home/kalle/projects/rawcandle/data/analysis.db-wal` present, `158M` |
| SHM file observed | `/home/kalle/projects/rawcandle/data/analysis.db-shm` present, `320K` |

WAL/SHM files were only listed. They were not modified or deleted.

## Commands Run

```bash
git status --short
git diff --stat
ls -lh /home/kalle/projects/rawcandle/data/analysis.db
ls -lh /home/kalle/projects/rawcandle/data/analysis.db-wal /home/kalle/projects/rawcandle/data/analysis.db-shm 2>/dev/null || true
PYTHONPATH=. python3 -m rawcandle.cli.preflight_dc_dashboard_legacy_db_cleanup --db /home/kalle/projects/rawcandle/data/analysis.db
PYTHONPATH=. python3 -m rawcandle.cli.preflight_dc_dashboard_legacy_db_cleanup --db /home/kalle/projects/rawcandle/data/analysis.db --format json
```

The CLI opens SQLite with read-only URI mode.

## Preflight Result

| Check | Result |
|---|---|
| status | `NO_LEGACY_DASHBOARD_SNAPSHOT_TABLES_FOUND` |
| legacy snapshot table count | `0` |
| total legacy snapshot rows | `0` |
| other `dc_dashboard%` unknown tables | none |
| related indexes for legacy snapshot tables | none |
| related triggers for legacy snapshot tables | none |
| related views for legacy snapshot tables | none |
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` violations | `0` |
| `page_count` | `1,125,401` |
| `freelist_count` | `8,877` |

## Old Snapshot Table Inventory

No old snapshot-style dashboard tables were present.

| Table | Present | Row count |
|---|---:|---:|
| `dc_dashboard_decision_trace` | no | `0` |
| `dc_dashboard_market_map` | no | `0` |
| `dc_dashboard_runs` | no | `0` |
| `dc_dashboard_source_reports` | no | `0` |
| `dc_dashboard_ticker_status` | no | `0` |
| `dc_dashboard_watchlist_status` | no | `0` |

## Current Preserved Tables

These current `_daily` dashboard/enrichment tables were present and must not be dropped by legacy snapshot cleanup.

| Table | Present | Row count |
|---|---:|---:|
| `dc_dashboard_action_summary_daily` | yes | `32` |
| `dc_dashboard_decision_trace_daily` | yes | `34,383` |
| `dc_dashboard_enrichment_run_daily` | yes | `9` |
| `dc_dashboard_group_enrichment_daily` | yes | `486` |
| `dc_dashboard_ticker_enrichment_daily` | yes | `2,124` |

## Unknown Dashboard-Like Tables

No additional `dc_dashboard%` tables were reported as `UNKNOWN_REVIEW_REQUIRED`.

## Related Schema Objects

No indexes, triggers, or views were associated with old snapshot-style dashboard tables because no old snapshot-style dashboard tables were present.

## Cleanup Assessment

No dashboard snapshot cleanup is needed for `/home/kalle/projects/rawcandle/data/analysis.db` based on this preflight.

Cleanup is not blocked by unknown dashboard-like tables, integrity issues, or foreign-key issues. There is also no old snapshot table cleanup candidate to act on.

## Warnings

- This was a read-only verification/reporting step.
- No DB writes were performed.
- No tables were dropped.
- No backup was created in this step.
- The current `_daily` enrichment tables must not be dropped by legacy snapshot cleanup.
- Any future cleanup requires a separate approved prompt with an explicit DB path, verified backup, rollback plan, and approved drop list.
- `VACUUM` and `VACUUM INTO` remain separate high-risk operations requiring backup and disk-space checks.

## Recommended Next Step

No `dc_dashboard` DB cleanup is recommended for `analysis.db`.

If another database is suspected to contain old snapshot-style dashboard tables, run the same read-only preflight against that explicit DB path before planning any cleanup.
