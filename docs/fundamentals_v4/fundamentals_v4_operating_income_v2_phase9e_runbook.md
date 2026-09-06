# Operating-Income V2 Phase 9E Production Runbook

Status: `NOT_AUTHORIZED`

This runbook may be executed only after explicit Phase 9E production authorization. Phase 9D commands reject production destinations.

## Locked Identities

| Layer | Version | Fingerprint |
|---|---|---|
| Score | `SIMPLE_FUNDAMENTAL_SCORE_V2` | `271585e4136f6733c047e89dac7646f2ff91f8c84b10f88c56356ad495970360` |
| Lifecycle | `V4_FUNDAMENTAL_LIFECYCLE_V2` | `0502822c20501c1487d09a20a378e86c0908a0953dfcb13b384428822fc4e175` |
| Valuation | `ABSOLUTE_VALUATION_SCORE_V2` | `9675c2d947a86d2115f366424eab7454ec013cc100c7548af004c19c691c9aeb` |
| Delta | `CURRENTLY_REVISED_FUNDAMENTAL_DELTA_V2` | `c65062c1ac66f1e98ab239404dba96c43060708a35a84bcfd2ed01c30d5e2f11` |
| Relative Position | `RELATIVE_POSITION_V2` | `993a3cfbbfd7d724852cf78466a91edf0a1adca8cd08c35e8bcc2891a5cbe30f` |
| Diagnostic Flags | `DIAGNOSTIC_FLAGS_V2` | `d5434e139b68ee8af44dffce34cb9225538f0badb61d5d1074fb976a4de3185d` |
| Company Snapshot | `COMPANY_SNAPSHOT_V2` | `7bfa88aa64f3897ea610894a1b7a3613abfc7881d9b9ea8e26912ef0426e7ee8` |

Do not continue if runtime constants differ from this table or the committed package fingerprint.

## Preflight

1. Require a clean worktree at the authorized Phase 9E commit and record `git status --short`, branch, and `git rev-parse HEAD`.
2. Inventory RawCandle and Scheduler processes with `ps` and database holders with `lsof`. Do not kill or stop anything implicitly.
3. Record database, WAL, and SHM path, size, mtime, SHA-256, schema hash, page/freelist counts, key row counts, `PRAGMA quick_check`, and `PRAGMA foreign_key_check` for every source database.
4. Read WAL databases through SQLite `mode=ro`. Never use `immutable=1` when a required WAL exists. Do not delete, move, truncate, rename, or checkpoint production sidecars.
5. Require free space for an online backup of every modified database, at least 476 MiB expected V2 growth, peak transaction WAL, artifacts, and 25% contingency. Abort below that amount.
6. Create timestamped SQLite online backups with `sqlite3.Connection.backup()`. Hash and run integrity checks on each completed backup before any migration.
7. Run the Phase 9D protected rehearsal against a new copy and require all tests, exact counts, deep replay, no-op replay, rollback injections, and production-content comparison to pass.

## Deployment Order

1. Acquire the application-level fundamentals maintenance lock. Do not run a provider update.
2. Begin one explicit analysis-database transaction.
3. Apply only the additive Phase 9D schema statements.
4. Persist complete Score V2 history.
5. Persist complete Lifecycle V2 revised history.
6. Persist complete Valuation V2 revised history.
7. Persist complete normalized Delta V2 history.
8. Persist all seven Diagnostic Flags V2 statuses for every endpoint.
9. Build and activate the V2 Relative Position snapshot under its own model-fingerprint pointer. Keep the V1 pointer.
10. Write the complete V2 package manifest last and commit.
11. Run deep reconciliation and require exact production-shaped counts, all component/evidence comparisons, no mixed references, no orphans, and all locked fingerprints.
12. Run the identical package a second time and require `NO_CHANGE`, zero logical writes, equal economic/physical fingerprints, and zero database growth.
13. In one separate atomic configuration change, switch all default readers to the complete V2 family. Never activate layers independently.
14. Activate Company Snapshot V2, generate temporary smoke reports, then switch production report generation only after coherent bundle validation.
15. Smoke-test the Scheduler UI and one pipeline cycle with provider fetching disabled.

The authorized Phase 9E implementation must expose a dedicated production command. Do not weaken or reuse Phase 9D's production-path rejection.

## Post-Deployment Checks

- Re-run database/WAL/SHM hashes and integrity metadata; explain expected analysis-database changes and require all source databases to remain content-identical.
- Verify the five reference companies and one REIT, not-ready, and lifecycle-candidate case.
- Query V1 and V2 explicitly from the same database and verify that both remain available.
- Confirm the live Snapshot identifies the complete V2 package and uses only Operating Income terminology.
- Archive commands, hashes, counts, fingerprints, timings, storage, reports, and test output under a timestamped Phase 9E artifact directory.

## Rollback

Rollback immediately on any fingerprint mismatch, row-count mismatch, orphan, mixed model reference, failed no-op, report incoherence, Scheduler error, unexpected storage growth, or source-database change.

1. Disable writes and retain all evidence.
2. Atomically restore the complete default reader configuration and Snapshot default to V1. Do not delete V2 rows as part of reader rollback.
3. Verify V1 readers, reports, Scheduler UI, and provider-disabled pipeline smoke.
4. If persisted V2 state is corrupt, restore `fundamentals_analysis.db` from the verified online backup while the maintenance lock is held; preserve the failed database for diagnosis.
5. Validate restored hashes, quick-check, foreign keys, V1 row counts, V1 fingerprints, and V1 report output before releasing the lock.

V1 removal is outside Phase 9E and requires a separate decision.
