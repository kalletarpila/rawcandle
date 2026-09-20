# Phase 13G.3.6: first_public_result_date Bootstrap

## 1. Purpose

This phase implements a one-time maintenance operation that establishes the historical
`first_public_result_date` baseline in the canonical Fundamentals V4 database. It does
not execute the production bootstrap.

## 2. Why Bootstrap Is Separate From First Refresh

Separating the 88,835-row metadata initialization from the first live Sharadar Refresh
keeps that Refresh attributable only to real source changes. The bootstrap neither
publishes nor advances Refresh state.

## 3. Date Semantics

For an existing quarter where `first_public_result_date IS NULL` and
`source_availability_date IS NOT NULL`, the candidate value is exactly the existing
`source_availability_date`. Established first-public dates are never overwritten.
Routine Refresh may later change `source_availability_date`, while the established
`first_public_result_date` remains immutable.

## 4. Stable Quarter Identity

The stable key is `(company_id, fiscal_year, fiscal_quarter)`, enforced by the existing
`v4_quarter` unique constraint. Preview fails closed for duplicate or NULL identity
components. The live Preview found zero duplicate or NULL identities.

## 5. Preview

`python3 -m rawcandle.cli.run_first_public_result_date_bootstrap preview`

Preview is read-only and binds SHA-256, size, mtime_ns, schema, row count, eligible
count, date state, and stable identity. It reports `READY`, `ALREADY_BOOTSTRAPPED`,
`REVIEW_REQUIRED`, or `BLOCKED`.

## 6. Test on Copy

Test requires the exact Preview result. It revalidates production before creating any
copy, uses SQLite online backup, updates only the copy, validates deterministic
fingerprints, emits lightweight evidence, and removes the test database immediately.

## 7. Intended Production Transaction

The implemented but unexecuted Production mode requires explicit confirmation and a
matching successful Preview/Test pair. Under the shared Admin and scheduler locks it
runs the shared publication recovery guard, revalidates the binding inside
`BEGIN IMMEDIATE`, updates eligible rows, validates before one commit, fsyncs, and runs
external postflight.

## 8. Backup and Rollback

Future Production creates one verified canonical SQLite online backup. Failures before
commit use SQLite rollback. A post-commit postflight failure restores the verified
canonical backup atomically and revalidates the old semantic generation. Provider and
analysis backups are not created.

## 9. Refresh-State Isolation

Preview and Test do not create or change `sharadar_refresh_state`, a Refresh watermark,
source fingerprints, authorization evidence, or a Refresh Production result.

## 10. Provider/Analysis Isolation

Provider and analysis SHA-256, size, and mtime_ns are captured before and after live
Preview/Test. They were identical. Neither database was copied or opened for writing.

## 11. Validation Invariants

Test proves unchanged quarter count, stable identity, all canonical content except the
target column, every `source_availability_date`, company/security control state, and
SQLite integrity. Established values are preserved and unresolved NULLs must equal the
Preview expectation.

## 12. Refresh Compatibility

Focused tests establish the standalone date and then move the later
`source_availability_date`, proving the two invariants independently. Existing Refresh
regressions continue to prove preservation during candidate rebuild and initialization
for genuinely new quarters. Defensive Refresh bootstrap behavior remains unchanged.

## 13. Scheduler Compatibility

The operation is not registered with Scheduler. Live evidence confirms unchanged
Refresh state, so the scheduler baseline and pending source changes remain unaffected.

## 14. Cleanup

The live Test database was deleted immediately. No candidate database, test database,
production backup, or publication journal was created or retained by Preview/Test.

## 15. Test Results

The focused bootstrap suite passed 16 tests. The relevant Refresh,
publication/recovery, workflow, scheduler, and Admin run passed 270 tests in total
(16 focused plus 254 regression tests). A separate canonical/V2/RP/RV run passed 100
tests. No tests were skipped or failed.

## 16. Production Safety

Live Preview/Test production state was unchanged. Canonical SHA-256 remained
`4bedbf6b1bace42fe7bf708e1c7b502873c348d1c5aa95e3f3550d1a85d93790`.
Provider remained `b71dfbb0128a4e5404a18c608e31e16ec08c07b75bbe416e1a48a62112469468`
and analysis remained `969eb38504893b260206f07033a292b0587c16164720556f11d1b77e69b834f2`.

## 17. Live Preview Result

- Outcome: `READY`
- Canonical rows: 88,835
- Established first-public dates: 0
- Eligible rows: 88,835
- Unresolved rows: 0
- Expected post-bootstrap non-null: 88,835
- Expected remaining NULL: 0

Run: `20260920T081819107454Z_first_public_result_date_bootstrap_preview`

## 18. Live Test Result

- Outcome: `COMPLETED`
- Updated on copy: 88,835
- Established after Test: 88,835
- Remaining NULL after Test: 0
- Every bootstrapped value equals its `source_availability_date`: passed
- Pre-existing established values preserved (baseline count 0): passed
- Identity, non-target content, source availability, counts, and integrity: passed
- Test database cleaned: Yes
- Production changed: No

Run: `20260920T081835733802Z_first_public_result_date_bootstrap_test`

## 19. Production Authorization Status

`NOT YET AUTHORIZED / NOT EXECUTED`

## 20. Git

Code, focused tests, and this document are committed together. No databases or live run
artifacts are committed. The phase commit hash is reported in the final response.
