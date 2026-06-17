# Datacenter Dashboard Rolling 5d Pullback Status Spec

## 1. Purpose

This document defines the proposed future **structured rolling 5d pullback status layer** for Datacenter dashboard enrichment.

The purpose of the layer is to improve enrichment-mode parity for:

- `pullback_validity`
- `entry_readiness`
- `candidate_priority`
- `candidate_priority_label`

Clarifications:

- this spec does not implement the layer
- this spec does not change scheduler behavior
- reports mode remains the reference and fallback path


## 2. Current Problem

Observed reports-mode pullback distribution:

- `VALID_PULLBACK=4`
- `EARLY_PULLBACK=28`
- `STRUCTURE_BLOCKED_PULLBACK=85`
- `BREAKDOWN_NOT_PULLBACK=12`
- `NO_PULLBACK=108`
- `INSUFFICIENT_DATA=0`

Observed enrichment-mode state after field-flow repair and conservative mapping:

- there is no remaining `INSUFFICIENT_DATA` field-flow problem
- pullback context remains materially weaker than reports mode
- conservative V0 mapping improved parity only modestly

Known DB-18j observations:

- enrichment `NO_PULLBACK` improved from `232` to `223`
- enrichment `STRUCTURE_BLOCKED_PULLBACK` improved from `3` to `11`
- enrichment `VALID_PULLBACK` improved from `0` to `1`
- `missing_pullback_context` improved only `100 -> 99`
- `missing_fresh_bullish_signal` improved `24 -> 14`

Known diagnostic conclusions:

- field-flow is fixed
- structured source data already contains pullback, bullish, BOS, and reset inputs
- simple direct field mapping is insufficient
- reports mode appears to use richer rolling 5d context than current enrichment mode


## 3. Non-Goals

- no `.md` parser dependency
- no broad report-generation copy-paste
- no scheduler switch
- no production DB write
- no HTML changes
- no dashboard decision rule changes unless explicitly approved later
- no hidden lookahead
- no use of future rows after `signal_date`


## 4. Canonical Source Principle

The future rolling 5d pullback layer must be derived from **structured `analysis.db` source tables**, not from `.md` reports.

Primary current candidate source:

- `dc_ticker_swing_signal_daily`

Required source fields if available:

- `signal_date`
- `ticker`
- `taxonomy_version`
- `pullback_signal`
- `conservative_ema20_pullback_signal`
- `fast_ema10_pullback_signal`
- `bullish_candle_signal`
- `bullish_divergence_signal`
- `hidden_bullish_divergence_signal`
- `latest_bos_event_type`
- `latest_reset_reason`
- `exit_risk_signal`
- `exit_risk_severity`
- `distance_to_ema20_pct`
- `return_5d`
- `return_10d`
- `price_data_status`

If a future exact rolling-report source table is added, this layer should prefer that table over heuristic recomputation from lower-level fields.


## 5. Proposed Target Table or Fields

### Option A: Extend `dc_dashboard_ticker_enrichment_daily`

Candidate added fields:

- `rolling_5d_pullback_status`
- `rolling_5d_pullback_days`
- `rolling_5d_latest_bullish_signal_age_td`
- `rolling_5d_structure_override`
- `rolling_5d_pullback_reason`
- `rolling_5d_calc_version`

### Option B: New Dedicated Table

Proposed table:

- `dc_dashboard_ticker_rolling5_pullback_daily`

Candidate columns:

- `signal_date`
- `taxonomy_version`
- `ticker`
- `rolling_5d_pullback_status`
- `pullback_days_5d`
- `latest_bullish_signal_age_td_5d`
- `structure_override_5d`
- `ma_break_or_breakdown_context`
- `source_rows_used`
- `data_quality_status`
- `calc_version`
- `run_id`
- `created_at_utc`

Recommendation:

- prefer **Option B** if the layer grows beyond a small field-mapping extension
- prefer **Option A** only for a minimal V1 if a dedicated audit table is not needed


## 6. Proposed Deterministic V1 Classification

Candidate V1 statuses:

- `VALID_PULLBACK_CONTEXT`
- `EARLY_PULLBACK_CONTEXT`
- `STRUCTURE_BLOCKED_PULLBACK_CONTEXT`
- `BREAKDOWN_NOT_PULLBACK_CONTEXT`
- `NO_PULLBACK_CONTEXT`
- `INSUFFICIENT_DATA`

This section defines a **proposal**, not a final production rule.

### Input Window

- use the last `5` source rows where `ticker` and `taxonomy_version` match
- require `signal_date <= selected signal_date`
- do not use future rows

### Candidate Pullback Presence

Treat pullback source as present if any of the following are true inside the window:

- `pullback_signal=1`
- `conservative_ema20_pullback_signal=1`
- `fast_ema10_pullback_signal=1`

### Bullish Confirmation

Derive latest bullish signal age from the most recent row where any of the following are true:

- `bullish_candle_signal=1`
- `bullish_divergence_signal=1`
- `hidden_bullish_divergence_signal=1`

### Structure Blocker

Treat structure blocker as true when:

- `latest_bos_event_type=BOS_DOWN`
- or `latest_reset_reason` contains `DOUBLE_BOS_DOWN`

### Breakdown Blocker

Treat breakdown blocker as true if available structured fields show a stronger failure state, for example:

- confirmed `ma_break_status` break
- hard-sell tokens already available in structured source
- severe recent negative return if already represented in structured source

### Proposed Classification

- `INSUFFICIENT_DATA` if fewer than required source rows exist or key inputs are missing
- `BREAKDOWN_NOT_PULLBACK_CONTEXT` if breakdown blocker is true
- `STRUCTURE_BLOCKED_PULLBACK_CONTEXT` if pullback source exists and structure blocker is true
- `VALID_PULLBACK_CONTEXT` if pullback source exists and bullish confirmation is fresh
- `EARLY_PULLBACK_CONTEXT` if pullback source exists but bullish confirmation is old or missing and no blocker exists
- `NO_PULLBACK_CONTEXT` otherwise

Important note:

- this is a proposed V1 only
- it must be validated against reports mode before production use
- exact thresholds remain a later implementation decision


## 7. Mapping Into Dashboard Decision Input

The future rolling 5d pullback layer should feed:

- `rolling_5d_status`
- `pullback_days`
- `latest_bullish_signal_age_td`
- `structure_warning_overrides_bullish_signal`
- `pullback_reason`
- `freshness_status` where appropriate

The layer must **not** map directly to final action.

Final:

- `pullback_validity`
- `entry_readiness`
- `candidate_priority`

must continue to be produced by the existing dashboard decision logic unless explicitly changed later.


## 8. No-Lookahead and Determinism

- only use source rows with `signal_date <= selected signal_date`
- ordering must be deterministic by `signal_date`
- no random tie-breaking
- no hidden current-date dependency
- `calc_version` and `run_id` must be deterministic enough for audit and rerun comparison


## 9. Validation / Parity Plan

Proposed staged follow-up plan:

### DB-18l

- decide whether schema/table support is needed
- add schema only if required

### DB-18m

- add a read-only audit for proposed V1 versus reports mode

### DB-18n

- implement writer in dry-run or temp mode

### DB-18o

- wire the layer into ticker enrichment writer or orchestrator behind an explicit flag

### DB-18p

- rerun manual enrichment plus temp dashboard validation

Acceptance targets:

- enrichment `VALID/EARLY/STRUCTURE_BLOCKED/BREAKDOWN` distribution is materially closer to reports mode
- enrichment `INSUFFICIENT_DATA` remains `0`
- acceptance report `blockers` remain `0`
- no action regression is introduced


## 10. Open Questions

- Should this live in a new table or in the existing ticker enrichment table?
- What exact source fields define a "fresh bullish signal"?
- What threshold separates `VALID` from `EARLY`?
- How should `conservative_ema20_pullback_signal` versus `fast_ema10_pullback_signal` be weighted?
- Should structure override use only the latest row or any row in the 5-row window?
- Does reports mode depend on exact rolling-report section fields not available in `analysis.db`?
- Should `source_horizons` be updated to include rolling 5d once this layer exists?


## 11. Recommended Next Step

Recommended next step is **not** scheduler source-mode switch if visual pullback parity is still required.

Recommended next implementation step is either:

### DB-18l

- decide table or field location
- add schema only if necessary
- no business logic yet

or:

### DB-18m

- implement a read-only proposed V1 classifier audit against reports mode before adding schema


## Reports-mode Pullback Semantic Source Investigation

Inspected files:

- `analysis/datacenter_indices/swing_weekly_report.py`
- `analysis/datacenter_indices/swing_daily_report.py`
- `analysis/datacenter_indices/swing_pipeline_orchestrator.py`
- `dev_tools/datacenter_dashboard_parser.py`
- `dev_tools/datacenter_dashboard_decisions.py`
- `dev_tools/run_datacenter_dashboard_rolling5_pullback_v2_classifier_audit.py`

### Source classification

- `STRUCTURED_SOURCE_PARTIAL`

### Where pullback_validity appears to originate

Reports-mode `pullback_validity` does not appear to exist upstream as a single reusable final field before dashboard parsing.

The inspected path is split into two layers:

1. `analysis/datacenter_indices/swing_weekly_report.py`
   - builds a structured rolling 5d row set in `_build_rolling_5_pullback_rows(...)`
   - computes upstream rolling 5d semantics in `_classify_rolling_5_pullback_row(...)`
   - emits structured rolling 5d states before markdown rendering

2. `dev_tools/datacenter_dashboard_decisions.py`
   - derives final dashboard `pullback_validity` later in `_classify_pullback_validity(...)`
   - uses parsed report rows plus acute structure / freshness / MA-break context

This means reports-mode pullback semantics are not markdown-only, but final dashboard `pullback_validity` is also not a direct upstream report field in the inspected report-generation code.

### Exact report / parser / decision tokens involved

Upstream rolling 5d structured/report states found in `swing_weekly_report.py`:

- `PULLBACK_CANDIDATE`
- `EARLY_PULLBACK`
- `FAILED_PULLBACK`
- `SHORT_TERM_BREAKDOWN`
- `NO_PULLBACK`
- `INSUFFICIENT_DATA`

Structured support fields emitted with rolling 5d rows include at least:

- `rolling_5_pullback_state`
- `pullback_days`
- `fast_ema10_pullback_days`
- `conservative_ema20_pullback_days`
- `latest_bos_event_type`
- `latest_bos_freshness`
- `latest_reset_reason`
- `latest_reset_freshness`
- `latest_bullish_relevance_class`
- `latest_bearish_relevance_class`
- `primary_reason`
- `blocking_reason`
- `next_action`

Final dashboard decision-side classes found in `datacenter_dashboard_decisions.py`:

- `VALID_PULLBACK`
- `EARLY_PULLBACK`
- `STRUCTURE_BLOCKED_PULLBACK`
- `BREAKDOWN_NOT_PULLBACK`
- `NO_PULLBACK`
- `INSUFFICIENT_DATA`

Decision-side tokens / fields used in `_classify_pullback_validity(...)` include:

- pullback context:
  - `pullback_days`
  - raw-field pullback tokens such as `pullback_candidate`, `early_pullback`, `failed_pullback`
- structure blocker context:
  - `freshness_status=STRUCTURE_WARNING_OVERRIDES_BULLISH`
  - `structure_warning_overrides_bullish_signal=1`
  - `latest_bos_event_type=BOS_DOWN`
  - fresh `latest_bos_freshness`
  - `latest_reset_reason` containing reset / `DOUBLE_BOS_DOWN`
  - fresh `latest_reset_freshness`
- breakdown context:
  - `ma_break_status=SMA50_CONFIRMED_BREAK`
  - `ma_break_status=EMA20_CONFIRMED_BREAK`
- bullish confirmation context:
  - `freshness_status=FRESH_BULLISH_SIGNAL`
  - acceptable or absent acute `ma_break_status`

### Whether reusable structured source exists before markdown

Reusable structured source does exist before markdown, but only partially.

Available before markdown:

- rolling 5d structured pullback state
- rolling 5d supporting reason / blocker / day-count fields

Not available as an inspected upstream structured field:

- final dashboard `pullback_validity`
- final dashboard `entry_readiness`
- final dashboard `candidate_priority`

`analysis/datacenter_indices/swing_pipeline_orchestrator.py` confirms the rolling 5d report is carried forward as a report artifact and exported as a pipeline report payload, but it does not expose a final upstream `pullback_validity` field on its own.

`dev_tools/datacenter_dashboard_parser.py` parses normalized columns plus generic `raw_fields`, so the reports-mode dashboard can consume the upstream rolling 5d state and supporting fields after report parsing. The parser is therefore a transport step, not the origin of the semantics.

### Should DB-18l add schema now or wait

Recommendation: wait before adding schema for the final dashboard class.

Reason:

- there is a reusable upstream rolling 5d semantic layer
- but the final dashboard pullback class is still a downstream decision derivation
- that final derivation also depends on acute daily / rolling 2d freshness and MA-break context, not only on the rolling 5d state itself

Adding schema immediately for the final class would likely store the wrong abstraction level.

### Recommended next step

Recommended next step:

- if parity is required, DB-18p should expose the reusable upstream rolling 5d structured semantic layer into the analysis/enrichment path


## Exact Current Reports-mode Algorithm

### 1. Inspected source functions

Inspected files and functions:

- `analysis/datacenter_indices/swing_weekly_report.py::_build_rolling_watchlist_rows`
- `analysis/datacenter_indices/swing_weekly_report.py::_classify_rolling_5_pullback_row`
- `analysis/datacenter_indices/swing_weekly_report.py::_build_rolling_5_pullback_rows`
- `analysis/datacenter_indices/swing_weekly_report.py::_has_fresh_bos_down`
- `analysis/datacenter_indices/swing_weekly_report.py::_has_fresh_reset`
- `analysis/datacenter_indices/swing_weekly_report.py::_is_pullback_oriented_status`
- `dev_tools/datacenter_dashboard_decisions.py::_normalize_horizon`
- `dev_tools/datacenter_dashboard_decisions.py::_collect_text_values`
- `dev_tools/datacenter_dashboard_decisions.py::_row_has_pullback_context`
- `dev_tools/datacenter_dashboard_decisions.py::_has_acute_confirmed_rolling_2d_bos_down`
- `dev_tools/datacenter_dashboard_decisions.py::_classify_pullback_validity`
- `dev_tools/datacenter_dashboard_decisions.py::_classify_entry_readiness`
- `dev_tools/datacenter_dashboard_decisions.py::_classify_candidate_priority`
- `dev_tools/datacenter_dashboard_parser.py::DatacenterDashboardRow`
- `dev_tools/datacenter_dashboard_parser.py::_COLUMN_SYNONYMS`

`analysis/datacenter_indices/swing_daily_report.py` and `analysis/datacenter_indices/swing_pipeline_orchestrator.py` were not needed to reconstruct the exact pullback algorithm itself.


### 2. Weekly rolling 5d upstream algorithm

The weekly report does not classify pullback directly from one raw daily row. It first builds a per-ticker rolling watchlist base row in `_build_rolling_watchlist_rows(...)`, then classifies that base row in `_classify_rolling_5_pullback_row(...)`, then emits a structured row in `_build_rolling_5_pullback_rows(...)`.

#### Base input row shape from `_build_rolling_watchlist_rows(...)`

For each ticker:

- `current_rows` = all ticker rows for that ticker, sorted ascending by `signal_date`
- `last_row` = latest row in that window
- matching same-date group context is looked up from:
  - `dc_group_swing_signal_daily`
  - synthetic group context keyed by `(signal_date, group_type, group_name)`

Computed base fields include:

- `pullback_days = count(row.pullback_signal == 1)`
- `fast_ema10_pullback_days = count(row.fast_ema10_pullback_signal == 1)`
- `conservative_ema20_pullback_days = count(row.conservative_ema20_pullback_signal == 1)`
- `breakout_days = count(row.breakout_signal == 1)`
- `exit_risk_days = count(row.exit_risk_signal == 1)`
- `high_exit_risk_days = count(row.exit_risk_severity == 'HIGH')`
- `medium_exit_risk_days = count(row.exit_risk_severity == 'MEDIUM')`
- latest acute fields copied from `last_row`:
  - `last_ticker_trend_state`
  - `last_latest_structure_label`
  - `last_latest_structure_freshness`
  - `last_latest_bos_event_type`
  - `last_latest_bos_freshness`
  - `last_latest_reset_reason`
  - `last_latest_reset_freshness`
  - `last_exit_risk_severity`
  - `last_exit_reason`
  - `last_price_data_status`
- latest same-date group/synthetic context:
  - `last_subindustry_trend_classification`
  - `last_subindustry_latest_structure_label`
  - `last_layer_trend_classification`
  - `last_layer_latest_structure_label`
  - `last_subindustry_timing_state`
  - `last_subindustry_overheat_risk_level`
  - `last_layer_timing_state`
  - `last_layer_overheat_risk_level`
- derived watchlist status fields:
  - `current_watchlist_status = _classify_rolling_current_watchlist_status(output_row)`
  - `window_watchlist_status = _classify_rolling_window_watchlist_status(output_row)`

If technical relevance rows are available, `_enrich_rows_with_technical_relevance_companions(...)` enriches the base row further before pullback classification.

#### Helper semantics used by pullback classification

- `_has_fresh_bos_down(row)` means a fresh bearish BOS condition is present.
- `_has_fresh_reset(row)` means a fresh reset condition is present.
- `_is_pullback_oriented_status(value)` is true only for:
  - `PULLBACK_CANDIDATE`
  - `ADD_ON_PULLBACK`

#### Exact emitted rolling 5d states

`_classify_rolling_5_pullback_row(...)` can emit exactly:

- `PULLBACK_CANDIDATE`
- `EARLY_PULLBACK`
- `FAILED_PULLBACK`
- `SHORT_TERM_BREAKDOWN`
- `NO_PULLBACK`
- `INSUFFICIENT_DATA`

#### Exact condition order in `_classify_rolling_5_pullback_row(...)`

Pseudocode, matching current order:

```text
if last_price_data_status is a missing-price status
or all_price_rows_missing is true:
    return INSUFFICIENT_DATA, MISSING_PRICE_CONTEXT, price_data_missing, WAIT_FOR_DATA

if ticker is empty:
    return INSUFFICIENT_DATA, MISSING_TICKER_CONTEXT, missing_ticker, WAIT_FOR_DATA

trend_state = last_ticker_trend_state
current_watchlist_status = current_watchlist_status
window_watchlist_status = window_watchlist_status
pullback_days = int(pullback_days or 0)
fast_ema10_pullback_days = int(fast_ema10_pullback_days or 0)
conservative_ema20_pullback_days = int(conservative_ema20_pullback_days or 0)
exit_risk_days = int(exit_risk_days or 0)
latest_exit_severity = last_exit_risk_severity
has_fresh_bos_down = _has_fresh_bos_down(row)
has_fresh_reset = _has_fresh_reset(row)
has_relevant_bearish_context = latest_bearish_relevance_class == RELEVANT
current_high_exit_risk = current_watchlist_status is a high-exit-risk status
window_high_exit_risk = window_watchlist_status is a high-exit-risk status
has_explicit_high_severity = latest_exit_severity is HIGH-like
has_explicit_extreme_severity = latest_exit_severity is EXTREME/CRITICAL-like

has_pullback_evidence =
    pullback_days > 0
    or fast_ema10_pullback_days > 0
    or conservative_ema20_pullback_days > 0
    or current_watchlist_status is pullback-oriented
    or window_watchlist_status is pullback-oriented

has_pullback_blocker =
    trend_state == DOWN
    or has_fresh_bos_down
    or has_fresh_reset
    or has_relevant_bearish_context
    or current_high_exit_risk
    or has_explicit_high_severity

has_severe_short_term_breakdown =
    has_fresh_bos_down
    or (has_fresh_reset and (trend_state == DOWN or current_high_exit_risk or has_explicit_high_severity))
    or (trend_state == DOWN and current_high_exit_risk)
    or has_explicit_extreme_severity
    or (has_relevant_bearish_context and current_high_exit_risk)

if not has_pullback_evidence:
    if has_severe_short_term_breakdown:
        return SHORT_TERM_BREAKDOWN,
               SHORT_TERM_BREAKDOWN_WITHOUT_PULLBACK_SETUP,
               one of {
                   recent_bos_down,
                   recent_reset,
                   extreme_exit_risk_severity,
                   down_trend_with_current_high_exit_risk,
                   relevant_bearish_context_with_current_high_exit_risk
               },
               MONITOR_EXIT_RISK
    return NO_PULLBACK, NO_MEANINGFUL_PULLBACK_EVIDENCE, "", NONE

if has_pullback_blocker:
    return FAILED_PULLBACK,
           PULLBACK_SETUP_BLOCKED,
           one of {
               recent_bos_down,
               recent_reset,
               high_exit_risk_status,
               high_exit_risk_severity,
               relevant_bearish_context,
               down_trend
           },
           REMOVE_FROM_PULLBACK_LIST

if has_pullback_evidence
and (trend_state == UP or current_watchlist_status is pullback-oriented or window_watchlist_status is pullback-oriented)
and exit_risk_days == 0
and not has_relevant_bearish_context
and not current_high_exit_risk
and not window_high_exit_risk:
    primary_reason =
        CONFIRMED_EMA20_PULLBACK_CONTEXT if conservative_ema20_pullback_days > 0
        else CONFIRMED_EMA10_PULLBACK_CONTEXT if fast_ema10_pullback_days > 0
        else PULLBACK_EVIDENCE_WITH_ACCEPTABLE_STRUCTURE
    return PULLBACK_CANDIDATE, primary_reason, "", REVIEW_FOR_DAILY_TRIGGER

if has_pullback_evidence:
    blocking_reason =
        EXIT_RISK_DAYS_WITHOUT_HIGH_SEVERITY if exit_risk_days > 0
        else MIXED_TREND_OR_STATUS
    return EARLY_PULLBACK, EARLY_OR_UNCONFIRMED_PULLBACK, blocking_reason, MONITOR_FOR_CONFIRMATION

return NO_PULLBACK, NO_MEANINGFUL_PULLBACK_EVIDENCE, "", NONE
```

#### How reasons and action are assigned

- `primary_reason` is assigned directly inside the chosen branch.
- `blocking_reason` is assigned only for blocked/breakdown/early branches.
- `next_action` is part of the upstream structured output:
  - `WAIT_FOR_DATA`
  - `MONITOR_EXIT_RISK`
  - `NONE`
  - `REMOVE_FROM_PULLBACK_LIST`
  - `REVIEW_FOR_DAILY_TRIGGER`
  - `MONITOR_FOR_CONFIRMATION`

#### How bullish/bearish relevance is used

- `latest_bearish_relevance_class == 'RELEVANT'` directly blocks pullback and contributes to:
  - `FAILED_PULLBACK`
  - `SHORT_TERM_BREAKDOWN`
- `latest_bullish_relevance_class` is carried into the structured row but is not directly consulted inside `_classify_rolling_5_pullback_row(...)`.


### 3. Dashboard `pullback_validity` algorithm

The final dashboard `pullback_validity` is not a direct mapping of `rolling_5_pullback_state`.
It is recomputed later by `dev_tools/datacenter_dashboard_decisions.py::_classify_pullback_validity(...)` from parsed dashboard rows plus acute daily / rolling-2d context.

#### Input row shape inspected by decision logic

The parser produces `DatacenterDashboardRow` with these relevant fields:

- horizon-related:
  - `horizon`
  - `source_file`
  - `section`
  - `row_kind`
- direct columns:
  - `raw_action`
  - `raw_status`
  - `reason`
  - `trend_state`
  - `latest_structure_label`
  - `latest_bos_event_type`
  - `latest_reset_reason`
  - `blocking_reasons`
  - `ma_break_status`
  - `freshness_status`
  - `structure_warning_overrides_bullish_signal`
  - `high_exit_risk_days_count`
- generic payload:
  - `raw_fields`

`_normalize_horizon(...)` only recognizes:

- `daily`
- `rolling 2d`
- `rolling 5d`
- `rolling 30d`

#### Text/token collection

`_collect_text_values(row)` lower-cases and aggregates:

- `raw_action`
- `raw_status`
- `reason`
- `trend_state`
- `latest_structure_label`
- `latest_bos_event_type`
- `latest_reset_reason`
- `blocking_reasons`
- every value in `raw_fields`

Important text-term sets used by pullback classification:

- `_PULLBACK_CONTEXT_TERMS`
  - `pullback_candidate`
  - `early_pullback`
  - `failed_pullback`
- `_ROLLING_2D_BOS_DOWN_TERMS`
  - `bos_down`
- `_ROLLING_2D_RESET_TERMS`
  - `reset`
- `_ROLLING_2D_CONFIRMATION_TERMS`
  - `reset`
  - `double_bos_down`
  - `high_exit_risk`
  - `failed_pullback`
  - `close_below_ema20`
  - `return_10d_lt_minus_8pct`
  - `sell`
- `_DAILY_BOS_DOWN_CONFIRMATION_TERMS`
  - `bos_down`
  - `reset`
  - `close_below_ema20`
  - `sell`

#### Exact condition order in `_classify_pullback_validity(...)`

Pseudocode, matching current order:

```text
sorted_rows = rows sorted by horizon priority:
    daily, rolling 2d, rolling 5d, rolling 30d

has_pullback_context =
    any text contains pullback_candidate / early_pullback / failed_pullback
    or raw_fields.pullback_days > 0

if not has_pullback_context:
    return NO_PULLBACK, NO_PULLBACK_CONTEXT

has_structure_or_freshness_context =
    any row has latest_bos_event_type
    or latest_reset_reason
    or freshness_status
    or structure_warning_overrides_bullish_signal is not None
    or ma_break_status
    or raw_fields.latest_bos_freshness
    or raw_fields.latest_reset_freshness

if not has_structure_or_freshness_context:
    return INSUFFICIENT_DATA, MISSING_STRUCTURE_OR_FRESHNESS_CONTEXT

acute_rows = rows with horizon in {daily, rolling 2d}

for row in acute_rows, in priority order:
    if freshness_status == STRUCTURE_WARNING_OVERRIDES_BULLISH:
        return STRUCTURE_BLOCKED_PULLBACK, STRUCTURE_WARNING_OVERRIDES_BULLISH_SIGNAL
    if structure_warning_overrides_bullish_signal == 1:
        return STRUCTURE_BLOCKED_PULLBACK, STRUCTURE_WARNING_OVERRIDES_BULLISH_SIGNAL
    if latest_bos_event_type == BOS_DOWN and raw_fields.latest_bos_freshness == FRESH:
        return STRUCTURE_BLOCKED_PULLBACK, FRESH_BOS_DOWN_BLOCKS_PULLBACK
    if latest_reset_reason contains DOUBLE_BOS_DOWN and raw_fields.latest_reset_freshness == FRESH:
        return STRUCTURE_BLOCKED_PULLBACK, FRESH_DOUBLE_BOS_DOWN_BLOCKS_PULLBACK
    if latest_reset_reason contains RESET and raw_fields.latest_reset_freshness == FRESH:
        return STRUCTURE_BLOCKED_PULLBACK, FRESH_RESET_BLOCKS_PULLBACK

if _has_acute_confirmed_rolling_2d_bos_down(sorted_rows):
    return STRUCTURE_BLOCKED_PULLBACK, ACUTE_BOS_DOWN_SELL_CONFIRMATION_BLOCKS_PULLBACK

for row in acute_rows:
    if ma_break_status == SMA50_CONFIRMED_BREAK:
        return BREAKDOWN_NOT_PULLBACK, SMA50_CONFIRMED_BREAK
    if ma_break_status == EMA20_CONFIRMED_BREAK:
        return BREAKDOWN_NOT_PULLBACK, EMA20_CONFIRMED_BREAK

has_fresh_bullish_signal =
    any row.freshness_status == FRESH_BULLISH_SIGNAL

has_structure_override =
    any row.freshness_status == STRUCTURE_WARNING_OVERRIDES_BULLISH
    or row.structure_warning_overrides_bullish_signal == 1

has_confirmed_ma_break =
    any acute row has ma_break_status in {SMA50_CONFIRMED_BREAK, EMA20_CONFIRMED_BREAK}

has_acceptable_ma_status =
    any acute row has ma_break_status in {OK, EMA20_WARNING}
    or no acute row has any ma_break_status at all

if has_acceptable_ma_status and not has_structure_override and has_fresh_bullish_signal:
    return VALID_PULLBACK, FRESH_BULLISH_PULLBACK_WITH_NO_STRUCTURE_BLOCK

if not has_confirmed_ma_break:
    return EARLY_PULLBACK, WAIT_FOR_BULLISH_CONFIRMATION

return INSUFFICIENT_DATA, MISSING_STRUCTURE_OR_FRESHNESS_CONTEXT
```

#### Additional acute BOS-down helper semantics

`_has_acute_confirmed_rolling_2d_bos_down(...)` requires:

- at least one `rolling 2d` row with `bos_down` token
- and at least one confirmation from:
  - `rolling 2d` reset token
  - daily bearish confirmation token
  - explicit sell / `return_10d_lt_minus_8pct`
  - fallback `close_below_ema20` when acute MA status is absent
  - acute rolling-2d confirmation token set
  - `high_exit_risk_days_count >= 1` in daily/rolling-2d rows

This means final `STRUCTURE_BLOCKED_PULLBACK` is partly an acute confirmation rule, not only a direct reuse of the weekly upstream state.


### 4. Entry readiness algorithm

Entry readiness is produced by:

- `dev_tools/datacenter_dashboard_decisions.py::_classify_entry_readiness(...)`

Exact logic:

```text
if pullback_validity is missing or action is missing:
    return INSUFFICIENT_DATA, MISSING_PULLBACK_VALIDITY_OR_ACTION

if pullback_validity == VALID_PULLBACK:
    if action in {WATCH, NEUTRAL}:
        return READY_TO_WATCH, VALID_PULLBACK_NO_STRONG_RISK_ACTION
    if action == TIGHTEN_STOP:
        return NEEDS_STOP_STABILIZATION, VALID_PULLBACK_BUT_HIGH_EXIT_RISK_DAYS
    if action == REDUCE:
        return NEEDS_RISK_CLEARANCE, VALID_PULLBACK_BUT_RISK_SIGNAL_PRESENT
    if action == SELL:
        return NOT_READY, VALID_PULLBACK_BUT_SELL_ACTION_PRESENT
    return INSUFFICIENT_DATA, MISSING_PULLBACK_VALIDITY_OR_ACTION

if pullback_validity == EARLY_PULLBACK:
    return EARLY_MONITOR, WAIT_FOR_BULLISH_CONFIRMATION

if pullback_validity in {
    STRUCTURE_BLOCKED_PULLBACK,
    BREAKDOWN_NOT_PULLBACK,
    NO_PULLBACK,
    INSUFFICIENT_DATA
}:
    return NOT_READY, pullback_validity

return INSUFFICIENT_DATA, MISSING_PULLBACK_VALIDITY_OR_ACTION
```

Important consequence:

- `READY_TO_WATCH`, `NEEDS_STOP_STABILIZATION`, and `NEEDS_RISK_CLEARANCE` are not produced from rolling 5d alone.
- They require final `VALID_PULLBACK` plus the already-computed final action.


### 5. Candidate priority algorithm

Candidate priority is produced by:

- `dev_tools/datacenter_dashboard_decisions.py::_classify_candidate_priority(...)`

It depends only on `entry_readiness`, not directly on rolling 5d state.

Exact mapping:

```text
READY_TO_WATCH -> (1, P1_READY_TO_WATCH, READY_TO_WATCH)
NEEDS_STOP_STABILIZATION -> (2, P2_STOP_STABILIZATION, VALID_PULLBACK_BUT_STOP_RISK_REMAINS)
NEEDS_RISK_CLEARANCE -> (3, P3_RISK_CLEARANCE, VALID_PULLBACK_BUT_RISK_SIGNAL_REMAINS)
EARLY_MONITOR -> (4, P4_EARLY_MONITOR, EARLY_PULLBACK_WAIT_FOR_CONFIRMATION)
NOT_READY -> (5, P5_NOT_READY, NOT_READY)
otherwise -> (9, P9_NOT_CANDIDATE, NOT_CANDIDATE_OR_INSUFFICIENT_DATA)
```

So current reports-mode priority semantics are:

- `candidate_priority`
- `candidate_priority_label`

are pure post-processing of `entry_readiness`.


### 6. Required enrichment payload to match reports-mode

Based strictly on the inspected code, enrichment must expose enough data to recreate both:

- the upstream rolling 5d row semantics
- the later acute dashboard pullback decision semantics

#### A. Upstream rolling 5d fields

Required or strongly implied upstream fields:

- `rolling_5_pullback_state`
- `pullback_days`
- `fast_ema10_pullback_days`
- `conservative_ema20_pullback_days`
- `primary_reason`
- `blocking_reason`
- `next_action`
- `latest_bullish_relevance_class`
- `latest_bullish_relevance_reason`
- `latest_bearish_relevance_class`
- `latest_bearish_relevance_reason`
- `latest_bos_event_type`
- `latest_bos_freshness`
- `latest_reset_reason`
- `latest_reset_freshness`
- `latest_ticker_trend_state`
- `current_watchlist_status`
- `window_watchlist_status`
- `last_price_data_status` or exact equivalent missing-price context
- `last_exit_risk_severity`
- `last_exit_reason`
- `exit_risk_days`

#### B. Acute override fields

Required downstream acute fields:

- `freshness_status`
- `structure_warning_overrides_bullish_signal`
- `latest_bos_event_type`
- `latest_bos_freshness`
- `latest_reset_reason`
- `latest_reset_freshness`
- `ma_break_status`
- `high_exit_risk_days_count`
- hard-sell raw tokens such as:
  - `sell`
  - `return_10d_lt_minus_8pct`
  - `close_below_ema20`

#### C. Adapter row shape

Decision logic expects a reports-parser-like row shape:

- horizon names exactly normalized to:
  - `daily`
  - `rolling 2d`
  - `rolling 5d`
  - `rolling 30d`
- meaningful `raw_status` / `raw_action` / `reason` / `blocking_reasons`
- `raw_fields` keys available for:
  - `pullback_days`
  - `latest_bos_freshness`
  - `latest_reset_freshness`
  - any extra rolling5 reasons/classes not promoted to top-level row fields


### 7. Gap against current enrichment adapter

Based on the inspected decision/parser code and the earlier DB-18r/DB-18t observations, the likely parity gaps are:

- upstream rolling 5d state is exposed as data, but not yet presented to decision logic as a true `rolling 5d` horizon row with reports-like `raw_status`/`reason` tokens
- `rolling_5_pullback_state` naming does not automatically satisfy `_PULLBACK_CONTEXT_TERMS` unless the adapter emits matching tokens such as:
  - `pullback_candidate`
  - `early_pullback`
  - `failed_pullback`
- `blocking_reason` is likely carried as payload, but not yet surfaced exactly the way reports rows expose `blocking_reasons`
- `latest_bos_freshness` and `latest_reset_freshness` must be accessible in `raw_fields` on the horizon row used by decision logic
- final `VALID_PULLBACK` requires acute `FRESH_BULLISH_SIGNAL`; upstream rolling 5d alone cannot produce it
- final `BREAKDOWN_NOT_PULLBACK` depends on acute `ma_break_status` in daily/rolling-2d rows, not on the weekly upstream row
- final `candidate_priority` mismatch is downstream of `entry_readiness`, which is downstream of final `pullback_validity`, so schema-only exposure of weekly fields is not enough


### 8. Recommended next implementation

Recommended next step:

#### DB-18v

- adjust the enrichment adapter row shape so the upstream rolling 5d structured row is emitted as a true `rolling 5d` horizon companion row with reports-like:
  - `raw_status`
  - `reason`
  - `blocking_reasons`
  - `raw_fields.latest_bos_freshness`
  - `raw_fields.latest_reset_freshness`
  - `raw_fields.pullback_days`
- keep daily and rolling-2d acute rows unchanged
- do not add scheduler switch
- do not add final pullback class storage
- avoid schema change if current payload metadata can already carry the required rolling5 fields
- it should not parse `.md` in production
- it should also not store only the final dashboard `pullback_validity` first

The narrowest useful upstream payload to expose appears to be:

- `rolling_5_pullback_state`
- `primary_reason`
- `blocking_reason`
- `pullback_days`
- `fast_ema10_pullback_days`
- `conservative_ema20_pullback_days`
- `latest_bos_event_type`
- `latest_bos_freshness`
- `latest_reset_reason`
- `latest_reset_freshness`
- bullish / bearish relevance companion fields

To preserve current decision semantics, the acute fields already consumed by dashboard decision logic must also remain available:

- `freshness_status`
- `structure_warning_overrides_bullish_signal`
- `ma_break_status`
- `latest_bullish_signal_age_td`

Net recommendation:

- do not treat reports-mode pullback semantics as `PARSER_ONLY_SOURCE`
- do not treat the current source as fully reusable final semantics either
- treat it as `STRUCTURED_SOURCE_PARTIAL`
- expose the upstream rolling 5d semantic layer plus the acute confirmation fields that the current dashboard decision logic already uses
