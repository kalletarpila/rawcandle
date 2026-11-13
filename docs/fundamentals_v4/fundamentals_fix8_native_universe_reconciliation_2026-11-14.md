# FIX8 — native identity-only universe reconciliation

**Implementation and disposable acceptance: PASS. Production gate: pending the
fresh native invocation after this source commit.** The implementation completes
FIX7's missing adapter using the existing generation preparer, expected-OLD
activation, durable journal, postflight and recovery. It does not introduce a
publication engine, identity registry, schema migration or financial calculation.
Phase 3E remains conditional on verified production reconciliation.

Starting accepted FIX7 HEAD: `40976977ddb96a05c0fa4202363901819a527a47`.
Governing inputs are [FIX7](fundamentals_phase3d_fix7_approved_financial_selection_2026-11-13.md),
[FIX6](fundamentals_phase3d_fix6_financial_membership_resolution_2026-11-13.md),
[FIX5](fundamentals_phase3d_fix5_representatives_actual_history_2026-11-13.md),
current native generation/journal/source contracts and the explicit combined
FIX8 + Phase 3E operator authorization. No StockCore access is needed.

The user authorizes identity-only production activation only after native
acceptance/preflight succeeds. That authorization does not permit publishing a
Phase 3E financial UPDATE, advancing its watermark, approving reviews, publishing
ownership/P/B, changing the twelve choices or enabling automatic Fundamentals.
No redundant operator approval is requested by the adapter.

## Exact approved scope

The live adapter requires the existing FIX7 approval content fingerprint
`edbde9bd7016eceac4b9a71dead231eb0b84670c66f31181f15291e708ce07d3`.
Changing a tuple or approval reference invalidates this scope.

| Company | Financial representative / security | Sharadar ID | Retained companion / security |
| ---: | --- | --- | --- |
| 442 | CENT / 442 | 197778 | CENTA / 443 |
| 627 | CYCN / 628 | 111101 | KRSA / 2558 |
| 886 | FOXA / 888 | 111125 | FOX / 887 |
| 912 | FWONA / 914 | 191707 | FWONK / 915 |
| 969 | GOOGL / 973 | 195146 | GOOG / 972 |
| 1272 | LBTYA / 1277 | 191556 | LBTYK / 1278 |
| 1296 | LILA / 1302 | 121104 | LILAK / 1303 |
| 1307 | LLYVA / 1314 | 640301 | LLYVK / 1315 |
| 1407 | METC / 1415 | 124161 | METCB / 1416 |
| 1600 | NWSA / 1610 | 191637 | NWS / 1609 |
| 2243 | UAA / 2254 | 194726 | UA / 2253 |
| 2441 | ZG / 2458 | 179220 | Z / 2452 |

FIX7's preparer rechecks current ownership, mappings, installed membership and
accepted provider/canonical provenance against exact OLD. KRSA has no incoming
map or eligibility; all 160 OLD provider observations remain protected. Neither
companion identities nor security-specific market/ownership economics change.
PSQL/QVCG remain historical authority, without manufactured provider maps.

## Adapter and native installation contract

`admin/universe_reconciliation.py:run_reconciliation` accepts only the native
`SnapshotEnvironment`, with its real production paths or qualified owned copy.
Relabelled live/copy flags, foreign environment shapes and mismatched copy-owner
roots are rejected. Explicit identity-only confirmation and production intent
are required; a financial UPDATE confirmation grants no authority here.

Before processing, the adapter loads a fingerprinted native Administration
`DISPOSABLE_ACCEPTANCE` result. It must attest the executed activation, postflight,
rollback, preparation/activation recovery, economics and stale-authority tests,
match exact tested source and approval fingerprints and cite test evidence. Live
use additionally requires the committed tested HEAD, matching committed source
bytes and the existing native source/worktree binding. This is a native Test
receipt for this operation; it is not a financial review approval or new registry.

Under the native Administration + scheduler kernel locks, the adapter:

1. Checks the healthy native journal/recovery state and explicit expected OLD and
   starting universe. It binds current configuration/HOLD, native queue authority,
   identity-review registry and code; rejects sidecars via the native environment;
   checks native disk estimates and available inodes.
2. Revalidates the twelve choices through the accepted FIX7 preparer. It preserves
   the exact old version, all unrelated members, historical members and identity
   mappings. The new version corrects CYCN/KRSA's stale counts without retiring
   or merging securities or transferring provider identity.
3. Binds a **current native compact market bundle and protected direct taxonomy**
   at the accepted analysis calculation date. OLD must pass the existing full
   native V2/package/RP/RV source/result validator before any financial role copy.
   Existing explicit universe-bound analysis dependencies requiring another
   reconciliation contract are rejected, not silently relabelled.
4. Copies all three immutable financial roles exactly, applies only the versioned
   universe selection in the inactive canonical copy, and proves schema plus all
   non-universe canonical table contents unchanged. Provider and analysis remain
   byte-identical to OLD. The copied analysis must pass native validation against
   the new canonical authority and the same staged read-only dependencies.
5. Rechecks OLD/universe/configuration/queue/registry/code, obtains verified native
   immutable backups, prepares one complete generation and writes the native
   generation-pointer journal. Expected-OLD activation and postflight verify the
   twelve representatives and role hashes before journal completion.

Ordinary failure restores OLD through the native journal **while writer/scheduler
ownership remains held**. Interrupted preparation or activation leaves native
recovery evidence; native recovery verifies the full prior role set and pointer.
There are no direct production SQL patches, standalone membership-pointer
publication or manually repaired manifests. No network call occurs in this adapter.

An identity-only generation activation, if it succeeds, is explicitly distinct
from financial UPDATE publication: provider, analysis, every accepted financial
fact/provenance/date/TTM row and financial watermark remain unchanged. If native
validation would require recomputing/replacing accepted economics, activation
stops. This task does not relax that condition.

## Disposable acceptance

**85 distinct targeted cases PASS.** The regression run passed 82 cases; the
final adapter run passed 20, including three final environment-scope checks.
Their seventeen overlapping adapter cases are counted once. No full suite or
StockCore suite was run; no failure demonstrated unrelated shared-core impact.

| Selection | Distinct passing cases |
| --- | ---: |
| New native reconciliation adapter | 20 |
| Accepted FIX7 selections, twelve real tuples and publication/history checks | 24 |
| FIX4 reviewed OLD retention, including null-provider restrictions | 15 |
| FIX5 actual historical endpoint gates and rollback | 6 |
| Installed membership, identity, reviews/accounting and old-scope regressions | 20 |

The new adapter tests exercise native preparation, atomic activation, postflight,
ordinary rollback at three boundaries, recovery before/after activation, stale
OLD/universe/code/qualification rejection, source drift, unchanged financial role
bytes and canonical economics, current-source RV mismatch STOP, scheduler margin
and native environment isolation. A published disposable selected universe feeds
the real snapshot FETCH/VALIDATE path with publication and ownership intent false.
No analysis rebuild is needed for a source-compatible identity-only case.

Final source/test hashes and JUnit/socket ledgers are retained under ignored
`temp/fundamentals_fix8_20261113/`. Actual source commit and production gate result
will be recorded in native Administration evidence after committing accepted code.

## Current observations and production gate

Fresh starting reads observed active generation
`current_rebuild_2a684ef130c6a540de4adc560ab171ad`, installed universe
`3b8121b74c852f08575fa1e2b70004e6`, source watermark `2026-10-28`, and native
journal `COMPLETED` / `PASSED` / `NOT_REQUIRED` for the prior controlled rebuild.
Scheduler configuration remains `SNAPSHOT_V1` / `FULL_WORKFLOW`, Fundamentals
automatic refresh disabled. These observations are rechecked by the live gate.

A preliminary read-only native validation of current OLD against current source
dependencies returned `V2_REBUILD_RV_SOURCE_OR_RESULT_MISMATCH` at the accepted
analysis date `2026-10-30`. Internal package checks had progressed to the native
RV/source comparison. This is evidence of a baseline compatibility boundary,
not a demonstrated root cause or permission to rebuild accepted results. The
fresh protected-source preflight after source commit determines whether activation
can proceed; no production success is claimed from the disposable tests.

Production runs and their source/selection/qualification/results are retained in
the existing `fundamental_reports/admin_runs/` infrastructure. The original failed
UPDATE `20261112T194901Z_refresh_fundamentals_a45d1fafcc56_snapshot_update_c604bb4c`,
its FETCH/SEC and validation evidence are not reused or modified.

If the fresh gate fails, production activation and Phase 3E stop. If it succeeds,
only the exact identity-only reconciliation may activate; a healthy completed
journal, preserved OLD and active approved selectors must be verified before
creating **one new** manual SNAPSHOT_V1 UPDATE. That UPDATE must use publication
and ownership intent false, existing Sharadar/SEC/freshness/quarantine policies,
and stop at legitimate BLOCKED/REVIEW_REQUIRED or inactive CANDIDATE_READY.

## Scheduler and resource boundaries

Normal nightly scheduling is not changed. Native scheduler leases are acquired
nonblockingly for local stages. The live adapter refuses to start an expensive
local reconciliation within the final sixty minutes before the next 04:45
Europe/Helsinki start. It never holds writer/taxonomy locks across source network
requests, pauses or cooldowns; live acquisition remains a separate native stage.

Market/taxonomy may legitimately change during normal jobs. They are bound at the
current native source stage; no historical whole-file checksums are required to
remain unchanged. Immutable original UPDATE evidence and financial/configuration
state are inventoried separately. Native source compatibility failures remain
visible and are not waived as ordinary checksum drift.

Necessary candidates, compact bundles and native backups may grow. No database
size cap, VACUUM, deduplication, schema/retention reduction, storage optimization or
unrelated cleanup is introduced. Actual operational timing/storage and before/after
generation/universe results belong in the final gate evidence/report update.

Task-owned files: the adapter, its focused tests, this report and the FIX7 follow-up
link. Runtime data, generated evidence and pre-existing unrelated changes are
excluded from Git. Push: **NO**.
