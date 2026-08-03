# EC Synthetic And Group Index Loader Taxonomy Scope

## Classification

```text
EC_SYNTHETIC_OHLC_LOADER_TAXONOMY_SCOPE_FIXED
```

## Confirmed Synthetic Root Cause

The fourth controlled DATACENTER EC V2 full-rebuild retry failed on
`2025-08-01` with a uniqueness violation in
`ec_group_synthetic_ohlc_daily`.

Read-only reconstruction confirmed the source-scope defect:

```text
dc_group_synthetic_ohlc_daily
date=2025-08-01
calc_version=<same selected calc version>

V1 source rows=53
V2 source rows=53
loader-selected rows before fix=106
distinct source groups=53
distinct target keys=53
duplicate target-key count=53
```

The V2-only source set was valid:

```text
layers=16
subindustries=37
source_row_count=53
source_distinct_group_count=53
```

The failure classification is therefore:

```text
SYNTHETIC_LOADER_MISSING_TAXONOMY_PREDICATE
```

It was not classified as a source duplicate, entity mapping collision, uncleared
target scope, or pre-existing target-row problem.

## Fixed Source Contract

`ec_group_synthetic_ohlc_daily` now scopes automatic calc-version resolution by:

```text
ohlc_date
taxonomy_version
```

Caller-supplied `ohlc_calc_version` is accepted only if rows exist inside:

```text
ohlc_date
calc_version
taxonomy_version
```

Source rows are selected by:

```text
ohlc_date
calc_version
taxonomy_version
```

The loader no longer resolves V2 calc version or V2 source rows from active V1
Datacenter rows.

## Source And Mapping Diagnostics

The synthetic loader now reports deterministic source diagnostics:

```text
requested_taxonomy_version
source_taxonomy_version
source_taxonomy_match
source_row_count
source_distinct_group_count
duplicate_source_group_count
unexpected_taxonomy_version_count
unexpected_calc_version_count
null_required_source_key_count
group_type_counts
data_quality_status_counts
```

Before insert, it validates mapped target keys:

```text
mapped_row_count
distinct_target_key_count
duplicate_target_key_count
null_target_key_count
unresolved_group_count
unresolved_groups
multiple_source_to_same_target_count
```

Blocking failures return structured `FAILED` summaries before insert when
source scope is unavailable, calc-version resolution is ambiguous, source keys
are duplicated or null, entity mapping is unresolved, or target keys are
duplicated or null. SQLite insert failures are caught inside the loader
transaction, rolled back, and returned with the original SQLite error.

## Group Index Review And Fix

The group-index loader had the same class of missing taxonomy scope. It now
scopes calc-version resolution and source selection by:

```text
index_date
calc_version
taxonomy_version
```

It returns equivalent source diagnostics, target-key validation diagnostics,
structured failure summaries, and SQL rollback behavior. Focused tests cover
V1/V2 mixed-source rows sharing date and calc version for both synthetic OHLC
and group index.

## Backfill And Orchestrator Propagation

`run_ec_source_layer_backfill` now preserves failed synthetic and group-index
loader summaries:

```text
synthetic_loader_summary
group_index_loader_summary
loader_error_code
duplicate_source_group_count
duplicate_target_key_count
unresolved_groups
```

The taxonomy full-rebuild orchestrator stores that backfill summary in
`ec_taxonomy_full_rebuild_progress.json`, so the failed chunk preserves the
deepest loader error instead of collapsing the failure into only a generic
backfill error.

## Retry Safety

Future controlled retry from the current partial production date is expected to
be idempotent without manual cleanup:

```text
existing V2 ticker rows for 2025-08-01       -> replaced by ticker loader
existing V2 group signal rows for 2025-08-01 -> replaced by group loader
synthetic V2 rows for 2025-08-01             -> inserted or replaced by synthetic loader
group index V2 rows                          -> inserted or replaced by index loader
```

The taxonomy rebuild predelete and per-loader replace scopes include:

```text
ecosystem_id
taxonomy_version_id
signal_date
```

Loader-specific replace scopes also include `signal_version` or `calc_version`.
This prevents a V2 retry from deleting V1 rows or another ecosystem.

## Per-Date Atomicity Assessment

The current canonical EC loaders still own independent transactions. Adding a
single transaction across ticker, group signal, synthetic OHLC, and group index
would require changing loader connection ownership and transaction boundaries.
That is broader than this targeted taxonomy-scope repair.

The compensating contract for this fix is:

```text
per-loader transaction rollback on failure
structured failure evidence
no watermark finalization after failure
idempotent taxonomy-scoped retry
```

Full per-date atomicity remains a separate hardening task.

No production EC rebuild, scheduler run, Datacenter pipeline, Stage 2 run,
activation, watermark update, production DB cleanup, restore, new backup,
taxonomy CSV edit, or watchlist edit occurred as part of this fix.
