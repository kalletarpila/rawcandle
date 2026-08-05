# Datacenter V2 First Scheduled Run EC Bridge Fix

## Summary

The first normal scheduled run after `DC_TAXONOMY_FULL_V2` activation completed
the Datacenter side of the pipeline, but the transitional EC bridge refused the
required historical backfill.

Final implementation classification:

```text
DATACENTER_V2_FIRST_RUN_COMPATIBILITY_FIXES_IMPLEMENTED
```

## First Scheduled Run Evidence

Run summary:

```text
summary=logs/stock_update_scheduler_summary_20260805T023003Z.json
started_at=2026-08-05T02:30:03Z
finished_at=2026-08-05T05:16:39Z
resolved_signal_date=2026-08-04
overall_status=OK_WITH_WARNINGS
```

Datacenter ran with:

```text
taxonomy_version=DC_TAXONOMY_FULL_V2
taxonomy_sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
```

DC materialization reached `2026-08-04`:

```text
ticker rows=257
group-signal rows=54
synthetic-OHLC rows=53
group-index rows=54
```

Stage 2 used incremental execution:

```text
incremental=true
plan=NEW_SIGNAL_DATES_WITH_LOOKBACK_OVERLAP
materialized_range=2026-07-27..2026-08-04
```

## Defects Fixed

The EC refresh/backfill planners still contained V1 taxonomy-count assumptions:

```text
row_count=329
ticker_count=236
```

The scheduler Datacenter command construction also passed the V1 ticker count to
the audit path:

```text
--expected-ticker-count 236
```

Finally, the Scheduler UI taxonomy inspect path used the obsolete membership
column:

```text
ec_membership.entity_id
```

The current canonical membership schema uses:

```text
ec_membership.child_entity_id
```

## Dynamic Taxonomy Contract

Normal execution no longer depends on V1 row or ticker constants. Expected
counts are derived from the configured taxonomy CSV and compared with loaded
taxonomy metadata.

The scheduler now derives:

```text
configured_taxonomy_version
configured_taxonomy_csv
configured_taxonomy_sha256
derived_taxonomy_row_count
derived_ticker_count
derived_group_count
derived_synthetic_group_count
```

For V2 these resolve to:

```text
derived_taxonomy_row_count=350
derived_ticker_count=257
derived_group_count=54
derived_synthetic_group_count=53
```

The EC planner still blocks malformed or mismatched taxonomy sources:

```text
configured/internal version mismatch
source SHA mismatch
loaded taxonomy metadata mismatch
duplicate membership keys
invalid primary membership coverage
missing current membership schema
```

## Schema Compatibility Policy

The taxonomy inspect path uses:

```text
CURRENT_SCHEMA_ONLY
```

It expects `ec_membership.parent_entity_id`, `ec_membership.child_entity_id`, and
`ec_membership.taxonomy_version_id`. Missing required current-schema columns are
reported as structured blocking errors instead of being silently ignored.

## Scheduler Status Policy

The existing scheduler policy is preserved:

```text
DC pipeline OK + required EC bridge failure => overall_status=OK_WITH_WARNINGS
```

The scheduler summary now exposes the chain status separately:

```text
datacenter_dc_status
datacenter_ec_status
datacenter_ec_retry_required
datacenter_taxonomy_version
datacenter_failed_component
datacenter_safe_next_action
```

An EC bridge failure therefore remains visible even when the scheduler process
itself completes.

## EC-Only Recovery Readiness

No production recovery was executed in this task.

Read-only planning confirms the failed range can be recovered without rerunning
Datacenter:

```text
DC rerun required=false
EC recovery required=true
EC required start=2026-07-27
EC required end=2026-08-04
taxonomy source status=OK
retry safe=true
```

The controlled recovery task should run the existing EC backfill for:

```text
2026-07-27..2026-08-04
```

using:

```text
taxonomy_version=DC_TAXONOMY_FULL_V2
taxonomy_csv=data/datacenter_taxonomy_full_v2.csv
watchlist=watchlists/datacenter_watchlist.txt
allow_replace_existing=true
```

It should then run coverage and parity checks, advance canonical EC heads and
watermarks to `2026-08-04`, leave DC facts and DC watermarks unchanged, and write
no V1 EC rows.

## Decision Summary Warning

The first V2 run skipped the decision summary because the previous V2 daily
report did not yet exist:

```text
decision_summary.skip_reason=missing_previous_daily
```

Classification:

```text
EXPECTED_FIRST_VERSION_RUN_EDGE
```

This is unrelated to the EC bridge blocker.

## Safety

This fix did not run production Scheduler, Datacenter pipeline, Stage 2, EC
refresh/backfill/recovery, taxonomy operations, migrations, production DB writes,
config writes, backups, restores, or unrelated cleanup.
