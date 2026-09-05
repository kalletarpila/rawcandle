# Diagnostic Flags V1 Phase 6D runbook

This is a proposed deployment procedure, not an active production command.

1. Stop Fundamentals writes and record sizes, mtimes, SHA-256, schema hashes, row counts, `quick_check`, foreign keys and WAL/SHM state for provider, canonical and analysis databases.
2. Create timestamped SQLite online backups of all three databases and verify each backup with read-only `quick_check` and row counts.
3. On production only after separate Phase 6D authorization, run the existing additive common-earnings migration. Verify provider `netinccmn` exists, the second apply writes zero rows, and canonical common-earnings/TTM fingerprints are unchanged.
4. Run the Phase 6A.2 five-field migration/backfill. Require 50,585 canonical endpoints, expected field/provenance coverage, no invalid values, clean foreign keys and a zero-write second apply.
5. Abort before downstream work if the upstream gate fails. Restore provider and canonical together from verified backups when rollback is required.
6. Apply the Diagnostic Flags schema to analysis. Repeated migration must be a no-op.
7. Calculate the explicit economic fingerprint `1d985892734c1401de55d91e06bbb1f295fe247e96bb3acbffcd6272027f26ad` package from the committed upstream state and apply the full revised history atomically.
8. Require 50,585 endpoint rows, 354,095 evaluation rows, exactly seven evaluations per endpoint, clean `quick_check`/foreign keys, and matching source/economic/physical fingerprints.
9. Run fresh engine-versus-persistence reconciliation. Require zero decision mismatches and numeric evidence within `1e-12`.
10. Run the identical second apply and require `NO_CHANGE` with zero logical inserts, updates and deletes.
11. Run a pipeline smoke without provider update. Proposed order is Score, Lifecycle, Valuation, Diagnostic Flags, then independently Delta and Relative Position.
12. Record final integrity evidence and remove the write freeze only after all gates pass.

If analysis schema/apply/reconciliation fails, restore only the analysis backup. Do not roll back already valid Score, Lifecycle, Valuation, Delta or Relative Position layers. If an upstream stage fails, do not activate Diagnostic Flags; restore the affected upstream databases from the matched backup set. Never use `VACUUM` as a deployment or rollback step.
