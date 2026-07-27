# Datacenter Stage 2 Incremental Production Preflight

Preflight timestamp: 2026-07-27T20:19:24+03:00

This was a strictly read-only production preflight for the Datacenter Stage 2
incremental pilot. No scheduler run, Datacenter pipeline run, Stage 2 run,
downstream Datacenter run, EC refresh/backfill, scheduler post-step, network
access, schema migration, code change, test change, or production database write
was performed.

## Repository State

- Branch: `chore/ignore-backups`
- HEAD: `86f5888d215b07d3262ca5fb69f9b2f569447c53`
- `origin/chore/ignore-backups`: `86f5888d215b07d3262ca5fb69f9b2f569447c53`
- Recent commits:
  - `86f5888 Verify Stage 2 incremental flow end to end`
  - `8044c7f Add transitional Datacenter EC bridge`
  - `cd9615c Wire Stage 2 incremental execution`
  - `ac3aefb Add Stage 2 incremental planner`
  - `9cd9b0c Align stock update tests with current contract`
- Initial `git status --short`: clean

Repository gate: PASS.

## Scheduler Configuration State

The Windows-side UI launcher uses:

```text
/home/kalle/projects/rawcandle/start_stock_update_ui
  -> /home/kalle/projects/rawcandle/scheduler_config.json
```

The active `scheduler_config.json` contains the production DB paths:

```text
analysis_db_path=/home/kalle/projects/rawcandle/data/analysis.db
osakedata_db_path=/home/kalle/projects/rawcandle/data/osakedata.db
ec_source_layer_enabled=true
ec_source_layer_mode=refresh_latest
ec_source_layer_require_legacy_reports_success=true
ec_source_layer_only_on_new_signal_date=true
enabled_markets=omxh, usa
run_time=05:30
timezone=Europe/Helsinki
```

The config file does not contain the new Stage 2 incremental keys. Current code
defaults therefore apply:

```text
datacenter_stage2_incremental_enabled=false
datacenter_stage2_overlap_trading_days=5
```

Activation gate: BLOCKED until `datacenter_stage2_incremental_enabled` is
explicitly enabled in production config.

## Database Filesystem Evidence

Before inspection:

```text
data/osakedata.db|regular file|1944010752|1785163009|2026-07-27 17:36:49.890358832 +0300
data/osakedata.db-wal|MISSING
data/osakedata.db-shm|MISSING
data/analysis.db|regular file|7028240384|1785169726|2026-07-27 19:28:46.347020901 +0300
data/analysis.db-wal|MISSING
data/analysis.db-shm|MISSING
scheduler_config.json|regular file|955|1781721755|2026-06-17 21:42:35.052036850 +0300
```

After inspection:

```text
data/osakedata.db|regular file|1944010752|1785163009|2026-07-27 17:36:49.890358832 +0300
data/osakedata.db-wal|MISSING
data/osakedata.db-shm|MISSING
data/analysis.db|regular file|7028240384|1785169726|2026-07-27 19:28:46.347020901 +0300
data/analysis.db-wal|MISSING
data/analysis.db-shm|MISSING
scheduler_config.json|regular file|955|1781721755|2026-06-17 21:42:35.052036850 +0300
```

Production DB metadata was unchanged during the preflight.

## Safe Inspection Method

No SQLite queries were executed directly against production DB paths. The
Datacenter planner code uses normal SQLite connections, so the inspection used
temporary copies instead of opening production databases:

```text
/tmp/rawcandle_stage2_preflight_20260727_201924/osakedata.db
/tmp/rawcandle_stage2_preflight_20260727_201924/analysis.db
```

The source DBs had no `-wal` or `-shm` files at copy time. The copied DB file
sizes and mtimes matched the production files:

```text
/tmp/rawcandle_stage2_preflight_20260727_201924/osakedata.db|regular file|1944010752|1785163009|2026-07-27 17:36:49.890358832 +0300
/tmp/rawcandle_stage2_preflight_20260727_201924/analysis.db|regular file|7028240384|1785169726|2026-07-27 19:28:46.347020901 +0300
```

Read-only method gate: PASS.

## Source and Fact Date Heads

Source price data in the copied `osakedata.db`:

```text
market  min_date    max_date    rows     tickers
omxh    2018-01-02  2026-07-27  196282   98
usa     2018-01-02  2026-07-27  7795133  4476
```

Recent price coverage:

```text
market  pvm         tickers
omxh    2026-07-23  96
omxh    2026-07-24  96
omxh    2026-07-27  96
usa     2026-07-23  4248
usa     2026-07-24  4180
usa     2026-07-27  2
```

Datacenter taxonomy primary ticker count: `236`.

Primary Datacenter ticker coverage:

```text
2026-07-20  227
2026-07-21  227
2026-07-22  227
2026-07-23  227
2026-07-24  227
```

Canonical Datacenter and EC fact heads in the copied `analysis.db`:

```text
table_name                     min_date    max_date    rows
dc_ticker_swing_signal_daily   2025-01-02  2026-07-24  92106
dc_group_swing_signal_daily    2025-01-02  2026-07-24  21144
dc_group_synthetic_ohlc_daily  2025-01-02  2026-07-24  21879
dc_group_index_daily           2020-01-02  2026-07-24  90294
ec_ticker_signal_daily         2026-05-18  2026-07-24  11092
ec_group_signal_daily          2026-05-18  2026-07-24  2538
ec_group_synthetic_ohlc_daily  2026-05-18  2026-07-24  2491
ec_group_index_daily           2026-05-18  2026-07-24  2538
```

Date-head gate: PASS for 2026-07-24. 2026-07-27 is not yet a valid USA
Datacenter signal date because only two USA price rows are present for that
date in the copied source DB.

## Watermark Evidence

Relevant DC watermark rows:

```text
TICKER_SWING_BASE         market=usa  signal_version=DC_SWING_SIGNAL_V1  start=2025-08-01  end=2026-07-24  status=OK
GROUP_SWING_BASE                      signal_version=DC_SWING_SIGNAL_V1  start=2025-08-01  end=2026-07-24  status=OK
GROUP_TIMING                          signal_version=DC_SWING_SIGNAL_V1  start=2025-08-01  end=2026-07-24  status=OK
GROUP_OVERHEAT                        signal_version=DC_SWING_SIGNAL_V1  start=2025-08-01  end=2026-07-24  status=OK
TICKER_SCANNER                        signal_version=DC_SWING_SIGNAL_V1  start=2025-08-01  end=2026-07-24  status=OK
SYNTHETIC_OHLC_BASE       market=usa  calc_version=DC_SWING_OHLC_V1     start=2025-08-01  end=2026-07-24  status=OK
SYNTHETIC_OHLC_RELATIVE   market=usa  calc_version=DC_SWING_OHLC_V1     start=2025-08-01  end=2026-07-24  status=OK
SYNTHETIC_OHLC_STRUCTURE  market=usa  calc_version=DC_SWING_OHLC_V1     start=2025-08-01  end=2026-07-24  status=OK
PIPELINE_AUDIT                        signal_version=DC_SWING_SIGNAL_V1  start=2026-07-24  end=2026-07-24  status=WARN
```

Relevant EC watermark rows:

```text
TICKER_SWING_BASE         dc_ticker_swing_signal_daily       latest=2026-07-24  status=OK
GROUP_SWING_BASE          dc_group_swing_signal_daily        latest=2026-07-24  status=OK
GROUP_INDEX               dc_group_index_daily               latest=2026-07-24  status=OK
SYNTHETIC_OHLC_BASE       dc_group_synthetic_ohlc_daily      latest=2026-07-24  status=OK
SYNTHETIC_OHLC_RELATIVE   dc_group_synthetic_ohlc_daily      latest=2026-07-24  status=OK
PIPELINE_AUDIT            UNKNOWN:PIPELINE_AUDIT             latest=2026-07-24  status=WARN
```

Watermark gate: PASS for current 2026-07-24 coverage. Existing audit warning
state remains visible and should not be hidden by the pilot.

## Selected Signal Date Resolution

Simulated scheduler date resolution against copied DBs for effective date
2026-07-27:

```text
requested_calendar_signal_date=2026-07-26
signal_date=2026-07-24
signal_date_source=DOWNSTREAM_VALID_DATE
signal_date_resolution=TICKER_AND_GROUP_VALID_DATE_WITH_MIN_TICKER_COUNT
min_price_ticker_count=59
candidate_count=246
ticker_valid_date_count=246
group_valid_date_count=246
skip_reason=
```

This matches the expected weekend behavior: Sunday 2026-07-26 is not a signal
date, and Monday 2026-07-27 has not yet received sufficient USA coverage.

## Simulated Stage 2 Plan

The Stage 2 incremental planner was run only against copied DBs:

```text
SUMMARY component=TICKER_SWING_BASE
SUMMARY mode=SKIP
SUMMARY requested_start=2025-08-01
SUMMARY requested_end=2026-07-26
SUMMARY effective_requested_end=2026-07-24
SUMMARY watermark_start=2025-08-01
SUMMARY watermark_end=2026-07-24
SUMMARY materialization_start=NONE
SUMMARY materialization_end=NONE
SUMMARY calculation_input_start=NONE
SUMMARY calculation_input_end=NONE
SUMMARY overlap_trading_days=5
SUMMARY max_valid_price_rows=220
SUMMARY write_mode=replace-date
SUMMARY reason_code=WATERMARK_COVERS_REQUESTED_TARGET
SUMMARY valid_signal_dates=246
SUMMARY output_dates=0
```

Downstream simulation:

```text
3  GROUP_SWING_BASE  STAGE2_SKIP_NO_DIRTY_RANGE
7  GROUP_TIMING      STAGE2_SKIP_NO_DIRTY_RANGE
8  GROUP_OVERHEAT    STAGE2_SKIP_NO_DIRTY_RANGE
9  TICKER_SCANNER    STAGE2_SKIP_NO_DIRTY_RANGE
6  SYNTHETIC_OHLC_STRUCTURE excluded: STAGE6_OUTSIDE_STAGE2_INCREMENTAL_PILOT
```

Planner gate: PASS for current state. If enabled now, Stage 2 incremental
planning would not require a materialization for the current selected date.

## Simulated EC Bridge Decision

Because the simulated Stage 2 plan is `SKIP`, there is no successfully
materialized Stage 2 output range in the current production snapshot. The
incremental bridge should therefore not trigger historical EC backfill for this
snapshot.

Expected current-state bridge result:

```text
ec_bridge_mode=SKIPPED_NO_MATERIALIZATION
ec_bridge_reason=NO_SUCCESSFUL_MATERIALIZATION
required_refresh_start=NONE
required_refresh_end=NONE
retry_required=false
```

Existing production logs from 2026-07-27 show the pre-activation legacy EC
latest-date behavior:

```text
logs/ec_source_layer_usa_20260727T1147Z.txt
status=REFRESH_COMPLETED
signal_date=2026-07-24
refresh_mode=new_selected_date
coverage_status=OK_WITH_WARNINGS
parity_status=OK_WITH_WARNINGS
total_mismatch_count=0
```

EC bridge gate: PASS for current no-materialization snapshot. Historical
backfill behavior still needs a real non-production dry run or a controlled
production activation window when a new eligible signal date appears.

## Activation Gates

PASS:

- Repository branch and HEAD match the expected production preflight baseline.
- Working tree was clean before DB inspection.
- Production DB files had no WAL/SHM sidecar files at copy time.
- Production DB file metadata was unchanged before and after inspection.
- Current copied source data supports Datacenter signal date 2026-07-24.
- DC and EC fact tables currently reach 2026-07-24.
- Stage 2 incremental planner returns `SKIP` for the current selected date
  because the Stage 2 watermark already covers 2026-07-24.

BLOCKED:

- `scheduler_config.json` does not enable `datacenter_stage2_incremental_enabled`.
  Production activation requires an explicit config-only change.

WARN:

- Existing EC coverage/parity statuses are `OK_WITH_WARNINGS` with
  `total_mismatch_count=0`. This is visible and consistent with the current
  system, but the activation owner should decide whether `OK_WITH_WARNINGS` is
  acceptable for the first production incremental run.
- 2026-07-27 USA price coverage is incomplete in the current source DB snapshot
  (`2` USA tickers), so the next materializing incremental run cannot yet be
  simulated from this snapshot.

## Unknowns

- No production historical EC backfill was executed in this preflight.
- No production Stage 2 incremental materialization was executed in this
  preflight.
- The first non-skip incremental production run still depends on a future source
  snapshot where a new eligible USA Datacenter signal date exists.

## Recommendation

Do not activate the Stage 2 incremental pilot solely from this preflight if the
goal is to observe a real materializing incremental path immediately: current
data resolves to 2026-07-24, and the watermark already covers that date.

It is reasonable to schedule activation after confirming that:

```text
datacenter_stage2_incremental_enabled=true
datacenter_stage2_overlap_trading_days=5
latest USA source coverage supports a signal date beyond 2026-07-24
EC OK_WITH_WARNINGS is accepted or tightened before activation
```

## Rollback Readiness

The pilot code is isolated behind `datacenter_stage2_incremental_enabled`. With
the current production config defaulting to `false`, rollback is currently just
leaving the flag disabled.

If the flag is later enabled and issues appear, the immediate rollback is to set
`datacenter_stage2_incremental_enabled=false` and rerun the legacy full-history
Datacenter path. Code-level rollback candidates are the recent commits:

```text
86f5888 Verify Stage 2 incremental flow end to end
8044c7f Add transitional Datacenter EC bridge
cd9615c Wire Stage 2 incremental execution
ac3aefb Add Stage 2 incremental planner
```

## Explicit No-Write Statement

No production database write was performed. No production SQLite connection was
opened for SQL queries. SQL and planner inspection used only copied databases
under `/tmp/rawcandle_stage2_preflight_20260727_201924`.

