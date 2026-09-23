# Phase 13G.3.30 Taxonomy Direct-Read Lock Proof

## Decision

Taxonomy DIRECT_LOCKED_READ is runtime-authorized by Phase 13G.3.30.

This authorizes the source-policy mechanism only. Refresh Test and Production remain on `FULL_SQLITE_BACKUP`; caller migration belongs to the next phase.

## Writer Inventory

Nine runtime mutation entrypoints can reach the active `ec_ecosystem`, `ec_taxonomy_version`, `ec_entity`, or `ec_membership` projection:

| Entry point | Mutation path | Lock status |
| --- | --- | --- |
| `run_datacenter_taxonomy_change` rebuild/resume | replacement orchestrator and EC taxonomy loader | authoritative lock corrected |
| `activate_datacenter_taxonomy_change` | taxonomy activation | authoritative lock |
| legacy `apply_datacenter_taxonomy_version` CLI | version load | authoritative lock added |
| legacy `apply_datacenter_taxonomy_activation` CLI | activation | authoritative lock added |
| `run_ec_source_layer_build` CLI | sidecar migration, taxonomy loader, watchlist entity loader | authoritative lock added |
| Scheduler UI rebuild | replacement orchestrator | authoritative lock corrected |
| Scheduler UI resume | replacement orchestrator | authoritative lock corrected |
| Scheduler UI validate/finalize | rebuild finalization | authoritative lock corrected |
| Scheduler UI activation | taxonomy activation | authoritative lock added |

The permanent structural test checks five CLI entrypoints and four UI lock sites.

The mutation primitives are `apply_datacenter_taxonomy_version`, `apply_datacenter_taxonomy_activation`, `load_datacenter_taxonomy_to_ec_sidecar`, `load_datacenter_watchlist_to_ec_sidecar`, and the sidecar schema migration used by the source-layer build. Their supported runtime callers are the locked entrypoints above.

The following are not live authoritative writers:

- Fundamentals Taxonomy Administration applies candidate taxonomy only to a copied database and rebuilds Fundamentals from the already-active production taxonomy.
- Phase 13D taxonomy apply rejects production/alias paths and is copy/test-only.
- schema migrations and test fixture SQL are migration/test-only.
- EC fact refresh/backfill changes dated fact tables, not the four active taxonomy projection tables.

No uncovered runtime writer remains after the targeted entrypoint fixes.

## Authoritative Lock

`TaxonomyOperationLock` at the default `temp/datacenter_taxonomy_changes/taxonomy_operation.lock` path is the single authority. Evidence roots remain configurable for reports, but they no longer select a competing runtime lock. A direct read rejects a valid-looking lock token from any non-authoritative root.

The lock is exclusive and fail-fast. A protected Fundamentals read holds it from semantic binding through all downstream taxonomy reads. Participating writers therefore cannot change the generation during that interval. The lock context removes ownership on normal completion and exceptions; the existing dead-PID recovery removes crash-stale ownership on the next acquisition.

## Lock Ordering

The supported nested order is:

`Fundamentals Admin Production lock -> scheduler lock -> taxonomy operation lock`

A scheduler-owned informational/Test path may acquire the taxonomy lock after its scheduler lock. A standalone taxonomy writer acquires only the taxonomy lock. No supported taxonomy mutation path acquires the Fundamentals Production lock or scheduler kernel lock while holding taxonomy ownership.

Reverse in-process acquisition is mechanically rejected:

- taxonomy then Fundamentals Production: `LOCK_ORDER_VIOLATION:TAXONOMY_BEFORE_ADMIN_PRODUCTION`
- taxonomy then scheduler: `LOCK_ORDER_VIOLATION:TAXONOMY_BEFORE_SCHEDULER`

All three locks are fail-fast rather than waiting locks, so cross-process contention stops an operation instead of forming a wait cycle.

## Semantic Binding

`DIRECT_LOCKED_READ` reuses the existing active DC taxonomy contract:

- mode
- `dc_ecosystem` domain
- active taxonomy version
- semantic fingerprint
- active membership row count

File SHA, size, and mtime are not semantic authority. The protected direct-read fixture matches the established full-copy binding. A post-Test version/source mutation changes the semantic contract and would stale Production exactly as under `FULL_SQLITE_BACKUP`.

## Concurrency And Cleanup Proof

Focused fixtures prove that a conflicting writer cannot enter during a protected read, repeated reads under protection retain the same semantic fingerprint, and read-only access leaves the taxonomy DB byte-identical. They also prove exception cleanup, dead-PID recovery, supported lock order, reverse-order rejection, and semantic staleness after a later authorized mutation.

A cross-entrypoint test holds the Fundamentals protected-read lock while invoking the real Scheduler UI rebuild handler with a separate evidence root. The UI writer fails on the same authoritative lock before the orchestrator is called, proving that evidence location cannot split lock identity.

The current full-copy Refresh source preparation tests remain unchanged and green. No runtime caller was migrated, no live workflow was run, and no production database or scheduler state was changed.

## Remaining Risk And Next Step

The lock serializes taxonomy writers and future direct Fundamentals readers. A process that bypasses all supported RawCandle entrypoints and writes SQLite directly cannot be controlled by an application lock; this is an operational boundary, not a supported runtime path.

The next phase may migrate Refresh Test and Production source preparation from `FULL_SQLITE_BACKUP` to `protected_direct_taxonomy_source`, retain the lock through downstream and postflight taxonomy reads, compare the same semantic Test/Production contract, and then run the full production-parity workflow suite.
