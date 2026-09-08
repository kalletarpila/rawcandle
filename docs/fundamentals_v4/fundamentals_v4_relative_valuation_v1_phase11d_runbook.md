# Phase 11D Relative Valuation Deployment Runbook

Phase 11D requires separate explicit production authorization. Do not execute
this runbook during Phase 11C.

1. Stop or exclude concurrent Fundamentals writers and capture protected
   production database/report inventories.
2. Confirm free space for the analysis database, online backup, migration,
   temporary journal/WAL peak, and safety reserve.
3. Create and independently verify an online SQLite backup of production
   `fundamentals_analysis.db`; require regular-file identity, `quick_check=ok`,
   zero foreign-key violations, schema/count parity, and recorded SHA-256.
4. Apply only the additive Relative Valuation schema migration under the
   production maintenance boundary. Recheck all pre-existing schema objects.
5. Load all source roles read-only, calculate the full universe with the exact
   model fingerprint, and require source/result reconciliation with an
   independently repeated calculation.
6. Apply the complete snapshot in one transaction. Run deep cardinality,
   formula, fingerprint, integrity, and HUBG freshness checks before accepting
   activation.
7. Atomically activate the Relative Valuation snapshot. Preserve the previous
   complete Relative Valuation snapshot as the rollback target.
8. Switch Company Snapshot/UI only through separately versioned economic and
   presentation identities that read the active persisted result. Do not make
   schema absence fall back to recalculation.
9. Run an independent second full calculation/apply and require exact
   `NO_CHANGE` with zero bulk writes, pointer changes, audit writes, and file
   growth.
10. Run provider-disabled pipeline, Snapshot, multi-ticker UI, secure download,
    package-resolution, production-isolation, and complete Fundamentals V4
    smoke suites.
11. Capture postflight inventories and compare every protected main/WAL hash,
    existing model fingerprint/count, active Operating-Income package, Relative
    Position snapshot, and production report aggregate.
12. For activation-only rollback, atomically point Relative Valuation to the
    retained previous complete snapshot and restore the prior Snapshot/UI
    identities. For content or schema failure, retain the failed database,
    verify the online backup, restore it to a new regular file with SQLite
    backup semantics, validate it, and atomically replace production.

Required gates are exact production paths, exact model/layout fingerprints,
full-universe mode, maintenance lock, verified backup, zero integrity errors,
independent no-op, and explicit activation authorization. Any mismatch stops
deployment; no count or fingerprint may be forced to the Phase 11C reference.
