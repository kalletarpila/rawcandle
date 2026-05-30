# Datacenter Report Canonical V2 Architecture: Daily, Rolling2, Rolling5, and Rolling30

## 1. Purpose

This document defines the final pre-schema Report Canonical V2 architecture for these in-scope reports:

- `daily`
- `rolling2`
- `rolling5`
- `rolling30`

Its purpose is to make all four reports formatter-only outputs over explicit canonical database tables.

The intended result is:

- all report-relevant calculations move into canonical DB tables
- all report classifications move into canonical DB tables
- renderers stay limited to sorting, grouping, headings, display formatting, and Markdown/CSV output
- Markdown/CSV report text is never treated as an upstream input path

Dashboard is explicitly out of scope.

## 2. Scope

This spec is limited to the current report formation paths rooted in:

- `analysis/datacenter_indices/swing_daily_report.py`
- `analysis/datacenter_indices/swing_weekly_report.py`
- `analysis/datacenter_indices/rolling2_sell_pressure_classifier.py`
- `analysis/datacenter_indices/rolling5_pullback_classifier.py`
- `analysis/datacenter_indices/rolling30_watchlist_classifier.py`

This document does not cover:

- dashboard code
- dashboard decision logic
- dashboard enrichment, fallback, or reference logic
- scheduler behavior
- runtime implementation details

This is a correction/finalization document only. It does not define a new architecture direction beyond the existing Report Canonical V2 direction.

## 3. Current Lineage Summary

### Daily

Current daily lineage starts from:

- `load_daily_swing_report_data(...)`
- `build_markdown_daily_swing_report(...)`
- `build_csv_daily_swing_report(...)`

Daily currently reads:

- `dc_group_swing_signal_daily`
- `dc_ticker_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`

Daily currently performs inside the report path:

- taxonomy-version resolution when not explicit
- watchlist membership attachment
- current watchlist status derivation
- layer/subindustry context joins
- layer/subindustry context-risk derivation
- daily trigger classification
- daily-specific ranking and section selection

### Rolling2

Current rolling2 lineage flows through the shared weekly framework:

- `load_weekly_swing_report_data(...)` with `window_size = 2`
- `build_markdown_weekly_swing_report(...)`
- `build_csv_weekly_swing_report(...)`
- `_build_rolling_2_sell_pressure_rows(...)`

Rolling2 classifier helper lineage:

- file: `analysis/datacenter_indices/rolling2_sell_pressure_classifier.py`
- class: `Rolling2SellPressureClassification`
- function: `classify_rolling_2_sell_pressure_row(...)`

Rolling2 currently performs inside the report path:

- valid signal-date selection for the 2-day window
- rolling window aggregation
- current and window watchlist status derivation
- rolling2 sell-pressure classification
- rolling2-specific section ordering

### Rolling5

Current rolling5 lineage flows through the shared weekly framework:

- `load_weekly_swing_report_data(...)` with `window_size = 5`
- `build_markdown_weekly_swing_report(...)`
- `build_csv_weekly_swing_report(...)`
- `_build_rolling_5_pullback_rows(...)`

Rolling5 classifier helper lineage:

- file: `analysis/datacenter_indices/rolling5_pullback_classifier.py`
- class: `Rolling5PullbackClassification`
- function: `classify_rolling_5_pullback_row(...)`

Rolling5 currently performs inside the report path:

- valid signal-date selection for the 5-day window
- rolling window aggregation
- current and window watchlist status derivation
- rolling5 pullback classification
- rolling5-specific section ordering

### Rolling30

Current rolling30 lineage flows through the shared weekly framework:

- `load_weekly_swing_report_data(...)` with `window_size = 30`
- `build_markdown_weekly_swing_report(...)`
- `build_csv_weekly_swing_report(...)`
- `_build_rolling_30_role_rows(...)`
- `build_rolling_30_role_rows_from_base_rows(...)`

Rolling30 classifier helper lineage:

- file: `analysis/datacenter_indices/rolling30_watchlist_classifier.py`
- classes:
  - `Rolling30BuyClassification`
  - `Rolling30ExitClassification`
- functions:
  - `classify_rolling_30_buy_row(...)`
  - `classify_rolling_30_exit_row(...)`
  - `build_rolling_30_role_rows_from_base_rows(...)`

Rolling30 currently performs inside the report path:

- valid signal-date selection for the 30-day window
- rolling window aggregation
- repeated signal counting
- current and window watchlist status derivation
- group current/window status derivation
- group status change derivation
- rolling30 buy classification
- rolling30 exit classification
- rolling30-specific section ordering

## 4. Source Tables

### dc_ticker_swing_signal_daily

Role:
Ticker-level raw source input for all four report horizons.

Expected grain:
`signal_date, taxonomy_version, ticker`

Relevant field families:

- ticker identity
- signal date
- taxonomy version
- signal version
- primary layer / primary subindustry
- breakout, pullback, and exit signal flags
- exit severity / exit reason
- return fields
- EMA-distance fields
- ticker trend / structure / BOS / reset fields
- price-data readiness fields
- bullish / bearish supporting signal fields if present

### dc_group_swing_signal_daily

Role:
Group timing and overheat source for ecosystem, layer, and subindustry report context.

Expected grain:
`signal_date, taxonomy_version, group_type, group_name`

Relevant field families:

- group identity
- timing state
- overheat risk level
- return fields
- breadth / participation fields
- data quality fields

### dc_group_synthetic_ohlc_daily

Role:
Synthetic group structure source for layer and subindustry report context.

Expected grain:
`ohlc_date, taxonomy_version, group_type, group_name`

Relevant field families:

- synthetic close / OHLC
- synthetic EMA-distance fields
- synthetic trend classification
- synthetic latest structure label
- synthetic BOS fields
- synthetic reset fields
- synthetic freshness fields
- synthetic data quality fields

### Auxiliary Inputs

Auxiliary report-relevant inputs that remain in scope:

- watchlist file membership
- MA helper history inputs
- signal freshness helper history inputs
- technical relevance rows if any report horizon still exposes them

## 5. Target Architecture

Target flow:

Raw/source DB tables  
→ canonical report context tables  
→ canonical report classification table  
→ `daily` / `rolling2` / `rolling5` / `rolling30` formatters

Rules:

- canonical context tables are the only source of report input truth
- canonical classification rows are the only source of report classification truth
- report rendering must not rebuild rolling windows
- report rendering must not derive current or window watchlist status
- report rendering must not derive group risk state
- report rendering must not derive daily trigger state
- report rendering must not derive rolling2 sell-pressure state
- report rendering must not derive rolling5 pullback state
- report rendering must not derive rolling30 buy or exit state
- Markdown and CSV are final outputs only

## 6. Canonical Table Set

The minimum report-canonical V2 table set for `daily`, `rolling2`, `rolling5`, and `rolling30` is:

- `dc_report_run_v2`
- `dc_report_context_group_v2`
- `dc_report_context_daily_v2`
- `dc_report_context_window_v2`
- `dc_report_classification_v2`

### dc_report_run_v2

Purpose:
One report-canonical calculation run record.

Grain:
`run_id`

Must contain:

- run identity
- signal date
- taxonomy version
- market if available
- calculation version
- source version metadata if available
- created timestamp
- status
- warning count
- error count
- notes

Used by:

- daily
- rolling2
- rolling5
- rolling30

### dc_report_context_group_v2

Purpose:
Canonical group context consumed by daily and all rolling horizons.

Grain:
`signal_date, taxonomy_version, horizon, group_type, group_name`

Allowed horizon values:

- `daily`
- `rolling2`
- `rolling5`
- `rolling30`

Rules:

- for `daily`, window fields may be nullable
- for rolling horizons, this table must be horizon-aware and carry window-state fields directly

Must contain:

- group identity
- parent group identity where relevant
- timing state
- overheat risk level
- return fields used in report sections
- breadth fields used in report sections
- synthetic close
- synthetic EMA-distance fields
- synthetic trend classification
- synthetic latest structure label
- synthetic BOS fields
- synthetic reset fields
- synthetic freshness fields
- explicit group context risk status
- explicit group context readiness status
- `group_current_status`
- `group_window_status`
- `group_status_change`
- `window_start_date`
- `window_end_date`
- `valid_signal_dates`

Used by:

- daily ticker context joining
- daily synthetic/group sections
- rolling2 end-of-window group context
- rolling5 end-of-window group context
- rolling30 end-of-window group context
- rolling taxonomy-listing generation for all rolling horizons

### dc_report_context_daily_v2

Purpose:
Canonical ticker-level single-date context for rebuilding the daily report.

Grain:
`signal_date, taxonomy_version, ticker`

Must contain:

- ticker identity
- signal date
- taxonomy version
- market if available
- layer / subindustry membership
- ecosystem membership
- watchlist membership
- current watchlist status
- source breakout/pullback/exit fields
- exit severity and latest exit reason
- return fields used by daily sections
- EMA-distance fields used by daily sections
- MA break status
- freshness status
- technical relevance fields if retained
- trend / structure / BOS / reset fields
- layer timing / overheat fields
- subindustry timing / overheat fields
- layer context risk status
- subindustry context risk status
- daily context readiness status

Used by:

- daily watchlist sections
- daily breakout/pullback/exit sections
- daily trigger classification input
- daily taxonomy listing

### dc_report_context_window_v2

Purpose:
Canonical ticker-level rolling-window context for rebuilding rolling2, rolling5, and rolling30 reports.

Grain:
`signal_date, taxonomy_version, ticker, horizon`

Allowed horizon values:

- `rolling2`
- `rolling5`
- `rolling30`

Must contain:

- ticker identity
- report end date as canonical signal date
- taxonomy version
- market if available
- horizon
- window start date
- window end date
- valid trading day count
- ecosystem membership
- watchlist membership
- current watchlist status
- window watchlist status
- breakout day count
- pullback day count
- fast EMA10 pullback day count
- conservative EMA20 pullback day count
- exit risk day count
- high exit risk day count
- medium exit risk day count
- first signal date
- last signal date
- latest exit reason
- layer timing / overheat snapshot
- subindustry timing / overheat snapshot
- layer context risk status
- subindustry context risk status
- last ticker trend / structure / BOS / reset snapshot
- MA break status
- freshness status
- window context readiness status

The same window-context table must carry the horizon-specific aggregated fields needed for:

- rolling2 sell-pressure input
- rolling5 pullback input
- rolling30 buy input
- rolling30 exit input

### dc_report_classification_v2

Purpose:
Canonical report-only classification outputs.

Grain:
`signal_date, taxonomy_version, ticker, horizon, classification_type`

Allowed horizon values:

- `daily`
- `rolling2`
- `rolling5`
- `rolling30`

Allowed `classification_type` values:

- `daily_trigger`
- `rolling2_sell_pressure`
- `rolling5_pullback`
- `rolling30_buy`
- `rolling30_exit`

This table must use generic classification columns:

- `classification_state`
- `primary_reason`
- `blocking_reason` nullable
- `risk_reason` nullable
- `next_action` nullable
- `classification_status`
- `classification_version`
- `run_id`
- `created_at_utc`

Rules:

- daily trigger output is one row per ticker with `horizon = 'daily'` and `classification_type = 'daily_trigger'`
- rolling2 output is one row per ticker with `horizon = 'rolling2'` and `classification_type = 'rolling2_sell_pressure'`
- rolling5 output is one row per ticker with `horizon = 'rolling5'` and `classification_type = 'rolling5_pullback'`
- rolling30 buy output is one row per ticker with `horizon = 'rolling30'` and `classification_type = 'rolling30_buy'`
- rolling30 exit output is one row per ticker with `horizon = 'rolling30'` and `classification_type = 'rolling30_exit'`

This table must not assume one row that simultaneously contains both rolling30 buy and rolling30 exit fields.

## 7. Daily Contract

Current report loader path:

- `load_daily_swing_report_data(...)`

Shared report framework:

- daily-specific file `analysis/datacenter_indices/swing_daily_report.py`

Current classifier helper lineage:

- `_classify_daily_trigger_row(...)`
- `_build_daily_trigger_rows(...)`

To rebuild `daily` as a formatter-only report, V2 must provide these field classes.

### Source-formatted fields

- ticker identity
- signal date
- taxonomy version
- primary layer / primary subindustry
- breakout / pullback / exit fields
- exit severity / latest exit reason
- return fields
- EMA-distance fields
- trend / structure / BOS / reset fields

### Canonical derived context

- ecosystem membership
- watchlist membership
- current watchlist status
- layer timing state
- layer overheat risk
- layer context risk
- subindustry timing state
- subindustry overheat risk
- subindustry context risk
- MA break status
- freshness status
- technical relevance fields if retained

### Classifier output

- `classification_type = 'daily_trigger'`
- `classification_state = daily_trigger_state`
- `primary_reason`
- `blocking_reason`
- `next_action`

### Formatter-only behavior

- top-N selection
- section grouping
- section headings
- table rendering
- deterministic sorting inside sections
- metadata line formatting

## 8. Rolling2 Contract

Current report loader path:

- `load_weekly_swing_report_data(...)` with `window_size = 2`

Shared weekly report framework:

- `build_markdown_weekly_swing_report(...)`
- `build_csv_weekly_swing_report(...)`
- `_build_rolling_2_sell_pressure_rows(...)`

Rolling2 classifier helper lineage:

- file: `analysis/datacenter_indices/rolling2_sell_pressure_classifier.py`
- class: `Rolling2SellPressureClassification`
- function: `classify_rolling_2_sell_pressure_row(...)`

To rebuild `rolling2` as a formatter-only report, V2 must provide these field classes.

### Source-formatted fields

- ticker identity
- taxonomy version
- primary layer / primary subindustry
- last-row exit severity / latest exit reason
- last-row trend / structure / BOS / reset snapshot
- source group timing / overheat rows

### Canonical derived window context

- horizon `rolling2`
- window start date
- window end date
- valid trading day count
- ecosystem membership
- watchlist membership
- current watchlist status
- window watchlist status
- exit risk day count
- high exit risk day count
- medium exit risk day count
- first signal date
- last signal date
- layer timing / overheat snapshot
- subindustry timing / overheat snapshot
- layer context risk
- subindustry context risk
- MA break status if retained in rolling output
- freshness status if retained in rolling output

### Classifier output

- `classification_type = 'rolling2_sell_pressure'`
- `classification_state = rolling_2_sell_pressure_state`
- `primary_reason`
- `risk_reason`
- `next_action`

### Formatter-only behavior

- ordering inside rolling2 sell-pressure section
- headings
- section grouping
- Markdown/CSV rendering
- incomplete-window banner

## 9. Rolling5 Contract

Current report loader path:

- `load_weekly_swing_report_data(...)` with `window_size = 5`

Shared weekly report framework:

- `build_markdown_weekly_swing_report(...)`
- `build_csv_weekly_swing_report(...)`
- `_build_rolling_5_pullback_rows(...)`

Rolling5 classifier helper lineage:

- file: `analysis/datacenter_indices/rolling5_pullback_classifier.py`
- class: `Rolling5PullbackClassification`
- function: `classify_rolling_5_pullback_row(...)`

To rebuild `rolling5` as a formatter-only report, V2 must provide these field classes.

### Source-formatted fields

- ticker identity
- taxonomy version
- primary layer / primary subindustry
- last-row exit severity / latest exit reason
- last-row trend / structure / BOS / reset snapshot
- source group timing / overheat rows

### Canonical derived window context

- horizon `rolling5`
- window start date
- window end date
- valid trading day count
- ecosystem membership
- watchlist membership
- current watchlist status
- window watchlist status
- breakout day count
- pullback day count
- fast EMA10 pullback day count
- conservative EMA20 pullback day count
- exit risk day count
- high exit risk status if present through current/window status
- first signal date
- last signal date
- layer timing / overheat snapshot
- subindustry timing / overheat snapshot
- layer context risk
- subindustry context risk
- MA break status if retained in rolling output
- freshness status if retained in rolling output

### Classifier output

- `classification_type = 'rolling5_pullback'`
- `classification_state = rolling_5_pullback_state`
- `primary_reason`
- `blocking_reason`
- `next_action`

### Formatter-only behavior

- ordering inside rolling5 pullback section
- headings
- section grouping
- Markdown/CSV rendering
- incomplete-window banner

## 10. Rolling30 Contract

Current report loader path:

- `load_weekly_swing_report_data(...)` with `window_size = 30`

Shared weekly report framework:

- `build_markdown_weekly_swing_report(...)`
- `build_csv_weekly_swing_report(...)`
- `_build_rolling_30_role_rows(...)`
- `build_rolling_30_role_rows_from_base_rows(...)`

Rolling30 classifier helper lineage:

- file: `analysis/datacenter_indices/rolling30_watchlist_classifier.py`
- classes:
  - `Rolling30BuyClassification`
  - `Rolling30ExitClassification`
- functions:
  - `classify_rolling_30_buy_row(...)`
  - `classify_rolling_30_exit_row(...)`
  - `build_rolling_30_role_rows_from_base_rows(...)`

To rebuild `rolling30` as a formatter-only report, V2 must provide these field classes.

### Source-formatted fields

- ticker identity
- taxonomy version
- primary layer / primary subindustry
- last-row exit severity / latest exit reason
- last-row trend / structure / BOS / reset snapshot
- source group timing / overheat rows
- source synthetic group rows

### Canonical derived window context

- horizon `rolling30`
- window start date
- window end date
- valid trading day count
- ecosystem membership
- watchlist membership
- current watchlist status
- window watchlist status
- breakout day count
- pullback day count
- fast EMA10 pullback day count
- conservative EMA20 pullback day count
- exit risk day count
- high exit risk day count
- medium exit risk day count
- first signal date
- last signal date
- layer timing / overheat snapshot
- subindustry timing / overheat snapshot
- layer context risk
- subindustry context risk
- MA break status
- freshness status

### Classifier output

- `classification_type = 'rolling30_buy'`
- `classification_state = rolling_30_buy_state`
- `primary_reason`
- `blocking_reason`

- `classification_type = 'rolling30_exit'`
- `classification_state = rolling_30_exit_state`
- `primary_reason`
- `risk_reason`

### Formatter-only behavior

- ordering of repeated breakout rows
- ordering of repeated pullback rows
- ordering of repeated exit-risk rows
- ordering of rolling30 buy rows
- ordering of rolling30 exit rows
- headings
- section grouping
- Markdown/CSV rendering
- incomplete-window banner

## 11. Shared Explicit Signals

The following signals are currently implicit or reconstructed and should become explicit canonical fields if used by daily or rolling classification:

- `close_below_ema20_flag`
- `close_below_ema50_flag`
- `return_10d_lt_minus_8pct_flag`
- `double_bos_down_flag`
- `double_bos_up_flag`
- `fresh_bos_flag`
- `fresh_reset_flag`
- `stale_structure_flag`
- `layer_overheat_risk_flag`
- `subindustry_overheat_risk_flag`
- `severe_exit_risk_flag`

Placement guidance:

- daily-only trigger inputs belong in `dc_report_context_daily_v2`
- rolling2, rolling5, and rolling30 window-sensitive inputs belong in `dc_report_context_window_v2`
- group-level risk/structure state belongs in `dc_report_context_group_v2`

## 12. Current-to-V2 Field Mapping

| Current concept / field | Current location | Current source type | V2 target table | V2 target field | Applies to | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| ticker | `dc_ticker_swing_signal_daily`, report rows | raw source | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `ticker` | all | canonical ticker identity |
| signal_date | loader input, source rows | raw source / derived report date | all context tables | `signal_date` | all | rolling horizons use window end date as canonical report date |
| taxonomy_version | source tables, loader resolution | raw source / inferred selection | all context tables | `taxonomy_version` | all | explicit or inferred upstream |
| market | not explicit in inspected report paths | unresolved source | all context tables | `market` | all | still open before migration |
| primary_layer | `dc_ticker_swing_signal_daily.primary_layer` | raw source | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `primary_layer` | all | |
| primary_subindustry | `dc_ticker_swing_signal_daily.primary_subindustry` | raw source | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `primary_subindustry` | all | |
| ecosystem membership | report-built watchlist/taxonomy rows | derived context | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `in_datacenter_ecosystem` | all | should be explicit in V2 |
| watchlist membership | watchlist file | auxiliary input | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `is_watchlist` | all | explicit membership flag |
| current_watchlist_status | daily/weekly report helpers | derived context | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `current_watchlist_status` | all | must not remain renderer-derived |
| window_watchlist_status | weekly report helpers | derived window context | `dc_report_context_window_v2` | `window_watchlist_status` | rolling2, rolling5, rolling30 | |
| breakout_days | weekly report aggregation | derived window context | `dc_report_context_window_v2` | `breakout_days` | rolling5, rolling30 | present if horizon uses it |
| pullback_days | weekly report aggregation | derived window context | `dc_report_context_window_v2` | `pullback_days` | rolling5, rolling30 | present if horizon uses it |
| fast_ema10_pullback_days | weekly report aggregation | derived window context | `dc_report_context_window_v2` | `fast_ema10_pullback_days` | rolling5, rolling30 | |
| conservative_ema20_pullback_days | weekly report aggregation | derived window context | `dc_report_context_window_v2` | `conservative_ema20_pullback_days` | rolling5, rolling30 | |
| exit_risk_days | weekly report aggregation | derived window context | `dc_report_context_window_v2` | `exit_risk_days` | rolling2, rolling5, rolling30 | |
| high_exit_risk_days | weekly report aggregation | derived window context | `dc_report_context_window_v2` | `high_exit_risk_days` | rolling2, rolling30 | |
| medium_exit_risk_days | weekly report aggregation | derived window context | `dc_report_context_window_v2` | `medium_exit_risk_days` | rolling2, rolling30 | |
| first_signal_date | weekly report aggregation | derived window context | `dc_report_context_window_v2` | `first_signal_date` | rolling2, rolling5, rolling30 | |
| last_signal_date | weekly report aggregation | derived window context | `dc_report_context_window_v2` | `last_signal_date` | rolling2, rolling5, rolling30 | |
| latest_exit_reason | `exit_reason` / last window snapshot | raw source normalized to window end | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `latest_exit_reason` | all | daily from same-day row, rolling from last row |
| trend_state | `ticker_trend_state` | raw source / window-end snapshot | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `trend_state` | all | |
| latest_structure_label | ticker / synthetic rows | raw source / snapshot | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2` | `latest_structure_label`, `synthetic_latest_structure_label` | all | ticker and group flavors both required |
| latest_bos_event_type | ticker / synthetic rows | raw source / snapshot | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2` | `latest_bos_event_type`, `synthetic_latest_bos_event_type` | all | |
| latest_bos_freshness | ticker / synthetic rows | raw source / snapshot | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2` | `latest_bos_freshness`, `synthetic_latest_bos_freshness` | all | |
| latest_reset_reason | ticker / synthetic rows | raw source / snapshot | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2` | `latest_reset_reason`, `synthetic_latest_reset_reason` | all | |
| latest_reset_freshness | ticker / synthetic rows | raw source / snapshot | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2` | `latest_reset_freshness`, `synthetic_latest_reset_freshness` | all | |
| layer timing state | group rows joined by layer | derived context join | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2` | `layer_timing_state` or `timing_state` | all | group table remains canonical source |
| layer overheat risk | group rows joined by layer | derived context join | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2` | `layer_overheat_risk_level` or `overheat_risk_level` | all | |
| layer context risk | daily/weekly report helpers | derived context | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `layer_context_risk_status` | all | explicit derived enum/flag |
| subindustry timing state | group rows joined by subindustry | derived context join | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2` | `subindustry_timing_state` or `timing_state` | all | |
| subindustry overheat risk | group rows joined by subindustry | derived context join | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2` | `subindustry_overheat_risk_level` or `overheat_risk_level` | all | |
| subindustry context risk | daily/weekly report helpers | derived context | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `subindustry_context_risk_status` | all | explicit derived enum/flag |
| group_current_status | rolling taxonomy listing | derived group window context | `dc_report_context_group_v2` | `group_current_status` | rolling2, rolling5, rolling30 | now resolved into horizon-aware group table |
| group_window_status | rolling taxonomy listing | derived group window context | `dc_report_context_group_v2` | `group_window_status` | rolling2, rolling5, rolling30 | |
| group_status_change | rolling taxonomy listing | derived group window context | `dc_report_context_group_v2` | `group_status_change` | rolling2, rolling5, rolling30 | |
| daily_trigger_state | daily trigger builder | classifier output | `dc_report_classification_v2` | `classification_state` | daily | `classification_type = 'daily_trigger'` |
| rolling_2_sell_pressure_state | rolling2 classifier | classifier output | `dc_report_classification_v2` | `classification_state` | rolling2 | `classification_type = 'rolling2_sell_pressure'` |
| rolling_5_pullback_state | rolling5 classifier | classifier output | `dc_report_classification_v2` | `classification_state` | rolling5 | `classification_type = 'rolling5_pullback'` |
| rolling_30_buy_state | rolling30 buy classifier | classifier output | `dc_report_classification_v2` | `classification_state` | rolling30 | `classification_type = 'rolling30_buy'` |
| rolling_30_exit_state | rolling30 exit classifier | classifier output | `dc_report_classification_v2` | `classification_state` | rolling30 | `classification_type = 'rolling30_exit'` |
| primary_reason | daily/rolling classifiers | classifier output | `dc_report_classification_v2` | `primary_reason` | all | generic column |
| blocking_reason | daily, rolling5, rolling30 buy classifiers | classifier output | `dc_report_classification_v2` | `blocking_reason` | daily, rolling5, rolling30 | nullable generic column |
| risk_reason | rolling2 and rolling30 exit classifiers | classifier output | `dc_report_classification_v2` | `risk_reason` | rolling2, rolling30 | nullable generic column |
| next_action | daily, rolling2, rolling5 classifiers | classifier output | `dc_report_classification_v2` | `next_action` | daily, rolling2, rolling5 | nullable generic column |
| ma_break_status | MA helper rows | derived helper output | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `ma_break_status` | all | report-visible support field |
| freshness_status | freshness helper rows | derived helper output | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `freshness_status` | all | report-visible support field |
| technical relevance status | optional technical relevance enrichment | optional late-derived context | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `technical_relevance_status` and companion fields | daily, rolling30, possibly rolling2/rolling5 if exposed | optional and still open |

## 13. Formatter-Only Contract

Future `daily`, `rolling2`, `rolling5`, and `rolling30` renderers may still do:

- sorting
- top-N selection
- section grouping
- headings
- display formatting
- Markdown rendering
- CSV rendering
- deterministic label rendering from canonical enums

Future `daily`, `rolling2`, `rolling5`, and `rolling30` renderers must not do:

- daily trigger classification
- rolling2 sell-pressure classification
- rolling5 pullback classification
- rolling30 buy classification
- rolling30 exit classification
- rolling window aggregation
- current status inference
- window status inference
- group risk inference
- report-to-report reconstruction
- Markdown/CSV parser reconstruction
- hidden text-token classification

## 14. Open Items

The remaining open items that still matter before implementation are:

- `market` is not explicitly sourced in the inspected report paths
- technical relevance is optional and currently injected late
- exact SQL column names and SQL types will be finalized in `DB-V2-03`

## 15. Next Step Boundary

The next step must be exactly:

`DB-V2-03 — Add SQL migration and schema tests for report-canonical V2 tables only.`

DB-V2-03 must not add:

- builders
- CLIs
- report-renderer changes
- scheduler changes
- dashboard changes
- data backfill
- DB writes outside migration tests
