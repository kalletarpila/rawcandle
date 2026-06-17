# dc_report_*_v2 analysis DB preflight

## Executive summary

Read-only Phase G preflight was run against `/home/kalle/projects/rawcandle/data/analysis.db` for retired Canonical Report V2 `dc_report_*_v2` tables.

Assessment: `CLEANUP_CANDIDATE_WITH_BACKUP_REQUIRED`.

The database contains all 17 known retired `dc_report_*_v2` tables with 2,341 total rows. `PRAGMA integrity_check` returned `ok`, and `PRAGMA foreign_key_check` reported 0 violations. Current preserved `dc_*` source fact tables and current `ec_*` key tables were present. Later cleanup appears technically feasible, but only through a separate approved prompt with verified backup, explicit drop plan, rollback instructions, and post-cleanup checks.

No DB writes were performed. No tables were dropped. No backup was created in this step. `VACUUM` remains a separate high-risk operation requiring explicit approval and disk-space checks.

## Target DB

| Field | Value |
|---|---|
| DB path | `/home/kalle/projects/rawcandle/data/analysis.db` |
| DB file size | `4,609,642,496` bytes |
| Read-only command | `rawcandle.cli.preflight_dc_report_v2_db_cleanup` |
| Preflight status | `DC_REPORT_V2_TABLES_FOUND` |
| Assessment | `CLEANUP_CANDIDATE_WITH_BACKUP_REQUIRED` |

WAL/SHM files were present and were not modified intentionally:

- `/home/kalle/projects/rawcandle/data/analysis.db-wal`
- `/home/kalle/projects/rawcandle/data/analysis.db-shm`

## Commands Run

```bash
git status --short
ls -lh /home/kalle/projects/rawcandle/data/analysis.db
ls -lh /home/kalle/projects/rawcandle/data/analysis.db-wal /home/kalle/projects/rawcandle/data/analysis.db-shm
PYTHONPATH=. python3 -m rawcandle.cli.preflight_dc_report_v2_db_cleanup --db /home/kalle/projects/rawcandle/data/analysis.db
PYTHONPATH=. python3 -m rawcandle.cli.preflight_dc_report_v2_db_cleanup --db /home/kalle/projects/rawcandle/data/analysis.db --format json
```

The preflight CLI opens the DB with SQLite read-only URI mode and only runs schema inventory queries plus read-only PRAGMAs.

## V2 Table Inventory

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

Total old V2 rows: `2,341`.

Missing known V2 tables: none.

## Related Schema Objects

Related indexes found: `49`.

| Table | Indexes |
|---|---|
| `dc_report_classification_v2` | `idx_dc_report_classification_v2_date_horizon`, `idx_dc_report_classification_v2_ticker`, `sqlite_autoindex_dc_report_classification_v2_1` |
| `dc_report_context_daily_v2` | `idx_dc_report_context_daily_v2_date`, `idx_dc_report_context_daily_v2_ticker`, `sqlite_autoindex_dc_report_context_daily_v2_1` |
| `dc_report_context_group_v2` | `idx_dc_report_context_group_v2_date_horizon`, `idx_dc_report_context_group_v2_group`, `sqlite_autoindex_dc_report_context_group_v2_1` |
| `dc_report_context_window_v2` | `idx_dc_report_context_window_v2_date_horizon`, `idx_dc_report_context_window_v2_ticker_horizon`, `sqlite_autoindex_dc_report_context_window_v2_1` |
| `dc_report_data_quality_summary_v2` | `idx_dc_report_data_quality_summary_v2_date_taxonomy_window_status`, `idx_dc_report_data_quality_summary_v2_scope`, `sqlite_autoindex_dc_report_data_quality_summary_v2_1` |
| `dc_report_ecosystem_window_change_v2` | `idx_dc_report_ecosystem_window_change_v2_change_status`, `idx_dc_report_ecosystem_window_change_v2_date_taxonomy_window_scope`, `sqlite_autoindex_dc_report_ecosystem_window_change_v2_1` |
| `dc_report_group_overheat_progression_v2` | `idx_dc_report_group_overheat_progression_v2_date_taxonomy_window_scope`, `idx_dc_report_group_overheat_progression_v2_progression`, `sqlite_autoindex_dc_report_group_overheat_progression_v2_1` |
| `dc_report_group_relative_change_v2` | `idx_dc_report_group_relative_change_v2_date_taxonomy_window_scope`, `idx_dc_report_group_relative_change_v2_metric_direction`, `sqlite_autoindex_dc_report_group_relative_change_v2_1` |
| `dc_report_group_timing_persistence_v2` | `idx_dc_report_group_timing_persistence_v2_date_taxonomy_window_scope`, `idx_dc_report_group_timing_persistence_v2_persistence_status`, `sqlite_autoindex_dc_report_group_timing_persistence_v2_1` |
| `dc_report_ma_break_status_v2` | `idx_dc_report_ma_break_status_v2_break_status`, `idx_dc_report_ma_break_status_v2_date_taxonomy_window_scope`, `sqlite_autoindex_dc_report_ma_break_status_v2_1` |
| `dc_report_run_v2` | `sqlite_autoindex_dc_report_run_v2_1` |
| `dc_report_signal_freshness_v2` | `idx_dc_report_signal_freshness_v2_date_taxonomy_window_scope`, `idx_dc_report_signal_freshness_v2_freshness_status`, `sqlite_autoindex_dc_report_signal_freshness_v2_1` |
| `dc_report_synthetic_event_history_v2` | `idx_dc_report_synthetic_event_history_v2_bos_reset`, `idx_dc_report_synthetic_event_history_v2_date_taxonomy_window_scope`, `idx_dc_report_synthetic_event_history_v2_event_type_direction`, `sqlite_autoindex_dc_report_synthetic_event_history_v2_1` |
| `dc_report_taxonomy_ticker_coverage_v2` | `idx_dc_report_taxonomy_ticker_coverage_v2_date_taxonomy_status`, `idx_dc_report_taxonomy_ticker_coverage_v2_ticker`, `sqlite_autoindex_dc_report_taxonomy_ticker_coverage_v2_1` |
| `dc_report_technical_relevance_context_v2` | `idx_dc_report_technical_relevance_context_v2_date_taxonomy_window_ticker`, `idx_dc_report_technical_relevance_context_v2_relevance_family`, `sqlite_autoindex_dc_report_technical_relevance_context_v2_1` |
| `dc_report_valid_signal_date_v2` | `idx_dc_report_valid_signal_date_v2_date_taxonomy_window`, `sqlite_autoindex_dc_report_valid_signal_date_v2_1` |
| `dc_report_watchlist_ticker_v2` | `idx_dc_report_watchlist_ticker_v2_date_taxonomy_window_status`, `idx_dc_report_watchlist_ticker_v2_ticker`, `sqlite_autoindex_dc_report_watchlist_ticker_v2_1` |

Related triggers: none.

Related views: none.

## Integrity and FK Checks

| Check | Result |
|---|---|
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` violation count | `0` |
| `page_count` | `1,125,401` |
| `freelist_count` | `8,493` |

No integrity or foreign-key issue was found that would block a later backup-confirmed cleanup plan.

## Preserved Current Tables

Current `dc_*` source fact tables:

| Table | Presence |
|---|---|
| `dc_group_index_daily` | present |
| `dc_group_swing_signal_daily` | present |
| `dc_group_synthetic_ohlc_daily` | present |
| `dc_pipeline_watermark` | present |
| `dc_ticker_swing_signal_daily` | present |

Current `ec_*` key tables:

| Table | Presence |
|---|---|
| `ec_group_index_daily` | present |
| `ec_group_signal_daily` | present |
| `ec_group_synthetic_ohlc_daily` | present |
| `ec_pipeline_watermark` | present |
| `ec_ticker_signal_daily` | present |

## Recommended Next Step

Prepare a separate backup-confirmed Phase H cleanup prompt only if the user approves table removal. That prompt should create and verify a backup first, define an explicit drop list for the 17 V2 tables, preserve current `dc_*` and `ec_*` tables, run post-cleanup integrity/FK checks, and keep `VACUUM` out of scope unless separately approved.

If cleanup is not approved, leave the V2 tables in place and keep this preflight as the recorded DB state.

## Explicit Warnings

- No DB writes were performed.
- No tables were dropped.
- No backup was created in this step.
- Any cleanup requires a separate approved prompt with backup and rollback instructions.
- `VACUUM` and `VACUUM INTO` remain separate high-risk operations requiring explicit approval and disk-space checks.
