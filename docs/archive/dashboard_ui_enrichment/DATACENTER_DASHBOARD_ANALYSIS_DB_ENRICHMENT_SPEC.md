# Datacenter Dashboard Analysis DB Enrichment Spec

## 1. Purpose and Boundaries

This document defines the intended **dashboard-ready enrichment layer** inside `analysis.db` for Datacenter dashboard publishing.

Separation of responsibilities:

- `analysis.db` is the calculation and enrichment layer.
- `ecosystem_dashboard.db` is the final published dashboard snapshot layer used by the existing read model and DB-backed HTML.
- `.md` reports remain human-readable and audit-friendly artifacts. They are not the long-term machine input source for the structured dashboard path.

Current production-safe reference path remains:

`.md reports` -> parser / decision logic -> `EcosystemDashboardInput` -> `persist_ecosystem_dashboard_input(...)` -> `ecosystem_dashboard.db` -> DB-backed HTML

Current `analysis.db` export V0 is intentionally partial:

- it can emit `source_reports`
- it can emit partial `market_map`
- it can emit partial `tickers`
- it cannot yet emit dashboard-ready `watchlist`, `action_summary`, or `decision_trace`

This spec does not change:

- `ecosystem_dashboard.db`
- dashboard HTML
- scheduler behavior
- reports mode
- existing report generation
- dashboard decision rules


## 2. Current Source Tables

Relevant existing `analysis.db` source tables:

- `dc_ticker_swing_signal_daily`
- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`
- `dc_group_index_daily`
- `dc_pipeline_watermark`

These are analysis-layer tables, not final dashboard snapshot tables.

Important constraint:

- old `dc_dashboard_*` tables were intentionally removed from `analysis.db`
- they must not be recreated as snapshot tables

The target is a new enrichment layer in `analysis.db` that is dashboard-ready but still remains an analysis-side intermediate layer.


## 3. Proposed New Dashboard-Ready Enrichment Tables in `analysis.db`

### A. `dc_dashboard_ticker_enrichment_daily`

Purpose:

- ticker-level enriched dashboard row source

Recommended columns:

```sql
signal_date TEXT NOT NULL
taxonomy_version TEXT NOT NULL
ticker TEXT NOT NULL
primary_layer TEXT NULL
primary_subindustry TEXT NULL
close REAL NULL
return_5d REAL NULL
return_10d REAL NULL
return_20d REAL NULL
return_60d REAL NULL
action TEXT NULL
severity TEXT NULL
primary_reason TEXT NULL
current_status TEXT NULL
start_status_30d TEXT NULL
status_change_30d TEXT NULL
status_change_5d TEXT NULL
window_status_30d TEXT NULL
window_status_5d TEXT NULL
window_status_2d TEXT NULL
ma_break_status TEXT NULL
freshness_status TEXT NULL
trend_state TEXT NULL
trend_state_age_td INTEGER NULL
latest_structure_label TEXT NULL
latest_structure_age_td INTEGER NULL
latest_bos_event_type TEXT NULL
latest_bos_age_td INTEGER NULL
latest_reset_reason TEXT NULL
latest_reset_age_td INTEGER NULL
latest_candle TEXT NULL
latest_candle_age_td INTEGER NULL
latest_divergence TEXT NULL
latest_divergence_age_td INTEGER NULL
latest_chart_pattern TEXT NULL
latest_chart_pattern_age_td INTEGER NULL
pullback_validity TEXT NULL
entry_readiness TEXT NULL
candidate_priority TEXT NULL
candidate_priority_label TEXT NULL
daily_status TEXT NULL
rolling_2d_status TEXT NULL
rolling_5d_status TEXT NULL
rolling_30d_status TEXT NULL
horizons_present TEXT NULL
source_run_ids TEXT NULL
source_components TEXT NULL
is_watchlist INTEGER NOT NULL DEFAULT 0
data_quality_status TEXT NOT NULL
calc_version TEXT NOT NULL
run_id TEXT NOT NULL
created_at_utc TEXT NOT NULL
```

Primary key recommendation:

```sql
PRIMARY KEY (signal_date, taxonomy_version, ticker)
```

Recommended indexes:

- ticker/date lookup
- `signal_date, action`
- `signal_date, is_watchlist`
- `signal_date, primary_layer, primary_subindustry`

Notes:

- `candidate_priority` is specified here as `TEXT` because the prompt requires that exact shape for this design task.
- `source_run_ids` should hold the contributing upstream run ids in a deterministic serialized form.
- `source_components` should identify the upstream logic/components that contributed to the row.


### B. `dc_dashboard_group_enrichment_daily`

Purpose:

- enriched market-map source for ecosystem, layer, and subindustry levels

Recommended columns:

```sql
signal_date TEXT NOT NULL
taxonomy_version TEXT NOT NULL
market_level TEXT NOT NULL
name TEXT NOT NULL
parent_name TEXT NULL
layer TEXT NULL
subindustry TEXT NULL
taxonomy_path TEXT NULL
taxonomy_key TEXT NOT NULL
current_status TEXT NULL
start_status_30d TEXT NULL
status_change_30d TEXT NULL
status_change_5d TEXT NULL
window_status_30d TEXT NULL
window_status_5d TEXT NULL
window_status_2d TEXT NULL
overheat_risk TEXT NULL
pct_above_ema20 REAL NULL
pct_above_ma10 REAL NULL
ema20_breadth_delta_5d REAL NULL
return_5d REAL NULL
return_10d REAL NULL
return_20d REAL NULL
return_60d REAL NULL
dow_trend_state TEXT NULL
dow_trend_state_age_td INTEGER NULL
latest_structure_label TEXT NULL
latest_structure_age_td INTEGER NULL
latest_bos_event_type TEXT NULL
latest_bos_age_td INTEGER NULL
latest_reset_reason TEXT NULL
latest_reset_age_td INTEGER NULL
latest_candle TEXT NULL
latest_candle_age_td INTEGER NULL
latest_divergence TEXT NULL
latest_divergence_age_td INTEGER NULL
latest_chart_pattern TEXT NULL
latest_chart_pattern_age_td INTEGER NULL
source_horizons TEXT NULL
source_run_ids TEXT NULL
source_components TEXT NULL
data_quality_status TEXT NOT NULL
calc_version TEXT NOT NULL
run_id TEXT NOT NULL
created_at_utc TEXT NOT NULL
```

Primary key recommendation:

```sql
PRIMARY KEY (signal_date, taxonomy_version, market_level, taxonomy_key)
```

Rationale for `taxonomy_key`:

- SQLite primary keys should not depend on expressions such as `COALESCE(parent_name, '')`.
- `taxonomy_key` should be written as a normalized stored key, for example:
  - ecosystem: `DC_ECOSYSTEM_TOTAL`
  - layer: `DC_ECOSYSTEM_TOTAL > Infrastructure`
  - subindustry: `DC_ECOSYSTEM_TOTAL > Infrastructure > AI Accelerators`

Recommended indexes:

- `signal_date, market_level`
- `signal_date, layer`
- `signal_date, subindustry`
- `signal_date, taxonomy_key`


### C. `dc_dashboard_action_summary_daily`

Purpose:

- precomputed action summary derived from ticker enrichment rows

Required columns:

```sql
signal_date TEXT NOT NULL
taxonomy_version TEXT NOT NULL
action TEXT NOT NULL
count INTEGER NOT NULL
calc_version TEXT NOT NULL
run_id TEXT NOT NULL
created_at_utc TEXT NOT NULL
```

Primary key:

```sql
PRIMARY KEY (signal_date, taxonomy_version, action)
```


### D. `dc_dashboard_decision_trace_daily`

Purpose:

- auditable decision trace for enriched ticker actions

Required columns:

```sql
signal_date TEXT NOT NULL
taxonomy_version TEXT NOT NULL
ticker TEXT NOT NULL
trace_index INTEGER NOT NULL
action TEXT NULL
matched_rule TEXT NULL
matched_token TEXT NULL
matched_value TEXT NULL
horizon TEXT NULL
field TEXT NULL
calc_version TEXT NOT NULL
run_id TEXT NOT NULL
created_at_utc TEXT NOT NULL
```

Primary key:

```sql
PRIMARY KEY (signal_date, taxonomy_version, ticker, trace_index)
```


### E. Optional `dc_dashboard_enrichment_run_daily`

Purpose:

- run-level audit, readiness, and warnings

Columns:

```sql
run_id TEXT PRIMARY KEY
signal_date TEXT NOT NULL
taxonomy_version TEXT NOT NULL
status TEXT NOT NULL
readiness TEXT NOT NULL
ticker_rows INTEGER NOT NULL
group_rows INTEGER NOT NULL
action_summary_rows INTEGER NOT NULL
decision_trace_rows INTEGER NOT NULL
warnings TEXT NULL
calc_version TEXT NOT NULL
created_at_utc TEXT NOT NULL
```

This table is optional but strongly recommended because the V0 path already surfaces readiness and warning semantics.


## 4. Deterministic Write Semantics

Supported future writer modes:

- `insert-missing`
- `upsert`
- `replace-date`

Default recommendation:

- `replace-date`

Rationale:

- deterministic daily rebuilds are easier to audit
- parity comparisons are easier when one logical date/taxonomy slice is rebuilt atomically

Deletion scope for `replace-date`:

- delete only rows for `signal_date + taxonomy_version`
- never delete rows for other dates
- never delete rows for other taxonomy versions

Recommended behavior by table:

- ticker enrichment: replace selected date/version slice only
- group enrichment: replace selected date/version slice only
- action summary: replace selected date/version slice only
- decision trace: replace selected date/version slice only
- optional run table: insert a new run record or replace same `run_id`, depending on implementation choice


## 5. No-Lookahead Rules

Enrichment rows for a selected `signal_date` must only use information available as of that date.

Allowed inputs:

- source rows where `signal_date` or equivalent source date is `<= selected date`
- rolling windows already calculated as-of the selected date
- structure/BOS/RESET/Dow fields whose effective confirmation date is `<= selected date`

Disallowed inputs:

- future prices
- future-confirmed events
- recalculated forward-looking labels that were not knowable as of the selected date

Design intent:

- the enrichment layer must be safe for historical parity review and backfilled daily rebuilds


## 6. Source-to-Enrichment Mapping

### Ticker enrichment mapping

Primary technical source:

- `dc_ticker_swing_signal_daily`

It should supply at minimum:

- ticker identity
- layer/subindustry identity
- close
- return fields
- trend/structure/BOS/RESET fields
- candle/divergence/chart pattern style fields when available
- data quality / price status

Additional semantic requirements:

- watchlist membership must come from an explicit source
- `current_status`, `start_status_30d`, `status_change_30d`, `status_change_5d`, `window_status_30d`, `window_status_5d`, and `window_status_2d` must come from deterministic horizon fusion, not guessing
- `action`, `severity`, `primary_reason`, `pullback_validity`, `entry_readiness`, `candidate_priority`, and related labels must come from existing dashboard decision semantics or a named enrichment rule version

Pseudo ticker rule:

- pseudo rows must be filtered out before enrichment rows are written
- examples of disallowed pseudo rows:
  - empty ticker
  - date-like ticker
  - section heading
  - layer heading
  - subindustry heading


### Group enrichment mapping

Primary sources:

- `dc_group_swing_signal_daily`
- `dc_group_synthetic_ohlc_daily`
- `dc_group_index_daily`

Expected mapping:

- `dc_group_swing_signal_daily` supplies timing state, breadth, and return context
- `dc_group_synthetic_ohlc_daily` supplies structure/BOS/RESET/group Dow fields
- `dc_group_index_daily` may supply longer-horizon returns or similar supporting metrics when not already present in swing rows

Semantic requirements:

- `market_level` must be one of ecosystem, layer, or subindustry in normalized published form
- `taxonomy_key` and `taxonomy_path` must be deterministic
- `source_horizons` should describe which horizon computations contributed to the row


### Action summary mapping

Source:

- derived from `dc_dashboard_ticker_enrichment_daily`

Rules:

- derive only from finalized ticker actions in the enrichment table
- do not compute from guessed watchlist rows
- do not compute from raw group states


### Decision trace mapping

Source:

- must use the same decision rule implementation as reports-mode dashboard decisions

Constraint:

- decision rules must not be duplicated manually in a new enrichment writer

Design requirement:

- the enrichment writer should call the same decision semantics that the reports-mode dashboard uses today, but on deterministic structured inputs


## 7. Required Writer CLIs for Future Steps

These are future tools only. They are not implemented by this spec task.

### A. `run_datacenter_dashboard_enrichment_write.py`

Arguments:

- `--analysis-db PATH`
- `--price-db PATH`
- `--signal-date YYYY-MM-DD`
- `--taxonomy-version TEXT`
- `--mode insert-missing|upsert|replace-date`
- `--run-id TEXT` optional
- `--dry-run`
- `--write-report-json PATH` optional

Expected summary family:

- `SUMMARY datacenter_dashboard_enrichment_write.*`


### B. `run_datacenter_dashboard_enrichment_audit.py`

Arguments:

- `--analysis-db PATH`
- `--signal-date YYYY-MM-DD`
- `--taxonomy-version TEXT`

Expected outputs:

- counts
- coverage
- warnings
- missing sections


### C. Future update to `run_datacenter_dashboard_analysis_db_export.py`

Future intended behavior:

- read enrichment tables first
- fall back to current V0 partial source only when an explicit fallback flag is used
- emit `EcosystemDashboardInput` with `readiness=READY` only when all required sections are present and semantically complete


## 8. Test Strategy

Future test files:

- `tests/test_datacenter_dashboard_enrichment_schema.py`
- `tests/test_datacenter_dashboard_enrichment_writer.py`
- `tests/test_datacenter_dashboard_enrichment_audit_cli.py`
- updates to `tests/test_datacenter_dashboard_analysis_db_builder.py`
- parity tests against reports-mode fixtures

Acceptance criteria:

- no pseudo tickers
- watchlist parity versus reports mode
- ticker count near reports mode
- market map count near reports mode
- decision trace populated
- action summary populated
- `readiness=READY` only when all required sections are complete
- parity audit reports remaining differences deterministically

Additional parity expectations:

- structured export should remain deterministic
- section counts should be stable for the same `signal_date` and taxonomy version
- warnings should be explicit when a section is intentionally unavailable


## 9. Migration Plan

Future migration work is required, but it is not implemented in this task.

Requirements for that future step:

- add migration under the existing migration convention
- preserve old data
- do not recreate removed `dc_dashboard_*` snapshot tables
- the new tables are enrichment tables inside `analysis.db`, not final published dashboard snapshot tables

Migration design note:

- snapshot publishing remains in `ecosystem_dashboard.db`
- enrichment remains in `analysis.db`


## 10. Rollout Plan

Stage 1:

- spec only

Stage 2:

- migration + empty/audit CLI

Stage 3:

- ticker enrichment writer

Stage 4:

- group enrichment writer

Stage 5:

- action summary + decision trace writer

Stage 6:

- analysis-db export reads enrichment tables

Stage 7:

- parity audit versus reports mode

Stage 8:

- scheduler switch only after parity acceptance

Reports mode remains the production reference and fallback until Stage 7 parity is acceptable and Stage 8 is explicitly approved.


## 11. Explicit Non-Goals

This spec does not authorize:

- `ecosystem_dashboard.db` schema changes
- HTML changes
- scheduler switch
- reports-mode removal
- `.md` report parsing as the future machine input path
- recreation of old `dc_dashboard_*` snapshot tables in `analysis.db`
- DB-13b implementation code in this task


## Appendix: Current V0 Gap Summary

Known `analysis.db` export V0 result for `2026-05-22`:

- `source_reports=1`
- `action_summary=0`
- `market_map=54`
- `watchlist=0`
- `tickers=236`
- `decision_trace=0`
- `readiness=PARTIAL`

Known V0 warnings:

- `ACTION_SUMMARY_SOURCE_NOT_AVAILABLE`
- `DECISION_TRACE_SOURCE_NOT_AVAILABLE`
- `WATCHLIST_SOURCE_NOT_AVAILABLE`
- `WINDOW_STATUS_ENRICHMENT_NOT_DIRECT_FROM_ANALYSIS_DB`

Interpretation:

- `analysis.db` already contains useful raw and analysis-level data
- it does not yet contain the dashboard-ready semantic enrichment layer required for full structured parity
