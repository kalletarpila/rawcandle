# EC Ticker Fact Loader Taxonomy Scope

## Classification

```text
EC_TICKER_FACT_LOADER_TAXONOMY_SCOPE_FIXED
```

## Confirmed Bug

The DATACENTER EC V2 taxonomy rebuild failed in
`load_ec_ticker_signal_daily_from_dc` because the ticker source query selected
`dc_ticker_swing_signal_daily` rows by only:

```sql
WHERE signal_date = ?
  AND signal_version = ?
```

During the V2 rebuild, active V1 and proposed V2 source rows coexisted for
`2025-08-01` and `DC_SWING_SIGNAL_V1`:

```text
V1 rows=236
V2 rows=257
mixed selected rows=493
mixed distinct tickers=272
```

The target context was V2, so V1-only tickers had no V2 primary membership and
the loader returned `FAILED` before inserts.

## Fixed Contract

The loader now uses one explicit taxonomy context for source selection, signal
version resolution, target taxonomy ID, and membership mapping.

Source rows are selected by:

```sql
WHERE signal_date = ?
  AND signal_version = ?
  AND taxonomy_version = ?
```

Signal-version auto-resolution is scoped by:

```text
signal_date
taxonomy_version
```

If the caller provides a signal version, the loader validates that rows exist
for the requested taxonomy/date/signal scope.

## Source And Mapping Validation

Before mapping or insert, the loader reports and enforces:

```text
requested_taxonomy_version
source_taxonomy_version
source_taxonomy_match
source_row_count
source_distinct_ticker_count
duplicate_source_ticker_count
unexpected_taxonomy_version_count
```

Before insert, the loader reports and enforces:

```text
mapped_row_count
unresolved_membership_count
unresolved_tickers
duplicate_target_key_count
null_target_key_count
```

Duplicate source ticker rows inside the requested taxonomy/signal scope are
blocking. Unresolved ticker entities or primary memberships are blocking.
Duplicate or null target keys are blocking. Failed mapping validation returns a
structured `FAILED` summary before writes.

## Failure Propagation

`run_ec_source_layer_backfill` preserves ticker-loader failure details in the
single-range summary:

```text
loader_status
loader_error
loader_error_code
source_taxonomy_version
source_row_count
source_distinct_ticker_count
unexpected_taxonomy_version_count
unresolved_membership_count
unresolved_tickers
duplicate_source_ticker_count
duplicate_target_key_count
ticker_loader_summary
```

The taxonomy full-rebuild orchestrator stores that backfill summary in failed
chunk progress evidence. This prevents the root cause from being reduced to only
`Ticker fact loader returned FAILED`.

## Retry Safety

The failed production retry left:

```text
V2 EC canonical rows=0
completed chunk count=0
EC canonical watermarks unchanged
deployment ec_rebuild_status=FAILED
V2 inactive
V1 active
```

No restore or cleanup is required before a later guarded retry after this code
fix. The retry should reuse the same deployment, accepted V2 DC range, and
original pre-DC-rebuild backup.

No production EC rebuild, scheduler run, Datacenter pipeline, activation,
watermark update, migration, production DB write, new full backup, or taxonomy
CSV/watchlist edit occurred as part of this code-fix task.
