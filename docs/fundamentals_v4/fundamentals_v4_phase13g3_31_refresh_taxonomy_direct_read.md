# Phase 13G.3.31 Refresh Taxonomy Direct Read

## Decision

Refresh Test and Production now use `STABLE_SOURCE_BUNDLE` for market and
`DIRECT_LOCKED_READ` for taxonomy.

The previous normal path created a full SQLite backup of `data/analysis.db` for
each Test and Production candidate. The migrated path uses the Phase 13G.3.30
protected source mechanism and passes the authoritative live taxonomy path to
V2, RP, RV, candidate validation, and Production postflight. It never falls
back to an unprotected live read. The old full-copy helper remains available
only as an explicitly selected compatibility utility; neither normal Refresh
caller selects it.

## Protection Lifetime And Ordering

Test acquires the authoritative taxonomy lock after its canonical candidate is
ready. It holds the lock while the compact market bundle is bound, through the
full V2/RP/RV rebuild and validation/evidence work, and until candidate cleanup
has completed. Exceptions clean the candidate lane before the context releases
the lock.

Production acquires taxonomy protection after its existing Admin Production and
scheduler lock context. The order remains:

`Admin Production lock -> scheduler lock -> taxonomy lock`

Production retains taxonomy ownership through bundle construction, downstream
rebuild, candidate validation, final source revalidation, publication,
published-generation postflight, journal terminalization, rollback when needed,
and candidate cleanup. The lock is released in terminal cleanup on success,
ordinary failure, stale stop, rollback, and recovery outcomes. Reverse lock
ordering remains mechanically rejected by the Phase 13G.3.30 contract.

## Semantic Binding

Test persists `DIRECT_LOCKED_READ`, domain, active version, semantic
fingerprint, and active membership count in `read_only_source_binding.json`.
Production creates a fresh protected binding from its own canonical candidate
and compares the same semantic projection with the successful Test. File SHA,
mtime, and physical layout are not taxonomy authority.

A changed active taxonomy version, fingerprint, or membership contract after
Test produces `REFRESH_TEST_SOURCE_BINDING_STALE` before downstream publication.
Lock acquisition and binding failures remain explicit failures; they are not
reported as `NO_CHANGE` or silently converted to a stale result.

## Publication And Cleanup

Taxonomy is never a publication, rollback, or recovery role. The journal and
OLD-generation restore set remain exactly `provider`, `canonical`, and
`analysis`. No taxonomy candidate or backup is created by the normal Test or
Production path, and no taxonomy-copy cleanup is needed. Compact market bundle
cleanup is unchanged. Terminal fixtures verify no candidate source DB or lock
ownership remains.

## Acceptance

Phase 13G.3.31 includes a full Refresh Full Workflow production-parity rerun
after taxonomy caller migration. The fixture exercises Preview, Test,
Production, publication/postflight, cleanup, market drift, taxonomy drift,
rollback, crash/recovery, and writer contention. A writer is rejected while
Test downstream reads are active and again while Production postflight reads
are active. All terminal paths release the authoritative lock, taxonomy remains
unchanged on read paths, and publication/recovery roles remain the three
Fundamentals databases.

Fixture evidence per Test or Production run records 73,728 market source bytes
and 20,480 taxonomy bytes of full copies avoided, 94,208 bytes combined, while
the fixture compact market DB is 86,016 bytes. SQLite page granularity makes the
fixture unsuitable for compression claims.

Accepted production-shaped evidence remains the Phase 13G.3.24/26 measurement:
1,990,488,064 market bytes plus 11,078,471,680 taxonomy bytes, or
13,068,959,744 bytes (12.171 GiB) of old full-source copies avoided per Refresh
run. The compact market DB was 14,508,032 bytes. This phase did not create a new
large taxonomy copy or run a live workflow.

## Remaining Risk

The application lock serializes every supported RawCandle taxonomy writer.
Direct manual SQLite mutation outside those entrypoints is outside this runtime
contract. The protected reader intentionally favors correctness over concurrent
taxonomy activation: contention fails closed and the operator retries after the
other operation completes.
