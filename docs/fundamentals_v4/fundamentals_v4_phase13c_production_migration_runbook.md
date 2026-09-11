# Fundamentals V4 Phase 13C Production Migration Runbook

Phase 13C may migrate only the Phase 13B dependency foundation. It must not add tickers, edit taxonomy content, refresh Relative Position, refresh Relative Valuation, change Scheduler UI behavior or move active result pointers beyond the additive foundation tables.

## Preconditions

Required before applying to production:

- Maintenance lock acquired.
- No writer processes active against Fundamentals production databases.
- Fresh online backups created for canonical, analysis and taxonomy databases.
- Backup fingerprints, sizes and `PRAGMA quick_check` recorded.
- Production preflight inventory recorded.
- Operator confirms the exact database paths and Phase 13B contract versions.

## Apply Scope

Apply only:

- Candidate operational universe schema.
- Candidate dependency schema.
- Current production company/security universe backfill.
- Current Relative Valuation, Relative Position and Operating Income V2 dependency metadata.

The migration is additive and idempotent. A second apply must report no logical change and leave physical database fingerprints unchanged.

## Compatibility Gates

After apply:

- Existing Fundamentals readers still pass without consulting new tables.
- Active Relative Valuation selection still follows Phase 11E non-future semantics.
- Existing Relative Position and Operating Income V2 active package guards remain unchanged.
- Dependency checks classify incompatible operational universe or economic taxonomy fingerprints before any future Add Tickers or Taxonomy Update operation can claim coherence.

## Rollback

Rollback is database-level only.

Old package manifests, active pointers or result rows are not sufficient rollback targets because Phase 13B introduces cross-database dependency metadata. If Phase 13C fails after modifying any production database, restore every modified database from the verified Phase 13C backups, then rerun postflight inventory and `PRAGMA quick_check`.

## Deferred Work

These operations remain explicitly deferred after Phase 13C:

- Add Tickers UI.
- Fundamentals Taxonomy Update UI.
- Taxonomy content changes.
- New ticker onboarding.
- Recalculation of Relative Position or Relative Valuation.

