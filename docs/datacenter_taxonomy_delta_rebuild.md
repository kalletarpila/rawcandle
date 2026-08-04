# Datacenter Taxonomy Delta Rebuild

## Classification

```text
DATACENTER_TAXONOMY_DELTA_REBUILD_IMPLEMENTED
```

No production taxonomy change, scheduler run, Datacenter pipeline run, EC loader,
cleanup, finalization, activation, migration apply, production DB write,
production config write, production backup, restore, taxonomy CSV edit, or
watchlist edit occurred as part of this implementation.

## Purpose

The delta backend lets the unified taxonomy-change orchestrator construct a
complete proposed Datacenter fact state without recalculating every unchanged
ticker and group history for ordinary monthly taxonomy changes.

The invariant is:

```text
new taxonomy version = carried-forward unchanged rows
                     + recalculated affected rows
                     - removed rows
```

The target proposed taxonomy must still pass the same completeness, coverage,
parity, cleanup, watermark, and activation gates as a full rebuild.

## Supported Changes

Delta mode supports:

```text
added ticker
removed ticker
primary membership change
secondary membership add
secondary membership removal
scope flag change
```

The monthly delta assumption is that layer and subindustry vocabularies remain
stable.

## Safety Gates

Explicit `DELTA_REBUILD` is blocked when structural incompatibility is detected:

```text
added layer
removed layer
added subindustry
removed subindustry
renamed layer
renamed subindustry
group semantic incompatibility
```

`AUTO` selects `DELTA_REBUILD` only when delta is safe. Otherwise it selects
`FULL_REBUILD`. The persisted execution mode is always explicit.

## Affected Scope

The planner derives deterministic sorted lists for:

```text
affected_tickers
unaffected_tickers
affected_groups
unaffected_groups
membership_changed_tickers
scope_flag_changed_tickers
```

Affected groups are the union of old and new memberships for added, removed, and
membership-changed tickers. Scope-only changes affect ticker classification but
do not dirty group histories by themselves.

Each ticker receives a structured classification:

```text
ticker
change_types
old_scope_flag
new_scope_flag
old_primary_group
new_primary_group
old_secondary_groups
new_secondary_groups
affected_groups
ticker_history_action
```

Ticker actions are:

```text
REBUILD_NEW_TICKER
COPY_UNCHANGED_TICKER_HISTORY
OMIT_REMOVED_TICKER
```

## Date Policy

The current backend uses the requested historical range for:

```text
ticker_history_range
group_history_range
downstream_history_range
validation_range
```

Added ticker history is rebuilt for the requested range. Affected groups are
rebuilt for the requested range. Unaffected ticker and group facts may be
carried forward for the requested range when table-level safety checks pass.

Stage 2's regular signal planner already distinguishes output dates from its
input warmup through the existing bounded 220-valid-price-row preload. This
delta backend does not change that Stage 2 calculation contract.

## Carry-Forward Contract

Carry-forward is allowed only when all of these hold:

```text
source taxonomy is the active/current taxonomy
target taxonomy is the proposed taxonomy
source and target versions differ
copy scope is explicit and deterministic
target range is exact
table has taxonomy_version lineage
target rows are replaced only inside the confirmed scope/range
projected duplicate target keys are blocked
operation is idempotent
row counts and hashes are returned as evidence
```

For ticker facts, `taxonomy_version`, `primary_layer`, and
`primary_subindustry` are rewritten to the proposed taxonomy. The technical
price-derived fields are copied. Added tickers are not copied. Removed tickers
are not represented in the proposed rows.

The implemented carry-forward helper is intentionally scoped to canonical DC
fact tables with explicit `taxonomy_version` columns:

```text
dc_ticker_swing_signal_daily
dc_group_swing_signal_daily
dc_group_synthetic_ohlc_daily
dc_group_index_daily
```

Unsupported or absent tables are skipped explicitly in the evidence result.

## Dependency Map

Planner output classifies relevant components as:

```text
dc_ticker_swing_signal_daily -> REBUILD_AFFECTED_TICKERS plus safe copy
dc_group_swing_signal_daily -> REBUILD_AFFECTED_GROUPS
dc_group_synthetic_ohlc_daily -> REBUILD_AFFECTED_GROUPS
dc_group_index_daily -> REBUILD_AFFECTED_GROUPS
derived Stage 5-9 group components -> REBUILD_AFFECTED_GROUPS
technical relevance and reports -> REBUILD_FULL_DATE
EC canonical tables -> REBUILD_FROM_COMPLETE_PROPOSED_DC_STATE
coverage/parity/watermarks -> REVALIDATE_ONLY
```

Confirmed code evidence: Stage 2 reads the taxonomy for primary ticker universe
and primary group metadata, while technical metrics are calculated from price
history and enrichment sources. Group components consume taxonomy memberships
and therefore require affected-group recalculation.

## EC Construction

EC construction remains a transitional bridge:

```text
completed proposed DC state -> existing canonical DC-to-EC loaders
```

The delta backend does not introduce a permanent DC-specific EC sync-debt schema.
Future EC architecture should derive ecosystem facts directly from raw or shared
source layers, not from Datacenter tables as a permanent source model.

## Validation

Delta output must prove proposed-version completeness across the requested
range:

```text
proposed tickers represented by data-quality policy
removed tickers absent
proposed groups represented
removed groups absent
duplicate keys zero
taxonomy purity
fact-head completeness
coverage accepted
parity accepted
mismatch count zero
stale rows zero
watermark readiness
```

The optional compact fixture comparison target is:

```text
FULL_REBUILD output == DELTA_REBUILD output
delta_vs_full_total_mismatch_count=0
```

## Resume And Failure Policy

The execution facade reports completed phases and does not silently fall back to
full rebuild after a delta failure. A full fallback requires a new confirmed
plan.

Delta phases include:

```text
DELTA_SCOPE_PLANNED
DELTA_CARRY_FORWARD
AFFECTED_TICKERS_BUILT
AFFECTED_GROUPS_BUILT
DOWNSTREAM_BUILT
DC_DELTA_VALIDATED
EC_DELTA_BUILT
COVERAGE_PARITY_VALIDATED
READY_TO_ACTIVATE
```

`READY_TO_ACTIVATE` and `ACTIVE` remain no-op states for rebuild execution.

## UI-Facing Fields

Preparation and inspection consumers can show:

```text
requested_rebuild_mode
recommended_rebuild_mode
selected_rebuild_mode
delta_safe
delta_blocking_reasons
delta_scope_summary
dependency_map
estimated_delta_work
estimated_full_work
safe_next_action
```
