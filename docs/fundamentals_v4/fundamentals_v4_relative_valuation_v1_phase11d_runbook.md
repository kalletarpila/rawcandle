# Phase 11D Relative Valuation Deployment Runbook

Phase 11D deployed successfully on 2026-09-08. This is now the protected manual
refresh and rollback runbook. The deployment record is
`fundamentals_v4_relative_valuation_v1_phase11d_deployment.md`.

## Refresh Command

Run first without `--apply --confirm-production`, inspect the output, then add
both flags only for an authorized production refresh. Replace the four expected
content identities with those from a deterministic rehearsal when source data
has legitimately changed.

```bash
PYTHONPATH=. python3 -m rawcandle.cli.run_fundamentals_v4_relative_valuation_production \
  --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db \
  --provider-db /home/kalle/projects/rawcandle/data/fundamentals_provider.db \
  --analysis-db /home/kalle/projects/rawcandle/data/fundamentals_analysis.db \
  --market-db /home/kalle/projects/rawcandle/data/osakedata.db \
  --taxonomy-db /home/kalle/projects/rawcandle/data/analysis.db \
  --output /home/kalle/projects/rawcandle/temp/fundamentals_v4_relative_valuation_phase11d/REFRESH_ID \
  --backup-dir /home/kalle/projects/rawcandle/backups \
  --as-of-date YYYY-MM-DD \
  --model-fingerprint 76c2974108b2c5085b7dfa102acd4bb04eea36a5267bbdb1930a2bc7dc8cb35e \
  --persistence-version RELATIVE_VALUATION_CURRENT_SNAPSHOT_V1 \
  --layout-fingerprint 9ffbfa6dd1ed86be3c5858607eb3284070d7a20285f0d46799cc198ba2a6d523 \
  --expected-active-package 0e269e52a63500342df8a08ee2f91552fdc8fb216fa68cfe469bafb6aa8e3c30 \
  --expected-source-fingerprint FULL_REHEARSED_SOURCE_FINGERPRINT \
  --expected-result-fingerprint FULL_REHEARSED_RESULT_FINGERPRINT \
  --expected-physical-fingerprint FULL_REHEARSED_PHYSICAL_FINGERPRINT \
  --expected-snapshot-id FULL_REHEARSED_SNAPSHOT_ID \
  --full-universe
```

The production apply adds `--apply --confirm-production`. Never reuse stale
expected fingerprints merely to pass the gate.

## Deployment Procedure

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
