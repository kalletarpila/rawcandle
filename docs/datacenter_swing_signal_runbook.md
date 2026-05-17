# Datacenter Swing Signal Runbook

## Purpose

This runbook documents the current datacenter swing signal workflow and the intended separation between:

- the daily swing signal workflow for the previous valid trading day
- the weekly report role as a last 5 valid trading days summary ending on that same previous valid trading day

The swing workflow is read/write until the final report step. The final daily report is read-only.

## Date Semantics

### Daily report

- The daily report should normally be run for the previous valid trading day, not the current calendar day.
- Previous valid trading day means the latest date with valid persisted market, index, and swing rows after market close.
- Do not describe the daily report as today's report unless the selected `signal_date` is explicitly today and all required data is complete.

Use a placeholder like:

```bash
SIGNAL_DATE=<previous_valid_trading_day>
```

### Weekly report

- Weekly report means last 5 valid trading days.
- It is not a calendar week report.
- The weekly window should end on the same previous valid trading day used by the daily report.
- The 5 day window must be based on valid trading observations, not calendar days.
- In documentation and operations, describe it as last 5 valid trading days or 5 trading day weekly report.

## Data Sources

- `osakedata.db` or the configured OHLCV SQLite database:
  - ticker OHLCV input for swing ticker snapshots
  - ticker OHLCV input for synthetic group OHLC and relative OHLC
- `analysis.db`:
  - `dc_group_index_daily`
  - `dc_ticker_swing_signal_daily`
  - `dc_group_swing_signal_daily`
  - `dc_group_synthetic_ohlc_daily`
  - persisted ticker-level Dow, divergence, and candlestick outputs used by the swing enrichment readers
- Datacenter taxonomy CSV:
  - membership and taxonomy version input for index, ticker swing, group swing, and synthetic OHLC runs

## Required Existing Preconditions

Before the daily swing workflow is run:

1. Price data must already be updated in the OHLCV database.
2. Ticker-level technical analysis in `analysis.db` must already be updated:
   - Dow structure
   - divergence
   - candlestick findings
3. The datacenter taxonomy CSV must be available for the intended taxonomy version(s).
4. `analysis.db` must already contain the current datacenter schema and swing tables.

## Daily Workflow Run Order

The current intended order is:

1. Ensure price data is updated in `osakedata.db`.
2. Ensure ticker-level technical analysis in `analysis.db` is updated:
   - Dow structure
   - divergence
   - candlestick findings
3. Run datacenter base index update with `run_datacenter_indices.py`.
4. Run ticker swing snapshot persistence with `run_datacenter_ticker_swing_signals.py`.
5. Run group swing metrics persistence with `run_datacenter_group_swing_signals.py`.
6. Run synthetic OHLC base persistence with `run_datacenter_group_synthetic_ohlc.py`.
7. Run relative OHLC20 update with `run_datacenter_group_synthetic_ohlc.py --relative-only`.
8. Run group structure update with `run_datacenter_group_synthetic_ohlc.py --structure-only`.
9. Run group timing state update with `run_datacenter_group_swing_signals.py --timing-only`.
10. Run group overheat update with `run_datacenter_group_swing_signals.py --overheat-only`.
11. Run ticker scanner update with `run_datacenter_ticker_swing_signals.py --scanner-only`.
12. Run the read-only daily report with `run_datacenter_daily_signal_report.py`.

## Exact CLI Sequence Template

The commands below use the actual current CLI flags.

```bash
SIGNAL_DATE=<previous_valid_trading_day>
START_DATE=<range_start_for_index_or_synthetic_backfill>
END_DATE=${SIGNAL_DATE}
ANALYSIS_DB=<analysis_db_path>
PRICE_DB=<ohlcv_db_path>
TAXONOMY_CSV=<taxonomy_csv_path>
TAXONOMY_VERSION=<taxonomy_version>
MARKET=<market>

python3 run_datacenter_indices.py \
  --ohlcv-db "${PRICE_DB}" \
  --analysis-db "${ANALYSIS_DB}" \
  --taxonomy-csv "${TAXONOMY_CSV}" \
  --taxonomy-version "${TAXONOMY_VERSION}" \
  --market "${MARKET}" \
  --index-base-date 2020-01-01 \
  --start-date "${START_DATE}" \
  --end-date "${END_DATE}" \
  --write-mode replace-range

python3 run_datacenter_ticker_swing_signals.py \
  --price-db "${PRICE_DB}" \
  --analysis-db "${ANALYSIS_DB}" \
  --taxonomy-csv "${TAXONOMY_CSV}" \
  --as-of-date "${SIGNAL_DATE}" \
  --market "${MARKET}" \
  --write-mode replace-date

python3 run_datacenter_group_swing_signals.py \
  --analysis-db "${ANALYSIS_DB}" \
  --taxonomy-csv "${TAXONOMY_CSV}" \
  --signal-date "${SIGNAL_DATE}" \
  --write-mode replace-date

python3 run_datacenter_group_synthetic_ohlc.py \
  --price-db "${PRICE_DB}" \
  --analysis-db "${ANALYSIS_DB}" \
  --taxonomy-csv "${TAXONOMY_CSV}" \
  --start-date "${START_DATE}" \
  --end-date "${END_DATE}" \
  --market "${MARKET}" \
  --write-mode replace-range

python3 run_datacenter_group_synthetic_ohlc.py \
  --price-db "${PRICE_DB}" \
  --analysis-db "${ANALYSIS_DB}" \
  --taxonomy-csv "${TAXONOMY_CSV}" \
  --start-date "${START_DATE}" \
  --end-date "${END_DATE}" \
  --market "${MARKET}" \
  --write-mode replace-relative-range \
  --relative-only

python3 run_datacenter_group_synthetic_ohlc.py \
  --analysis-db "${ANALYSIS_DB}" \
  --start-date "${START_DATE}" \
  --end-date "${END_DATE}" \
  --write-mode replace-structure-range \
  --structure-only

python3 run_datacenter_group_swing_signals.py \
  --analysis-db "${ANALYSIS_DB}" \
  --signal-date "${SIGNAL_DATE}" \
  --write-mode replace-timing-range \
  --timing-only

python3 run_datacenter_group_swing_signals.py \
  --analysis-db "${ANALYSIS_DB}" \
  --signal-date "${SIGNAL_DATE}" \
  --write-mode replace-overheat-range \
  --overheat-only

python3 run_datacenter_ticker_swing_signals.py \
  --analysis-db "${ANALYSIS_DB}" \
  --as-of-date "${SIGNAL_DATE}" \
  --write-mode replace-scanner-range \
  --scanner-only

python3 run_datacenter_daily_signal_report.py \
  --analysis-db "${ANALYSIS_DB}" \
  --signal-date "${SIGNAL_DATE}" \
  --output-md reports/datacenter_daily_swing_signal_report_${SIGNAL_DATE}.md \
  --output-csv reports/datacenter_daily_swing_signal_report_${SIGNAL_DATE}.csv
```

## Write-Mode Guidance

Recommended normal daily usage with currently implemented modes:

- Datacenter indices:
  - `run_datacenter_indices.py --write-mode replace-range`
- Ticker base snapshot:
  - `replace-date` for a clean rerun of one date
  - `upsert` if a non-destructive rerun is preferred
- Group swing metrics:
  - `replace-date` for a clean rerun of one date
  - `upsert` if a non-destructive rerun is preferred
- Synthetic OHLC base:
  - `replace-range` when recalculating a chain-linked range
  - `upsert` only when the existing base range is already trusted
- Relative OHLC:
  - `replace-relative-range` for deterministic reruns
  - `update-existing` for a narrower correction pass
- Group structure:
  - `replace-structure-range` for deterministic reruns
  - `update-existing` for a narrower correction pass
- Group timing:
  - `replace-timing-range` for deterministic reruns
  - `update-existing` for a narrower correction pass
- Group overheat:
  - `replace-overheat-range` for deterministic reruns
  - `update-existing` for a narrower correction pass
- Ticker scanners:
  - `replace-scanner-range` for deterministic reruns
  - `update-existing` for a narrower correction pass

## Backfill Guidance

### Synthetic OHLC

Synthetic OHLC is chain-linked.

- Stable long-history synthetic OHLC should be recalculated from the intended base date.
- Do not calculate each day independently.
- Backfills should run in chronological ranges.
- Daily updates may use a range that preserves the intended chain behavior.

### Ticker EMA warmup

Ticker swing snapshot persistence uses bounded warmup history instead of reading full price history for every date.

- This is expected behavior.
- It is intended to provide enough valid observation warmup for V1 swing metrics without full-history-per-date reads.

## No-Lookahead Safeguards

- Ticker-level Dow, divergence, and candlestick logic is not recalculated inside the datacenter swing layer.
- Ticker swing snapshot enrichment reads only persisted ticker-level analysis outputs from `analysis.db`.
- Daily report rendering is read-only and does not calculate or mutate signals.
- Synthetic OHLC structure uses confirmation lag semantics and must be updated before the report if structure fields are expected to be current.
- Daily and weekly interpretations should always use persisted valid trading observations, not calendar-day shortcuts.

## How Ticker-Level Dow, Divergence, and Candle Data Is Used

- Ticker-level Dow structure, divergence, and candlestick outputs are assumed to already exist in `analysis.db`.
- The datacenter swing workflow reads those persisted outputs through the swing enrichment reader layer.
- The daily report reads only the already persisted swing snapshot fields in `dc_ticker_swing_signal_daily`.
- The daily report does not read ticker technical source tables directly.

## What the Daily Report Does Not Do

The daily report does not:

- insert, update, or delete rows
- recalculate ticker metrics
- recalculate group metrics
- recalculate synthetic OHLC
- recalculate timing, overheat, or scanner signals
- replace missing upstream pipeline stages

It only renders persisted rows for one selected `signal_date`.

## Weekly Workflow Role

The weekly workflow should mean a last 5 valid trading days summary ending on the same previous valid trading day used by the daily report.

That weekly view should answer:

- what changed over the last 5 valid trading days
- which subindustries improved or weakened during the last 5 trading days
- which scanner lists were repeatedly active
- whether overheat risk increased or decreased
- whether breadth deterioration persisted across the 5 day window

This weekly view is separate from the longer strategic datacenter index view.

The existing strategic datacenter index report remains the longer-horizon context tool for:

- 20d, 60d, and 120d returns
- `pct_above_ma50`
- `pct_above_ma200`
- relative strength versus `SPY` and `QQQ`
- layer and subindustry strategic strength
- data quality

Current status:

- The implemented 5 valid trading day weekly swing report CLI is `run_datacenter_weekly_swing_report.py`.
- It is separate from `run_datacenter_index_report.py`, which remains the longer strategic datacenter index report.
- `run_datacenter_index_report.py` remains the current strategic datacenter report entrypoint.
- The weekly swing report should not be confused with a calendar week report.

## Troubleshooting / Incomplete Pipeline Symptoms

Common signs that earlier stages were not run or were only partially run:

- Daily report shows missing `timing_state` rows.
- Daily report shows missing `overheat_risk_level` rows.
- Daily report shows ticker scanner fields still `NULL`.
- Synthetic OHLC rows are present but `latest_structure_label` is missing.
- Synthetic OHLC rows are present but `relative_close_20` is missing.
- Many ticker rows have `MISSING_AS_OF_DATE` or `MISSING_CLOSE_AS_OF_DATE`.
- Dashboard ecosystem row is missing.
- Scanner sections render `No rows.` when base snapshot data exists but the scanner-only update was not run.

## Validation Checklist

Before treating a daily report as complete:

1. Confirm `SIGNAL_DATE` is the previous valid trading day, not just the current calendar date.
2. Confirm OHLCV data is loaded through the selected `SIGNAL_DATE`.
3. Confirm ticker-level Dow, divergence, and candlestick updates were completed upstream.
4. Confirm `run_datacenter_indices.py` completed for the required taxonomy version and date range.
5. Confirm ticker swing base snapshots were persisted for `SIGNAL_DATE`.
6. Confirm group swing rows were persisted for `SIGNAL_DATE`.
7. Confirm synthetic OHLC base rows were persisted for the required range.
8. Confirm relative OHLC update was run.
9. Confirm structure update was run.
10. Confirm timing update was run.
11. Confirm overheat update was run.
12. Confirm ticker scanner update was run.
13. Confirm the daily report renders without missing required tables or invalid-date errors.
