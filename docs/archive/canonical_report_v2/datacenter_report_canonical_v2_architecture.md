# Datacenter Report Canonical V2 Architecture

## 1. Purpose

Datacenter Report Canonical V2 exists to make `daily`, `rolling2`, `rolling5`, and `rolling30` reports formatter-only outputs over explicit canonical database tables.

Its purpose is to:

- move all report-relevant calculations into explicit canonical DB tables
- remove hidden report-local classification and rolling-window aggregation
- avoid Markdown/CSV report parsing as an input path
- keep reports as downstream renderers of canonical context and classification data
- allow a parallel rollout beside the current reporting system until parity is proven

## 2. Current Problem Summary

DB-V2-01 showed that the current reporting path does not yet have one canonical report data model.

Current lineage starts from:

- `daily`: `analysis/datacenter_indices/swing_daily_report.py`
- `rolling2`, `rolling5`, `rolling30`: `analysis/datacenter_indices/swing_weekly_report.py`

Current report code reads these source tables directly:

- `dc_ticker_swing_signal_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`

In the current design:

- some fields are formatted directly from DB values
- some fields are calculated, aggregated, classified, or interpreted inside report code
- group context and group-aware status logic are duplicated or reconstructed across daily and rolling paths
- rolling reports build window context inside report generation instead of reading a canonical window-context table

As a result, report behavior is split across raw source reads, report-local aggregation, report-local classification, and report-local helper composition instead of a single canonical reporting layer.

## 3. Target Architecture

The target Report Canonical V2 flow is:

Raw/source DB tables  
→ V2 canonical report context tables  
→ V2 report output/classification tables  
→ `daily` / `rolling2` / `rolling5` / `rolling30` Markdown/CSV reports

Architecture rules:

- canonical context tables are the source of report input truth
- report output/classification tables are the source of report classification truth
- reports are downstream formatters only
- Markdown/CSV reports are outputs, not inputs
- rolling-window aggregation must happen before report rendering
- report code must not hide classification logic or reconstruct canonical context on the fly

## 4. Source Tables

Report Canonical V2 should read from the current Datacenter report source tables and only directly relevant auxiliary sources.

### dc_ticker_swing_signal_daily

Role:
Ticker-level raw source table for one Datacenter signal date.

Expected grain:
`signal_date, taxonomy_version, ticker`

Relevant field families:

- ticker identity
- `signal_date`
- `market`
- taxonomy version and signal version
- layer / subindustry membership
- breakout / pullback / exit signal fields
- exit severity / exit reason
- return fields
- EMA-distance fields
- structure / trend / BOS / RESET fields
- price-data readiness fields
- bullish / bearish supporting signal fields when available

V2 role:
Primary ticker-level raw input for daily and rolling report context builders.

### dc_group_swing_signal_daily

Role:
Group-level timing and risk source table for ecosystem, layer, and subindustry context.

Expected grain:
`signal_date, taxonomy_version, group_type, group_name`

Relevant field families:

- `group_type`
- `group_name`
- `signal_date`
- `timing_state`
- `overheat_risk_level`
- return fields
- breadth / participation fields if present
- data-quality/readiness fields

V2 role:
Primary source for canonical group timing and overheat context used by both daily and rolling reports.

### dc_group_synthetic_ohlc_daily

Role:
Synthetic group OHLC and structure source table used to add structure context to group reporting.

Expected grain:
`ohlc_date, taxonomy_version, group_type, group_name`

Relevant field families:

- `group_type`
- `group_name`
- `ohlc_date` and its relationship to report `signal_date`
- synthetic close / OHLC
- synthetic EMA-distance fields
- synthetic trend classification
- synthetic `latest_structure_label`
- synthetic BOS / RESET / freshness fields
- synthetic structure-readiness/data-quality fields if present

V2 role:
Primary source for canonical synthetic structure context at the group level.

### Other auxiliary source tables

Only directly report-relevant auxiliary sources should be included in Report Canonical V2.

Expected examples:

- watchlist source file or equivalent watchlist membership source used by current reports
- MA history inputs required by the MA break helper
- signal history inputs required by the signal freshness helper
- technical relevance source rows, if technical relevance remains a report-supported field family

Rules:

- include an auxiliary source only if it directly supports `daily`, `rolling2`, `rolling5`, or `rolling30`
- exclude dashboard tables entirely

## 5. Canonical Table Model

The minimum V2 report-only table model consists of one run table, two context tables, one horizon-window context table, and one classification table.

### dc_report_run_v2

Purpose:
Operational metadata for one canonical report calculation run.

Expected grain:
`run_id`

Primary key concept:
One row per canonical report calculation run.

Source field families:

- requested report date
- taxonomy version
- market
- source version metadata

Derived field families:

- run status
- warning / error counts
- created timestamp
- calculation version

Downstream report consumers:

- all report generation entrypoints for provenance and run validation

Notes / constraints:

- this table is operational metadata, not report content
- one run may populate multiple V2 context and classification tables for the same `signal_date`
- source version fields should be explicit where available instead of embedded in free text

Required field families:

- `run_id`
- `signal_date`
- `taxonomy_version`
- `market`
- `calculation_version`
- `source_versions` / `source_table_versions` if available
- `created_at_utc`
- `status`
- `warning_count`
- `error_count`
- `notes`

### dc_report_context_group_v2

Purpose:
Canonical group context for layer/subindustry/group-level timing, risk, and synthetic structure used by reports.

Expected grain:
`signal_date, taxonomy_version, group_type, group_name`

Primary key concept:
One canonical group-context row per report date and group identity.

Source field families:

- `dc_group_swing_signal_daily` timing and overheat fields
- `dc_group_swing_signal_daily` return and breadth fields
- `dc_group_synthetic_ohlc_daily` synthetic price and structure fields

Derived field families:

- parent group identity
- canonical group-risk status
- canonical readiness status
- normalized synthetic structure fields aligned to report date

Downstream report consumers:

- `daily`
- `rolling2`
- `rolling5`
- `rolling30`

Notes / constraints:

- must be the single source of truth for report-visible group timing/overheat context
- must unify group timing and synthetic structure into one canonical row
- `group_context_risk_status` should be an explicit canonical enum, not re-inferred in reports

Required field families:

- `signal_date`
- `taxonomy_version`
- `market`
- `group_type`
- `group_name`
- `parent_group_type`
- `parent_group_name`
- `timing_state`
- `overheat_risk_level`
- `return_2d` / `return_5d` / `return_30d` if available or needed
- breadth / participation fields if available or needed
- `synthetic_close`
- synthetic EMA-distance fields
- `synthetic_trend_state` / `trend_classification`
- `synthetic_latest_structure_label`
- `synthetic_latest_bos_event_type`
- `synthetic_latest_bos_freshness`
- `synthetic_latest_reset_reason`
- `synthetic_latest_reset_freshness`
- `group_context_risk_status`
- `group_context_readiness_status`

### dc_report_context_daily_v2

Purpose:
Canonical ticker-level daily report context at one signal date.

Expected grain:
`signal_date, taxonomy_version, ticker`

Primary key concept:
One canonical daily-context row per ticker on one report date.

Source field families:

- ticker source fields from `dc_ticker_swing_signal_daily`
- group context fields from `dc_report_context_group_v2`
- auxiliary helper inputs for MA break, freshness, watchlist membership, and technical relevance where supported

Derived field families:

- current watchlist status
- layer/subindustry context risk statuses
- explicit helper outputs such as MA break and freshness
- canonical daily trigger state
- daily readiness status

Downstream report consumers:

- `daily`

Notes / constraints:

- must hold all ticker-level daily report semantics needed by the formatter
- report code must not recalculate watchlist status or daily trigger state once this table exists
- if technical relevance remains visible in daily output, it must enter here explicitly rather than through ad hoc report-side enrichment

Required field families:

- `signal_date`
- `taxonomy_version`
- `market`
- `ticker`
- `primary_layer`
- `primary_subindustry`
- `in_datacenter_ecosystem`
- `is_watchlist`
- `current_watchlist_status`
- breakout signal fields
- pullback signal fields
- exit signal fields
- `exit_severity`
- `latest_exit_reason`
- return fields
- EMA-distance fields
- `ma_break_status`
- `freshness_status`
- `technical_relevance_status` if available
- `trend_state`
- `latest_structure_label`
- `latest_bos_event_type`
- `latest_bos_freshness`
- `latest_reset_reason`
- `latest_reset_freshness`
- `layer_timing_state`
- `layer_overheat_risk_level`
- `layer_context_risk_status`
- `subindustry_timing_state`
- `subindustry_overheat_risk_level`
- `subindustry_context_risk_status`
- `daily_trigger_state`
- `daily_context_readiness_status`

### dc_report_context_window_v2

Purpose:
Canonical ticker-level rolling-window report context for `rolling2`, `rolling5`, and `rolling30` horizons.

Expected grain:
`signal_date, taxonomy_version, ticker, horizon`

Primary key concept:
One canonical window-context row per ticker, report date, and supported horizon.

Allowed horizon values:

- `rolling2`
- `rolling5`
- `rolling30`

Source field families:

- daily ticker signal history from `dc_ticker_swing_signal_daily`
- group context from `dc_report_context_group_v2`
- auxiliary helper inputs for MA break and freshness where rolling reports display them

Derived field families:

- resolved window date range
- valid trading day count
- repeated signal counts
- current and window watchlist statuses
- group status snapshots and change fields
- horizon-specific readiness state

Downstream report consumers:

- `rolling2`
- `rolling5`
- `rolling30`

Notes / constraints:

- must be built as-of `signal_date` with no lookahead
- must externalize all rolling-window aggregation currently performed inside report generation
- must store the canonical window-end snapshot fields used by rolling classifiers

Required field families:

- `signal_date`
- `taxonomy_version`
- `market`
- `ticker`
- `horizon`
- `window_start_date`
- `window_end_date`
- `valid_trading_days`
- `current_watchlist_status`
- `window_watchlist_status`
- `breakout_days`
- `pullback_days`
- `fast_ema10_pullback_days`
- `conservative_ema20_pullback_days`
- `exit_risk_days`
- `high_exit_risk_days`
- `medium_exit_risk_days`
- `first_signal_date`
- `last_signal_date`
- `latest_exit_reason`
- `status_change`
- `group_current_status`
- `group_window_status`
- `group_status_change`
- `layer_context_risk_status`
- `subindustry_context_risk_status`
- `trend_state`
- `latest_structure_label`
- `latest_bos_event_type`
- `latest_bos_freshness`
- `latest_reset_reason`
- `latest_reset_freshness`
- `ma_break_status`
- `freshness_status`
- `window_context_readiness_status`

### dc_report_classification_v2

Purpose:
Canonical report classification output for daily and rolling report rows.

Expected grain:
`signal_date, taxonomy_version, ticker, horizon`

Primary key concept:
One canonical classification row per ticker, report date, and report horizon.

Allowed horizon values:

- `daily`
- `rolling2`
- `rolling5`
- `rolling30`

Source field families:

- `dc_report_context_daily_v2`
- `dc_report_context_window_v2`
- reusable pure helper outputs where preserved

Derived field families:

- horizon-specific classifier states
- normalized reasons and next action
- readiness / priority outputs that remain report-scoped

Downstream report consumers:

- `daily`
- `rolling2`
- `rolling5`
- `rolling30`

Notes / constraints:

- this table is for report classification only
- it must not model dashboard actions, dashboard trace, or dashboard decision semantics
- only relevant classifier fields need to be populated per horizon; non-applicable classifier fields may remain null

Required field families:

- `signal_date`
- `taxonomy_version`
- `market`
- `ticker`
- `horizon`
- `daily_trigger_state`
- `rolling_2_sell_pressure_state`
- `rolling_5_pullback_state`
- `rolling_30_buy_state`
- `rolling_30_exit_state`
- `pullback_validity`
- `entry_readiness`
- `candidate_priority`
- `candidate_priority_label`
- `primary_reason`
- `blocking_reason`
- `risk_reason`
- `next_action`
- `classification_status`
- `classification_version`
- `run_id`
- `created_at_utc`

## 6. Explicit Report Signal Model

Implicit or text-derived report signals that matter for report semantics should become explicit canonical fields.

### close_below_ema20

- proposed canonical field name: `close_below_ema20_flag`
- field type concept: boolean
- likely source input: ticker close vs EMA20 or explicit exit-reason helper interpretation
- location: `dc_report_context_daily_v2`, `dc_report_context_window_v2`

### close_below_ema50

- proposed canonical field name: `close_below_ema50_flag`
- field type concept: boolean
- likely source input: MA break helper / ticker close vs SMA50 or EMA50 equivalent source
- location: `dc_report_context_daily_v2`, `dc_report_context_window_v2`

### return_10d_lt_minus_8pct

- proposed canonical field name: `return_10d_lt_minus_8pct_flag`
- field type concept: boolean
- likely source input: `return_10d`
- location: `dc_report_context_daily_v2`, `dc_report_context_window_v2`

### failed_pullback

- proposed canonical field name: `failed_pullback_flag`
- field type concept: boolean or enum-backed boolean
- likely source input: rolling5 classifier output or pullback-blocker derivation
- location: `dc_report_classification_v2`

### double_bos_down

- proposed canonical field name: `double_bos_down_flag`
- field type concept: boolean
- likely source input: reset/structure interpretation from ticker or group structure fields
- location: `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2`

### double_bos_up

- proposed canonical field name: `double_bos_up_flag`
- field type concept: boolean
- likely source input: reset/structure interpretation from ticker or group structure fields
- location: `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2`

### exit_reason-derived severe risk flags

- proposed canonical field name: `severe_exit_risk_flag`
- field type concept: boolean or enum
- likely source input: exit severity plus explicit exit-reason normalization
- location: `dc_report_context_daily_v2`, `dc_report_context_window_v2`

### layer_overheat_risk flag

- proposed canonical field name: `layer_overheat_risk_flag`
- field type concept: boolean
- likely source input: layer `overheat_risk_level`
- location: `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2`

### subindustry_overheat_risk flag

- proposed canonical field name: `subindustry_overheat_risk_flag`
- field type concept: boolean
- likely source input: subindustry `overheat_risk_level`
- location: `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2`

### stale_structure flag

- proposed canonical field name: `stale_structure_flag`
- field type concept: boolean
- likely source input: structure freshness fields
- location: `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2`

### fresh_bos flag

- proposed canonical field name: `fresh_bos_flag`
- field type concept: boolean
- likely source input: BOS event type plus freshness
- location: `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2`

### fresh_reset flag

- proposed canonical field name: `fresh_reset_flag`
- field type concept: boolean
- likely source input: reset reason plus freshness
- location: `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2`

## 7. Current-to-V2 Field Mapping

| Current concept / field | Current location | Current source type | V2 target table | V2 target field | Notes |
| --- | --- | --- | --- | --- | --- |
| ticker | `dc_ticker_swing_signal_daily`, report rows | raw source | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_classification_v2` | `ticker` | canonical ticker identity |
| signal_date | daily and rolling report loaders | raw source / derived window end | all V2 tables except run metadata-only fields | `signal_date` | rolling tables use report end date |
| market | source/report parameters | source metadata | all V2 tables | `market` | persist explicitly |
| taxonomy_version | source tables / report loader | raw source | all V2 tables | `taxonomy_version` | shared partition field |
| layer | `primary_layer` | raw source | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `primary_layer` | ticker classification membership |
| subindustry | `primary_subindustry` | raw source | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `primary_subindustry` | ticker classification membership |
| watchlist membership | watchlist file + report context | auxiliary / derived | `dc_report_context_daily_v2` | `is_watchlist` | explicit boolean/flag |
| current_watchlist_status | report-local status builders | derived in report code | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `current_watchlist_status` | remove report-local recomputation |
| window_watchlist_status | rolling report code | derived in report code | `dc_report_context_window_v2` | `window_watchlist_status` | horizon-specific |
| breakout_days | rolling report code | derived window aggregation | `dc_report_context_window_v2` | `breakout_days` | built as-of window |
| pullback_days | rolling report code | derived window aggregation | `dc_report_context_window_v2` | `pullback_days` | built as-of window |
| fast_ema10_pullback_days | rolling report code | derived window aggregation | `dc_report_context_window_v2` | `fast_ema10_pullback_days` | preserve current semantics |
| conservative_ema20_pullback_days | rolling report code | derived window aggregation | `dc_report_context_window_v2` | `conservative_ema20_pullback_days` | preserve current semantics |
| exit_risk_days | rolling report code | derived window aggregation | `dc_report_context_window_v2` | `exit_risk_days` | preserve current semantics |
| high_exit_risk_days | rolling report code | derived window aggregation | `dc_report_context_window_v2` | `high_exit_risk_days` | preserve current semantics |
| medium_exit_risk_days | rolling report code | derived window aggregation | `dc_report_context_window_v2` | `medium_exit_risk_days` | preserve current semantics |
| trend_state | ticker/group structure fields | raw source or synthetic source | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2` | `trend_state` / `synthetic_trend_state` | explicit split between ticker and group |
| latest_structure_label | ticker/group structure fields | raw source or synthetic source | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2` | `latest_structure_label` / `synthetic_latest_structure_label` | preserve source meaning |
| latest_bos_event_type | ticker/group structure fields | raw source or synthetic source | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2` | `latest_bos_event_type` / `synthetic_latest_bos_event_type` | explicit source split |
| latest_bos_freshness | ticker/group structure fields | raw source or synthetic source | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2` | `latest_bos_freshness` / `synthetic_latest_bos_freshness` | explicit source split |
| latest_reset_reason | ticker/group structure fields | raw source or synthetic source | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2` | `latest_reset_reason` / `synthetic_latest_reset_reason` | explicit source split |
| latest_reset_freshness | ticker/group structure fields | raw source or synthetic source | `dc_report_context_daily_v2`, `dc_report_context_window_v2`, `dc_report_context_group_v2` | `latest_reset_freshness` / `synthetic_latest_reset_freshness` | explicit source split |
| layer timing state | group report context | raw source | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `layer_timing_state` | join from canonical group table |
| layer overheat risk | group report context | raw source | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `layer_overheat_risk_level` | join from canonical group table |
| subindustry timing state | group report context | raw source | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `subindustry_timing_state` | join from canonical group table |
| subindustry overheat risk | group report context | raw source | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `subindustry_overheat_risk_level` | join from canonical group table |
| daily_trigger_state | daily report code | report-local classification | `dc_report_classification_v2` and optionally mirrored in `dc_report_context_daily_v2` | `daily_trigger_state` | classification truth belongs in classification table |
| rolling_2_sell_pressure_state | rolling2 classifier path | helper classification | `dc_report_classification_v2` | `rolling_2_sell_pressure_state` | horizon `rolling2` |
| rolling_5_pullback_state | rolling5 classifier path | helper classification | `dc_report_classification_v2` | `rolling_5_pullback_state` | horizon `rolling5` |
| rolling_30_buy_state | rolling30 classifier path | helper classification | `dc_report_classification_v2` | `rolling_30_buy_state` | horizon `rolling30` |
| rolling_30_exit_state | rolling30 classifier path | helper classification | `dc_report_classification_v2` | `rolling_30_exit_state` | horizon `rolling30` |
| ma_break_status | MA helper / report helper rows | helper-derived | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `ma_break_status` | persist explicit helper output |
| freshness_status | freshness helper / report helper rows | helper-derived | `dc_report_context_daily_v2`, `dc_report_context_window_v2` | `freshness_status` | persist explicit helper output |
| pullback_validity | report-scoped downstream classification | derived | `dc_report_classification_v2` | `pullback_validity` | keep report-scoped only |
| entry_readiness | report-scoped downstream classification | derived | `dc_report_classification_v2` | `entry_readiness` | keep report-scoped only |
| candidate_priority | report-scoped downstream classification | derived | `dc_report_classification_v2` | `candidate_priority` | keep report-scoped only |
| candidate_priority_label | report-scoped downstream classification | derived | `dc_report_classification_v2` | `candidate_priority_label` | canonical enum label |
| primary_reason | daily/rolling classifier outputs | helper / report-local classification | `dc_report_classification_v2` | `primary_reason` | explicit reason output |
| blocking_reason | daily/rolling classifier outputs | helper / report-local classification | `dc_report_classification_v2` | `blocking_reason` | explicit reason output |
| risk_reason | daily/rolling classifier outputs | helper classification | `dc_report_classification_v2` | `risk_reason` | explicit reason output |
| next_action | daily/rolling classifier outputs | helper classification | `dc_report_classification_v2` | `next_action` | report-scoped next step, not dashboard action |

## 8. Helper Preservation Plan

| Helper / logic | Preservation class | Rationale |
| --- | --- | --- |
| rolling2 sell pressure classifier | Preserve but call from canonical report builder | Current classifier is already close to a pure horizon helper once given canonical window context. |
| rolling5 pullback classifier | Preserve but call from canonical report builder | Current classifier is reusable if the window context row is built canonically first. |
| rolling30 watchlist/buy classifier | Preserve but call from canonical report builder | Current logic should consume canonical rolling30 window context instead of report-built base rows. |
| MA break helper | Preserve but refactor into pure helper first | It should remain reusable, but the canonical builder must own persistence of its output. |
| signal freshness helper | Preserve but refactor into pure helper first | Same pattern as MA break; keep logic, remove report-local dependency. |
| group-aware watchlist status logic | Preserve but refactor into pure helper first | It is currently duplicated across daily and rolling paths and should become one canonical status derivation. |
| daily trigger state logic | Preserve but call from canonical report builder | Daily trigger semantics should survive, but classification must be persisted before report rendering. |
| rolling window aggregation logic | Replace with canonical field | Window counts and status transitions should be materialized into `dc_report_context_window_v2`, not recomputed in reports. |

## 9. Reports-As-Formatters Contract

### daily report

V2 tables it should read:

- `dc_report_run_v2`
- `dc_report_context_group_v2`
- `dc_report_context_daily_v2`
- `dc_report_classification_v2` for `horizon = 'daily'`

Logic that must be removed from report code:

- current watchlist status derivation
- group risk inference
- daily trigger classification
- technical helper recomputation when already available canonically

Logic allowed to remain in report code:

- sorting
- top-N selection
- section grouping
- headings
- display formatting
- Markdown/CSV rendering
- deterministic label rendering from canonical enums

### rolling2 report

V2 tables it should read:

- `dc_report_run_v2`
- `dc_report_context_group_v2`
- `dc_report_context_window_v2` for `horizon = 'rolling2'`
- `dc_report_classification_v2` for `horizon = 'rolling2'`

Logic that must be removed from report code:

- rolling 2-day window aggregation
- current/window watchlist status derivation
- group status change derivation
- rolling2 sell-pressure classification

Logic allowed to remain in report code:

- sorting
- top-N selection
- section grouping
- headings
- display formatting
- Markdown/CSV rendering
- deterministic label rendering from canonical enums

### rolling5 report

V2 tables it should read:

- `dc_report_run_v2`
- `dc_report_context_group_v2`
- `dc_report_context_window_v2` for `horizon = 'rolling5'`
- `dc_report_classification_v2` for `horizon = 'rolling5'`

Logic that must be removed from report code:

- rolling 5-day window aggregation
- pullback day counting
- group-aware status reconstruction
- rolling5 pullback classification

Logic allowed to remain in report code:

- sorting
- top-N selection
- section grouping
- headings
- display formatting
- Markdown/CSV rendering
- deterministic label rendering from canonical enums

### rolling30 report

V2 tables it should read:

- `dc_report_run_v2`
- `dc_report_context_group_v2`
- `dc_report_context_window_v2` for `horizon = 'rolling30'`
- `dc_report_classification_v2` for `horizon = 'rolling30'`

Logic that must be removed from report code:

- rolling 30-day window aggregation
- repeated signal counting
- group/window status reconstruction
- rolling30 buy/exit classification

Logic allowed to remain in report code:

- sorting
- top-N selection
- section grouping
- headings
- display formatting
- Markdown/CSV rendering
- deterministic label rendering from canonical enums

Forbidden report logic for all report types:

- trigger classification
- rolling window aggregation
- group risk inference
- report-to-report reconstruction
- Markdown/CSV parser reconstruction
- hidden text-token based classification

## 10. Parallel Rollout Plan

The recommended rollout sequence is:

1. Add V2 schema migrations for report canonical tables.
2. Add group report context builder.
3. Add daily report context builder.
4. Add window report context builder.
5. Add report classification writer using current pure helpers where possible.
6. Add parity audit CLI comparing V2 canonical output to current daily/rolling reports.
7. Convert daily report to formatter mode behind an explicit flag.
8. Convert rolling2 report to formatter mode behind an explicit flag.
9. Convert rolling5 report to formatter mode behind an explicit flag.
10. Convert rolling30 report to formatter mode behind an explicit flag.
11. Remove report-local hidden calculation only after parity is proven.

## 11. Test Strategy

Focused future tests should include:

- schema migration tests
- group report context builder unit tests
- daily report context builder unit tests
- window report context builder unit tests
- no-lookahead / as-of-date tests
- helper parity tests
- report classification tests
- report formatter tests
- acceptance / parity tests against current daily / rolling reports

Priority guidance:

- first prove schema shape and key constraints
- then prove no-lookahead correctness for `rolling2`, `rolling5`, and `rolling30`
- then prove helper parity against current daily/rolling report semantics
- then prove formatter parity after reports switch to V2-backed mode

## 12. First Implementation Step After This Spec

Recommended next task:

`DB-V2-03 — Add read-only SQL migration for V2 report canonical tables and schema tests only.`

Scope clarification for DB-V2-03:

- add only the V2 report-canonical schema migration work
- add only schema-focused tests
- do not add builders
- do not add CLIs
- do not change reports
- do not change scheduler logic
- do not add dashboard changes
- do not add dashboard-related logic
