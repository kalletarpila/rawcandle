# SIMPLIFY-02 — one confirmed generation and retained-OLD rollback

Implementation follows [SIMPLIFY-01](fundamentals_simplify01_architecture_audit_2026-11-14.md).
Starting HEAD: `9dd6ff4d160257f9a7667532edaf1ffa97fea529`.
Production activation, live acquisition and financial/review writes are outside
this task. All execution evidence below is from native disposable environments.

## Changes and remaining contract

`universe_reconciliation.py` no longer defines `_qualification`,
`QUALIFIED_FEATURES` or accepts `qualification_run_id`. Test fixtures no longer
write a synthetic `DISPOSABLE_ACCEPTANCE` result. No replacement issuer or
acceptance receipt is introduced.

The same existing run prepares and verifies B using native generation preparation.
Publication additionally requires `confirm_candidate(binding)`: a caller confirms
the exact binding it receives, or declines by returning anything else. The callback
gets a detached copy; the adapter compares its response to the original verified
binding. This is the single exact-candidate operator confirmation, not a test PASS.
The existing operation confirmation string and live/copy intent still restrict
which operation/environment the caller is invoking.

The binding records operation ID, B's generation manifest/role hashes, expected A,
approved selection fingerprint, installed/candidate universe, configuration,
review/identity registry and relevant code authority, and semantic dependencies.
After confirmation the adapter rechecks current authority, B role bytes, staged
market bytes and nightly coordination before recording publication intent. The
protected taxonomy reader remains held through the local consumer/postflight.
The callback must return from existing operator intent without network or human
waiting under the writer lease. No live call is made by this task.

Prepared B metadata is retained in the operation result even if confirmation is
refused. Existing native journal preparation, atomic activation/fsync, economic
postflight and rollback remain the publication engine. Candidate failure leaves A
active; no copied approval or unrelated test authorizes a pointer change.

`refresh_update._code_binding` uses the financial source tree plus relevant dirty
changes and entry hashes, rather than repository HEAD itself. Documentation-only
commits therefore do not invalidate this binding. Relevant financial source/model
changes still change it; FIX8 also binds its direct model/verification modules.
Normal financial candidate publication keeps its existing exact-candidate operator
grant and financial/review gates; only its rollback source changes here.

## No additional OLD copies

`refresh_production._verified_backups` retains its legacy default. Its explicit
`retain_old=True, immutable_generation=True` branch verifies a real current
retained generation and role paths/hashes/absence of sidecars. It returns references
to A's existing role files using the current journal record shape. It does not
create a backup directory or copy OLD. Only `refresh_update._publish_candidate`
and FIX8 reconciliation opt into this path in this change.

Three additional OLD role copies are eliminated per qualified operation. At the
current role sizes this avoids **2,630,053,888 copied bytes per operation**.
Necessary B construction still has its own provider/canonical/analysis files.
Existing shared storage estimates remain conservative; no global storage manager,
VACUUM, deduplication or historical-artifact cleanup is introduced.

`publication_journal` continues to validate its rollback references. New retained
references resolve to A itself; historical copied-backup references continue to
resolve to those copies. The journal format remains version 1 and older records
remain readable. There is no second journal/recovery mechanism.

Before pointer recovery, current active generation must be this operation's A or
B. An unexpected C causes recovery failure without changing C. Reactivating A also
passes the observed current generation ID into the native expected-generation
check, preventing a stale rollback switch. Missing/corrupt A fails closed. The
legacy ROLE_REPLACEMENT restoration branch still verifies and restores physical
backups; other `_verified_backups` callers and existing backup files are unchanged.

Successful publication retains A; recovery cleanup protects its role paths. No
new code deletes A after postflight, deletes historical backups or implements an
acceptance/retention manager. A remains a rollback obligation until later operator
acceptance and safe cleanup. A failed confirmation can leave an inactive prepared
B for diagnosis; it is never activated automatically.

## Disposable validation

The focused selection covers:

- Native A/B preparation, activation and economic postflight, ordinary failures
  before/after activation and interrupted preparation/activation recovery.
- Mandatory exact confirmation, wrong B/A, wrong role hash, changed candidate
  bytes, review/configuration drift, and stale starting universe/OLD/code.
- Missing/corrupt A, no backup role copies, retained A after success, completed
  publication recovery no-op, and refusal to overwrite an independently installed C.
- All twelve approved identity tuples with authored economics, companions,
  provider/canonical history, source restrictions and no duplicate company history.
- Safe empty taxonomy WAL/SHM, unsafe WAL rejection and protected source lifetime.
- Normal native financial snapshot publication/recovery, old copied-backup
  journals, and explicit legacy ROLE_REPLACEMENT recovery from physical backups.

Two legacy test modules now select LEGACY explicitly inside their fixtures instead
of inheriting the local SNAPSHOT_V1 scheduler setting. Production configuration is
not edited. The original missing import found during development was corrected;
intermediate failing runs are retained as development evidence, not acceptance.
The focused suite is not the full repository suite. Final qualification: **153 PASS**, zero failures/errors/skips. Counts and duration
are recorded below.

## Production preservation and changed files

No production operation, backup, candidate, UPDATE, source network call, review
approval or scheduler mutation is performed. Before/after protected metadata
checks cover the active manifest, journal, scheduler configuration and all three
financial role files. The existing active generation/universe remain
`current_rebuild_2a684ef130c6a540de4adc560ab171ad` /
`3b8121b74c852f08575fa1e2b70004e6`; Fundamentals remains HOLD. Financial acceptance,
publication-date semantics, historical retention, identity evidence and the twelve
approved choices are unchanged.

Intentional source changes: `admin/universe_reconciliation.py`,
`admin/refresh_production.py`, `admin/refresh_update.py`,
`admin/publication_journal.py`. `generations.py` and `snapshot_environment.py` are
reused without changes. Test changes: new
`test_fundamentals_simplified_publication.py`, removal of the FIX8 fixture receipt
in `test_fundamentals_universe_reconciliation.py`, and explicit legacy routing in
`test_fundamentals_generations.py` / `test_fundamentals_generation_recovery_binding.py`.
Documentation: this report and the FIX8 follow-up contract note.

Evidence remains under ignored `temp/fundamentals_simplify02/`, the socket-denial
ledgers under `temp/fundamentals_fix8a_20261114/rawcandle_simplify02_*_network.json`,
and owned `/tmp/rawcandle_simplify02_*` fixture copies. Old journal/backup artifacts
are not removed. No runtime evidence is committed. Push: NO.

Next action: a separate production readiness assessment using the committed code,
current OLD/universe/dependencies, and explicit exact-B/A confirmation. This task
does not authorize production activation or live acquisition. No new test-receipt
issuer is a prerequisite. SIMPLIFY-01's VALIDATE/SEC changes remain later work.

## Final evidence

**153 PASS**, JUnit duration 409.872 seconds; socket attempts **0**.

- `tests.test_fundamentals_financial_selection`: 24.
- `tests.test_fundamentals_generation_recovery_binding`: 19.
- `tests.test_fundamentals_generations`: 13.
- `tests.test_fundamentals_simplified_publication`: 12.
- `tests.test_fundamentals_snapshot_integration`: 34.
- `tests.test_fundamentals_taxonomy_sidecars`: 30.
- `tests.test_fundamentals_universe_reconciliation`: 21.

Current implementation source hashes match the final test evidence. Protected
live manifest/journal/configuration and financial role metadata match the
pre-task baseline. No implementation blocker remains in the targeted scope.
Production readiness and any activation remain separate authorized work.
