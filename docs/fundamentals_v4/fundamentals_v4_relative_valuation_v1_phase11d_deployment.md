# Phase 11D Relative Valuation V1 Production Deployment

## Outcome

Status: `PRODUCTION_ACTIVE`.

Phase 11E later superseded only the exact-date report-selection rule documented
below. Production persistence, rows, active snapshot, and manual refresh policy
remain those deployed here. See
`fundamentals_v4_relative_valuation_v1_phase11e_reporting.md`.

On 2026-09-08, Phase 11D additively migrated production
`data/fundamentals_analysis.db`, persisted and atomically activated the first
full-universe Relative Valuation snapshot, and promoted the persisted reader
for newly generated Company Snapshot V2 reports and the Fundamentals UI.
Existing reports were not regenerated or overwritten. No provider, canonical,
TTM, market, taxonomy, Score, Lifecycle, Absolute Valuation, Delta, Relative
Position, or Diagnostic Flags calculation was changed.

Implementation commits before the production write:

- `b99095bf64ff0a67e6748022e9845c350ae20ca1` - protected production gate,
  activation, persisted Snapshot integration, and tests
- `428ce9f9875319d5ffdf6a044086e559221dc1d2` - deterministic schema-evidence
  fingerprint correction
- `be015d6059404a5cc9370daf3f2def97ebae7328` - explicit five-path CLI gate

## Locked Identities

| Identity | Value |
|---|---|
| Model | `CURRENTLY_REVISED_RELATIVE_VALUATION_V1` |
| Model fingerprint | `76c2974108b2c5085b7dfa102acd4bb04eea36a5267bbdb1930a2bc7dc8cb35e` |
| Persistence | `RELATIVE_VALUATION_CURRENT_SNAPSHOT_V1` |
| Layout fingerprint | `9ffbfa6dd1ed86be3c5858607eb3284070d7a20285f0d46799cc198ba2a6d523` |
| Source fingerprint | `ed787b5261a3e82f9737be6ec6920c3ee0d6a1737cfed4f643e43fb45b878ca6` |
| Result fingerprint | `3ab99303e4e9696aab0ad8fc5f40ea6f3879fb90e298ac6d3b6aab3928817f97` |
| Physical-content fingerprint | `1431b72cd1bf744fd77dc7e0f976d4b001c95527451a3ff7c402511fe2acff61` |
| Active snapshot | `b7f786edfa7632a320df5281182761471a15281ca1c518d2d729bbfab36dc5df` |
| Snapshot economic contract | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_RELATIVE_VALUATION_V1` |
| Snapshot fingerprint | `a688cb7f1637126bb354d179cd12610d891073a10f0692a9a83830c3f6b12391` |
| Presentation contract | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V8_RELATIVE_VALUATION` |
| Presentation fingerprint | `e1eecc4d12942470236ecc3ae7a885eb8f562de8b401a774f27efc7f439d6738` |
| Active Operating-Income package | `0e269e52a63500342df8a08ee2f91552fdc8fb216fa68cfe469bafb6aa8e3c30` |

The exact as-of date is `2026-09-08`. Market-price input covers 2026-08-18
through 2026-09-07. Activation completed at `2026-09-08T17:14:08Z`.

## Safety And Backup

Preflight found a clean worktree, no conflicting writer, no stale database
sidecar, an openable production database, `journal_mode=delete`,
`quick_check=ok`, and zero foreign-key violations. Free space was about 451 GB;
the enforced requirement was 1,700,899,840 bytes, including the full backup,
expected 5.7 MB growth, transaction overhead, artifacts, and margin.

The final pre-write online backup was made with `sqlite3.Connection.backup()`:

```text
/home/kalle/projects/rawcandle/backups/fundamentals_analysis.phase11d.20260908T171358Z.db
```

It is a 1,146,810,368-byte regular non-symlink file with SHA-256
`5e944b7e6bd2107c8d1e480e5988598dfbf25f611b7f9e7987b1ced4cbd9eae7`
and schema hash
`7a3df25afdf8d8496aeb9c0b92a7da6295dd23688ad3970062cc0a821c6f4da8`.
It opens independently, has no WAL/SHM dependency, passes `quick_check`, has
zero foreign-key violations, retains the active Operating-Income package, and
contains no Relative Valuation objects.

Dry-run, preflight audit, and backup-derived rehearsal evidence is under:

```text
temp/fundamentals_v4_relative_valuation_phase11d/20260908T170000Z/
```

The final rehearsal reproduced every locked identity and count, passed deep
reconciliation, nine injected rollback boundaries, retention behavior, and an
independent `NO_CHANGE` apply.

## Production Apply

The protected command requires all five absolute production paths, output and
backup locations, explicit as-of, full model/persistence/layout/source/result/
physical/snapshot identities, full-universe mode, expected active package,
`--apply`, and `--confirm-production`. It is dry-run by default and holds the
maintenance lock across revalidation, migration, calculation, persistence,
reconciliation, and activation. The operational command is documented in the
Phase 11D runbook.

The first apply returned `ACTIVATED` and inserted:

| Object | Rows |
|---|---:|
| Company result | 2,448 |
| Peer position | 9,792 |
| Own history | 2,448 |
| Component history | 7,344 |
| Snapshot metadata | 1 |
| Active pointer | 1 |
| Schema metadata | 1 |
| Bounded audit | 1 |

There were zero deletes, one pointer change, and one retained snapshot. The
additive schema consists of eight `relative_valuation_*` tables and measured
indexes `idx_relative_valuation_snapshot_model`,
`idx_relative_valuation_peer_group`, and
`idx_relative_valuation_audit_model`. No unrelated table was rebuilt and no
`VACUUM` was run.

Coverage reconciles as follows:

- current-fresh companies: 2,431
- current peer eligible: 2,245
- own-history `READY`, current-fresh: 874
- own-history `LIMITED_HISTORY`, current-fresh: 124
- broader calculable `READY`: 875

HUBG is the sole 875-versus-874 case. Its endpoint is 2025 Q3, availability
date 2025-11-05, age 307 days, and `current_fresh=0`; it remains persisted for
status/audit completeness but is excluded from current-fresh rankings.

Deep checks found one complete active snapshot, four peer rows and three
component rows per company, no duplicates or orphans, exact 40/40/20
aggregation, reconstructed peer/own-history percentiles, matching source,
result and physical identities, `quick_check=ok`, and zero foreign-key errors.

## Snapshot And UI

New reports read the active persisted snapshot. They never launch a
full-universe calculation. Exact date match is required. Missing activation
renders `RELATIVE_VALUATION_SNAPSHOT_NOT_ACTIVE`; another report date renders
`RELATIVE_VALUATION_AS_OF_MISMATCH`. In both cases the established report still
renders and Relative Valuation is explicitly unavailable.

Fifteen production-reader reports and deterministic repeats are under
`temp/fundamentals_v4_relative_valuation_phase11d/20260908T170000Z/smoke-reports-complete/`.
They cover the requested companies and readiness/status variants without
publishing to `fundamental_reports`. A real stale-date NVDA report is under
`.../stale-smoke/`. UI route, batch separators, duplicate removal, partial
success, overwrite protection, recent files, secure download, traversal and
symlink rejection, and error handling passed.

## Independent No-Change

The separate second production invocation is recorded under `.../second-apply/`.
It returned `NO_CHANGE` with zero company, peer, own-history, component,
snapshot, pointer, audit, or deletion writes. Activation time, database SHA,
mtime, size, page count, freelist, active identity and every content identity
were unchanged.

## Postflight And Immutability

The production analysis database grew from 1,146,810,368 to 1,152,614,400
bytes, exactly 5,804,032 bytes. Page count changed from 279,983 to 281,400;
freelist remained zero. Final SHA-256 is
`4e7bc02191a705a73942d7df40cecc92ed5719633091bcd7b4e4a7c92146df97`
and schema hash is
`20e81a6f075504fa11a7cae0ea0804902aa3083dd5e84c03354754dd104da9d0`.
Journal mode remains `delete`, WAL/SHM are absent, `quick_check=ok`, and the
foreign-key check is empty.

Pre/post protected inventories prove byte-identical canonical, provider,
market, taxonomy, ecosystem-dashboard, and combo-workbench databases. Existing
model/package invariants and all 15 production reports are unchanged; their
aggregate report fingerprint remains
`d95ff084174fc3b60ca533f75f6a55325d48479e242a55fd5a5b0d25a7886ad1`.
The active Operating-Income package is unchanged. Audit evidence is in
`.../preflight-audit/` and `.../postflight-audit/`.

The final audit after the complete repository suite is in `.../posttest-audit/`.
All main database hashes, schemas, counts, logical fingerprints and report
invariants still match postflight. Read-only test connections changed only the
mtimes of `analysis.db-shm` and `ecosystem_dashboard.db-shm`; both sidecars
retained the same 32,768-byte size and SHA-256
`fd4c9fda9cd3f9ae7c962b0ddf37232294d55580e1aa165aa06129b8549389eb`.
No logical or main-file content changed.

Measured persisted-reader times were 0.18 ms for one company, 1.06 ms for 20,
8.76 ms for 2,448 current-universe rows, and 5.32 ms for 2,245 universe-peer
rows. Evidence is `.../reader_latency.json`.

## Rollback

The safe-copy rehearsal under `.../rollback-rehearsal-2/` removed only the
Relative Valuation pointer, generated an explicit-unavailable report, restored
the exact pointer and activation time, and preserved non-Relative-Valuation
table fingerprints. SQLite and Relative Valuation checks passed.

Activation rollback uses `deactivate_snapshot()` when no previous Relative
Valuation snapshot exists, or `set_active_snapshot()` for a retained complete
snapshot. Full restore requires stopping writers, preserving the failed file,
verifying the retained backup SHA, restoring via SQLite backup semantics to a
new regular file, opening read-only, and requiring `quick_check=ok`, zero
foreign-key violations, original schema, and original active package before
replacement.

## Verification

- focused pre-write Relative Valuation/Snapshot tests: 149 passed
- production CLI gate after final tightening: 4 passed
- Snapshot/UI/stale-path group: 83 passed in 31.26 s
- complete Fundamentals V4: 798 passed in 101.03 s
- Snapshot, production-isolation and Scheduler group: 249 passed in 17.05 s
- complete repository: 2,729 passed, 8 warnings in 392.36 s
- `compileall` and `git diff --check`: passed

No installed optional linter was available, and none was installed. V1 uses an
explicit protected manual refresh after a successful source/market refresh;
there is no scheduler hook and report generation never refreshes the universe.
The main remaining limitation is the locked currently revised, non-PIT
semantic model.
