# Datacenter Swing Signal Implementation Plan

## Purpose

This document defines the current backend data-source contracts for the planned datacenter swing signal extension.

This step does not implement swing signal calculation. Its purpose is to make the current boundaries explicit so later implementation can stay small, auditable, deterministic, and no-lookahead safe.

## Current Data Sources

### Datacenter taxonomy

- Taxonomy CSV loading and validation lives in `analysis/datacenter_indices/taxonomy.py`.
- The current contract is `load_datacenter_taxonomy_csv(...)`.
- Required CSV columns are:
  - `taxonomy_version`
  - `ticker`
  - `layer`
  - `subindustry`
  - `report_group_status`
  - `is_primary`
  - `role_weight`
  - `notes`

### Datacenter index calculation

- Group index calculation logic lives in `analysis/datacenter_indices/calculator.py`.
- Current persistence/orchestration lives in `analysis/datacenter_indices/persistence.py`.
- CLI entrypoint lives in `run_datacenter_indices.py`.
- Existing datacenter index logic already reads:
  - taxonomy rows from the taxonomy CSV
  - ticker close history from `osakedata.db`
  - persisted group index rows from `analysis.db`

### Datacenter index report generation

- Report loading and export logic lives in `analysis/datacenter_indices/reporting.py`.
- CLI entrypoint lives in `run_datacenter_index_report.py`.
- Reports currently read persisted rows from `dc_group_index_daily` in `analysis.db`.
- Optional ticker-level performance sections also read price history from `osakedata.db` and membership rows from the taxonomy CSV.

### OHLCV price data access

- The current market/price database access layer is centered on `market_repository.py`.
- The current `osakedata` table contract is maintained by `ensure_market_schema(...)`.
- `osakedata` contains:
  - `osake`
  - `pvm`
  - `open`
  - `high`
  - `low`
  - `close`
  - `volume`
  - `market`
- Current datacenter index logic uses direct SQLite reads in `analysis/datacenter_indices/persistence.py` and `analysis/datacenter_indices/reporting.py`.

### analysis.db access

- The main analysis database initializer is `analysis/database_manager.py`.
- Current datacenter analysis tables already include:
  - `dc_ecosystem_membership`
  - `dc_group_index_daily`
- Current ticker-level technical analysis outputs are already persisted into `analysis.db` through existing analysis flows.

## Existing Reusable analysis.db Layers

### Ticker-level Dow structure layer

- Current computation and persistence live in `analysis/stock_dow_structure.py`.
- Persisted table:
  - `stock_dow_structure_events`
- Supporting status table:
  - `stock_dow_structure_status`
- Important current fields for future read-side use include:
  - `ticker`
  - `market`
  - `event_date`
  - `confirmed_as_of_date`
  - `event_type`
  - `trend_state`
  - `dow_label_high`
  - `dow_label_low`
  - `structure_epoch_id`
  - `structure_epoch_start_date`

### Ticker-level divergence layer

- Current recompute/read-side usage exists in `analysis/divergence_recompute.py` and `analysis/run_analysis.py`.
- Main table schema is initialized in `analysis/database_manager.py`.
- Persisted table:
  - `divergence_data`
- Important current fields for future read-side use include:
  - `ticker`
  - `date`
  - `bullish_strength`
  - `bearish_strength`
  - `hidden_bullish_strength`
  - `hidden_bearish_strength`
  - `rsi`
  - `is_bullish_divergence_r3`
  - `is_bearish_divergence_r3`
  - `is_hidden_bullish_divergence_r3`
  - `is_hidden_bearish_divergence_r3`
  - `pivot2_date_r3`

### Ticker-level candlestick pattern layer

- Current candle pattern detection logic lives in `analysis/candlestick_patterns.py`.
- The shared candle analysis flow lives in `analysis/run_analysis.py`.
- Main persisted findings table schema is initialized in `analysis/database_manager.py`.
- Persisted table:
  - `analysis_findings`
- Important current fields for future read-side use include:
  - `ticker`
  - `date`
  - `pattern`
  - `signal_strength`
  - `rsi14`

### Existing datacenter membership and index layer

- Membership table:
  - `dc_ecosystem_membership`
- Existing group index table:
  - `dc_group_index_daily`
- These remain the current datacenter aggregation layer and must not be changed semantically by the swing extension.

## What the Datacenter Swing Layer Should Calculate Itself

The datacenter swing layer should calculate only new group-level artifacts that do not already exist as ticker-level technical analysis outputs.

Planned examples:

- swing-oriented datacenter persistence tables
- ticker technical metric snapshots used only as normalized group inputs
- group breadth metrics
- synthetic group OHLC
- clamped synthetic OHLC integrity rules
- rolling-base relative OHLC20 series
- group timing states
- ticker scanner signals that combine existing ticker outputs with new group state
- daily and weekly datacenter swing reports

Synthetic group OHLC is a new group-level layer and is separate from ticker-level OHLC analysis.

## What the Datacenter Swing Layer Should Only Read From analysis.db

The datacenter swing layer must read existing ticker-level technical outputs from `analysis.db` and must not recalculate them.

This includes:

- ticker-level Dow structure state and events from `stock_dow_structure_events`
- ticker-level divergence outputs from `divergence_data`
- ticker-level candlestick findings from `analysis_findings`

Ticker-level Dow, candle, and divergence logic must not be duplicated in the datacenter swing layer.

The current architectural assumption is explicit:

- `analysis.db` already contains ticker-level technical analysis outputs such as candles, divergences, and Dow structures
- the datacenter swing layer must not recalculate those ticker-level technical analysis signals
- the datacenter swing layer should later read those existing results through explicit reader contracts

## No-Lookahead Requirements

All future datacenter swing calculations must be deterministic and no-lookahead safe.

Required safeguards:

- group calculations for an `as_of_date` must only use source rows known on or before that `as_of_date`
- future implementations reading Dow structures must enforce `confirmed_as_of_date <= as_of_date`
- future implementations reading divergence or candle outputs must only read rows with event dates on or before `as_of_date`
- no forward-fill for exact `as_of_date` signal rows
- historical group calculations must use the relevant `taxonomy_version`, not only the current taxonomy state

The swing layer must preserve the distinction between:

- current taxonomy state used for current reporting
- historical taxonomy version used for historical backfills or historical signal reproduction

## Backend Safeguards

Future synthetic group OHLC generation must clamp impossible candles after aggregation:

- `synthetic_high = max(synthetic_high, synthetic_open, synthetic_close)`
- `synthetic_low = min(synthetic_low, synthetic_open, synthetic_close)`

Future EMA-based timing or state logic should include sufficient warmup before production signal persistence.

Recommended rule:

- require an explicit EMA warmup period before writing production-grade swing states or signals

Exact daily signal rows must not use forward-filled values from later dates.

## Proposed First Implementation Phases

1. Inventory and reader contracts
2. New DB migrations for swing tables
3. Ticker technical metrics
4. `analysis.db` enrichment readers
5. Group swing metrics and breadth
6. Synthetic OHLC and clamp
7. Rolling-base relative OHLC20
8. Group timing states
9. Ticker scanner signals
10. Daily signal report CLI
11. Weekly report separation

## Proposed Future Reader Contracts

This repository does not currently expose a clear shared reader/port abstraction layer for these sources, so this step does not add placeholder code stubs.

If a dedicated read-side module is introduced later, it should define narrow contracts for:

- `DowStructureReader`
  - read ticker Dow events as of `as_of_date`
  - enforce `confirmed_as_of_date <= as_of_date`
- `DivergenceSignalReader`
  - read divergence rows by ticker and `as_of_date`
  - expose only persisted divergence outputs, not recomputation
- `CandlePatternReader`
  - read persisted candlestick findings by ticker and `as_of_date`
  - expose only persisted findings rows from `analysis_findings`

These contracts should remain read-only and must not embed new calculation semantics.
