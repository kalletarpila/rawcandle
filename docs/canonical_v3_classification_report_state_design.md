# Canonical V3 Classification / Report-State Design

## 1. Purpose

Canonical V3 needs a dedicated classification/report-state layer because current V3 facts already cover:

- taxonomy and watchlist master data
- entity/window coverage and quality
- entity snapshots
- metrics
- signal observations and relevance
- ticker structure events
- layer/subindustry synthetic structure events

Those layers represent analytical facts well, but legacy Datacenter reports also contain decision semantics that are not just facts or measurements.

Examples:

- `daily_trigger_state`
- `rolling_2_sell_pressure_state`
- `rolling_5_pullback_state`
- `rolling_30_buy_state`
- `rolling_30_exit_state`
- `primary_reason`
- `blocking_reason`
- `risk_reason`
- `next_action`
- priority and ranking semantics

These are not naturally modeled as:

- one generic snapshot field
- one metric name/value row
- one signal observation
- one dated event

The largest current missing area is rolling30 decision content. Daily, rolling2, and rolling5 have partial state coverage through `eco_entity_window_snapshot.classification_state`, but V3 does not yet preserve the full decision payload that legacy reports expose.

The purpose of this design is to define a dedicated canonical V3 decision layer before implementation.


## 2. Current V3 Coverage Summary

Current accepted V3 coverage already includes:

- `eco_entity_window_snapshot` for entity/window summary state
- `eco_entity_metric_value` for numeric metric families
- `eco_signal_observation` and `eco_signal_relevance` for the technical relevance pilot
- `eco_entity_event` for ticker structure events and group synthetic structure events

Current snapshot classification coverage:

- `daily` classification state exists
- `rolling2` classification state exists
- `rolling5` classification state exists
- `rolling30` classification state is currently missing/null

Current missing decision semantics:

- `primary_reason`
- `blocking_reason`
- `risk_reason`
- `next_action`
- `priority_score`
- `priority_label`
- `sort_rank`

Conclusion:

- current V3 has strong factual foundations
- current V3 does not yet have a canonical decision-output layer


## 3. Design Decision

Recommended decision:

- add a dedicated V3 fact table named `eco_classification_decision`

Reasoning:

- classification/report-state is a first-class downstream analytical output
- it depends on metrics, snapshots, signals, relevance, and events
- it is not itself a raw metric family
- it contains mixed semantic payload:
  - state
  - reason
  - blocker/risk
  - action
  - priority/ranking

Why not overload `eco_entity_window_snapshot`:

- snapshot is already a compact entity/window summary row
- adding all classifier reasons, blockers, next-action, and ranking fields would turn snapshot into an overloaded report-output row
- one window can eventually have more than one classifier dimension

Why not overload `eco_entity_metric_value`:

- metric rows are better for scalar values
- reason/action payload is categorical and semantic, not metric-oriented
- priority/rank could fit numerically, but would fragment one decision across many rows

Why not overload `eco_signal_observation`:

- classifier decisions are not always source signal observations
- they are synthesized report-state outputs from multiple inputs

Why not overload `eco_entity_event`:

- classifier decisions are not naturally dated event history
- they are report-date/window anchored decisions


## 4. Proposed Table: `eco_classification_decision`

### Purpose

Store canonical decision/classification outputs for one entity/window/run/date/classifier combination.

This table is the canonical source of truth for:

- classification state
- primary reason
- blocking reason
- risk reason
- next action
- optional priority/ranking metadata

### Grain

`run_id / signal_date / taxonomy_version_id / window_code / entity_id / classification_type`

### Proposed Columns

- `classification_id INTEGER PRIMARY KEY`
- `run_id TEXT NOT NULL`
- `ecosystem_id INTEGER NOT NULL`
- `signal_date TEXT NOT NULL`
- `taxonomy_version_id INTEGER NOT NULL`
- `window_code TEXT NOT NULL`
- `entity_id INTEGER NOT NULL`
- `classification_type TEXT NOT NULL`
- `classification_state TEXT NOT NULL`
- `primary_reason TEXT NULL`
- `blocking_reason TEXT NULL`
- `risk_reason TEXT NULL`
- `next_action TEXT NULL`
- `priority_score REAL NULL`
- `priority_label TEXT NULL`
- `sort_rank INTEGER NULL`
- `source_classifier TEXT NULL`
- `classification_version TEXT NULL`
- `source_run_id TEXT NULL`
- `created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP`
- `updated_at_utc TEXT NULL`

### Suggested Uniqueness

`UNIQUE(run_id, signal_date, taxonomy_version_id, window_code, entity_id, classification_type)`

### Suggested Foreign Keys

- `run_id -> eco_report_run.run_id`
- `ecosystem_id -> eco_ecosystem.ecosystem_id`
- `taxonomy_version_id -> eco_taxonomy_version.taxonomy_version_id`
- `window_code -> eco_report_window.window_code`
- `entity_id -> eco_entity.entity_id`

### Supported `classification_type` Values

- `daily_trigger`
- `rolling2_sell_pressure`
- `rolling5_pullback`
- `rolling30_buy`
- `rolling30_exit`

### Suggested Indexes

- `(run_id, window_code, classification_type)`
- `(entity_id, signal_date, classification_type)`
- `(classification_type, classification_state)`
- `(window_code, classification_type, sort_rank)`

### Enum / Check Guidance

Use check constraints conservatively.

Recommended:

- constrain `classification_type`
- do not hard-constrain `classification_state` initially across all classifiers, because states differ materially by classifier family
- leave `next_action` as unconstrained `TEXT` initially
- leave `priority_label` as unconstrained `TEXT` initially unless one stable canonical enum is clearly accepted

### Nullability Guidance

- `classification_state` must be non-null
- `primary_reason` should usually be populated when a classifier exists, but nullable for forward compatibility
- `blocking_reason` and `risk_reason` should remain nullable because only some classifiers emit them
- `next_action` should remain nullable because not all horizons currently emit it
- `priority_score`, `priority_label`, and `sort_rank` should remain nullable until a stable ranking policy is finalized


## 5. Relationship to Existing V3 Tables

### `eco_report_run`

- anchors the operational run identity
- classification decisions are run-scoped facts

### `eco_entity`

- classification decisions attach to a canonical entity
- initial scope is expected to be mainly `TICKER`, but schema should not hard-code that forever

### `eco_report_window`

- classifier semantics are window-specific
- `daily_trigger` belongs to `daily`
- `rolling2_sell_pressure` belongs to `rolling2`
- `rolling5_pullback` belongs to `rolling5`
- `rolling30_buy` and `rolling30_exit` belong to `rolling30`

### `eco_entity_window_snapshot`

- snapshot stores compact entity/window summary state
- classification decision table stores full classifier output semantics

### `eco_entity_metric_value`

- classifier builders consume metric values
- decision rows should not duplicate all input metrics

### `eco_signal_observation` and `eco_signal_relevance`

- classifiers may use signal/relevance context
- decision rows should reference the classifier output, not duplicate every source signal

### `eco_entity_event`

- classifiers may use structure/BOS/reset event context
- decision rows should remain separate from event history

Conclusion:

- `eco_classification_decision` depends on existing V3 state
- it does not replace snapshots, metrics, signals, relevance, or events
- it stores decision outputs only


## 6. Relationship to Snapshots

Recommended policy:

- keep `eco_entity_window_snapshot.classification_state` as a compact summary/convenience field
- make `eco_classification_decision` the canonical source for decision semantics

Implications:

- quick entity/window inspection can still read snapshot state
- reports, query layers, and parity-sensitive logic should use `eco_classification_decision` for:
  - `primary_reason`
  - `blocking_reason`
  - `risk_reason`
  - `next_action`
  - `priority_score`
  - `priority_label`
  - `sort_rank`

Suggested mirroring policy:

- the primary classifier state for a window may be mirrored into snapshot
- full decision payload must live in `eco_classification_decision`


## 7. Source Mapping by Report Horizon

### A. Daily

Expected `classification_type`:

- `daily_trigger`

Accepted V3-native runtime sources after `DB-V3-48c`:

- `dc_ticker_swing_signal_daily`
- `dc_group_swing_signal_daily`
- `eco_entity_coverage`
- `eco_entity`

Explicitly excluded runtime sources after `DB-V3-48c`:

- `dc_report_classification_v2`
- `dc_report_context_daily_v2`
- generated Markdown reports
- generated CSV reports

Accepted semantic policy after `DB-V3-48c`:

- V3-native `daily_trigger` uses current lower-level source truth.
- frozen V2 parity is not required when source drift is explicitly reported and accepted.
- coverage-complete V3 behavior is preferred over preserving the old frozen row count.
- dormant relevance-class fields remain `NULL` in this step.
- `priority_score`, `priority_label`, and `sort_rank` remain `NULL`.

Expected mapped fields:

- `classification_state`
- `primary_reason`
- `blocking_reason`
- `next_action`
- optional priority fields if present

### B. Rolling2

Expected `classification_type`:

- `rolling2_sell_pressure`

Likely sources:

- `dc_report_classification_v2` where `horizon = 'rolling2'`
- `rolling2_sell_pressure_classifier.py` contract if a direct V2 classification row is not sufficient
- `dc_report_context_window_v2` and supporting state as classifier inputs

Expected mapped fields:

- `classification_state`
- `primary_reason`
- `risk_reason`
- `next_action`

### C. Rolling5

Expected `classification_type`:

- `rolling5_pullback`

Likely sources:

- `dc_report_classification_v2` where `horizon = 'rolling5'`
- `rolling5_pullback_classifier.py` contract if direct V2 classification rows are incomplete

Expected mapped fields:

- `classification_state`
- `primary_reason`
- `blocking_reason`
- `next_action`

### D. Rolling30

Expected `classification_type` values:

- `rolling30_buy`
- `rolling30_exit`

Likely sources:

- `dc_report_classification_v2` where `horizon = 'rolling30'`
- `rolling30_watchlist_classifier.py`
- window context rows and existing V2 classifier output rows

Expected mapped fields:

- buy side:
  - `classification_state`
  - `primary_reason`
  - `blocking_reason`
  - optional priority fields
- exit side:
  - `classification_state`
  - `primary_reason`
  - `risk_reason`
  - optional priority fields

### Source Note

Documentation and classifier contracts indicate that V2 already treats classification as a distinct canonical layer through `dc_report_classification_v2`. That strongly supports building V3 decision rows from canonical V2 classification rows first, instead of re-running classifier logic unless necessary.

Exception after `DB-V3-48c`:

- `daily_trigger` is no longer planned around runtime dependence on `dc_report_classification_v2`.
- `daily_trigger` is explicitly accepted as a V3-native lower-level reconstruction path.
- frozen V2 payload remains useful for smoke/delta reporting, but not as the runtime source of truth.


## 8.1 Daily Trigger V3-Native Source-Truth Decision

Decision record:

- task: `DB-V3-48c`
- date: `2026-06-03`

Scope:

- target table: `eco_classification_decision`
- `classification_type = daily_trigger`
- `window_code = daily`
- `entity_type = TICKER`

Accepted runtime sources:

- `dc_ticker_swing_signal_daily`
- `dc_group_swing_signal_daily`
- `eco_entity_coverage`
- `eco_entity`

Explicitly excluded runtime sources:

- `dc_report_classification_v2`
- `dc_report_context_daily_v2`
- generated Markdown reports
- generated CSV reports

Accepted semantic policy:

- V3-native `daily_trigger` uses current lower-level source truth.
- frozen V2 parity is not required when source drift is explicitly reported and accepted.
- coverage-complete V3 behavior is preferred over preserving the frozen legacy row count.
- no compatibility mode is required to reproduce frozen V2 `daily_trigger` exactly.
- no new relevance sourcing is introduced in this step.
- dormant relevance-class fields remain `NULL`.
- `priority_score`, `priority_label`, and `sort_rank` remain `NULL`.

Accepted `CRGY` policy:

- if daily coverage exists but the lower-level ticker row is missing, `daily_trigger` is materialized as:
  - `INSUFFICIENT_DATA`
  - `MISSING_PRICE_CONTEXT`
  - `WAIT_FOR_DATA`
- this intentionally changes `daily_trigger` row count from `236` to `237`
- coverage-complete V3 behavior is preferred over silently omitting the row

Accepted `NXPI` source-drift policy:

- changed classification caused by lower-level source drift is accepted
- frozen V2 `NXPI` output is not preserved by force
- known accepted example:
  - frozen V2 / old production:
    - `BUY_WATCH`
    - `BULLISH_SETUP_NEEDS_CONFIRMATION`
    - `next_action = MONITOR_FOR_DAILY_CONFIRMATION`
  - V3-native lower-level rebuild:
    - `SELL_TRIGGER`
    - `DAILY_SELL_TRIGGER`
    - `blocking_reason = BEARISH_DAILY_SIGNAL`
    - `next_action = REVIEW_SELL_OR_TIGHTEN_STOP`

Expected production effect after future daily production replacement:

- `daily_trigger` expected row count:
  - old frozen production = `236`
  - expected V3-native = `237`
- `eco_classification_decision` expected total row count:
  - old total = `1180`
  - expected new total = `1181`
- `rolling2_sell_pressure`, `rolling5_pullback`, `rolling30_buy`, and `rolling30_exit` remain unchanged

Guardrails for the future production run:

- take a backup first
- verify the exact production DB path before write
- perform immediate post-run verification
- report row-count delta explicitly
- verify `CRGY` materialized as expected
- verify `NXPI` changed as expected
- verify no forbidden table changes
- verify no duplicate rows
- verify no orphan rows
- verify no coverage drift

Non-goals:

- no compatibility mode to preserve frozen V2 `daily_trigger` exactly
- no new relevance sourcing in this step
- no priority/rank logic
- no generated report parsing


## 8. Builder Strategy

Recommended staged implementation sequence:

1. `DB-V3-24`
   - add schema for `eco_classification_decision`
   - add indexes and constraints narrowly

2. `DB-V3-25`
   - implement V3 classification decision builder for:
     - `daily_trigger`
     - `rolling2_sell_pressure`
     - `rolling5_pullback`
   - prefer sourcing from `dc_report_classification_v2`
   - mirror primary state into snapshot only if explicitly desired

3. `DB-V3-26`
   - implement rolling30 decision builder for:
     - `rolling30_buy`
     - `rolling30_exit`
   - verify whether V2 classification rows already hold the required payload

4. `DB-V3-27`
   - smoke test on production DB copy

5. `DB-V3-28`
   - controlled production run

6. `DB-V3-29`
   - read-only production audit of V3 classification decision output

Recommended implementation preference:

- use canonical V2 classification rows where they already contain classifier output payload
- avoid re-running legacy classifiers inside V3 unless a required field is missing from V2 canonical rows


## 9. Open Questions

Before schema implementation, these questions should be answered:

1. Does `dc_report_classification_v2` already contain all required fields for every horizon:
   - `classification_state`
   - `primary_reason`
   - `blocking_reason`
   - `risk_reason`
   - `next_action`
   - `candidate_priority`
   - `candidate_priority_label`

2. Are `rolling30_buy` and `rolling30_exit` already represented as separate rows in `dc_report_classification_v2`, or do they need explicit split logic?

3. Should `priority_score` map directly from `candidate_priority` if present, or should V3 treat V2 priority as renderer-oriented and optional?

4. Should `classification_state` remain unconstrained `TEXT` initially because states differ by classifier family?

5. Should `next_action` remain free-text `TEXT`, or should V3 later define a compact enum?

6. Should `sort_rank` be stored canonically, or should ranking remain a query/renderer concern unless a stable ranking contract exists?

7. Should decision rows exist for every entity/window, or only for entities where a classifier was actually evaluated and emitted?

8. If snapshot mirroring remains, what is the exact policy when one window has more than one classifier dimension in future?


## 10. Non-goals

This task does not:

- create schema
- create migrations
- implement builders
- write to production
- modify existing V3 builders
- change V2 schema
- render reports
- integrate scheduler/dashboard behavior
- define full rendering/query behavior

This document is design-only and exists to guide the next schema and builder phases.
