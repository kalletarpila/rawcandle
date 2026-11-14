# FIX8A — taxonomy SQLite sidecar compatibility and native preflight

**FIX8A correction and targeted acceptance: PASS. Fresh production readiness:
CONDITIONAL. The SQLite compatibility gate passed; a matching native disposable
acceptance receipt for the committed FIX8A source is still required before a
separate production activation task.** No live reconciliation, candidate, UPDATE,
FETCH, financial publication or review mutation was performed.

Starting branch: `chore/ignore-backups`. Starting HEAD:
`b00ba789e7eba904e014462aefb58ce4fd1f3ed2`. Accepted FIX8 implementation
`06e5b24107e0e53d191f868e463e63c595687f54`, initial adapter `de07f6336fe9`.
The task-owned final commit/HEAD is recorded after committing in the native
readiness run's `final_head.json`. Qualified source hashes are recorded separately
and checked against the committed blobs. Unrelated worktree files remain outside
the commit; no push is performed.

Governing evidence: [accepted FIX8](fundamentals_fix8_native_universe_reconciliation_2026-11-14.md),
[FIX7 selections](fundamentals_phase3d_fix7_approved_financial_selection_2026-11-13.md),
the exact failed run and the current native SQLite/taxonomy protection helpers.
This task grants no production activation or live UPDATE/FETCH authority.

## Established root cause and current observations

Failed native run:
`20261113T224303Z_refresh_fundamentals_cce2b9c73301_universe_reconciliation_5a9bd5d0`.
Its unchanged receipt records `BLOCKED / NATIVE_PREFLIGHT` and
`ADMIN_PRODUCTION_SQLITE_SIDECAR_PRESENT:analysis.db-wal`.

The exact original path was `SnapshotEnvironment.writer_lock()` calling
`production_transaction._no_sidecars()` for every role. That helper, unchanged at
`production_transaction.py:115`, rejects `Path(str(path)+suffix).exists()` for any
`-wal`, `-shm` or `-journal`, regardless of transaction or lock state. Taxonomy is
`data/analysis.db`; it is distinct from the accepted immutable Fundamentals
financial analysis role.

| Observation | WAL | SHM | Main taxonomy bytes |
| --- | ---: | ---: | ---: |
| Original failed FIX8 preflight | 0 | 32,768 | 14,378,782,720 |
| FIX8A initial inspection after the completed nightly run | absent | absent | 14,471,372,800 |
| Fresh protected readiness use and final exit | 0 | 32,768 | 14,471,372,800 |

Initial header journal versions were 2/2; actual native SQLite inspection confirms
`PRAGMA journal_mode = wal`. A small isolated database reproduces the incident:
an explicitly closed `mode=ro` read can leave WAL 0 B and SHM 32 KiB with unchanged
main-file contents. File existence alone therefore did not prove a pending
transaction. This is consistent with SQLite's [WAL/read-only lifecycle](https://www.sqlite.org/wal.html).
The historical sidecars' individual owner/origin cannot be reconstructed from the
old receipt; no claim is made that the scheduler created them. The current
completed nightly run legitimately changed the main taxonomy database; its old
whole-file hash is not an acceptance prerequisite.

Bounded process inspection found no visible descriptor owner of the taxonomy or
native lock paths. The wider process inspection had 25 inaccessible processes,
so it alone was not used to prove quiescence. Actual nonblocking native admin and
scheduler kernel lock acquisition, native taxonomy ownership and SQLite writer
reservation all succeeded during the readiness assessment. Stale admin lock text
(PID 3 from the old run) was not treated as kernel ownership. The completed
scheduler status reports `finished_at_utc=2026-11-14T07:27:48Z`, not running.

## Minimal scoped correction and safe contract

`_no_sidecars()` remains unchanged for provider, canonical, financial analysis and
market. Only Snapshot's taxonomy branch now opts into the existing
`protected_direct_taxonomy_source` helper's checkpointed protection.
Legacy direct-source callers retain their previous default behavior and semantic
binding. No database schema, financial rule, selection decision or scheduler
behavior changes.

The local writer scope acquires in order:

1. Existing Administration kernel lease.
2. Existing scheduler kernel lease.
3. Existing authoritative taxonomy operation owner.
4. An actual SQLite `mode=ro` read transaction, pinned by a schema read.
5. A separate SQLite `mode=rw` connection used solely for `BEGIN IMMEDIATE`, then
   `PRAGMA query_only=ON`; it performs no DML and always rolls back.

The fifth connection reserves SQLite's own writer slot without changing data;
an active SQLite writer causes an immediate failure. Native and direct SQLite
writers are excluded for the consumer lifetime, while readers remain compatible.
The RO transaction stays alive until **after** the reservation connection closes.
Its main-file shared lock prevents the last-RW-close checkpoint/cleanup path,
including the tested race where another connection commits WAL just before
reservation acquisition. The RO connection then closes last. SQLite's documented
[transaction rules](https://www.sqlite.org/lang_transaction.html) and
[WAL locking/lifecycle](https://www.sqlite.org/walformat.html) support this ordering.
There is no `wal_checkpoint`, journal-mode setter, VACUUM, direct sidecar unlink or
truncate. No low-level custom WAL parser, OS byte-lock implementation, process
manager or additional source/publication framework is introduced.

| State | Snapshot taxonomy decision |
| --- | --- |
| Clean DELETE/WAL database, no sidecars | Accept under native ownership and SQLite reservation |
| Empty WAL plus regular same-owner SHM in native 32 KiB units | Accept only with WAL mode, stable source identity and held protection |
| Completed TRUNCATE checkpoint, empty WAL/SHM retained | Accept under the same protection; checkpoint occurs only in test fixtures |
| Valid nonempty committed/uncheckpointed WAL | Reject `TAXONOMY_SQLITE_NONEMPTY_WAL`; preserve it intact, never ignore committed data |
| Nonempty WAL retained after another checkpoint | Same conservative rejection; this route does not infer backfill state |
| Active reader | Compatible, including readers in other connections/processes |
| Active writer, pending transaction or competing native taxonomy owner | Fail closed without waiting or altering that owner's lock |
| Corrupt nonempty WAL | Reject before SQLite is opened; no attempted repair/recovery |
| Orphan, symlink, foreign-owner/device, multiply linked or malformed sidecar | Reject as ambiguous/inconsistent |
| Main source replaced/changed during acquisition or protected use | Reject dependency drift |

No new WAL-bearing logical-source fingerprint format is invented. Because this
route accepts only checkpointed main data, the existing main-file dependency
identity remains truthful; current native DC semantic binding still comes from
`bind_taxonomy_source`. Transient SHM lock bytes are not source authority.
Protection is acquired cheaply at writer entry; semantic dependency calculation
remains at the native `_taxonomy()` source-use boundary. `_taxonomy()` reuses the
held owner, avoiding a second taxonomy acquisition. Locks are released with the
local writer scope, never retained across source network work or cooldowns.

An unpinned reservation prototype was rejected before any production use because
last-RW-close could checkpoint a raced WAL. The final pinned-reader implementation
has an explicit regression proving that both the main database and the raced
committed WAL remain byte-identical on rejection. An alternative low-level-lock
prototype was also discarded after a same-process lock-lifetime failure. Only the
final `qualified.xml` run counts as current acceptance.

## Targeted acceptance and FIX8 compatibility

**60 passed**, zero failures/errors/skips, JUnit duration **57.046 s**:

| Focus | Cases |
| --- | ---: |
| New SQLite/native taxonomy sidecar cases | 30 |
| Existing FIX8 reconciliation/publication/rollback/recovery cases | 22 |
| Directly relevant existing native taxonomy/source-bundle regressions | 8 |

Coverage includes clean sources, reproduced zero WAL/SHM, completed checkpoints,
valid committed WAL rejection without data loss, active readers, active/pending
writers, corrupt/ambiguous/foreign-owned states, source replacement, acquisition
and binding drift, protected consumer lifetime, SQL no-write evidence and
same-process lock preservation after rejected acquisition. Real subprocesses
verify that another SQLite writer cannot enter until the guard is released.

A real FIX8 disposable run with empty WAL/SHM completes native generation
publication and postflight. Ordinary failures before/after activation restore OLD.
The unchanged FIX8 regression selection verifies inactive preparation, native
journal/crash recovery, stale authority rejection, economic input equivalence and
unchanged financial validation. Unsafe WAL still blocks before candidate creation.
The exact twelve approved decisions and financial selection rules are unchanged.
The adapter code binding now explicitly includes `snapshot_environment.py` and
`source_bundle.py`, preventing reuse of earlier qualification that omitted the
corrected guard.

The final test run used the socket-denial plugin; actual socket attempts were 0.
Earlier development artifacts are retained separately and are not additional
independent coverage. No full repository, unrelated Fundamentals or StockCore
suite was run. No targeted failure demonstrated a need to run those suites.

## One fresh read-only production readiness assessment

Native run: `20261114T104517Z_refresh_fundamentals_cce2b9c73301_fix8a_readiness_d80384c8`.
Start `2026-11-14T10:45:17.433871+00:00`; end `2026-11-14T10:46:15.733736+00:00`;
elapsed **57.683 seconds**. This is a readiness metadata run, not an
UPDATE. No production reconciliation entry point, candidate installer, generation
preparer, backup routine, recovery mutation or financial workflow was invoked.

The SQLite compatibility gate **PASSED**, including the actual reproduced
empty-WAL/SHM state left by native read-only use. The assessment checked current
financial roles through native SQLite integrity and manifest hashes; current
universe, review queue, identity registry, HOLD/configuration, source availability,
taxonomy semantic binding, actual leases and disk/inode capacity. Twelve physical
identity/provider tuples and accepted financial provenance were reverified
read-only, without generating a new candidate version or changing selection rows.

Current active financial generation:
`current_rebuild_2a684ef130c6a540de4adc560ab171ad`.
Current installed operational universe:
`3b8121b74c852f08575fa1e2b70004e6`.
Financial watermark: `2026-10-28`.
Native journal: `COMPLETED / PASSED / NOT_REQUIRED`; no recovery action needed.

Approved intended selections reverified (not newly installed):

| Company | Representative/security/Sharadar | Retained companion security |
| ---: | --- | ---: |
| 442 | CENT / 442 / 197778 | 443 |
| 627 | CYCN / 628 / 111101 | 2558 |
| 886 | FOXA / 888 / 111125 | 887 |
| 912 | FWONA / 914 / 191707 | 915 |
| 969 | GOOGL / 973 / 195146 | 972 |
| 1272 | LBTYA / 1277 / 191556 | 1278 |
| 1296 | LILA / 1302 / 121104 | 1303 |
| 1307 | LLYVA / 1314 / 640301 | 1315 |
| 1407 | METC / 1415 / 124161 | 1416 |
| 1600 | NWSA / 1610 / 191637 | 1609 |
| 2243 | UAA / 2254 / 194726 | 2253 |
| 2441 | ZG / 2458 / 179220 | 2452 |

KRSA retains **160 OLD provider observations** and no fabricated Sharadar map.
Existing OLD identity, history and financial approvals remain unchanged; intended
selection approval does not finalize or transfer review authority.

Current taxonomy is `DC_TAXONOMY_FULL_V2_1`, 350 membership rows, semantic
fingerprint `801698f6b352c445cc8e6f5fd51a1cac2779d11f6ce72a1c10bf71bb8aae4559`.
Market required native tables are available. Current source identities are bound
at this assessment's protected point, not to old nightly whole-file hashes.
Free space was **550,506,221,568 bytes**, free inodes
**66,706,420**. Native-equivalent storage arithmetic estimates
**22,361,534,464 bytes** for a later reconciliation's
local stages/backups on this filesystem. No backup/copy was created for this check.

Overall readiness is **CONDITIONAL**, not live activation permission. The earlier
FIX8 disposable receipt now fails the exact source binding with
`UNIVERSE_RECONCILIATION_MATCHING_ACCEPTANCE_REQUIRED`. A fresh native acceptance receipt must bind the
committed FIX8A code and its actual tests before a separate production activation
preflight. No approval or matching receipt was fabricated to turn that into PASS.
Current candidate economic equivalence, expected-OLD activation and postflight
remain mandatory in that later operation. This task authorizes no such operation.

**Recommended next operational action:** perform a separately authorized FIX8
identity-only activation task, starting with a fresh native Test binding to the
final FIX8A commit and a current-state preflight, preserving the exact twelve
choices and every financial publication restriction. Do not start Phase 3E until
that separate identity reconciliation is verified.

## Production no-write and scheduler evidence

The readiness wrapper adds a SQL authorizer that denies data/schema writes,
checkpoint/optimization calls and persistent PRAGMA setters on every connection.
Observed statement classes: `{"BEGIN": 2, "PRAGMA": 61, "ROLLBACK": 2, "SELECT": 2296}`.
Rejected write attempts: 0; data/schema write statements: 0. Network/socket
attempts: 0. Both the reservation's SQL rollback and the pinned reader's rollback
are explicit in the trace. Native SQLite opening created transient WAL 0 B / SHM
32 KiB, which remain after the final RO close. This is recorded honestly as
transient SQLite metadata creation, not a durable taxonomy data write.

Taxonomy main device/inode/size/mtime are identical before and after protected use.
All three financial role metadata sets are unchanged after native role verification.
Active generation manifest, publication journal and scheduler configuration
SHA-256/metadata compare exactly. Review queue content binding and identity
registry checksum also match before/after. There were no financial, taxonomy data,
review queue, active universe/generation or watermark changes by this task.
No sidecar was manually removed/truncated, no database optimized and no older
market/taxonomy file restored.

Fundamentals remains disabled / HOLD, `SNAPSHOT_V1 / FULL_WORKFLOW`. Scheduler
configuration is byte-identical to initial state. It records 04:30 Helsinki while
the task names 04:45; neither value was changed. The already completed normal
nightly run is confirmed separately; no normal job was stopped, restarted or
reconfigured. All readiness leases were released on exit.

## Changed files, evidence and Git

Intentional versioned files only:

- `rawcandle/fundamentals/admin/source_bundle.py`: opt-in checkpointed SQLite
  protection inside the existing direct taxonomy helper.
- `rawcandle/fundamentals/admin/snapshot_environment.py`: scoped taxonomy handling,
  existing lock order and reuse of the protected owner through local postflight.
- `rawcandle/fundamentals/admin/universe_reconciliation.py`: bind corrected source
  helper/environment bytes in native qualification.
- `tests/test_fundamentals_taxonomy_sidecars.py`: 30 focused cases.
- This report and the accepted FIX8 report's follow-up contract note.

Native evidence and report directory:
`fundamental_reports/admin_runs/20261114T104517Z_refresh_fundamentals_cce2b9c73301_fix8a_readiness_d80384c8/`.
Detailed read-only result, SQL class counts, source hashes, no-write evidence and
commit metadata are there. JUnit, network ledgers, initial state/process evidence
and tested source hashes remain under ignored
`temp/fundamentals_fix8a_20261114/`. Disposable fixtures remain under task-owned
`/tmp/rawcandle_fix8a_*` directories. No runtime database, sidecar, evidence bundle,
cache, backup, test output or unrelated worktree change is committed. Push: **NO**.
