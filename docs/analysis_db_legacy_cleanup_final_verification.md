# analysis.db legacy cleanup final verification

## Executive summary

Final read-only verification was completed for legacy cleanup state in `/home/kalle/projects/rawcandle/data/analysis.db`.

Assessment: `LEGACY_CLEANUP_VERIFIED`.

The database has no old `eco_*` tables and no known retired Canonical Report V2 `dc_report_*_v2` tables. Current preserved `dc_*` source fact tables and current `ec_*` key tables are present. `PRAGMA integrity_check` returned `ok`, and `PRAGMA foreign_key_check` reported 0 violations. No `VACUUM` was run.

Retired compatibility surface follow-up is documented in `docs/retired_compatibility_surface_audit.md`. R1 removed the retired V3 scheduler/config/output compatibility surface; Canonical Report V2 retired dev_tools stubs remain for a later R2 decision. This does not change the verified database cleanup state.

This verification step did not drop tables, modify databases, create backups, modify migrations, change runtime code, change tests, run scheduler, run stock update, or run any RawCandle DB-writing pipeline.

## Scope

| Field | Value |
|---|---|
| DB path | `/home/kalle/projects/rawcandle/data/analysis.db` |
| Verification mode | read-only |
| Assessment | `LEGACY_CLEANUP_VERIFIED` |
| DB size | `4,609,642,496` bytes |

Backups checked:

| Backup | Presence |
|---|---|
| `/home/kalle/projects/rawcandle/temp/analysis__before_eco_legacy_cleanup__20260617T132223Z.sqlite` | present |
| `/home/kalle/projects/rawcandle/temp/analysis__before_dc_report_v2_cleanup__20260617T143742Z.sqlite` | present |

## Commands Run

```bash
git status --short
ls -lh /home/kalle/projects/rawcandle/data/analysis.db
ls -lh /home/kalle/projects/rawcandle/temp/analysis__before_eco_legacy_cleanup__20260617T132223Z.sqlite
ls -lh /home/kalle/projects/rawcandle/temp/analysis__before_dc_report_v2_cleanup__20260617T143742Z.sqlite
PYTHONPATH=. python3 -m rawcandle.cli.preflight_eco_legacy_db_cleanup --db /home/kalle/projects/rawcandle/data/analysis.db --format json
PYTHONPATH=. python3 -m rawcandle.cli.preflight_dc_report_v2_db_cleanup --db /home/kalle/projects/rawcandle/data/analysis.db --format json
PYTHONPATH=. python3 -m rawcandle.cli.plan_ec_source_layer_refresh --db /home/kalle/projects/rawcandle/data/analysis.db --ecosystem DATACENTER --taxonomy-version DC_TAXONOMY_FULL_V1 --taxonomy-csv /home/kalle/projects/rawcandle/data/datacenter_ecosystem_taxonomy_full_v1.csv --watchlist /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt
```

Direct SQLite checks were run with read-only URI mode from Python.

## Preflight Results

| Check | Result |
|---|---|
| `eco_*` status | `NO_ECO_TABLES_FOUND` |
| `eco_*` table count | `0` |
| `eco_*` row count | `0` |
| `eco_*` related indexes/triggers/views | none |
| `eco_*` preflight integrity | `ok` |
| `eco_*` preflight FK violations | `0` |
| `dc_report_*_v2` status | `NO_DC_REPORT_V2_TABLES_FOUND` |
| `dc_report_*_v2` table count | `0` |
| `dc_report_*_v2` row count | `0` |
| `dc_report_*_v2` related indexes/triggers/views | none |
| `dc_report_*_v2` preflight integrity | `ok` |
| `dc_report_*_v2` preflight FK violations | `0` |

Both preflight CLIs reported `page_count=1,125,401` and `freelist_count=8,877`.

## Direct DB Checks

| Check | Result |
|---|---|
| `eco_*` tables | `0` |
| known `dc_report_*_v2` tables | `0` |
| `PRAGMA integrity_check` | `ok` |
| `PRAGMA foreign_key_check` violation count | `0` |

Current `dc_*` source fact table row-count smoke:

| Table | Rows |
|---|---:|
| `dc_ticker_swing_signal_daily` | 85,970 |
| `dc_group_swing_signal_daily` | 19,740 |
| `dc_group_synthetic_ohlc_daily` | 20,501 |
| `dc_group_index_daily` | 88,890 |
| `dc_pipeline_watermark` | 15 |

Current `ec_*` key table row-count smoke:

| Table | Rows |
|---|---:|
| `ec_ticker_signal_daily` | 3,068 |
| `ec_group_signal_daily` | 702 |
| `ec_group_synthetic_ohlc_daily` | 689 |
| `ec_group_index_daily` | 702 |
| `ec_pipeline_watermark` | 15 |

## No-write Readiness

`plan_ec_source_layer_refresh` was run in no-write planner mode against `analysis.db`.

Result summary:

| Field | Value |
|---|---|
| mode | `NO_WRITE_REFRESH_PLAN` |
| true `ec_*` tables | present |
| required `ec_*` missing | none |
| `eco_tables` | `[]` |
| selected signal date | `2026-06-16` |
| selected date exists in all EC facts | `True` |
| taxonomy/watchlist compatibility | `OK` |
| source hash match | `True` |
| plan status | `SKIP_UP_TO_DATE` |

The command prints a planned refresh sequence but does not perform the refresh.

## Tests and Checks

| Command | Result |
|---|---|
| `pytest -q tests/test_preflight_eco_legacy_db_cleanup_cli.py` | 8 passed |
| `pytest -q tests/test_preflight_dc_report_v2_db_cleanup_cli.py` | 10 passed |
| `pytest -q tests/test_report_canonical_v2_retired_cli.py` | 13 passed |
| `pytest -q tests/test_plan_ec_source_layer_build_cli.py tests/test_plan_ec_source_layer_refresh_cli.py tests/test_plan_ec_source_layer_backfill_cli.py` | 30 passed |
| `pytest -q tests/test_run_ec_source_layer_build_cli.py` | 13 passed |
| `pytest -q tests/test_stock_update_scheduler_runner.py -k "ec_source_layer or datacenter_pipeline or dashboard or summary"` | R1 follow-up check passed |
| `pytest -q tests/test_stock_update_scheduler_cli.py -k "summary or datacenter or ec_source_layer"` | R1 follow-up check passed |
| `python3 -m py_compile rawcandle/cli/preflight_eco_legacy_db_cleanup.py rawcandle/cli/preflight_dc_report_v2_db_cleanup.py analysis/database_manager.py rawcandle/scheduler/runner.py rawcandle/scheduler/config.py rawcandle/cli/run_stock_update_scheduler.py` | passed |
| `python3 -m py_compile dev_tools/run_report_canonical_v2_*.py` | passed |

## VACUUM Note

`VACUUM` and `VACUUM INTO` were not run. The SQLite file is not expected to shrink merely because old tables were dropped. File-size reduction should remain a separate decision only if needed, with explicit backup, disk-space checks, and rollback planning.

## Remaining Optional Future Decisions

- `VACUUM` or `VACUUM INTO`, only if file-size reduction is required.
- Archive/remove migrations `004`-`014`, only after migration-history compatibility is approved.
- Archive/remove migrations `015`-`018`, only after migration-history compatibility is approved.
- Delete retired Canonical Report V2 dev_tools stubs later if compatibility/discoverability is no longer needed.
- R2: delete Canonical Report V2 retired dev_tools stubs later if compatibility/discoverability is no longer needed.

## Things Not Touched

- No DB tables were dropped in this verification step.
- No database was modified in this verification step.
- No backup was created in this verification step.
- No `VACUUM` or `VACUUM INTO`.
- No stock update, scheduler, refresh, backfill, recovery, report generation, or Canonical V2 command.
- No migrations.
- No runtime code.
- No tests.
- No scheduler behavior or `scheduler_config.json`.
- No current `dc_*` source fact generation.
- No current legacy Datacenter reports.
- No current `ec_*` sidecar behavior.
- No `ec_source_layer`.
