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
