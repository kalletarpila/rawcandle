# D2 storage necessity and qualified retirement — 2026-11-04

**63 exact SQLite main/sidecar files removed; 138,128,224,256 allocated bytes
released. Three current Test candidates retained.** D2-A/B's historical copied
environments were closed as non-executable archives. D2-C was split by actual
current dependency: its three authoritative candidates remain, while obsolete
project/generation/input/queue copies were retired. No immutable receipt, live
journal, operational generation, review state or production database was changed.

## Baseline and scope

RawCandle started at `cf963fb8f4aa03183383bb5c1706c6d5830700b7`, branch
`chore/ignore-backups`, one worktree. StockCore stayed read-only at
`6881f6971304ff52d26e0f087c440ab55004f432`, branch `main`, one clean worktree.
No applicable RawCandle/ancestor AGENTS file was present; StockCore's root
instructions were read and respected. The final local commit is identified by
`git log -1 --format=%H -- docs/g_ops_d2_storage_necessity_and_retirement_2026_11.md`
and the chat handoff. No push occurred.

Inspection was bounded to the three named D2 roots, prior exact preservation
inventories, [D1 implementation/report](g_ops_d1_storage_necessity_and_retirement_2026_11.md),
[initial audit](g_ops_rehearsal_cleanup_2026_11.md),
[lifecycle proposal](g_ops_rehearsal_storage_lifecycle_proposal.md), owner reports,
current journal/configuration and directly relevant native Test/publication/
recovery functions. There was no unrelated code scan. The pre-existing modified
Fundamentals journal and unrelated worktree artifacts were preserved and excluded
from this commit.

Fresh inventory reconciled the 52 main files and **140,758,061,056 allocated main
bytes** exactly. Fourteen associated sidecars add 229,376 allocated bytes. Thus
66 SQLite files were individually classified; historical names or copied-generation
labels were not treated as permanent retention requirements.

## Owner decisions

### D2-A: completed legacy rebaseline

Owner: `FUNDAMENTALS-LEGACY-PAYLOAD-REBASELINE-AND-LIVE-REMEDIATION`.
Root: `temp/fundamentals_legacy_rebaseline_20261030`.
[Owner report](fundamentals_v4/fundamentals_legacy_payload_remediation_and_eligibility_2026-10-30.md).

Original purpose: native completeness repair/rebaseline on disposable inputs,
full copy publication/postflight/cleanup and preservation verification. Final
verification is PASSED, native cleanup COMPLETED, journal COMPLETED, postflight
PASSED, recovery NOT_REQUIRED. Its copied publication journal is also terminal.
The historical two unresolved source-version cases were subsequently addressed by
the accepted controlled current-state rebuild, not by this storage task.

All 15 mains are RETIRE_APPROVED: six copied generation roles, six role files in
`native_rehearsal/` and `lifecycle_project/fresh_test/`, market/global-Analysis
inputs and the copied queue. No current live/configuration or recovery consumer
requires them. Native/typed source and old-generation evidence used by current
production remain outside this root. Exact historical replay and copied-project
restore-old are optional capabilities intentionally relinquished. Original reports,
comparisons, acquired source evidence and durable completed seals preserve the
required historical explanation.

### D2-B: historical source-version STOP superseded

Owner: `FUNDAMENTALS-BMRA-NEOV-TARGETED-REMEDIATION`.
Root: `temp/fundamentals_bmra_neov_targeted_20261030`.
The owning report's historical targeted section records
STOP_UNRESOLVED_SOURCE_VERSION, no repair/exclusion/publication, and successful
non-mutation/preservation checks. That original result remains unchanged.

The report's later accepted rebuild section, the D2-C live closeout and the
current operational generation independently establish that BMRA/NEOV's current
source-version problem was superseded: complete accepted sources, 173 ELIGIBLE /
8 HISTORICAL_ONLY, no unresolved current-source bindings in the recorded closeout.
This is evidence of the later accepted result, not a new health acceptance or
an update to any current investigation. NEOV's separate frozen-history OPEN
conflicts were explicitly preserved by that rebuild; they do not make this older
copied environment the sole source of evidence. Its original provider/canonical
baseline remains in the retained operational previous generation and sealed
targeted evidence remains outside the disposable DB copies.

Seven mains and two queue sidecars are RETIRE_APPROVED: three copied generation
roles, copied market/Analysis inputs, the inactive provider candidate and queue.
There was no new publication or rollback image to recover in this historical
no-write investigation, and no observed current consumer needs this exact snapshot.
Optional replay of the old rejection against these copied databases is intentionally
lost; original rejection receipts, source acquisitions, fingerprints and comparisons
are preserved. Current Fundamentals blocker work was neither executed nor changed.

### D2-C: exact active Test boundary

Owner: `FUNDAMENTALS-CONTROLLED-CURRENT-STATE-REBUILD-V1`.
Root: `temp/fundamentals_current_state_rebuild_20261030`.
[Owner report](fundamentals_v4/fundamentals_controlled_current_state_rebuild_v1_2026-10-30.md).
The real rebuild and clone lifecycle completed with native publication, PASSED
postflight, NOT_REQUIRED recovery and completed/idempotent backup cleanup. The
copied project's publication journal is terminal too.

These exact files are **RETAIN_REQUIRED**:

| Path relative to D2-C | Allocated bytes | Continuing necessity |
| --- | ---: | --- |
| `native_test_final/provider.db` | 968,335,360 | Current sealed Test's provider candidate |
| `native_test_final/canonical.db` | 749,375,488 | Current sealed Test's canonical candidate |
| `native_test_final/downstream/analysis_candidate.db` | 912,355,328 | Current sealed Test's analysis candidate, also named by its native-analysis result |
| Total | 2,630,066,176 | Three exact candidates; no associated sidecars present |

The live publication journal's `scope_evidence.test.candidates` binds all three.
`current_state_rebuild.verify_test()` calls `measure()` on those exact candidates;
it checks data content against the retained operational baseline and hashes the
candidate roles. The native publication path uses that verifier. The current
journal's three absolute paths and additional relative analysis reference resolve,
and candidate hashes match. Compact receipts identify their bytes but cannot
substitute for the databases that this current contract reads.

The ending condition is a qualified successor publication that legitimately ends
this current Test dependency, or a separately approved native owner contract
change explicitly releasing it while preserving historical receipts. No such
change was made. Required current/previous operational source roles remain intact
outside D2. These are real present holds, not NEEDS_OWNER_DECISION placeholders.

The remaining **27 mains and 12 sidecars are RETIRE_APPROVED**. They comprise the
superseded `project_copy_v1` environment (including its two nested Test areas),
`native_test_v1`, the old `queue_before` image and the market/taxonomy inputs in
`native_test_final`. Native full analysis consumed the latter two during Test
construction. Current `verify_test()/measure()` reads the three candidate roles
and operational baseline, not those copied market/taxonomy inputs. Their hashes
remain historical provenance in the sealed result. Retiring these inputs ends
optional full calculation replay; it does not break current candidate validation.

No current consumer needs the whole copied project. The authoritative three-role
Test environment remains usable under its existing contract; earlier cloned
execution environments are deliberately archived/non-executable. No acceptance
function was misused to manufacture cleanup completion, and no receipt IDs,
paths, hashes, validators or generation pointers were rewritten.

## Exact results and remaining evidence

Counts below include SQLite sidecars. Every reviewed SQLite file received a
decision; NEEDS_OWNER_DECISION is zero in all three groups.

| Group | Mains / sidecars reviewed | RETAIN_REQUIRED | RETIRE_APPROVED / removed | Allocated bytes released | Remaining whole-directory allocation |
| --- | ---: | ---: | ---: | ---: | ---: |
| D2-A | 15 / 0 | 0 | 15 / 15 | 26,531,532,800 | 593,231,872 |
| D2-B | 7 / 2 | 0 | 9 / 9 | 19,610,320,896 | 774,144 |
| D2-C | 30 / 12 | 3 | 39 / 39 | 91,986,370,560 | 2,633,166,848 |
| Total | 52 / 14 | 3 | 63 / 63 | 138,128,224,256 | 3,227,172,864 |

The remaining directories contain 523 original non-SQLite historical/source
evidence files (426 A, 24 B, 73 C), allocating 596,856,832 bytes; 249,856 bytes
are directory metadata. These files have explicit RETAIN_REQUIRED audit/source
preservation decisions under their original owners. Large JSON artifacts such as
the original receipt/catalog collections were not silently treated as disposable
database scratch. They remain until a separate owner evidence disposition ends
that historical/source requirement. No speculative recovery hold was invented
for the retired SQLite copies.

## Guarded execution and preservation

Reused the committed D1 `identity`, `database_files`, `close`, durable JSON and
`retire_exact` implementation. One ignored D2 executor was narrowly adapted from
the D1 orchestration, with three exact roots and positive current-Test exclusions.
Separate owner records bind immutable evidence, exact identities and the deliberate
replay loss. D2-C's closeout retains its active requirements rather than claiming
the entire group is retired.

Real host process/descriptor/mapping and CWD checks established inactive D2
ownership outside the sandbox PID namespace. The existing UI, Fundamentals
Production and shared scheduler locks were read-opened and held continuously
through the pass; owner text was unchanged and no taxonomy sentinel was present.
The dry run passed before deletion. All files were exclusive regular files with
link count 1, canonical path confinement and fresh device/inode/size/mtime/ctime
identities. No copied file was a hardlinked operational source.

Before each exact unlink, current journal/configuration pins, owner-decision seals,
the three retained candidates' identities, recovery state, unexpected SQLite
artifacts and host users/mappings were rechecked. Durable intent preceded a second
gate check and parent-descriptor-relative unlink; directories were fsynced and each
outcome recorded. Sidecars preceded their bound mains. There was one pass, no
ambiguous outcome/retry, no recursive directory deletion and no new full DB copy.

Independent postflight found precisely 63 approved paths absent and **all 7,332
preserved files unchanged** against the fresh 7,395-path inventory. Metadata/header
checks cover live Source/Analysis databases and queues. Original D2 evidence was
also fully SHA-256 checked, including large JSON files; arbitrary large production
databases were not all byte-hashed. Nine full role hashes passed before/after:
current and previous operational roles plus the three current Test candidates.
Native Preview/Test seals verified and the live/completed journal objects match.
Live journal SHA-256 remains
`91fadb71f55be7bad2107db8948744abb17a1a7494bfb3d64d78fe2d155c1e72`.
Active generation `current_rebuild_2a684ef130c6a540de4adc560ab171ad` and previous
generation `payload_repair_c76f86e26cbc7735_99b4b068a24f` remain intact.

## Measurements, implementation and tests

| ext4 observation, 2026-11-04 Europe/Helsinki | Used bytes | All free bytes | User-available bytes |
| --- | ---: | ---: | ---: |
| Before, 20:21:08 | 563,023,880,192 | 518,077,296,640 | 463,084,941,312 |
| Postflight, 20:23:12 | 424,902,590,464 | 656,198,586,368 | 601,206,231,040 |

Available space increased 138,121,289,728 bytes. Exact file allocation released
is 138,128,224,256 bytes; the 6,934,528-byte difference reflects concurrent
filesystem/evidence activity. No hardlink or open/mapped user retained a removed
file. Final host observation at 20:23:50 reported 601,200,971,776 available bytes.
Windows API measurement at that time returned D: available 253,469,466,624 bytes
and `D:\WSL\Ubuntu-22.04\ext4.vhdx` physical allocation 724,118,274,048 bytes,
equal to its logical file length. Windows allocation/free space remained unchanged;
freed ext4 blocks are available within WSL. No VHDX compaction, trim command, WSL
restart/shutdown or host configuration change occurred.

Host service properties were unchanged: stock scheduler already failed with
MainPID 0/exit 1, forecast service inactive and its timer waiting. No service was
started, repaired or rescheduled. Final host checks found no project database
descriptors/mappings. StockCore HEAD and clean status remain unchanged.

The existing [owner helper](../scripts/pb_rehearsal_closeout.py) now registers the
three D2 owners alongside D1, hashes large evidence in bounded streaming reads,
and exposes a narrow read-only `rebuild_test_requirements()` extractor. It rejects
nonterminal/unknown ownership, conflicting candidate identities and malformed
current paths; it supplies concrete three-role holds to the existing closeout.
It is not a replacement production validator. The caller pins the journal and
verifies actual hashes. Future D2 harnesses reuse `run_harness`/begin/close, record
creation purpose/cost and ending event, and include current requirements in their
closeout. Retained GB/reasons and interruption holds are reported. No new cleanup
service, scheduler or automatic global deletion policy was introduced.

[D2 focused tests](../tests/test_d2_rehearsal_closeout.py): **13 passed**.
Adjacent [D1 guard tests](../tests/test_pb_rehearsal_closeout.py): **18 passed**.
**31 passed, zero failed**, tiny isolated SQLite fixtures under this task's ignored
Temp directory. Coverage includes completed copies, superseded versus genuinely
open STOP, exact current Test holds, unreferenced copies, rollback/WAL/SHM holds,
invalid current bindings and interrupted cleanup; adjacent tests cover inode/path
drift, real concurrent writer, repeated retirement and ambiguous unlink handling.
Full suite: **NO**. No acquisition or production rehearsal was run.

## Evidence and next action

Detailed inventories/ledgers stay Git-ignored under
`temp/g_ops_d2_necessity_20261104/`: `retirement_manifest.json`,
`retirement_ledger.json`, three owner archive/creation records,
`current_test_requirements.json`, `retained_historical_evidence.json`, before/after
inventories, role hashes, native seal checks, host/Windows observations, directory
measurements, copied journal summaries, dry-run/execution records and test log.
Only the helper adaptation, new focused tests and this report are committed.

The next legitimate storage action for the remaining three DBs is an owner
decision after a qualified successor publication, or a separately reviewed Test
evidence lifecycle change. They must remain while the current contract requires
their paths/bytes. No further D2 database is left held by uncertainty. Optional
later review of large historical JSON/source evidence or host VHDX reclamation
requires its own exact scope; neither was performed here.

Current publication/Test references preserved: **YES**. Historical receipts
preserved: **YES**. Production DB writes: **NO**. Provider requests: **NO**.
Scheduler/service modifications: **NO**. StockCore writes: **NO**. Push: **NO**.
