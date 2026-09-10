# Phase 12E: Ten-Year Operational Deployment Runbook

## Authorization Gate

Do not execute this runbook until Phase 12D Outcome B is resolved by an explicit
decision on Relative Valuation refresh and activation ordering. Phase 12E must be a
separately authorized production change. The target remains the operational
append-only provider population; it does not include the historical-only universe.

## Preflight

1. Require a clean worktree, no merge/rebase, the approved commit, and recorded HEAD.
2. Acquire the maintenance lock and stop Scheduler/provider/rebuild/report writers.
3. Inventory open handles and all production WAL/SHM files.
4. Record schemas, row counts, logical fingerprints, file sizes, mtimes, page counts,
   freelists, active pointers, report hashes, Scheduler hash, and SHA-256 values.
5. Require enough free space for verified backups, rollback journals/WAL, canonical
   growth, analysis growth, and an independent verification copy. Phase 12D used a
   9.79 GB minimum copy gate; production authorization must retain additional margin.
   Run a monitored final rehearsal to capture peak transient journal/WAL bytes; Phase
   12D left no sidecar after commit but did not capture the transient peak.
6. Verify `quick_check=ok` and zero foreign-key errors for every source database.
7. Verify the provider policy fingerprint and the accepted ARQ source fingerprint.
8. Reserve at least 20 minutes for the measured rebuild/apply work, plus independent
   no-op, Relative Valuation (if authorized), Snapshot/UI smoke tests, and rollback
   margin. Recalculate this window from the monitored final preflight rehearsal.

## Backups

1. Create SQLite Online Backup API copies of provider, canonical, analysis, market,
   and taxonomy databases as applicable.
2. Archive the currently active coherent package and Relative Valuation snapshot.
3. Record backup hashes, sizes, schemas, row counts, quick checks, and foreign keys.
4. Restore the backups into a disposable location and prove the old active package
   and report reader remain independently readable before production writes begin.

## Write Order

1. Reconcile canonical ARQ observations and provenance in one protected boundary.
2. Verify 87,319 selected winners, zero unresolved operational identities, zero
   duplicate fiscal identities, complete non-null-field provenance, and zero
   unexplained overlap differences.
3. Rebuild and verify TTM values and input-quarter evidence before analysis writes.
4. Persist Score, Lifecycle, Absolute Valuation, Delta, eight-flag Diagnostics, and
   required Relative Position rows as one coherent candidate package.
5. Verify all model fingerprints remain locked and assign the new source/result/
   physical/package identities. Do not reuse an old package fingerprint.
6. Keep the production active pointer unchanged until every reconciliation passes.

## Failure Boundaries

Stop and roll back on any canonical/provenance mismatch, TTM chain or availability
error, missing-to-zero conversion, component-total mismatch, diagnostic engine/
persistence/reader mismatch, unknown status/reason, orphan, duplicate, foreign-key
error, fingerprint collision, partial manifest, or unexpected production-side write.

Canonical, TTM, downstream persistence, manifest creation, and activation must each
have an explicit rollback boundary. A failed stage must leave the prior active
package readable and must not expose a partial candidate.

## Relative Valuation Decision

Relative Valuation is a separately refreshed current snapshot. If its refresh is
authorized, run it only after the new Absolute Valuation inputs are complete and
before exposing a Snapshot that claims package compatibility. Validate its source,
result, physical, snapshot, and active-pointer identities independently.

If refresh is not authorized, do not activate or report a combination that mixes the
new 87,319-row package with the old 50,585-row Relative Valuation input population.
Leave production on the archived coherent package.

## Activation

1. Recheck the maintenance lock and active package immediately before activation.
2. Compare the candidate with the approved Phase 12D fingerprints and row counts.
3. Activate only the complete coherent package in one atomic pointer transaction.
4. Activate a separately authorized refreshed Relative Valuation snapshot only after
   its own gates pass.
5. Never overwrite historical manifests, package rows, or audit records.

## Mandatory Verification

1. Run an independent identical rebuild/apply after activation; require `NO_CHANGE`
   and zero logical writes.
2. Reconcile all canonical, TTM, Score, Lifecycle, Valuation, Delta, Diagnostic, and
   Relative Position row/component counts and fingerprints.
3. Verify the eight Diagnostic flags through pure engine, persistence, reader, and
   Snapshot assembly. Check Non-Operating Earnings Gap direction/evidence and Working
   Capital current-versus-exact-Q-1 routing.
4. Run production Company Snapshot and UI smoke tests for the established reference
   tickers without changing the frozen presentation identity.
5. Confirm generated reports use only compatible active package/snapshot identities.
6. Repeat production inventory and compare databases, sidecars, pointers, Scheduler,
   and reports with the expected authorized delta only.

## Rollback

Before activation, discard the candidate and restore any modified canonical/analysis
databases from verified backups. After activation, atomically restore the archived
active package pointer and, if changed, the archived Relative Valuation pointer;
restore database backups when append-only rollback is insufficient. Re-run quick
checks, foreign keys, package readability, Snapshot/UI smoke tests, and postflight
inventory. Do not delete failed candidate evidence or audit rows needed for diagnosis.

## Postflight

Release the maintenance lock only after the independent no-op, report/UI smoke tests,
active identities, backup readability, and production inventory pass. Record exact
commands, durations, storage growth, hashes, package identities, approved Relative
Valuation treatment, rollback disposition, commit, and operator. Keep the Phase 12B
contract unchanged; a research replay is evidence, not an activation prerequisite
for any prediction model.
