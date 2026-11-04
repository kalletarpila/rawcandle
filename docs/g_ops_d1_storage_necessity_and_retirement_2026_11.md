# D1 storage necessity, owner closeout and retirement — 2026-11-04

**83 exact D1 files retired; 128,285,233,152 allocated bytes released.** All
nonempty/empty SQLite mains and associated sidecars in the two specified D1
groups have been removed. The remaining D1 allocation is **11,616,256 bytes** of
compact original evidence and directory metadata. No D2 or production data was
removed. Original receipts, source scripts, logs and historical reports remain
unchanged.

This task replaces the continuing-retention interpretation of the earlier
[qualification audit](g_ops_rehearsal_cleanup_2026_11.md), while preserving that
report and its manifest as the historical record of the earlier no-deletion task.
Historical executable receipt references do not create permanent operational
requirements after their disposable owning environment is explicitly retired.

## Repository and bounded review

Starting RawCandle HEAD: `799dc4a4463040a4bb53feff876f393b4dbbcfb6`, branch
`chore/ignore-backups`, one worktree. StockCore remains read-only at
`6881f6971304ff52d26e0f087c440ab55004f432`, branch `main`, one clean worktree.
No applicable RawCandle/ancestor/nested AGENTS file was found; StockCore's root
AGENTS was read. Its recovery, read-only, Git and isolated-test instructions were
observed. The task's final commit is identified by
`git log -1 --format=%H -- docs/g_ops_d1_storage_necessity_and_retirement_2026_11.md`
and the final handoff, avoiding a self-referential commit hash here.

Inspection used the prior exact manifest/preservation path list, the two owner
reports and their harnesses/receipts, directly relevant native Test/publication/
acceptance/recovery functions, current configuration/journal and relevant user
units. There was no broad repository content search. The existing modified
Fundamentals journal and unrelated research/OHLCV files remain outside this commit.
No current Fundamentals investigation code, acceptance state or review row changed.

## Continuing necessity decisions

Owners:

- D1-A: `P/B-OWNERSHIP-FUTURE-AUTO-RECONCILIATION-1`,
  `temp/pb_future_reconciliation_20261029`;
  [owner report](fundamentals_v4/pb_ownership_future_auto_reconciliation_2026-10-29.md).
- D1-B: `P/B-FUTURE-NO-SAFE-CHANGES-INTEGRATION-FIX`,
  `temp/pb_no_safe_changes_20261029`;
  [owner report](fundamentals_v4/pb_ownership_safe_no_changes_integration_fix_2026-10-29.md).

Both original closeouts and successful copy results are PASSED. The reports bind
800 and 274 historical focused tests respectively, source commits, input hashes,
native copied publication/cleanup, protected-content comparisons and repeat no-ops.
The successful harnesses' structured live before/after states are equal. Their
stated purpose was disposable local integration validation, not durable production
recovery or a continuing exact-vintage research dataset.

| Reviewed role | Original purpose/consumer and terminal state | Continuing exact-byte need and decision | Capability intentionally lost |
| --- | --- | --- | --- |
| 33 copied current/previous generation mains | Native copied Test/publication and receipt role validation; terminal or abandoned disposable environments | No current live/configuration/development consumer or production recovery binding. RETIRE_APPROVED after owner archive closeout. A copied pointer's historical role is not a live operational generation. | Executable historical role validation and copied generation replay |
| Nine nested Test backup mains | Restore-old preparation inside nested copied Test publications; cleanup eligibility recorded, not native cleanup completion | All three nested journals are COMPLETED / PASSED / NOT_REQUIRED. No restore is pending and no retired copied project is to be resumed. RETIRE_APPROVED as part of whole-environment archival retirement. | Restore-old inside those disposable Test projects |
| 25 nonempty source/market/taxonomy/queue/inactive-candidate mains | Exact October 29 inputs, native decisions and preservation comparisons for the completed rehearsals | No named current investigation requires this vintage. The original source remains outside D1; copied vintage uniqueness alone is not a continuing requirement. Compact immutable comparisons/outcomes suffice for the promised historical audit. RETIRE_APPROVED. | Exact historical input/queue replay, not live recovery |
| One empty interrupted main | Abandoned copy setup in `current_copy_085354`; no operational publication journal | Superseded setup, not a pending recoverable production operation. No restart is intended. RETIRE_APPROVED. | Resuming the obsolete partial setup |
| 15 WAL/SHM/rollback sidecars | SQLite state exclusive to these retired copies, including nonempty historical WAL and the 1,024-byte setup rollback journal | No users/writers/mappings; parent copies positively approved for abandonment. RETIRE_APPROVED with the bound parent. | SQLite replay/recovery of the abandoned copied environment |

The earlier source-drift attempt was explained and superseded by a successful
corrected rehearsal that preserved the existing empty-WAL state. It is not an open
defect requiring its full copied databases. All five copied publication journals
(two outer and three nested) were independently checked as COMPLETED / PASSED /
NOT_REQUIRED. The separate empty interrupted setup has no such publication to
recover. No D1 requirement remains as NEEDS_OWNER_DECISION.

The following compact D1 files are **RETAIN_REQUIRED under the explicit historical
evidence preservation requirement**: 185 original files, allocating 11,124,736
bytes. They include receipts/seals, reports, input/source summaries, comparisons,
scripts, logs and original noncandidate context files. Their owners are the two
named rehearsal tasks. Deleting them would lose the explanation and immutable
evidence of completed results; a database-only replay cannot replace that record.
They are outside this task's database/sidecar deletion scope and remain until a
separate owner disposition ends their historical audit retention. Directory
metadata accounts for the additional 491,520 bytes. There is no retained D1
database/recovery hold.

## Owner archival closeout and exact execution

Separate forward-looking owner records were durably written under
`temp/g_ops_d1_necessity_20261104/`: `D1-A_owner_archive.json` and
`D1-B_owner_archive.json`. Each binds the exact fresh inventory, original compact
evidence hashes, terminal owner outcome and accepted loss of optional historical
execution/rollback. These records do not amend any old receipt or declare a fresh
native acceptance success.

The native `pb_ownership_future.production()` validator remains unchanged: it must
still read its Test journal and hash its published roles for a current operation.
The native rollback and `run_acceptance_cleanup` contracts also remain unchanged.
No native acceptance function was invoked to repurpose eligibility as completed
cleanup. Instead, the user-authorized owner archive closeout ends the meaningful
need to recover/resume these entire disposable environments. The original nested
receipts still truthfully record eligibility at their historical time.

| Scope | Mains | Sidecars | RETAIN_REQUIRED candidates | RETIRE_APPROVED | NEEDS_OWNER_DECISION | Actually removed | Released allocated bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| D1-A | 43 (42 nonempty) | 9 | 0 | 52 | 0 | 52 | 78,549,188,608 |
| D1-B | 25 | 6 | 0 | 31 | 0 | 31 | 49,736,044,544 |
| Total exact DB/sidecar scope | 68 | 15 | 0 | 83 | 0 | 83 | 128,285,233,152 |

The fresh set matched all 83 paths of the prior exact TSV. All were exclusive
regular files with link count 1, confined canonically inside the two D1 roots;
none was a shared/hardlinked original source. No full database backup was made.

Host visibility was established outside the sandbox's isolated PID namespace.
The pass held the existing UI, Fundamentals Production and shared scheduler locks
continuously, read-opened without rewriting owner text. The taxonomy sentinel was
absent. A dry run verified exact identities, immutable compact evidence, terminal
recovery, current configuration/journal references, process CWDs, descriptors and
mappings before any deletion.

Before every unlink, current live pins and owner decision seals were rechecked,
all D1 SQLite users/mappings and unexpected artifacts were rejected, and canonical
path/device/inode/link/size/mtime/ctime identity was verified. A PREPARED decision
was durably recorded, gates were repeated, and an exact basename was unlinked
through a pinned parent directory descriptor. Every result was recorded and the
directory synced. Sidecars preceded their bound mains after no-user checks. There
was one pass, no ambiguous outcome/retry and no recursive directory removal.

## Intentionally retired executable environments

All paths below are relative to their named D1 root. Their original journals,
pointers, receipts and source scripts remain historical evidence. They must not be
presented as currently executable or resumed against missing databases.

| Group | Environment |
| --- | --- |
| D1-A | `current_copy_084355/project` |
| D1-A | `current_copy_084355/project/reports/admin_runs/20261029T095147Z_refresh_fundamentals_d00eb7239fed_full_workflow_9b02e155/ownership_auto/test/project` — superseded source-drift attempt |
| D1-A | `current_copy_084355/project/reports/admin_runs/20261029T095635Z_refresh_fundamentals_d00eb7239fed_full_workflow_b8018778/ownership_auto/test/project` — successful nested Test |
| D1-A | `current_copy_085354/project` — abandoned partial setup |
| D1-B | `copy_121207/project` |
| D1-B | `copy_121207/project/reports/admin_runs/20261029T121259Z_refresh_fundamentals_d00eb7239fed_full_workflow_be9a0a6d/ownership_auto/test/project` |

## Preservation and measured space

Independent postflight compared the 7,471 exact known preflight paths: precisely
the 83 approved files were absent and **all 7,388 preserved files were unchanged**
under the recorded identity/metadata/header and compact-file hash checks. This
includes every original D1 compact artifact, D2 files, live data/journal/queue,
configuration, locks, production source and historical reports in the prior
preservation inventory. It does not claim a full byte hash of every large database.

Nine separate full-byte checks passed before and after: the three live current
roles, three live previous roles and three current live Test candidates. Current
generation `current_rebuild_2a684ef130c6a540de4adc560ab171ad` and previous generation
`payload_repair_c76f86e26cbc7735_99b4b068a24f` remain intact. Live journal SHA-256
remains `91fadb71f55be7bad2107db8948744abb17a1a7494bfb3d64d78fe2d155c1e72`.
Source `data/osakedata.db` and global Analysis `data/analysis.db` retained their
sizes, device/inodes, timestamps and headers. Active queues/reviews and required
production recovery points were not changed.

| ext4 observation, Europe/Helsinki | Used bytes | All free bytes | User-available bytes |
| --- | ---: | ---: | ---: |
| Before, 2026-11-04 19:59:54 | 691,287,441,408 | 389,813,735,424 | 334,821,380,096 |
| Postflight, 2026-11-04 20:03:24 | 563,010,891,776 | 518,090,285,056 | 463,097,929,728 |

The measured user-available increase is **128,276,549,632 bytes**. Exact retired
file allocation is **128,285,233,152 bytes**; the 8,683,520-byte difference reflects
other filesystem/evidence activity, so free-space delta is not substituted for
the per-file release accounting. No remaining link/connection held a removed
file. D1-A remaining directory allocation is 6,598,656 bytes and D1-B is 5,017,600
bytes; all remaining SQLite main/sidecar allocation is zero.

Windows API measurement at 20:03:27: D: available **253,469,466,624 bytes**;
`D:\WSL\Ubuntu-22.04\ext4.vhdx` physical allocation **724,118,274,048 bytes**,
equal to its logical file length. These host values are unchanged from preflight.
Released ext4 blocks are available inside WSL; they did not immediately become
NTFS free space. No WSL restart/shutdown, VHDX compaction, DiskPart, trim command,
sparse-file or WSL configuration change occurred.

Services retained their observed properties: stock-update scheduler already
failed (MainPID 0, exit 1), forecast service inactive, forecast timer waiting.
Nothing was started, repaired or rescheduled. A postflight descriptor observed
on the live provider database belonged to this task's read-only role-hash verifier,
not a publication or writer. The pre-existing scheduler failure remains outside
this task.

## Future closeout improvement and tests

Added [scripts/pb_rehearsal_closeout.py](../scripts/pb_rehearsal_closeout.py) as the
small maintained owner closeout/runner interface for **both** P/B harness owners.
The original dated harness scripts remain immutable historical evidence. Future
harness bodies use `run_harness(...)`, which records purpose, owner, estimated
allocated size and the event ending necessity before entering the body, then
always writes a closeout report. The body returns its actual outcome, compact
evidence, concrete current requirements and explicit acceptable replay loss.
Exceptions record an unresolved interrupted closeout rather than silently orphaning
copies. The `begin`/`close` CLI supports separately staged owner workflows.

The closeout inventories exact mains/sidecars and their allocations. Required
copies need a named owner, concrete reason and ending event; an interrupted
unclosed run remains NEEDS_OWNER_DECISION. Closed disposable snapshots without a
continuing requirement become RETIRE_APPROVED with their deliberate replay loss
documented. The report totals retained and approved bytes and decimal GB.
Repeated closeout reuses the sealed decision and rejects changed requirements or
evidence. No CLI closeout automatically deletes anything, and no current native
publication validator is weakened. The exact-file retirement primitive is used
only by an explicitly authorized caller supplying current-reference/ownership and
host-user checks under the established locks, as this task's one-time executor did.
No general storage service, scheduler or global Temp deletion policy was added.

[Focused tests](../tests/test_pb_rehearsal_closeout.py): **18 passed** using tiny
real SQLite fixtures under `temp/g_ops_d1_necessity_20261104/`. They cover completed
disposable work, live dependencies, nested backup recovery, interrupted work,
obsolete generation/immutable receipts, changed inode/symlink, an actual concurrent
SQLite writer, repeated closeout/retirement, preserved audit bytes, both owner
runners, failure reporting, nonspecific holds, changed requirements, post-decision
live drift, WAL/SHM recovery holds and ambiguous unlink failure. Full suite: **NO**.
No full-sized rehearsal or provider acquisition was performed.

## D2 next steps and evidence locations

The same necessity-first review can later apply to D2-A's 26,531,532,800 main bytes
and D2-B's 19,610,288,128 main bytes. Distinguish their historical source-version
investigation from the separate currently active Fundamentals work; do not infer
that either all copies remain necessary or all are disposable. Start with the six
previously enumerated D2-A native-rehearsal/fresh-Test role files and D2-B's inactive
candidate only after confirming their current owner need. No D2 file changed here.
D2-C's 94,616,240,128 main bytes remain held: the live journal still names
`native_test_final/provider.db`, `canonical.db` and
`downstream/analysis_candidate.db`, whose exact bytes verified successfully. Those
are current executable Test obligations, unlike retired D1-only references.

Exact inventories, decisions and outcomes stay outside Git under
`temp/g_ops_d1_necessity_20261104/`: `retirement_manifest.json`,
`retirement_ledger.json`, both owner archive/creation records,
`retained_compact_evidence.json`, `before.json`, `after.json`, `postflight.json`,
live-role hashes, host/Windows observations, copied journal summaries, dry-run and
execution records, the one-time `prepare.py`/`execute.py`, and focused test logs.
The per-file manifest and ledger enumerate all 83 exact removed paths. No large
manifest, DB, backup, runtime record or log is committed. Only the new maintained
helper, its focused tests and this report belong to the local commit.

Current production references preserved: **YES**. Historical receipts preserved:
**YES**. Production DB writes: **NO**. Provider requests: **NO**. Scheduler/service
changes: **NO**. StockCore writes: **NO**. D2 changes: **NO**. Push: **NO**.
