# dc_dashboard Enrichment DB Cleanup: analysis.db

## Executive summary

Assessment: `DASHBOARD_ENRICHMENT_TABLE_CLEANUP_COMPLETED`.

The five retired dashboard enrichment `_daily` tables were removed from `/home/kalle/projects/rawcandle/data/analysis.db` after creating and verifying a SQLite backup. No other `dc_dashboard%` tables were present before cleanup, and no `dc_dashboard%` tables remain after cleanup.

No `VACUUM` or `VACUUM INTO` was run. Migrations `002`/`003`, runtime code, tests, `scheduler_config.json`, current `dc_*` source facts, current `ec_*` sidecar tables, and `ec_source_layer` were not modified.

## Scope

| Field | Value |
|---|---|
| Target DB | `/home/kalle/projects/rawcandle/data/analysis.db` |
| Backup path | `/home/kalle/projects/rawcandle/temp/analysis__before_dc_dashboard_enrichment_cleanup__20260617T170509Z.sqlite` |
| Backup size | `4,609,642,496` bytes |
| Cleanup type | drop five retired dashboard enrichment tables |
| `VACUUM` | not run |
| `VACUUM INTO` | not run |

## Backup verification

The backup was created with the SQLite backup API from the live target DB.

Backup verification:

| Check | Result |
|---|---|
| backup file exists | yes |
| backup size | `4,609,642,496` bytes |
| `PRAGMA integrity_check` | `ok` |
| backup preflight status | `NO_LEGACY_DASHBOARD_SNAPSHOT_TABLES_FOUND` |
| backup legacy snapshot table count | `0` |
| backup unknown `dc_dashboard%` table count | `0` |
| backup FK violations | `0` |

Backup contained the same five retired `_daily` tables and row counts as the pre-cleanup target preflight.

## Pre-cleanup preflight summary

Read-only preflight command:

```bash
PYTHONPATH=. python3 -m rawcandle.cli.preflight_dc_dashboard_legacy_db_cleanup --db /home/kalle/projects/rawcandle/data/analysis.db --format json
```

| Check | Result |
|---|---|
| status | `NO_LEGACY_DASHBOARD_SNAPSHOT_TABLES_FOUND` |
| legacy snapshot table count | `0` |
| total legacy snapshot rows | `0` |
| unknown `dc_dashboard%` table count | `0` |
| `PRAGMA integrity_check` | `ok` |
| FK violations | `0` |
| page_count | `1,125,401` |
| freelist_count | `8,801` |
| DB size | `4,609,642,496` bytes |

Retired `_daily` tables before cleanup:

| Table | Present | Row count |
|---|---:|---:|
| `dc_dashboard_action_summary_daily` | yes | `32` |
| `dc_dashboard_decision_trace_daily` | yes | `34,383` |
| `dc_dashboard_enrichment_run_daily` | yes | `9` |
| `dc_dashboard_group_enrichment_daily` | yes | `486` |
| `dc_dashboard_ticker_enrichment_daily` | yes | `2,124` |

## Drop list executed

Only these five tables were dropped from `/home/kalle/projects/rawcandle/data/analysis.db`:

```sql
DROP TABLE IF EXISTS dc_dashboard_decision_trace_daily;
DROP TABLE IF EXISTS dc_dashboard_action_summary_daily;
DROP TABLE IF EXISTS dc_dashboard_ticker_enrichment_daily;
DROP TABLE IF EXISTS dc_dashboard_group_enrichment_daily;
DROP TABLE IF EXISTS dc_dashboard_enrichment_run_daily;
```

The drops were executed in a single transaction and committed only after all five statements succeeded.

## Post-cleanup preflight summary

Read-only preflight after cleanup:

| Check | Result |
|---|---|
| status | `NO_LEGACY_DASHBOARD_SNAPSHOT_TABLES_FOUND` |
| legacy snapshot table count | `0` |
| total legacy snapshot rows | `0` |
| unknown `dc_dashboard%` table count | `0` |
| remaining `dc_dashboard%` tables | `0` |
| `PRAGMA integrity_check` | `ok` |
| FK violations | `0` |
| page_count | `1,125,401` |
| freelist_count | `14,196` |
| DB size | `4,609,642,496` bytes |

Retired `_daily` tables after cleanup:

| Table | Present | Row count |
|---|---:|---:|
| `dc_dashboard_action_summary_daily` | no | `NA` |
| `dc_dashboard_decision_trace_daily` | no | `NA` |
| `dc_dashboard_enrichment_run_daily` | no | `NA` |
| `dc_dashboard_group_enrichment_daily` | no | `NA` |
| `dc_dashboard_ticker_enrichment_daily` | no | `NA` |

The preflight CLI still refers to these as current dashboard tables because it predates the retirement decision. Missing `_daily` tables are now the intended Phase 4 state.

## Preserved table checks

Current `dc_*` source fact tables were present after cleanup:

- `dc_group_index_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`
- `dc_pipeline_watermark`
- `dc_ticker_swing_signal_daily`

Current `ec_*` sidecar key tables were present after cleanup:

- `ec_group_index_daily`
- `ec_group_signal_daily`
- `ec_group_synthetic_ohlc_daily`
- `ec_pipeline_watermark`
- `ec_ticker_signal_daily`

## Tests and checks

| Check | Result |
|---|---|
| `pytest -q tests/test_preflight_dc_dashboard_legacy_db_cleanup_cli.py` | `11 passed` |
| `pytest -q tests/test_stock_update_scheduler_runner.py` | `71 passed` |
| `pytest -q tests/test_stock_update_scheduler_cli.py` | `6 passed` |
| `pytest -q tests/test_stock_update_scheduler_ui.py -x` | `20 passed` |
| `pytest -q tests/test_plan_ec_source_layer_build_cli.py tests/test_plan_ec_source_layer_refresh_cli.py tests/test_plan_ec_source_layer_backfill_cli.py` | `30 passed` |
| `pytest -q tests/test_run_ec_source_layer_build_cli.py` | `13 passed` |
| `python3 -m py_compile rawcandle/cli/preflight_dc_dashboard_legacy_db_cleanup.py analysis/database_manager.py rawcandle/scheduler/runner.py rawcandle/scheduler/config.py rawcandle/cli/run_stock_update_scheduler.py` | passed |

## Rollback instructions

If rollback is required:

1. Stop DB writers and any process using `/home/kalle/projects/rawcandle/data/analysis.db`.
2. Replace the modified DB with the verified backup:
   `/home/kalle/projects/rawcandle/temp/analysis__before_dc_dashboard_enrichment_cleanup__20260617T170509Z.sqlite`.
3. Re-run read-only dashboard preflight against `/home/kalle/projects/rawcandle/data/analysis.db`.
4. Re-run `PRAGMA integrity_check` and `PRAGMA foreign_key_check`.
5. Confirm the five `dc_dashboard_*_daily` tables and their pre-cleanup row counts are restored.

## Things not touched

- `/home/kalle/projects/rawcandle/data/osakedata.db` was not touched.
- No `VACUUM` or `VACUUM INTO` was run.
- Migrations `002`/`003` were not modified or deleted.
- Runtime code was not modified.
- Tests were not modified.
- `scheduler_config.json` was not modified.
- Current `dc_*` source fact generation was not changed.
- Current legacy Datacenter Markdown/CSV reports were not changed.
- Current `ec_*` sidecar behavior and `ec_source_layer` were not changed.
