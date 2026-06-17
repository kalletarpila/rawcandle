# eco legacy DB cleanup: data/analysis.db

## Executive summary

Phase 3D old `eco_*` legacy table cleanup was completed for `/home/kalle/projects/rawcandle/data/analysis.db`.

Assessment: `ECO_TABLE_CLEANUP_COMPLETED`.

The cleanup was backup-confirmed. A SQLite backup API backup was created and verified before any table drops. The target DB then had only the approved old `eco_*` tables dropped. No `VACUUM` or `VACUUM INTO` was run, and no attempt was made to shrink the SQLite file.

## Target And Backup

| Field | Value |
|---|---|
| Target DB | `/home/kalle/projects/rawcandle/data/analysis.db` |
| Backup path | `/home/kalle/projects/rawcandle/temp/analysis__before_eco_legacy_cleanup__20260617T132223Z.sqlite` |
| Backup method | SQLite backup API |
| Backup size | 4,609,642,496 bytes |
| Backup integrity | `ok` |
| Backup old `eco_*` table count | 16 |

WAL and SHM files existed before cleanup and were not deleted manually.

## Commands Run

```bash
git status --short
ls -lh /home/kalle/projects/rawcandle/data/analysis.db
ls -lh /home/kalle/projects/rawcandle/data/analysis.db-wal /home/kalle/projects/rawcandle/data/analysis.db-shm 2>/dev/null || true
PYTHONPATH=. python3 -m rawcandle.cli.preflight_eco_legacy_db_cleanup --db /home/kalle/projects/rawcandle/data/analysis.db --format json
python3 - <<'PY'
# SQLite backup API backup and verification
PY
python3 - <<'PY'
# transactionally drop only the approved old eco_* tables
PY
PYTHONPATH=. python3 -m rawcandle.cli.preflight_eco_legacy_db_cleanup --db /home/kalle/projects/rawcandle/data/analysis.db --format json
sqlite3 -header -column /home/kalle/projects/rawcandle/data/analysis.db "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'eco_*' ORDER BY name; PRAGMA integrity_check; PRAGMA foreign_key_check;"
sqlite3 -header -column /home/kalle/projects/rawcandle/data/analysis.db "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'ec_*' ORDER BY name; SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'dc_*' ORDER BY name LIMIT 20;"
pytest -q tests/test_preflight_eco_legacy_db_cleanup_cli.py
pytest -q tests/test_plan_ec_source_layer_build_cli.py tests/test_plan_ec_source_layer_refresh_cli.py tests/test_plan_ec_source_layer_backfill_cli.py
pytest -q tests/test_run_ec_source_layer_build_cli.py
python3 -m py_compile rawcandle/cli/preflight_eco_legacy_db_cleanup.py rawcandle/scheduler/runner.py rawcandle/scheduler/config.py rawcandle/cli/run_stock_update_scheduler.py
```

No scheduler, stock update, refresh, backfill, recovery, or report generation command was run.

## Pre-Cleanup Preflight

| Field | Value |
|---|---|
| Status | `ECO_TABLES_FOUND` |
| eco table count | 16 |
| total eco rows | 72,931 |
| integrity_check | `ok` |
| foreign_key_check violation count | 0 |
| page_count | 1,125,401 |
| freelist_count | 0 |
| DB size | 4,609,150,976 bytes |

## Drop Tables Executed

Only these approved tables were dropped:

| Order | Table |
|---:|---|
| 1 | `eco_signal_relevance` |
| 2 | `eco_signal_observation` |
| 3 | `eco_entity_event` |
| 4 | `eco_classification_decision` |
| 5 | `eco_entity_window_snapshot` |
| 6 | `eco_entity_metric_value` |
| 7 | `eco_entity_coverage` |
| 8 | `eco_quality_summary` |
| 9 | `eco_report_run` |
| 10 | `eco_watchlist_member` |
| 11 | `eco_watchlist` |
| 12 | `eco_taxonomy_entity_relation` |
| 13 | `eco_report_window` |
| 14 | `eco_entity` |
| 15 | `eco_taxonomy_version` |
| 16 | `eco_ecosystem` |

The cleanup ran in a transaction. `PRAGMA foreign_keys=OFF` was used only during the drop transaction because these old legacy tables had intra-`eco_*` foreign-key relationships and the whole approved old schema was being removed together. Foreign keys were re-enabled before post-cleanup checks.

No table outside this list was dropped.

## Post-Cleanup Preflight

| Field | Value |
|---|---|
| Status | `NO_ECO_TABLES_FOUND` |
| eco table count | 0 |
| total eco rows | 0 |
| integrity_check | `ok` |
| foreign_key_check violation count | 0 |
| related indexes | 0 |
| related triggers | 0 |
| related views | 0 |
| page_count | 1,125,401 |
| freelist_count | 8,493 |
| DB size | 4,609,642,496 bytes |

Direct SQLite checks also found no remaining old `eco_*` tables. `PRAGMA integrity_check` returned `ok`, and `PRAGMA foreign_key_check` returned no rows.

## Preservation Checks

`ec_*` table preservation check returned current sidecar tables, including:

- `ec_ecosystem`
- `ec_entity`
- `ec_entity_alias`
- `ec_group_index_daily`
- `ec_group_signal_daily`
- `ec_group_synthetic_ohlc_daily`
- `ec_membership`
- `ec_pipeline_watermark`
- `ec_signal_calendar`
- `ec_signal_run`
- `ec_taxonomy_version`
- `ec_ticker_signal_daily`
- `ec_watchlist`
- `ec_watchlist_member`

`dc_*` table preservation check returned legacy Datacenter/source tables, including:

- `dc_dashboard_action_summary_daily`
- `dc_dashboard_decision_trace_daily`
- `dc_dashboard_enrichment_run_daily`
- `dc_dashboard_group_enrichment_daily`
- `dc_dashboard_ticker_enrichment_daily`
- `dc_ecosystem_membership`
- `dc_group_index_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`
- `dc_pipeline_watermark`
- `dc_report_classification_v2`
- `dc_report_context_daily_v2`
- `dc_report_context_group_v2`
- `dc_report_context_window_v2`
- `dc_report_data_quality_summary_v2`
- `dc_report_ecosystem_window_change_v2`
- `dc_report_group_overheat_progression_v2`
- `dc_report_group_relative_change_v2`
- `dc_report_group_timing_persistence_v2`
- `dc_report_ma_break_status_v2`

## Tests And Checks

| Check | Result |
|---|---|
| `pytest -q tests/test_preflight_eco_legacy_db_cleanup_cli.py` | 8 passed |
| `pytest -q tests/test_plan_ec_source_layer_build_cli.py tests/test_plan_ec_source_layer_refresh_cli.py tests/test_plan_ec_source_layer_backfill_cli.py` | 30 passed |
| `pytest -q tests/test_run_ec_source_layer_build_cli.py` | 13 passed |
| `python3 -m py_compile rawcandle/cli/preflight_eco_legacy_db_cleanup.py rawcandle/scheduler/runner.py rawcandle/scheduler/config.py rawcandle/cli/run_stock_update_scheduler.py` | passed |

## Rollback Instructions

If rollback is required:

1. Stop all DB writers that could use `/home/kalle/projects/rawcandle/data/analysis.db`.
2. Move the modified DB aside.
3. Replace it with the verified backup at `/home/kalle/projects/rawcandle/temp/analysis__before_eco_legacy_cleanup__20260617T132223Z.sqlite`.
4. Rerun the read-only preflight CLI against the restored DB.
5. Rerun `PRAGMA integrity_check;` and `PRAGMA foreign_key_check;`.
6. Confirm the old `eco_*` table count is back to 16 if restoring the pre-cleanup state is the intended outcome.

## Things Not Touched

- No `VACUUM` or `VACUUM INTO` was run.
- `/home/kalle/projects/rawcandle/data/osakedata.db` was not touched.
- Migrations `015`-`018` were not modified or deleted.
- Migrations `019`-`024` were not modified.
- Runtime scheduler behavior was not changed.
- `scheduler_config.json` was not changed.
- `ec_*`, `ec_source_layer`, and `dc_*` behavior was not changed.
- Retired V3 scheduler/config/output compatibility fields were removed later in R1.
- The backup file and DB files were not staged for commit.
