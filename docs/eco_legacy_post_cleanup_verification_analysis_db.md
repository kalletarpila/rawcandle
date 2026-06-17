# eco legacy post-cleanup verification: data/analysis.db

## Executive summary

Phase 3E read-only post-cleanup verification was completed for `/home/kalle/projects/rawcandle/data/analysis.db`.

Assessment: `POST_CLEANUP_READINESS_OK`.

The cleaned analysis DB remains in the expected post-cleanup state: no old `eco_*` tables remain, integrity is clean, foreign-key checks are clean, current `ec_*` sidecar tables are present, and `dc_*` source tables are present. The rollback backup was also checked read-only and still contains the old `eco_*` tables.

This step was read-only for databases. No DB tables were dropped, no backup was created, and no `VACUUM` or `VACUUM INTO` was run.

## Target And Backup Checked

| Field | Value |
|---|---|
| Target DB | `/home/kalle/projects/rawcandle/data/analysis.db` |
| Target DB size observed | 4.3G |
| Backup checked | `/home/kalle/projects/rawcandle/temp/analysis__before_eco_legacy_cleanup__20260617T132223Z.sqlite` |
| Backup size observed | 4.3G |
| WAL observed | `/home/kalle/projects/rawcandle/data/analysis.db-wal`, 158M |
| SHM observed | `/home/kalle/projects/rawcandle/data/analysis.db-shm`, 320K |

WAL/SHM files were not deleted or modified manually.

## Commands Run

```bash
git status --short
ls -lh /home/kalle/projects/rawcandle/data/analysis.db
ls -lh /home/kalle/projects/rawcandle/temp/analysis__before_eco_legacy_cleanup__20260617T132223Z.sqlite
ls -lh /home/kalle/projects/rawcandle/data/analysis.db-wal /home/kalle/projects/rawcandle/data/analysis.db-shm 2>/dev/null || true
PYTHONPATH=. python3 -m rawcandle.cli.preflight_eco_legacy_db_cleanup --db /home/kalle/projects/rawcandle/data/analysis.db --format json
PYTHONPATH=. python3 -m rawcandle.cli.preflight_eco_legacy_db_cleanup --db /home/kalle/projects/rawcandle/temp/analysis__before_eco_legacy_cleanup__20260617T132223Z.sqlite --format json
python3 - <<'PY'
# read-only SQLite direct table, integrity, FK, and row-count smoke checks
PY
PYTHONPATH=. python3 -m rawcandle.cli.plan_ec_source_layer_build --db /home/kalle/projects/rawcandle/data/analysis.db --ecosystem DATACENTER --taxonomy-version DC_TAXONOMY_FULL_V1 --taxonomy-csv /home/kalle/projects/rawcandle/data/datacenter_ecosystem_taxonomy_full_v1.csv --watchlist /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt
PYTHONPATH=. python3 -m rawcandle.cli.plan_ec_source_layer_refresh --db /home/kalle/projects/rawcandle/data/analysis.db --ecosystem DATACENTER --taxonomy-version DC_TAXONOMY_FULL_V1 --taxonomy-csv /home/kalle/projects/rawcandle/data/datacenter_ecosystem_taxonomy_full_v1.csv --watchlist /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt
rg -n "report_canonical_v3|reporting_v3_query|reporting_v3_markdown|write_latest_v3_markdown_reports|write_v3_markdown_prototypes|run_canonical_v3_latest_build|plan_canonical_v3_latest_build|inspect_canonical_v3" rawcandle tests
rg -n "eco_ecosystem|eco_taxonomy_version|eco_entity|eco_report_run|eco_entity_metric_value|eco_classification_decision|eco_signal|eco_quality|eco_watchlist|eco_taxonomy" rawcandle tests docs dev_tools
rg -n "datacenter_v3_reports|v3_reports" rawcandle/scheduler rawcandle/cli/run_stock_update_scheduler.py tests/test_stock_update_scheduler_runner.py tests/test_stock_update_scheduler_cli.py docs
pytest -q tests/test_preflight_eco_legacy_db_cleanup_cli.py
pytest -q tests/test_plan_ec_source_layer_build_cli.py tests/test_plan_ec_source_layer_refresh_cli.py tests/test_plan_ec_source_layer_backfill_cli.py
pytest -q tests/test_run_ec_source_layer_build_cli.py
pytest -q tests/test_stock_update_scheduler_runner.py -k "v3_reports or ec_source_layer or datacenter_pipeline"
pytest -q tests/test_stock_update_scheduler_cli.py -k "v3_reports or summary or datacenter"
python3 -m py_compile rawcandle/cli/preflight_eco_legacy_db_cleanup.py rawcandle/scheduler/runner.py rawcandle/scheduler/config.py rawcandle/cli/run_stock_update_scheduler.py
```

No scheduler, stock update, refresh, backfill, recovery, report generation, or DB-writing RawCandle command was run.

## Cleaned Analysis DB Preflight

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
| db_size_bytes | 4,609,642,496 |

## Backup Sanity Preflight

| Field | Value |
|---|---|
| Backup path | `/home/kalle/projects/rawcandle/temp/analysis__before_eco_legacy_cleanup__20260617T132223Z.sqlite` |
| Status | `ECO_TABLES_FOUND` |
| eco table count | 16 |
| total eco rows | 72,931 |
| integrity_check | `ok` |
| foreign_key_check violation count | 0 |

The backup still contains the old `eco_*` tables and remains a valid rollback source.

## Direct DB Checks

| Check | Result |
|---|---|
| Remaining old `eco_*` table count | 0 |
| `ec_*` table count | 14 |
| `dc_*` table count | 28 |
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` | 0 violations |

Current `ec_*` tables found:

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

First 20 `dc_*` tables found:

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

### Row-count smoke checks

| Table | Rows |
|---|---:|
| `ec_ecosystem` | 1 |
| `ec_taxonomy_version` | 1 |
| `ec_entity` | 291 |
| `ec_ticker_signal_daily` | 3,068 |
| `ec_group_signal_daily` | 702 |
| `ec_group_synthetic_ohlc_daily` | 689 |
| `ec_group_index_daily` | 702 |
| `ec_pipeline_watermark` | 15 |
| `dc_ticker_swing_signal_daily` | 85,970 |
| `dc_group_swing_signal_daily` | 19,740 |
| `dc_group_synthetic_ohlc_daily` | 20,501 |
| `dc_group_index_daily` | 88,890 |
| `dc_pipeline_watermark` | 15 |

## Planner And Readiness Checks

`plan_ec_source_layer_build` was run in no-write mode. It returned exit code 2 with `plan_status=BLOCKED_EXISTING_EC_SCHEMA`, which is expected for a database that already has the current `ec_*` sidecar installed. Relevant readiness fields:

- `mode=NO_WRITE`
- `true_ec_tables` listed the installed `ec_*` sidecar tables.
- `eco_tables=[]`
- `dc_*` source tables were present with latest source date `2026-06-16`.
- Taxonomy source had 329 rows, 236 distinct tickers, 16 layers, and 37 subindustries.
- Watchlist source had 16 tickers and `contains_crgy=True`.

`plan_ec_source_layer_refresh` was run in no-write refresh-plan mode. It returned exit code 0 with:

- `status=SKIP_UP_TO_DATE`
- `mode=NO_WRITE_REFRESH_PLAN`
- `required_ec_missing=[]`
- `eco_tables=[]`
- `selected_signal_date=2026-06-16`
- `latest_loaded_fact_date=2026-06-16`
- `selected_date_exists_in_all_facts=True`
- `compatibility_status=OK`
- `source_hash_match=True`
- `watchlist_missing_in_loaded=[]`
- `watchlist_loaded_only=[]`

This confirms the current refresh-readiness path does not require old `eco_*` tables.

## Reference Search Summary

The old V3 core-code reference search in `rawcandle` and `tests` returned no matches for removed modules or CLIs:

- `report_canonical_v3`
- `reporting_v3_query`
- `reporting_v3_markdown`
- `write_latest_v3_markdown_reports`
- `write_v3_markdown_prototypes`
- `run_canonical_v3_latest_build`
- `plan_canonical_v3_latest_build`
- `inspect_canonical_v3`

Remaining old `eco_*` references are limited to expected categories:

- Migrations `015`-`018`.
- Archived old V3/eco docs under `docs/archive/old_v3_eco/`.
- Audit/status docs.
- Preflight and cleanup documentation.

No active old V3 runtime module or test reference was found.

Scheduler compatibility references remain intentional:

- `rawcandle/scheduler/config.py` still accepts `datacenter_v3_reports_*` compatibility fields.
- `rawcandle/scheduler/runner.py` still emits deterministic removed/skipped V3 report status.
- `rawcandle/cli/run_stock_update_scheduler.py` still prints `v3_reports.*` summary fields.
- Scheduler tests assert `v3_reports_status="SKIPPED_REMOVED"` and error text `old V3/eco report generation has been removed`.

## Tests And Checks

| Check | Result |
|---|---|
| `pytest -q tests/test_preflight_eco_legacy_db_cleanup_cli.py` | 8 passed |
| `pytest -q tests/test_plan_ec_source_layer_build_cli.py tests/test_plan_ec_source_layer_refresh_cli.py tests/test_plan_ec_source_layer_backfill_cli.py` | 30 passed |
| `pytest -q tests/test_run_ec_source_layer_build_cli.py` | 13 passed |
| `pytest -q tests/test_stock_update_scheduler_runner.py -k "v3_reports or ec_source_layer or datacenter_pipeline"` | 9 passed, 101 deselected |
| `pytest -q tests/test_stock_update_scheduler_cli.py -k "v3_reports or summary or datacenter"` | 7 passed, 10 deselected |
| `python3 -m py_compile rawcandle/cli/preflight_eco_legacy_db_cleanup.py rawcandle/scheduler/runner.py rawcandle/scheduler/config.py rawcandle/cli/run_stock_update_scheduler.py` | passed |

## Rollback Reminder

Rollback source:

`/home/kalle/projects/rawcandle/temp/analysis__before_eco_legacy_cleanup__20260617T132223Z.sqlite`

If rollback is required:

1. Stop all DB writers using `/home/kalle/projects/rawcandle/data/analysis.db`.
2. Move the modified DB aside.
3. Replace it with the verified backup.
4. Rerun the read-only preflight CLI.
5. Rerun `PRAGMA integrity_check;` and `PRAGMA foreign_key_check;`.
6. Confirm the old `eco_*` table count is back to 16 if restoring the pre-cleanup state is intended.

## VACUUM Note

`VACUUM` and `VACUUM INTO` were not run. File-size reduction remains a separate optional decision only if reclaiming SQLite file space is required.

## Things Not Touched

- No database was modified in this step.
- No backup was created in this step.
- No `VACUUM` or `VACUUM INTO` was run.
- No scheduler, stock update, refresh, backfill, recovery, or report generation command was run.
- `/home/kalle/projects/rawcandle/data/osakedata.db` was not touched.
- Migrations `015`-`018` were not modified or deleted.
- Migrations `019`-`024` were not modified.
- Runtime scheduler behavior was not changed.
- `scheduler_config.json` was not changed.
- `ec_*`, `ec_source_layer`, and `dc_*` behavior was not changed.
- Scheduler `v3_reports_*` compatibility fields were not removed.
- DB, WAL/SHM, backup, export, temp, and unrelated files were not staged or committed.
