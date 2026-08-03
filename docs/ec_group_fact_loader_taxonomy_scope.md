# EC Group Fact Loader Taxonomy Scope

## Classification

```text
EC_GROUP_FACT_LOADER_TAXONOMY_SCOPE_FIXED
```

## Confirmed Bug

The DATACENTER EC V2 taxonomy full rebuild failed in `ec_group_signal_daily`
because the group fact loader selected source rows by `signal_date` and
`signal_version` only. During the V2 rebuild, V1 and V2 `dc_group_*` rows
coexisted for the same date and signal version, so the loader selected both
taxonomies and attempted to insert them into the V2 target taxonomy scope.

The failing target key was:

```text
ecosystem_id
taxonomy_version_id
signal_date
entity_id
signal_version
```

For the incident date, the mixed source produced:

```text
V1 source rows=54
V2 source rows=54
loader-selected rows=108
distinct target keys=54
duplicate target keys=54
```

The V2-only source was valid:

```text
source_row_count=54
mapped_row_count=54
distinct_target_key_count=54
duplicate_target_key_count=0
unresolved_group_count=0
```

## Fixed Contract

`ec_group_signal_daily` loading now uses the requested taxonomy version for:

```text
signal-version resolution
source row selection
target taxonomy_version_id resolution
source validation diagnostics
target duplicate-key validation
structured failure summaries
```

The source predicate is:

```text
signal_date
signal_version
taxonomy_version
```

The loader does not infer the source taxonomy from the active scheduler
taxonomy. Ordinary V1 calls continue to pass and use V1 explicitly through the
existing default argument.

## Diagnostics

The loader reports deterministic source diagnostics before mapping:

```text
requested_taxonomy_version
source_taxonomy_version
source_taxonomy_match
source_row_count
source_distinct_group_count
duplicate_source_group_count
unexpected_taxonomy_version_count
unexpected_signal_version_count
null_required_source_key_count
group_type_counts
data_quality_status_counts
```

It also validates mapped target keys before insert:

```text
mapped_row_count
distinct_target_key_count
duplicate_target_key_count
null_target_key_count
unresolved_group_count
unresolved_groups
multiple_source_to_same_target_count
```

Validation failures return structured `FAILED` summaries. SQL insert failures
are caught inside the group-loader transaction, rolled back, and returned with
the original SQLite error text.

## Backfill Propagation

`run_ec_source_layer_backfill` preserves `group_loader_summary` and the
important flattened diagnostics in failed summaries. The taxonomy full-rebuild
orchestrator stores the same summary in chunk progress JSON and includes the
group loader error fields in rendered output.

## Retry Safety

The production partial state from the failed retry was ticker-only for V2 on
`2025-08-01`. It does not require cleanup before the next controlled retry
because canonical loader replacement is scoped by:

```text
ecosystem_id
taxonomy_version_id
signal_date
signal_version
```

This scoped delete-and-replace contract is idempotent for the partial V2 date
and does not touch V1 or other ecosystems.

## Deferred Hardening

The current canonical loaders commit independently. A future improvement is a
per-date transaction boundary:

```text
ticker + group + synthetic + index for one signal date
-> all succeed or all rollback
```

That requires a broader loader transaction refactor and was intentionally
deferred. The required minimum for the next retry is taxonomy-scoped source
selection, structured diagnostics, duplicate prevalidation, and idempotent
replace behavior.

No production EC rebuild, scheduler run, Datacenter pipeline, activation,
watermark update, production DB write, cleanup, restore, new backup, taxonomy
CSV change, or watchlist change occurred as part of this fix.
