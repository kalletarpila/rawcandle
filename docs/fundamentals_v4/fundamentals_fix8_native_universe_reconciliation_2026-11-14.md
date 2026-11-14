# FIX8 — native identity-only universe reconciliation

[SIMPLIFY-02](fundamentals_simplify02_publication_rollback_2026-11-14.md)
supersedes the extra disposable-acceptance gate below: publication now uses a
verified native B and explicit exact-B/A confirmation, with retained immutable A
as rollback source. Historical FIX8/FIX8A/FIX8B observations below are preserved;
they do not describe the new authorization API. No production activation occurs
in SIMPLIFY-02.

Subsequent [FIX8A](fundamentals_phase3d_fix8a_taxonomy_sidecar_compatibility_2026-11-14.md)
corrects the taxonomy-only sidecar compatibility boundary. Snapshot retains strict
sidecar rejection for financial and market roles. Taxonomy now requires the native
owner plus a pinned RO transaction and query-only SQLite writer reservation;
only checkpointed/empty-WAL states pass and source identity remains protected for
the consumer lifetime. The fresh read-only SQLite gate passed; overall readiness
is conditional on a new native Test binding for the committed FIX8A code. No
production reconciliation or UPDATE was authorized or executed by FIX8A. The
original FIX8 incident/result below remains historical evidence.

**Implementation and disposable acceptance: PASS. Production gate: BLOCKED by
the native taxonomy SQLite sidecar guard. Phase 3E: NOT REACHED.** The implementation completes
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
   at the accepted analysis calculation date. OLD is checked as an already accepted historical result; its current native
   RV input fingerprint is captured before any financial role copy.
   Accepted V2 package/physical integrity is checked natively. Existing explicit
   universe-bound analysis dependencies requiring another contract are rejected,
   not silently relabelled.
4. Copies all three immutable financial roles exactly, applies only the versioned
   universe selection in the inactive canonical copy, and proves schema plus all
   non-universe canonical table contents unchanged. Provider and analysis remain
   byte-identical to OLD. The copied analysis must retain native package integrity and the exact same
   economic company domain and native RV inputs under the new authority and
   those same staged dependencies.
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
fact/provenance/date/TTM row and financial watermark remain unchanged. If the identity operation changes native economic inputs or accepted result
contents, activation stops. The native financial rebuild validator is unchanged: a
financial UPDATE candidate must still match its fresh source/result calculation.

## Disposable acceptance

**87 current-code targeted cases PASS**, zero failures/errors/skips in the final
qualification run. It includes all 22 adapter cases and 65 directly relevant
FIX3–FIX7 regressions. Earlier prototype runs are not counted as additional
independent coverage. No full suite or
StockCore suite was run; no failure demonstrated unrelated shared-core impact.

| Selection | Distinct passing cases |
| --- | ---: |
| New native reconciliation adapter | 22 |
| Accepted FIX7 selections, twelve real tuples and publication/history checks | 24 |
| FIX4 reviewed OLD retention, including null-provider restrictions | 15 |
| FIX5 actual historical endpoint gates and rollback | 6 |
| Installed membership, identity, reviews/accounting and old-scope regressions | 20 |

The new adapter tests exercise native preparation, atomic activation, postflight,
ordinary rollback at three boundaries, recovery before/after activation, stale
OLD/universe/code/qualification rejection, source drift, unchanged financial role
bytes and canonical economics, operation-induced native-input drift STOP, scheduler margin
and native environment isolation. A published disposable selected universe feeds
the real snapshot FETCH/VALIDATE path with publication and ownership intent false.
No analysis rebuild occurs for an identity-only operation. A test deliberately
changes market prices after OLD acceptance: identity-only publication preserves
OLD while native financial rebuild validation still rejects its stale RV result
both before and after the identity operation. No financial freshness is reasserted.

Final source/test hashes and JUnit/socket ledgers are retained under ignored
`temp/fundamentals_fix8_20261113/`. Actual source commit and production gate result are recorded in native
Administration evidence after committing accepted code. The first operational
Test receipt was correctly rejected before the database phase because its
descriptive authorization field was redacted after fingerprinting. Its original
record is retained; subsequent Test receipts fingerprint the final sanitized
native payload. No approval or verification check is bypassed.

## Current observations and production gate

Fresh starting reads observed active generation
`current_rebuild_2a684ef130c6a540de4adc560ab171ad`, installed universe
`3b8121b74c852f08575fa1e2b70004e6`, source watermark `2026-10-28`, and native
journal `COMPLETED` / `PASSED` / `NOT_REQUIRED` for the prior controlled rebuild.
Scheduler configuration remains `SNAPSHOT_V1` / `FULL_WORKFLOW`, Fundamentals
automatic refresh disabled. These observations are rechecked by the live gate.

A preliminary read-only **financial-rebuild** validation of current OLD against
current source dependencies returned `V2_REBUILD_RV_SOURCE_OR_RESULT_MISMATCH` at the accepted
analysis date `2026-10-30`. Internal package checks had progressed to the native
RV/source comparison. It is not permission to rebuild accepted results. Review of native generation
activation and the model read closure showed the purpose distinction: generation
activation accepts verified role contents, while financial rebuild validation
compares newly calculated results to current inputs. Of the model readers in this
bounded scope, RV alone reads the operational universe, and its calculation uses
the eligible company domain; the version identifier is diagnostic metadata.

The corrected adapter therefore proves identity-only reuse through unchanged
financial/provider/analysis contents, unchanged native V2 package fingerprints,
identical economic company membership and equal before/after native RV input
fingerprints under one current staged market/taxonomy source. It retains original
calculation dates/provenance and records `financial_freshness_reasserted=false`.
The native financial rebuild validator and every financial UPDATE acceptance gate
remain unchanged. This avoids treating legitimate independent source maintenance
as an identity-induced financial mutation. The reuse proof is retained in the
native publication journal scope evidence. No production success is claimed
from disposable tests.

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
state are inventoried separately. Operation-induced economic input changes remain STOPs. Existing financial
freshness is neither repaired nor relabelled by identity publication.

Necessary candidates, compact bundles and native backups may grow. No database
size cap, VACUUM, deduplication, schema/retention reduction, storage optimization or
unrelated cleanup is introduced. Actual operational timing/storage and before/after
generation/universe results belong in the final gate evidence/report update.

Task-owned files: the adapter, its focused tests, this report and the FIX7 follow-up
link. Runtime data, generated evidence and pre-existing unrelated changes are
excluded from Git. Push: **NO**.

## Actual production gate and final outcome

**FIX8 source and disposable acceptance PASS; production reconciliation BLOCKED;
Phase 3E NOT REACHED.** No production universe was installed and no new UPDATE was
allocated. This is an actual native STOP, not a successful rollout.

Source history:
- Accepted starting FIX7: `40976977ddb96a05c0fa4202363901819a527a47`.
- Initial adapter commit: `de07f6336fe99858101cb07aaadc6e0d8fd3c19e`.
- Final qualified FIX8 implementation: `06e5b24107e0e53d191f868e463e63c595687f54`.
- A separate final documentation commit records this outcome. The exact final
  repository HEAD is recorded after that commit in native run
  `20261113T224303Z_refresh_fundamentals_cce2b9c73301_universe_reconciliation_5a9bd5d0/final_head.json`; source/test bytes remain those qualified above.

Qualification `20261113T224216Z_refresh_fundamentals_cce2b9c73301_fix8_disposable_acceptance_53f5dd45` is a sealed native Administration Test receipt. Readback
verification passed with all nine required features, exact FIX7 approval content,
committed source hashes and native source binding. Its qualified JUnit records
**87 PASS**, zero failures/errors/skips, **177.629 seconds**. Prototype/development
runs are preserved separately and are not added to the independent test count.
The explicit operator identity-only production permission was present; complete
production preflight was **not** satisfied.

Native production reconciliation `20261113T224303Z_refresh_fundamentals_cce2b9c73301_universe_reconciliation_5a9bd5d0` began and finished at
`2026-11-13T22:43:03Z` (second-resolution timestamps). It returned:

```text
outcome: BLOCKED
failed_stage: NATIVE_PREFLIGHT
error: ADMIN_PRODUCTION_SQLITE_SIDECAR_PRESENT:analysis.db-wal
```

`SnapshotEnvironment.writer_lock()` checks all five native role paths for SQLite
sidecars before yielding ownership to the adapter. The blocked role is
**taxonomy**, `/home/kalle/projects/rawcandle/data/analysis.db`, not the immutable
Fundamentals financial analysis role. Observed sidecars at final verification:

| Artifact | Bytes | Observed mtime UTC |
| --- | ---: | --- |
| `data/analysis.db-wal` | 0 | 2026-11-13T21:52:23.891630+00:00 |
| `data/analysis.db-shm` | 32,768 | 2026-11-13T21:52:23.898258+00:00 |

The native contract rejects existence, including a zero-length WAL. Sidecar
ownership/origin was not proven; the timestamp overlaps this task's read-only
source inspection and is not evidence of financial mutation or a current writer.
Neither sidecar was removed, checkpointed or used to weaken the native gate.
There was no activation intent, live candidate copy, generation preparation,
publication backup or reconciliation journal entry. The live twelve-selection
provenance/candidate phase was not entered. The approved twelve tuples above remain
the exact tested intended content; they are **not** claimed installed in production.

The missing operational boundary is a qualified native taxonomy SQLite
connection/sidecar lifecycle that permits the existing writer precondition to
succeed. Investigate and resolve that boundary natively before another fresh
preflight. Do not remove files manually, relabel a candidate, bypass the guard or
make a financial acceptance-policy change. The original conditional authorization
is not an unrestricted permission to change the native source lifecycle.

### Final financial and evidence preservation

Fresh final verification at `2026-11-13T22:45:30.180225+00:00` found:

| Authority | Before | After |
| --- | --- | --- |
| Financial generation | `current_rebuild_2a684ef130c6a540de4adc560ab171ad` | same |
| Installed universe | `3b8121b74c852f08575fa1e2b70004e6` | same; no new installed version |
| Financial watermark | `2026-10-28` | `2026-10-28` |
| Native journal | `COMPLETED / PASSED / NOT_REQUIRED` | same; prior controlled rebuild |
| Automatic Fundamentals | HOLD / disabled | same |
| Route / mode | `SNAPSHOT_V1 / FULL_WORKFLOW` | same |

All three immutable financial database files, the active manifest, original native
journal and scheduler configuration matched their pre-task SHA-256, inode, mtime
and size exactly. This protects all accepted OLD financial facts, provenance,
publication dates, approvals and historical retention, including KRSA's 160
provider observations and the accepted PSQL/QVCG safeguards. The original failed
UPDATE/FETCH/validation's **26,861 files** matched
pre-task path/size/inode/mtime metadata with zero missing/changed files. Those
bodies were not reopened as new UPDATE authority or redundantly rehashed.

There were **zero Sharadar and zero SEC calls** during this task. No new UPDATE,
FETCH, SEC bundle, financial VALIDATE receipt, financial candidate or publication
was created. Eligible discovery, verified/quarantined/pending slot counts, source
seal/freshness and VALIDATE partitions are **not applicable**, not successful zero
work. No financial or ownership publication, watermark advance, review
approval/finalization or scheduler enablement occurred.

Scheduler configuration is byte-identical to its pre-task value. It records
`run_time=04:30`, `timezone=Europe/Helsinki`; the operator constraint names 04:45.
No timing was changed or inferred from obsolete market/taxonomy file checksums.
This attempt ended at 00:43 Helsinki, well before either stated time. Native
locks were released on the blocked exit, and no network/local stage was left
running. Normal enabled nightly work was not stopped or reconfigured.

### Measured resources and retained artifacts

| Current native database role | Bytes |
| --- | ---: |
| Accepted provider | 968,331,264 |
| Accepted canonical | 749,371,392 |
| Accepted financial analysis | 912,351,232 |
| Market source | 2,040,012,800 |
| Taxonomy source | 14,378,782,720 |

The three financial roles total **2,630,053,888 bytes** and did not grow.
New live financial candidates/generations/backups: **0 bytes**. No compact live
market bundle was built. Task-owned retained test copies and evidence at the
measurement point total **1,015,213,626 logical bytes /
1,030,553,600 allocated bytes**; final small report
and Git metadata growth is additional. Free filesystem space was
**531,978,592,256 bytes**. The largest task-owned retained directories
are `/tmp/rawcandle_fix8_qualified` (393,393,721 bytes) and the earlier acceptance
copy (371,166,755 bytes). They remain evidence, rather than being deleted to
reclaim space. Largest existing native consumer among these roles is taxonomy
(14,378,782,720 bytes); it was not copied or optimized for this blocked attempt.

Qualified JUnit duration was 177.629 seconds. The separate read-only diagnostic
financial-rebuild check took 54.700 seconds; it did not rebuild accepted results.
Native production preflight stopped within the timestamped second, after the
wrapper's preceding OLD/receipt verification. A complete filesystem-growth or
peak-RSS baseline was not recorded, so no invented global growth/peak claim is
made. Exact measured task-owned retained sizes and database before/after sizes
are in `final_operator_evidence.json`. Later opportunities include retiring
released test copies and examining source/candidate storage lifetimes; no storage
optimization, VACUUM or retention reduction was performed.

### Evidence and next boundary

Native runtime directory:
`fundamental_reports/admin_runs/20261113T224303Z_refresh_fundamentals_cce2b9c73301_universe_reconciliation_5a9bd5d0/`.
It contains the original `result.json`, native reconciliation report,
`FINAL_OPERATOR_REPORT.md`, `final_operator_evidence.json`, final HEAD and artifact
manifest. Temporary tests, socket ledgers and preservation measurements remain
under `temp/fundamentals_fix8_20261113/`. The valid native qualification and earlier
rejected fingerprint receipt are retained in their original separate run dirs.
Runtime evidence/databases, existing unrelated changes and disposable copies are
excluded from commits. Push: **NO**.

There is no Phase 3E report because Phase 3E was not reached. The next decision is
how to resolve the taxonomy sidecar lifecycle within the native safety contract.
After a qualified resolution, perform a new current-state preflight and verify
identity-only reconciliation before allocating the one new Phase 3E UPDATE.
Do not reuse the old incorrectly scoped UPDATE or infer a future activation PASS
from this implementation/test result.
