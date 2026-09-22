# Phase 13G.3.25: Stable read-only source bundle foundation

## Result and scope

Phase 13G.3.25 adds a versioned, adapter-ready `StableReadOnlySourceBundle`
foundation and proves the compact **market** read closure against fixture-sized
full SQLite copies. It does not change any existing workflow caller.

The scope was corrected during implementation: taxonomy is not packaged in the
compact bundle. It is represented by a separate source-policy binding with its
active version and semantic fingerprint. A direct taxonomy read is a candidate
only while the taxonomy mutation lock is held, and it remains marked
`runtime_authorized=false` because coverage of every taxonomy writer by that lock
has not yet been proven. The full SQLite taxonomy copy remains the authority and
fallback.

`No Production/Test caller uses the compact bundle by default in Phase 13G.3.25.`

`The existing full SQLite source-copy path remains the runtime authority until caller migration and production-parity acceptance are complete.`

## Versioned contract

The implementation is in
`rawcandle/fundamentals/admin/source_bundle.py` and uses source contract
`FUNDAMENTALS_READ_ONLY_SOURCE_V1`.

The module exposes:

- `StableReadOnlySourceBundle`, which points to one immutable compact market DB
  and its manifest;
- `ReadOnlySourceMode.STABLE_SOURCE_BUNDLE` and
  `ReadOnlySourceMode.FULL_SQLITE_BACKUP` for an explicit future caller choice;
- `TaxonomySourceMode.DIRECT_LOCKED_READ` and
  `TaxonomySourceMode.FULL_SQLITE_BACKUP`;
- centralized `MARKET_READ_CLOSURE` and `TAXONOMY_READ_CLOSURE` registries;
- construction and validation functions that fail closed on schema, drift,
  integrity, coverage, or physical fingerprint errors.

There is no automatic fallback to a live multi-connection read. Existing callers
continue to invoke the unchanged online-backup path.

## Proven market read closure

The compact market DB has reader-compatible `ticker_meta`, `osakedata`, and
`splits_data` tables. The registered closure is:

| Reader need | Included rows |
|---|---|
| V2 split normalization | All `splits_data` rows |
| Classification and peer fingerprint | All consumed `ticker_meta` columns and rows |
| Filing-date valuation | Latest valid exact-ticker OHLC row on or before every non-null V4 TTM availability date; null availability is explicit `NO_CUTOFF` evidence |
| RV current-price input | Exact-ticker and case-folded last 32 OHLC rows on or before the as-of date |
| Snapshot current-price input | Case-folded last 32 OHLC rows on or before the as-of date |
| Rebuild validation source state | Complete price history for the deterministic snapshot-validation sample ticker |

Rows selected by more than one rule are deduplicated by `osakedata.id`. A reused
ID with different content fails closed. The canonical binding includes all V4 TTM
price requirements, relevant recent-window tickers, the validation sample ticker,
the as-of date, and the source-contract version.

Each TTM requirement receives one deterministic coverage status:
`PRICE_FOUND`, `NO_MATCHING_VALID_PRICE`, `NO_TICKER`, or `NO_CUTOFF`. The
manifest records counts and a sorted TTM-ID fingerprint for every status. An
accepted absence is therefore bound evidence, not a silently dropped row.

Case-folded readers are supported by discovering physical `osake` spellings once
through the covering ticker/date index and then issuing exact-ticker indexed
window queries. Multiple spellings are retained when their date/value histories
are compatible. Conflicting OHLC values for the same normalized ticker and date
fail with `READ_ONLY_SOURCE_CASEFOLD_PRICE_CONFLICT`.

The complete validation-sample ticker history is intentionally retained in V1 of
the compact contract. The existing snapshot source-state reader asks for
`COUNT(*)`, `MAX(pvm)`, and `MAX(id)` over that history. Replacing that query with
compact metadata is deferred until callers can consume a versioned adapter.

`operating_income_v2.reporting` is not part of the full rebuild/candidate
validation call graph and is not registered in this contract. If a later caller
uses a compact bundle for that module, the closure and contract version must be
extended first.

## Taxonomy policy and closure

The taxonomy closure is registered but no taxonomy SQLite file is produced. The
current readers consume active data from `ec_taxonomy_version`, `ec_ecosystem`,
`ec_entity`, and `ec_membership` through:

- the V2 active Datacenter membership loader;
- RP/peer taxonomy context and identity mapping;
- snapshot taxonomy source-state and membership presentation.

`bind_taxonomy_source()` records the exact active domain, version, semantic
fingerprint, and membership count read from `analysis.db`. Direct read mode
requires an active `TaxonomyOperationLock` whose persisted identity matches the
lock object. It still reports
`LOCK_HELD_BUT_ALL_WRITER_COVERAGE_UNPROVEN` and is not runtime-authorized.

Before caller migration, RawCandle must prove that the taxonomy mutation lock is
the authoritative lock for every writer that can change active `ec_*` state,
define lock ordering with scheduler/Fundamentals locks, and add production-parity
fault tests. Until then, callers keep taking the complete taxonomy online backup.

## Manifest and fingerprints

The manifest contains:

- contract version, mode, and as-of date;
- canonical semantic binding and requirement counts;
- normalized market semantic fingerprint;
- compact DB SHA-256 and schema fingerprint;
- table row counts and valuation coverage counts;
- source device/inode/size/mtime and SQLite pragmas as audit evidence;
- taxonomy policy binding, when supplied;
- the complete registered read-closure declarations.

Semantic authority is the SHA-256 of normalized JSON row content plus contract,
as-of, and canonical binding. File size and mtime are evidence only. The compact
SQLite physical SHA protects the validated artifact after construction.

## Snapshot and drift behavior

Market extraction runs in a read-only SQLite transaction and closes that snapshot
before compact-DB construction. The relevant projection is then evaluated again
from a new read snapshot. A semantic mismatch, or a source device/inode change,
returns `READ_ONLY_SOURCE_DRIFT` and removes the partial bundle.
The canonical requirements and canonical device/inode binding are also evaluated
again; their drift returns `SOURCE_BUNDLE_CANONICAL_BINDING_DRIFT`.

This means a selected value-only change is detected even when row counts do not
change. A price row outside all registered requirements can leave the semantic
fingerprint unchanged. Source pragmas and file identity are not substituted for
the semantic comparison.

The bundle is first built in a disposable sibling directory, checked with
`quick_check`, checked against its row/schema/physical manifest, made read-only,
and renamed to its final path. Injected interruption and drift tests prove that no
partial final bundle remains. The source DB hash, size, and mtime remain unchanged
during successful fixture construction.

## Parity and failure evidence

Fixture parity compares a full online copy with the compact market DB through the
existing readers for:

- canonical V2 valuation-source rows and source fingerprint;
- peer/RP classification map and fingerprint;
- split-event loading used by V2 score calculation;
- RV last-32 price-bar loading;
- rebuild-validation price count/max state.

Taxonomy parity compares the current full-copy loader with a locked direct read,
including memberships, active version, and semantic fingerprint. It does not
claim that the direct policy is ready for runtime selection.

The focused suite also covers relevant value drift, irrelevant post-as-of data,
DELETE-journal market extraction, WAL-mode taxonomy reads, atomic source-file
replacement, interrupted construction, unsupported schemas, missing compact row
coverage, lock absence, and source non-mutation.

## Fixture measurement

The deterministic two-company fixture contained 400 market price rows and three
TTM requirements, including one `NO_CUTOFF` case. The contract selected 232
unique price rows, two classification rows, and one split row. Construction took
approximately 0.070 seconds on the local test environment. The source and compact
DB were both 57,344 bytes because SQLite page granularity dominates at this tiny
scale; the JSON manifest was 4,940 bytes.

These fixture byte sizes are functional evidence, not a production compression
claim. The Phase 13G.3.24 read-only study measured the current full market and
taxonomy copy footprint at 12.171 GiB and estimated roughly 171,000 market rows
before deduplication. This phase intentionally did not create another production-
sized copy or benchmark live databases.

## Remaining work before migration

- Prove all authoritative taxonomy writers participate in one lock contract.
- Benchmark the correlated filing-date selection against production-shaped local
  data without creating multi-GiB snapshots.
- Decide whether source-state validation will retain one complete ticker history
  or move to a versioned compact metadata adapter.
- Bind Test and Production manifests and reject stale Test evidence before
  candidate construction.
- Run full rebuild output parity, production-path fault injection, and cleanup
  acceptance before routing any Admin workflow through the bundle.
- Increment the source-contract version whenever a new reader or query changes
  the registered closure.

No publication, recovery, scheduler, Add Tickers, Refresh, Sector/Industry, or
Taxonomy Administration runtime behavior changed in this phase.
