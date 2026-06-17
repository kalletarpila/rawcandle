# dc_report_*_v2 analysis DB cleanup

## Executive summary

Phase H backup-confirmed cleanup completed for retired Canonical Report V2 `dc_report_*_v2` tables in `/home/kalle/projects/rawcandle/data/analysis.db`.

Assessment: `DC_REPORT_V2_TABLE_CLEANUP_COMPLETED`.

The cleanup dropped exactly the 17 known retired V2 tables from `rawcandle.cli.preflight_dc_report_v2_db_cleanup.KNOWN_V2_TABLES`. A verified SQLite backup was created before any successful write. Post-cleanup preflight found no remaining known V2 tables, `PRAGMA integrity_check` returned `ok`, and `PRAGMA foreign_key_check` reported 0 violations. Current preserved `dc_*` source fact tables and current `ec_*` key tables remained present.

No `VACUUM` or `VACUUM INTO` was run. File-size reduction is out of scope for this phase.

## Target and Backup

| Field | Value |
|---|---|
| Target DB | `/home/kalle/projects/rawcandle/data/analysis.db` |
| Backup path | `/home/kalle/projects/rawcandle/temp/analysis__before_dc_report_v2_cleanup__20260617T143742Z.sqlite` |
| Backup size | `4,609,642,496` bytes |
| Backup method | SQLite backup API |
| Backup integrity | `ok` |
| Backup V2 table count | `17` |
| Backup V2 row count | `2,341` |

The backup preflight confirmed the same 17 V2 tables, the same total V2 row count, clean integrity/FK checks, and preserved current `dc_*` / `ec_*` key table presence before cleanup proceeded.

## Pre-cleanup Preflight

| Field | Value |
|---|---|
| Status | `DC_REPORT_V2_TABLES_FOUND` |
| V2 table count | `17` |
| Total V2 rows | `2,341` |
| Missing known V2 tables | none |
| Related indexes | `49` |
| Related triggers | none |
| Related views | none |
| `integrity_check` | `ok` |
| FK violation count | `0` |
| `page_count` | `1,125,401` |
| `freelist_count` | `8,493` |
| DB size | `4,609,642,496` bytes |

Pre-cleanup row counts:

| Table | Row count |
|---|---:|
| `dc_report_classification_v2` | 1,180 |
| `dc_report_context_daily_v2` | 236 |
| `dc_report_context_group_v2` | 216 |
| `dc_report_context_window_v2` | 708 |
| `dc_report_data_quality_summary_v2` | 0 |
| `dc_report_ecosystem_window_change_v2` | 0 |
| `dc_report_group_overheat_progression_v2` | 0 |
| `dc_report_group_relative_change_v2` | 0 |
| `dc_report_group_timing_persistence_v2` | 0 |
| `dc_report_ma_break_status_v2` | 0 |
| `dc_report_run_v2` | 1 |
| `dc_report_signal_freshness_v2` | 0 |
| `dc_report_synthetic_event_history_v2` | 0 |
| `dc_report_taxonomy_ticker_coverage_v2` | 0 |
| `dc_report_technical_relevance_context_v2` | 0 |
| `dc_report_valid_signal_date_v2` | 0 |
| `dc_report_watchlist_ticker_v2` | 0 |

## Drop List Executed

The first drop command attempt failed before `BEGIN` because of shell quoting in an inspection query. It did not drop tables or commit changes. The corrected command validated that all 17 known V2 tables were present, opened a transaction, and dropped only the following exact known V2 tables:

| Order | Table |
|---:|---|
| 1 | `dc_report_classification_v2` |
| 2 | `dc_report_context_daily_v2` |
| 3 | `dc_report_context_group_v2` |
| 4 | `dc_report_context_window_v2` |
| 5 | `dc_report_data_quality_summary_v2` |
| 6 | `dc_report_ecosystem_window_change_v2` |
| 7 | `dc_report_group_overheat_progression_v2` |
| 8 | `dc_report_group_relative_change_v2` |
| 9 | `dc_report_group_timing_persistence_v2` |
| 10 | `dc_report_ma_break_status_v2` |
| 11 | `dc_report_signal_freshness_v2` |
| 12 | `dc_report_synthetic_event_history_v2` |
| 13 | `dc_report_taxonomy_ticker_coverage_v2` |
| 14 | `dc_report_technical_relevance_context_v2` |
| 15 | `dc_report_valid_signal_date_v2` |
| 16 | `dc_report_watchlist_ticker_v2` |
| 17 | `dc_report_run_v2` |

`PRAGMA foreign_keys=ON` was used for the successful drop transaction. No `VACUUM` was run.

## Post-cleanup Preflight

| Field | Value |
|---|---|
| Status | `NO_DC_REPORT_V2_TABLES_FOUND` |
| V2 table count | `0` |
| Total V2 rows | `0` |
| Remaining known V2 tables | none |
| Related indexes/triggers/views | none |
| `integrity_check` | `ok` |
| FK violation count | `0` |
| `page_count` | `1,125,401` |
| `freelist_count` | `8,877` |
| DB size | `4,609,642,496` bytes |

Direct SQLite checks also found no remaining known V2 tables. `PRAGMA integrity_check` returned `ok`; `PRAGMA foreign_key_check` returned no rows.

## Preserved Current Tables

Current `dc_*` source fact tables remained present:

| Table | Presence |
|---|---|
| `dc_group_index_daily` | present |
| `dc_group_swing_signal_daily` | present |
| `dc_group_synthetic_ohlc_daily` | present |
| `dc_pipeline_watermark` | present |
| `dc_ticker_swing_signal_daily` | present |

Current `ec_*` key tables remained present:

| Table | Presence |
|---|---|
| `ec_group_index_daily` | present |
| `ec_group_signal_daily` | present |
| `ec_group_synthetic_ohlc_daily` | present |
| `ec_pipeline_watermark` | present |
| `ec_ticker_signal_daily` | present |

## Tests and Checks

| Command | Result |
|---|---|
| `pytest -q tests/test_preflight_dc_report_v2_db_cleanup_cli.py` | 10 passed |
| `pytest -q tests/test_preflight_eco_legacy_db_cleanup_cli.py` | 8 passed |
| `pytest -q tests -k "report_canonical_v2"` | R2 follow-up check passed |
| `pytest -q tests/test_plan_ec_source_layer_build_cli.py tests/test_plan_ec_source_layer_refresh_cli.py tests/test_plan_ec_source_layer_backfill_cli.py` | 30 passed |
| `pytest -q tests/test_run_ec_source_layer_build_cli.py` | 13 passed |
| `pytest -q tests/test_stock_update_scheduler_runner.py -k "v3_reports or ec_source_layer or datacenter_pipeline"` | 9 passed, 101 deselected |
| `pytest -q tests/test_stock_update_scheduler_cli.py -k "v3_reports or summary or datacenter"` | 7 passed, 10 deselected |
| `python3 -m py_compile rawcandle/cli/preflight_dc_report_v2_db_cleanup.py rawcandle/cli/preflight_eco_legacy_db_cleanup.py` | passed |
| `python3 -m py_compile analysis/database_manager.py rawcandle/scheduler/runner.py rawcandle/scheduler/config.py rawcandle/cli/run_stock_update_scheduler.py` | passed |
| Canonical Report V2 retired dev_tools py_compile | removed in R2; no stub files remain |

No scheduler, stock update, refresh, backfill, recovery, report generation, or Canonical V2 build/publish/smoke command was run.

## Rollback Instructions

If rollback is required:

1. Stop all DB writers and confirm no scheduler, refresh, backfill, stock update, report, or manual DB process is using `analysis.db`.
2. Replace `/home/kalle/projects/rawcandle/data/analysis.db` with `/home/kalle/projects/rawcandle/temp/analysis__before_dc_report_v2_cleanup__20260617T143742Z.sqlite`.
3. Handle WAL/SHM files consistently with the chosen restore method; do not reuse stale WAL/SHM state without verification.
4. Re-run read-only V2 preflight against the restored DB.
5. Re-run `PRAGMA integrity_check` and `PRAGMA foreign_key_check`.
6. Verify current `dc_*` and `ec_*` key table presence.

## Things Not Touched

- No `VACUUM` or `VACUUM INTO`.
- No migrations `004`-`014`.
- No migrations `019`-`024`.
- No runtime code.
- No tests.
- No scheduler behavior or scheduler config shape.
- No `scheduler_config.json`.
- No current `dc_*` source fact builders/loaders.
- No current legacy Datacenter reports.
- No current `ec_*` sidecar files.
- No `ec_source_layer` behavior.
- No `/home/kalle/projects/rawcandle/data/osakedata.db`.

## Recommended Next Step

Run a read-only post-cleanup readiness verification phase against `analysis.db` if desired. Keep `VACUUM` separate; file-size reduction requires a distinct approval, disk-space check, and backup strategy.
