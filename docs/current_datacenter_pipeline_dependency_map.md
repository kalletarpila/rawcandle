# Current Datacenter Pipeline Dependency Map

This document maps the current Datacenter swing pipeline as implemented in the
codebase. It is a read-only current-state evidence document. It does not define
the target incremental contract or implementation plan.

Evidence status labels:

- `CONFIRMED_FROM_CODE`: directly observed in the current source.
- `INFERRED_FROM_FLOW`: inferred from call order, names, or summary output.
- `REQUIRES_VERIFICATION`: plausible but not fully proven in this pass.

## Scope

Pipeline entry point:

- CLI: `run_datacenter_swing_pipeline.py`
- Orchestrator: `analysis/datacenter_indices/swing_pipeline_orchestrator.py`
- Current configured scheduler use: Datacenter post-step after USA stock update.

The current orchestrator builds a linear stage list and runs each stage in order.
For each stage, it executes the runner, then writes the stage watermark if that
stage has a `watermark_builder`. Watermark writes happen after the runner returns
successfully. If a runner raises, the stage status is marked failed in the in-run
summary and the exception propagates.

Current stage order:

```text
1. Datacenter base index
2. Ticker swing base snapshots
3. Group swing base metrics
4. Synthetic OHLC base
5. Relative OHLC20
6. Group structure / BOS / RESET
7. Group timing states
8. Group overheat risk
9. Ticker scanners
10. Pipeline audit
11. Automatic technical relevance
12. Daily report
13. Rolling 30 report
14. Rolling 5 report
15. Rolling 2 report
16. Windows report copy
```

## Pipeline Dependency Chain

```text
source data
  osakedata.db: osakedata
  taxonomy CSV
  analysis enrichments: DOW structure, divergence, candlestick

canonical dc_* materializations
  Stage 1 -> dc_group_index_daily
  Stage 2 -> dc_ticker_swing_signal_daily base snapshot fields
  Stage 3 -> dc_group_swing_signal_daily base group fields
  Stage 4 -> dc_group_synthetic_ohlc_daily base OHLC fields

derived dc_* materializations
  Stage 5 -> dc_group_synthetic_ohlc_daily relative OHLC20 fields
  Stage 6 -> dc_group_synthetic_ohlc_daily structure/BOS/RESET fields
  Stage 7 -> dc_group_swing_signal_daily timing fields
  Stage 8 -> dc_group_swing_signal_daily overheat fields
  Stage 9 -> dc_ticker_swing_signal_daily scanner fields

audits and derived contexts
  Stage 10 -> read-only pipeline audit over dc_* facts
  Stage 11 -> technical_signal_relevance_* tables

reports and artifacts
  Stage 12 -> daily markdown/csv
  Stage 13 -> rolling 30 markdown/csv
  Stage 14 -> rolling 5 markdown/csv
  Stage 15 -> rolling 2 markdown/csv
  Stage 16 -> copies generated report files to /mnt/d/swing_reports

EC source-layer loaders
  scheduler post-step after Datacenter pipeline -> ec_* source-layer refresh
  historical backfill CLI -> per-date ec_* source-layer backfill

watermarks
  Datacenter stages -> dc_pipeline_watermark
  EC refresh/build -> ec_pipeline_watermark copied from dc_pipeline_watermark
  EC historical backfill -> intentionally does not refresh ec_pipeline_watermark
```

Field-level materialization grouping observed in the current code:

```text
ec_ticker_signal_daily
  <- Stage 2 base fields
  <- Stage 9 scanner fields

ec_group_signal_daily
  <- Stage 3 base fields
  <- Stage 7 timing fields
  <- Stage 8 overheat fields

ec_group_synthetic_ohlc_daily
  <- Stage 4 base fields
  <- Stage 5 relative fields
  <- Stage 6 structure fields
```

Implication for later contract work: table-to-table dependency is too coarse to
fully describe dirty propagation. The same source and EC target table can receive
materialized changes from multiple stages and field groups. A Stage 2 pilot can
merge such effects conservatively by range, but the dependency model should not
assume one source table has one producing stage.

## Cross-Cutting Current Behavior

- The pipeline receives one `start_date`, one `signal_date`, and one
  `index_base_date`.
- Most canonical/derived stages are invoked with the same `start_date` to
  `signal_date` range.
- The orchestrator currently constructs all stage arguments directly. Existing
  `dc_pipeline_watermark` rows are not used by the orchestrator to skip or narrow
  stage execution.
- `analysis/datacenter_indices/pipeline_plan.py` can read watermarks and produce
  planning actions, but this plan is not currently the execution driver for
  `run_datacenter_swing_pipeline`.
- Report stages are skipped only after a pipeline audit `FAIL`. `WARN` still
  allows reporting.
- Stage-level watermarks are written after successful stage runner completion.
  The audit stage writes its validation status (`OK`, `WARN`, or `FAIL`) as the
  watermark status.
- A missing or old stage watermark does not prove that no rows were written.
  Several stages perform date/range writes before the final stage watermark is
  recorded.
- Automatic technical relevance and Windows copy do not currently have
  Datacenter watermark builders in the orchestrator.

## Stage Cards

### Stage 1: Datacenter Base Index

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- CLI: `run_datacenter_indices.py`
- Function: `analysis.datacenter_indices.persistence.run_datacenter_indices`
- Orchestrator key: `datacenter_base_index`

Inputs:

- `osakedata.db` table `osakedata`
- taxonomy CSV
- `taxonomy_version`
- `market`
- `index_base_date`
- `start_date`
- `end_date` / pipeline `signal_date`
- benchmark tickers `SPY`, `QQQ`

Outputs:

- `analysis.db` table `dc_group_index_daily`

Write semantics:

- Orchestrator always passes `--write-mode replace-range`.
- Persistence deletes existing rows for the taxonomy/date range and inserts the
  calculated rows.

Date/range semantics:

- Orchestrator passes `--start-date index_base_date` and `--end-date signal_date`.
- Current scheduler run used `2020-01-01` through selected signal date.

Lookback or full-history dependency:

- `CONFIRMED_FROM_CODE`: current orchestrator treats this as full range from
  `index_base_date`.
- `INFERRED_FROM_FLOW`: index levels are chain-like and currently rebuilt from
  base date.

Validation:

- CLI/function summary reports write status and data quality counts.
- Full pipeline audit later validates selected signal date readiness.

Watermark reads:

- None in current orchestrator execution.

Watermark writes:

- `dc_pipeline_watermark` component `GROUP_INDEX`
- `start_date=index_base_date`, `end_date=signal_date`, `market=market`

Direct downstream consumers:

- Stage 3 uses valid group index dates and group returns from
  `dc_group_index_daily`.
- Reports/audit read group index indirectly or directly.
- EC loader `ec_group_index_daily` reads this table.

Indirect downstream effects:

- Group swing metrics depend on index dates/returns.
- Scanner and reports can be affected through group timing/overheat downstream.

EC impact:

- Canonical EC source table: `ec_group_index_daily`.

Report/scheduler/UI impact:

- Included in final pipeline summary and watermarks UI.

Failure and partial-success behavior:

- If the CLI exits non-zero, the orchestrator raises and the pipeline stops.
- Watermark is not written for the failed stage.

### Stage 2: Ticker Swing Base Snapshots

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- CLI: `run_datacenter_ticker_swing_signals.py`
- Function:
  `analysis.datacenter_indices.swing_ticker_persistence.persist_datacenter_ticker_swing_snapshots_for_dates`
- Orchestrator key: `ticker_swing_base_snapshots`

Inputs:

- `osakedata.db` table `osakedata`
- taxonomy CSV primary ticker universe
- analysis enrichments read through `swing_analysis_readers`:
  DOW structure, divergence, candlestick
- `market`
- `signal_version`
- range `start_date..signal_date`

Outputs:

- `analysis.db` table `dc_ticker_swing_signal_daily`
- Base snapshot fields: price, returns, MA/EMA metrics, DOW context,
  divergence/candlestick enrichment, price status.
- Scanner fields are initialized as `NULL` in this stage and filled later by
  Stage 9.

Write semantics:

- Orchestrator passes `--write-mode replace-date`.
- Range CLI resolves valid price dates, then calls per-date persistence.
- For each date, `replace-date` deletes matching
  `(signal_date, signal_version, taxonomy_version)` rows and inserts freshly
  built rows.

Date/range semantics:

- Range CLI first calls `load_valid_price_dates_for_market`.
- That function currently selects distinct `osakedata.pvm` values in the range
  for the market and taxonomy primary tickers.
- It does not enforce a minimum ticker count by itself.

Lookback or full-history dependency:

- `CONFIRMED_FROM_CODE`: default `max_valid_price_rows=220`.
- For a single date, it loads up to 220 valid price rows per ticker through the
  as-of date.
- For a range, it preloads a shared price-history window. It finds the earliest
  required input date by taking up to 220 valid rows before the earliest selected
  output signal date per ticker, then reads price rows from that global input
  start through the latest signal date.
- Metrics include 5/10/20/60-day returns, MA10, EMA10, EMA20, highest close 20d,
  volume average 20d, EMA slope flags, and trading-day ages for DOW events.

Validation:

- Per-date summary reports rows prepared, price-data status counts, inserts,
  deletes, and `validation_status=OK`.
- No full parity or row-count expectation is enforced inside Stage 2 itself.
  Full pipeline audit later checks selected signal date counts/readiness.

Watermark reads:

- None in current orchestrator execution.

Watermark writes:

- `dc_pipeline_watermark` component `TICKER_SWING_BASE`
- `start_date=start_date`, `end_date=signal_date`, `market=market`,
  `signal_version=signal_version`

Direct downstream consumers:

- Stage 3 reads `dc_ticker_swing_signal_daily`.
- Stage 9 updates scanner fields on `dc_ticker_swing_signal_daily`.
- Stage 10 audit reads it.
- Stage 11 technical relevance ticker selection reads it.
- Stage 12 and rolling reports read it.
- EC loader `ec_ticker_signal_daily` reads it.

Indirect downstream effects:

- The confirmed materialization chain is at least:

```text
Stage 2
  -> Stage 3
     -> Stage 7
        -> Stage 9
  -> Stage 9
```

- Group metrics, timing, ticker scanners, reports, technical relevance, and EC
  source-layer rows can all be affected by changed Stage 2 output.
- Stage 8 is not currently shown as a direct Stage 9 input, but it updates group
  overheat fields that are consumed by reports and the EC group source layer.

EC impact:

- Canonical EC source table: `ec_ticker_signal_daily`.
- Current target combines Stage 2 base fields and Stage 9 scanner fields.
- Current scheduler EC refresh only refreshes the selected latest signal date.
  Historical EC backfill has a separate CLI.

Report/scheduler/UI impact:

- Large runtime contributor in daily Datacenter pipeline.
- Current daily scheduler starts this stage at the configured pipeline
  `start_date`, currently `2025-08-01`.

Failure and partial-success behavior:

- Each per-date write commits inside the Stage 2 persistence function.
- If range execution fails after earlier dates have completed, earlier per-date
  writes may remain while later dates are not processed.
- Orchestrator watermark is written only if the whole Stage 2 CLI returns
  success.
- Therefore a future materialized-output record must describe the actual
  validated written range, not only the range originally planned.

### Stage 3: Group Swing Base Metrics

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- CLI: `run_datacenter_group_swing_signals.py`
- Function:
  `analysis.datacenter_indices.swing_group_persistence.persist_datacenter_group_swing_signal_range`
- Orchestrator key: `group_swing_base_metrics`

Inputs:

- taxonomy CSV
- `dc_ticker_swing_signal_daily` for each signal date
- `dc_group_index_daily` for valid group index dates and group return history
- `signal_version`

Outputs:

- `dc_group_swing_signal_daily` base group metrics

Write semantics:

- Orchestrator passes `--write-mode replace-date`.
- Range function selects valid signal dates from `dc_group_index_daily`.
- For each selected date, `replace-date` deletes and reinserts group rows for
  that date/taxonomy/signal version.

Date/range semantics:

- Effective processed dates are dates present in `dc_group_index_daily` for the
  selected taxonomy versions.
- Requested calendar days without group index rows are skipped.

Lookback or full-history dependency:

- Uses current-date ticker snapshots and historical group index levels for
  returns/breadth deltas.
- Exact minimum input lookback was not fully quantified in this pass.

Validation:

- Per-date and range summaries report group row counts and data quality counts.
- Full pipeline audit later checks selected signal date readiness.

Watermark reads:

- None in current orchestrator execution.

Watermark writes:

- `dc_pipeline_watermark` component `GROUP_SWING_BASE`
- `start_date=start_date`, `end_date=signal_date`, `signal_version=signal_version`

Direct downstream consumers:

- Stage 7 timing state updates.
- Stage 8 overheat updates.
- Stage 9 ticker scanners via subindustry timing state.
- Reports and audit.
- EC loader `ec_group_signal_daily`.

Indirect downstream effects:

- Scanner classifications and report classifications can change when group
  metrics/timing change.

EC impact:

- Canonical EC source table: `ec_group_signal_daily`.

Report/scheduler/UI impact:

- Included in reports and pipeline summaries.

Failure and partial-success behavior:

- Range processing commits per selected date through the per-date persistence.
- Earlier dates can remain written if a later date fails.
- Watermark is written only after the full stage returns success.

### Stage 4: Synthetic OHLC Base

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- CLI: `run_datacenter_group_synthetic_ohlc.py`
- Function:
  `analysis.datacenter_indices.swing_group_synthetic_ohlc.persist_datacenter_group_synthetic_ohlc`
- Orchestrator key: `synthetic_ohlc_base`

Inputs:

- `osakedata.db` table `osakedata`
- taxonomy CSV
- `market`
- `calc_version`
- range `start_date..signal_date`

Outputs:

- `dc_group_synthetic_ohlc_daily` base synthetic OHLC rows

Write semantics:

- Orchestrator passes `--write-mode replace-range`.
- Existing rows in the selected range/version/group scope are deleted and rows
  are inserted.

Date/range semantics:

- Uses requested start/end range directly.

Lookback or full-history dependency:

- `INFERRED_FROM_FLOW`: synthetic OHLC base is range materialization over source
  price data and taxonomy groups.
- Exact minimum warmup for all fields was not fully quantified in this pass.

Validation:

- Summary reports inserted/deleted rows and data quality counts.
- Full pipeline audit later validates selected signal date readiness.

Watermark reads:

- None in current orchestrator execution.

Watermark writes:

- `dc_pipeline_watermark` component `SYNTHETIC_OHLC_BASE`
- `start_date=start_date`, `end_date=signal_date`, `market=market`,
  `calc_version=ohlc_calc_version`

Direct downstream consumers:

- Stage 5 relative OHLC20.
- Stage 6 group structure/BOS/RESET.
- Reports and audit.
- EC loader `ec_group_synthetic_ohlc_daily`.

Indirect downstream effects:

- Group structure and report context can change when synthetic base OHLC changes.

EC impact:

- Canonical EC source table: `ec_group_synthetic_ohlc_daily`.

Report/scheduler/UI impact:

- Included in reports and audit.

Failure and partial-success behavior:

- Function is expected to fail non-zero on exception.
- Watermark is written only after successful stage completion.

### Stage 5: Relative OHLC20

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- CLI: `run_datacenter_group_synthetic_ohlc.py --relative-only`
- Function:
  `analysis.datacenter_indices.swing_group_synthetic_ohlc.persist_datacenter_group_relative_ohlc`
- Orchestrator key: `relative_ohlc20`

Inputs:

- `dc_group_synthetic_ohlc_daily` existing rows in selected range
- `osakedata.db` source prices and taxonomy CSV for ticker-relative inputs
- `relative_base_window`, default 20

Outputs:

- Updates relative OHLC20 fields on `dc_group_synthetic_ohlc_daily`

Write semantics:

- Orchestrator passes `--write-mode replace-relative-range`.
- Existing relative fields are cleared to `NULL` for selected range/scope, then
  updated.

Date/range semantics:

- Uses requested `start_date..signal_date`.
- Relative input construction uses rolling window length 20.

Lookback or full-history dependency:

- Requires sufficient price history for the 20-row relative base window.
- Exact additional warmup behavior should be verified before narrowing this
  stage independently.

Validation:

- Summary reports rows with/without relative values and `validation_status`.
- Full pipeline audit later checks selected-date readiness.

Watermark reads:

- None in current orchestrator execution.

Watermark writes:

- `dc_pipeline_watermark` component `SYNTHETIC_OHLC_RELATIVE`

Direct downstream consumers:

- Reports and audit read relative fields.
- EC synthetic loader copies these fields.

Indirect downstream effects:

- Report classification/context can change when relative fields change.

EC impact:

- Same target table as Stage 4: `ec_group_synthetic_ohlc_daily`.

Report/scheduler/UI impact:

- Included in daily/rolling report context.

Failure and partial-success behavior:

- Clears and updates within the stage function. Confirm exact transaction scope
  before incremental implementation.
- Watermark is written only after successful stage completion.

### Stage 6: Group Structure / BOS / RESET

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- CLI: `run_datacenter_group_synthetic_ohlc.py --structure-only`
- Function:
  `analysis.datacenter_indices.swing_group_synthetic_ohlc.persist_datacenter_group_structure`
- Orchestrator key: `group_structure_bos_reset`

Inputs:

- `dc_group_synthetic_ohlc_daily` rows through `end_date`

Outputs:

- Updates structure, BOS, RESET, trend, freshness fields on
  `dc_group_synthetic_ohlc_daily`

Write semantics:

- Orchestrator passes `--write-mode replace-structure-range`.
- Existing structure fields are cleared for selected range/scope and then
  updated.

Date/range semantics:

- Requested output range is `start_date..signal_date`.
- Builder loads group synthetic rows through `end_date` and emits updates only
  inside the selected output range.

Lookback or full-history dependency:

- Structure uses pivot logic and stateful tracking through time.
- Pivot radius varies by group type.
- `CONFIRMED_FROM_CODE`: it reads rows through end date and filters output to
  the requested start/end.
- `REQUIRES_VERIFICATION`: whether narrowing `start_date` without earlier
  warmup/state replay is safe.

Validation:

- Summary reports structure rows with/without labels and status.
- Full pipeline audit later checks selected-date readiness.

Watermark reads:

- None in current orchestrator execution.

Watermark writes:

- `dc_pipeline_watermark` component `SYNTHETIC_OHLC_STRUCTURE`

Direct downstream consumers:

- Reports and audit.
- EC synthetic loader copies these fields.

Indirect downstream effects:

- Report state/freshness classifications can change.

EC impact:

- Same target table as Stage 4: `ec_group_synthetic_ohlc_daily`.

Report/scheduler/UI impact:

- Included in daily/rolling reports.

Failure and partial-success behavior:

- Watermark is written only after successful stage completion.
- Transaction behavior for range field clearing/updating should be verified
  before incremental implementation.

### Stage 7: Group Timing States

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- CLI: `run_datacenter_group_swing_signals.py --timing-only`
- Function:
  `analysis.datacenter_indices.swing_group_persistence.persist_datacenter_group_timing_states`
- Orchestrator key: `group_timing_states`

Inputs:

- Existing `dc_group_swing_signal_daily` rows in selected range

Outputs:

- Updates `timing_state` and `timing_reason` fields on
  `dc_group_swing_signal_daily`

Write semantics:

- Orchestrator passes `--write-mode replace-timing-range`.
- Existing timing fields are cleared for range/scope and then updated.

Date/range semantics:

- Uses requested `start_date..signal_date`.

Lookback or full-history dependency:

- `REQUIRES_VERIFICATION`: exact timing-state dependency on prior rows and
  whether range can be narrowed safely.

Validation:

- Summary reports updated/cleared counts and status.

Watermark reads:

- None in current orchestrator execution.

Watermark writes:

- `dc_pipeline_watermark` component `GROUP_TIMING`

Direct downstream consumers:

- Stage 8 can depend on group timing/risk context.
- Stage 9 ticker scanners read subindustry timing state.
- Reports and EC group loader consume updated fields.

Indirect downstream effects:

- Ticker scanner entry/exit classifications and report classifications can
  change.

EC impact:

- Same target table as Stage 3: `ec_group_signal_daily`.
- This target also receives Stage 3 base fields and Stage 8 overheat fields.

Report/scheduler/UI impact:

- Included in report context.

Failure and partial-success behavior:

- Watermark is written only after successful stage completion.

### Stage 8: Group Overheat Risk

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- CLI: `run_datacenter_group_swing_signals.py --overheat-only`
- Function:
  `analysis.datacenter_indices.swing_group_persistence.persist_datacenter_group_overheat_risk`
- Orchestrator key: `group_overheat_risk`

Inputs:

- Existing `dc_group_swing_signal_daily` rows in selected range

Outputs:

- Updates `overheat_risk_level` on `dc_group_swing_signal_daily`

Write semantics:

- Orchestrator passes `--write-mode replace-overheat-range`.
- Existing overheat fields are cleared for range/scope and then updated.

Date/range semantics:

- Uses requested `start_date..signal_date`.

Lookback or full-history dependency:

- `REQUIRES_VERIFICATION`: exact overheat dependency on prior rows should be
  quantified before independently narrowing this stage.

Validation:

- Summary reports updated/cleared counts and status.

Watermark reads:

- None in current orchestrator execution.

Watermark writes:

- `dc_pipeline_watermark` component `GROUP_OVERHEAT`

Direct downstream consumers:

- Reports and EC group loader.

Indirect downstream effects:

- Report context/risk sections can change.

EC impact:

- Same target table as Stage 3: `ec_group_signal_daily`.
- This target also receives Stage 3 base fields and Stage 7 timing fields.

Report/scheduler/UI impact:

- Included in report context.

Failure and partial-success behavior:

- Watermark is written only after successful stage completion.

### Stage 9: Ticker Scanners

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- CLI: `run_datacenter_ticker_swing_signals.py --scanner-only`
- Function:
  `analysis.datacenter_indices.swing_ticker_persistence.persist_datacenter_ticker_scanner_signals`
- Orchestrator key: `ticker_scanners`

Inputs:

- Existing `dc_ticker_swing_signal_daily` rows in selected range
- `dc_group_swing_signal_daily` subindustry timing state for each row/date

Outputs:

- Updates scanner fields on `dc_ticker_swing_signal_daily`:
  breakout, pullback, exit risk, exit reason/severity.

Write semantics:

- Orchestrator passes `--write-mode replace-scanner-range`.
- Existing scanner fields are cleared for range/scope and then updated.

Date/range semantics:

- Scanner CLI selects existing ticker signal dates in the requested range.
- Non-existing ticker-signal dates are skipped.

Lookback or full-history dependency:

- Scanner rules use already-materialized Stage 2 fields and same-date
  subindustry timing state.
- `CONFIRMED_FROM_CODE`: scanner itself does not read price history.

Validation:

- Summary reports updated/cleared counts, scanner counts, and status.

Watermark reads:

- None in current orchestrator execution.

Watermark writes:

- `dc_pipeline_watermark` component `TICKER_SCANNER`

Direct downstream consumers:

- Stage 10 audit.
- Stage 11 technical relevance ticker selection/context.
- Daily and rolling reports.
- EC ticker loader.

Indirect downstream effects:

- Report trigger sections and EC ticker facts can change.

EC impact:

- Same target table as Stage 2: `ec_ticker_signal_daily`.
- This target also receives Stage 2 base fields.

Report/scheduler/UI impact:

- Directly affects report counts such as breakout/pullback/exit risk.

Failure and partial-success behavior:

- Watermark is written only after successful stage completion.

### Stage 10: Pipeline Audit

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- Function: `analysis.datacenter_indices.swing_pipeline_audit.load_swing_pipeline_audit`
- Orchestrator key: `pipeline_audit`

Inputs:

- `dc_ticker_swing_signal_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`
- Expected counts passed by orchestrator, when configured
- Weekly window size

Outputs:

- No canonical table writes observed in this pass.
- Prints/returns summary validation result.

Write semantics:

- Read-only audit behavior inferred from code references.

Date/range semantics:

- Validates selected `signal_date`.
- Also evaluates weekly window readiness.

Lookback or full-history dependency:

- Reads latest selected date and rolling/weekly window context.

Validation:

- Produces `validation_status=OK|WARN|FAIL`.
- `daily_ready` and `weekly_ready` are explicit summary fields.

Watermark reads:

- None in current orchestrator execution.

Watermark writes:

- `dc_pipeline_watermark` component `PIPELINE_AUDIT`
- Status is the audit validation status, not always `OK`.

Direct downstream consumers:

- Orchestrator uses `FAIL` to stop report stages.
- `WARN` does not stop reports.

Indirect downstream effects:

- Final pipeline status becomes `WARN` when audit status is `WARN`.

EC impact:

- Scheduler EC source-layer refresh currently runs after Datacenter pipeline
  success/status handling, not inside this stage.

Report/scheduler/UI impact:

- Controls whether reports are allowed after audit failure.
- Summary status is visible in scheduler logs.

Failure and partial-success behavior:

- If audit raises or returns failure through strict mode, pipeline can stop
  before reports.
- Audit `FAIL` returns pipeline summary with `pipeline_status=FAIL`.

### Stage 11: Automatic Technical Relevance

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- Function:
  `analysis.datacenter_indices.swing_pipeline_orchestrator._run_automatic_technical_relevance_stage`
- Service:
  `rawcandle.technical_signal_relevance_service.run_technical_signal_relevance_for_tickers`
- Orchestrator key: `automatic_technical_relevance`

Inputs:

- Tickers loaded from Datacenter ticker snapshots for selected signal date.
- Technical signal/relevance source tables used by the service.
- Date range computed as `signal_date - 45 calendar days` through `signal_date`.

Outputs:

- Technical signal relevance persistence tables.
- Existing run is reused if the generated run id already exists.

Write semantics:

- Service writes records for selected tickers/date range.
- Existing run id causes reuse/skip summary.

Date/range semantics:

- Fixed 45 calendar-day lookback from selected signal date in current code.

Lookback or full-history dependency:

- `CONFIRMED_FROM_CODE`: 45 calendar days.
- `REQUIRES_VERIFICATION`: whether this should become trading-day based later.

Validation:

- Summary reports records written and missing context counts.

Watermark reads:

- None.

Watermark writes:

- None in current Datacenter orchestrator.

Direct downstream consumers:

- Daily and rolling reports when `technical_relevance_run_id` is passed.

Indirect downstream effects:

- Report relevance context can change.

EC impact:

- Not currently one of the four EC canonical source loaders.
- Side path for report context. Stage 2 historical dirty ranges do not
  automatically imply a Stage 11 rerun for the same historical range under the
  current semantics.

Report/scheduler/UI impact:

- Included in final report content and scheduler summary.

Failure and partial-success behavior:

- Runtime exception stops pipeline.
- Existing run id is treated as reused rather than failed.

### Stage 12: Daily Report

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- Function:
  `analysis.datacenter_indices.swing_daily_report.write_daily_swing_signal_report`
- Orchestrator key: `daily_report`

Inputs:

- `dc_group_swing_signal_daily`
- `dc_ticker_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`
- watchlist file
- optional technical relevance run id

Outputs:

- Markdown report
- CSV report

Write semantics:

- Writes files to `output_dir`; timestamped names are used by the orchestrator.
- Does not write canonical `dc_*` tables.

Date/range semantics:

- Selected `signal_date`.

Lookback or full-history dependency:

- Reads same-date Datacenter facts and report context.

Validation:

- Summary reports row counts and `validation_status=OK`.

Watermark reads:

- None.

Watermark writes:

- `dc_pipeline_watermark` component `DAILY_REPORT`
- This is artifact-generation evidence, not canonical `dc_*` materialization
  coverage.

Direct downstream consumers:

- Stage 16 Windows report copy.

Indirect downstream effects:

- User-facing daily report.

EC impact:

- None directly.

Report/scheduler/UI impact:

- Primary daily report artifact path is recorded in pipeline and scheduler
  summaries.

Failure and partial-success behavior:

- File write failure raises and stops later stages.

### Stage 13: Rolling 30 Report

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- Function:
  `analysis.datacenter_indices.swing_weekly_report.write_weekly_swing_report`
- Orchestrator key: `rolling_30_report`

Inputs:

- `dc_group_swing_signal_daily`
- `dc_ticker_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`
- watchlist file
- optional technical relevance run id

Outputs:

- Rolling 30 markdown report
- Rolling 30 CSV report

Write semantics:

- Writes files to `output_dir`.

Date/range semantics:

- Uses `end_date=signal_date` and `window_size=30`.
- Summary reports actual `window_start_date` and valid signal date count.

Lookback or full-history dependency:

- Requires 30 valid signal dates for a complete window.

Validation:

- Summary includes incomplete-window flag and `validation_status=OK`.

Watermark reads:

- None.

Watermark writes:

- `dc_pipeline_watermark` component `ROLLING_REPORT_30`
- `start_date` comes from report summary `window_start_date`.
- This is artifact-generation evidence, not canonical `dc_*` materialization
  coverage.

Direct downstream consumers:

- Stage 16 Windows report copy.

Indirect downstream effects:

- User-facing rolling report.

EC impact:

- None directly.

Report/scheduler/UI impact:

- Path recorded in final summaries and copied to Windows.

Failure and partial-success behavior:

- File write failure raises and stops later stages.

### Stage 14: Rolling 5 Report

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- Function:
  `analysis.datacenter_indices.swing_weekly_report.write_weekly_swing_report`
- Orchestrator key: `rolling_5_report`

Inputs:

- Same report inputs as Stage 13.

Outputs:

- Rolling 5 markdown and CSV reports.

Write semantics:

- Writes files to `output_dir`.

Date/range semantics:

- Uses `end_date=signal_date` and `window_size=5`.

Lookback or full-history dependency:

- Requires 5 valid signal dates for a complete window.

Validation:

- Summary includes incomplete-window flag and `validation_status=OK`.

Watermark reads:

- None.

Watermark writes:

- `dc_pipeline_watermark` component `ROLLING_REPORT_5`
- This is artifact-generation evidence, not canonical `dc_*` materialization
  coverage.

Direct downstream consumers:

- Stage 16 Windows report copy.

Indirect downstream effects:

- User-facing rolling report.

EC impact:

- None directly.

Report/scheduler/UI impact:

- Path recorded in final summaries and copied to Windows.

Failure and partial-success behavior:

- File write failure raises and stops later stages.

### Stage 15: Rolling 2 Report

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- Function:
  `analysis.datacenter_indices.swing_weekly_report.write_weekly_swing_report`
- Orchestrator key: `rolling_2_report`

Inputs:

- Same report inputs as Stage 13.

Outputs:

- Rolling 2 markdown and CSV reports.

Write semantics:

- Writes files to `output_dir`.

Date/range semantics:

- Uses `end_date=signal_date` and `window_size=2`.

Lookback or full-history dependency:

- Requires 2 valid signal dates for a complete window.

Validation:

- Summary includes incomplete-window flag and `validation_status=OK`.

Watermark reads:

- None.

Watermark writes:

- `dc_pipeline_watermark` component `ROLLING_REPORT_2`
- This is artifact-generation evidence, not canonical `dc_*` materialization
  coverage.

Direct downstream consumers:

- Stage 16 Windows report copy.

Indirect downstream effects:

- User-facing rolling report.

EC impact:

- None directly.

Report/scheduler/UI impact:

- Path recorded in final summaries and copied to Windows.

Failure and partial-success behavior:

- File write failure raises and stops later stages.

### Stage 16: Windows Report Copy

Evidence status: `CONFIRMED_FROM_CODE`

Entry point / function / CLI:

- Function:
  `analysis.datacenter_indices.swing_pipeline_orchestrator._copy_generated_report_files`
- Orchestrator key: `windows_report_copy`

Inputs:

- Generated daily/rolling markdown and CSV report paths.
- Destination directory `/mnt/d/swing_reports`.

Outputs:

- Copies report files to Windows-visible directory.

Write semantics:

- Creates destination directory if missing.
- Copies each source report file with `shutil.copy2`.

Date/range semantics:

- Artifact-level only.

Lookback or full-history dependency:

- None.

Validation:

- Verifies all source files exist before copy.

Watermark reads:

- None.

Watermark writes:

- None.

Direct downstream consumers:

- Windows/user report access.

Indirect downstream effects:

- None on canonical data.

EC impact:

- None.

Report/scheduler/UI impact:

- Makes generated reports available under `/mnt/d/swing_reports`.

Failure and partial-success behavior:

- If any source file is missing, raises before copying.
- Copy failure raises and causes pipeline failure after earlier report files have
  already been generated.

## EC Source-Layer Current Behavior

Evidence status: `CONFIRMED_FROM_CODE`

Scope note:

- The current `dc_* -> ec_*` load path is transitional architecture.
- Target state is that `ec_*` tables are built per ecosystem directly from raw
  data or durable shared source layers, not as copies of Datacenter tables.
- Therefore future EC watermark, dirty-range, and invalidation design should be
  based on EC's own source dependencies. This map describes the current bridge.

Current EC refresh entry point:

- CLI: `rawcandle/cli/run_ec_source_layer_refresh.py`
- Called by scheduler after Datacenter pipeline post-step.

Current EC historical backfill entry point:

- CLI: `rawcandle/cli/run_ec_source_layer_backfill.py`

EC source loaders:

- `load_ec_ticker_signal_daily_from_dc`
  - source: `dc_ticker_swing_signal_daily`
  - target: `ec_ticker_signal_daily`
- `load_ec_group_signal_daily_from_dc`
  - source: `dc_group_swing_signal_daily`
  - target: `ec_group_signal_daily`
- `load_ec_group_synthetic_ohlc_daily_from_dc`
  - source: `dc_group_synthetic_ohlc_daily`
  - target: `ec_group_synthetic_ohlc_daily`
- `load_ec_group_index_daily_from_dc`
  - source: `dc_group_index_daily`
  - target: `ec_group_index_daily`
- `load_ec_pipeline_watermark_from_dc`
  - source: `dc_pipeline_watermark`
  - target: `ec_pipeline_watermark`

Write semantics:

- Each fact loader is date-based.
- With `replace_existing=True`, it deletes existing target rows for the selected
  ecosystem/taxonomy/date/version/source scope and inserts current source rows.
- Without `replace_existing=True`, existing target rows block replacement.

Date/range semantics:

- Refresh CLI operates on a selected signal date.
- Historical backfill CLI plans a requested date range, selects aligned source
  dates, and runs date-based loaders for each selected date.
- Historical backfill intentionally skips `ec_pipeline_watermark` refresh.

Validation:

- Refresh/backfill run coverage audit and fact parity audit.
- Backfill output reports per-date `total_mismatch_count`.

Current gap relative to incremental execution:

- The scheduler refresh path currently syncs the selected latest signal date.
- It does not consume a Datacenter materialized-output artifact or persistent
  EC pending queue.

## Watermark Current Behavior

Evidence status: `CONFIRMED_FROM_CODE`

`dc_pipeline_watermark`:

- Written by Datacenter stage watermark builders after successful stage runner
  completion.
- Primary key:
  `(component_name, taxonomy_version, market, signal_version, calc_version)`.
- Contains `start_date`, `end_date`, `row_count`, `status`,
  `last_successful_run_id`, `last_successful_at_utc`, `notes`.

`ec_pipeline_watermark`:

- Loaded from `dc_pipeline_watermark` by EC build/refresh.
- Primary key: `(ecosystem_id, pipeline_name, source_table)`.
- Contains `latest_signal_date`, `latest_run_id`, `status`, timestamps.
- Unknown Datacenter components are represented with `UNKNOWN:` source table
  prefixes.

Planner use:

- `analysis/datacenter_indices/pipeline_plan.py` reads
  `dc_pipeline_watermark` and can classify components as `UP_TO_DATE`,
  `RUN_FULL_RANGE`, `RUN_INCREMENTAL_CANDIDATE`, `RUN_REQUIRED`, or
  `MISSING_WATERMARK`.
- Current Datacenter execution does not use that planner to skip or narrow
  stages.

Component role distinction for later contract work:

```text
DATA_COMPONENT
  Stage 1-4 canonical dc_* materializations

DERIVED_DATA_COMPONENT
  Stage 5-9 field-level derived dc_* materializations

VALIDATION_COMPONENT
  Stage 10 pipeline audit

REPORT_CONTEXT_COMPONENT
  Stage 11 automatic technical relevance

ARTIFACT_COMPONENT
  Stage 12-15 reports

COPY_COMPONENT
  Stage 16 Windows copy
```

Current watermark rows use component names, but do not explicitly encode this
role distinction.

## Stage 2 Pilot-Relevant Findings

Evidence status: `CONFIRMED_FROM_CODE` unless marked otherwise.

- Stage 2 is currently always invoked with the pipeline `start_date` through
  `signal_date`.
- Current scheduler configuration passes `start_date=2025-08-01`.
- Stage 2 writes per-date rows with `replace-date`; this is compatible with an
  overlap output range model.
- Stage 2 already separates effective price-history input from selected output
  dates in range mode through `load_bounded_ticker_ohlcv_history_window`.
- Stage 2 warmup is currently expressed as `max_valid_price_rows=220`, i.e. up
  to 220 valid price rows per ticker.
- Stage 2's direct downstream materialization consumers are Stage 3 and Stage 9.
- Stage 9 also consumes Stage 7 group timing state, so Stage 2 dirty propagation
  reaches Stage 9 both directly and through Stage 3 -> Stage 7.
- Stage 2's indirect downstream consumers include audit, technical relevance,
  reports, and EC ticker facts.
- EC impact cannot be reasoned about only as one source table to one target
  table: the four canonical EC target tables combine materialized fields from
  multiple Datacenter stages.
- There is no persistent materialized-output evidence table today.
- There is no persistent EC sync pending queue today.
- EC refresh/backfill can already perform date-based replace loads, but the
  normal scheduler refresh does not consume a range of successfully materialized
  Datacenter outputs.

## Open Verification Items

- Quantify the minimal safe trading-day warmup for Stage 2 beyond the existing
  `max_valid_price_rows=220` implementation detail.
- Verify whether Stage 6 structure/BOS/RESET can be narrowed safely with a
  warmup/state replay range, or whether it currently requires full history for
  correctness.
- Quantify Stage 7 timing-state lookback/state dependency.
- Quantify Stage 8 overheat lookback/state dependency.
- Confirm exact transaction boundaries in Stage 4-8 range update functions
  before designing partial failure recovery.
- Decide whether Stage 1 can ever be safely incremental; current code and
  planner treat it conservatively as full range from `index_base_date`.
- Define which Datacenter outputs are canonical sources for EC in the target
  contract and which are reports/artifacts only.

## Not Covered Here

This document intentionally does not define:

- Target schema for `dc_materialized_output` or `ec_sync_pending`.
- Incremental planner algorithm.
- EC sync contract requirements.
- Implementation phases.
- Test plan.

Those belong in the later `Datacenter Incremental Execution and EC Sync
Contract` and implementation plan documents.
