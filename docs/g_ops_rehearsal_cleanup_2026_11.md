# G-OPS rehearsal storage qualification — 2026-11-04

Outcome: **no deletion**. None of the D1 files conclusively satisfies every
retention gate. A successful rehearsal and an inactive process are insufficient
to retire copied generation, source or receipt dependencies. This is a completed
qualification audit with a deletion hold, not a claim that 128.28 GB was recovered.

## Scope, repository state and authority

RawCandle starting HEAD: `ed20e1907af2b57321b367776e780839919adffa`, branch
`chore/ignore-backups`, one worktree at `/home/kalle/projects/rawcandle`.
StockCore: `6881f6971304ff52d26e0f087c440ab55004f432`, branch `main`, one
worktree at `/home/kalle/projects/stockcore`; clean at inspection, strictly read-only.
The task's local documentation commit is the final RawCandle HEAD; obtain its full
identifier with `git log -1 --format=%H -- docs/g_ops_rehearsal_cleanup_2026_11.md`.
The final chat handoff records that identifier without creating a self-referential
commit hash in this document.

No applicable RawCandle/ancestor/nested `AGENTS.md` was found. The StockCore root
`AGENTS.md` was read; its read-only legacy, recovery, focused-check and Git rules
were observed. Its architectural Q07 retention principle does not transfer
RawCandle publication ownership or authorize retiring native evidence. There was
no reason to execute a StockCore implementation phase.

The pre-existing modified `data/.fundamentals_admin_publication_journal.json`,
untracked generation/pointer files, OHLCV work and research artifacts are outside
this task. No Fundamentals source, operational review, acceptance state, journal,
configuration, schedule or provider data was edited. No full database copy was made.
Only the two requested documents and a small exact D1 manifest belong to the commit.

## Preflight and operational ownership

Initial measurement: **2026-11-04 19:25:37 Europe/Helsinki**. The sandbox has an
isolated PID namespace and cannot reach the user service bus, so its empty process
list was rejected as ownership evidence. Subsequent authorized host observations
used the real process namespace and user systemd bus. Recorded host preflight at
19:29:30 found:

- No SC/RC workflow, publication, reconciliation, or D1 writer/connection observed.
  No project file descriptors or mapped project files were found. Same-UID PID 440
  was unreadable and was identified as systemd's `(sd-pam)` session helper in the
  host process listing; its existence is not positive proof about arbitrary future
  writers. These are point-in-time observations, not a perpetual exclusion lock.
- Existing UI operation, Fundamentals Production and shared scheduler lock files
  were read-opened and successfully probed with nonblocking kernel locks. Their
  contents and identities were preserved. No taxonomy operation sentinel existed.
- `stock-update-scheduler.service` was already **failed**, MainPID 0, exit status 1.
  `rawcandle-forecast-daily.service` was inactive, MainPID 0. Its timer was enabled,
  active/waiting, next due 2026-11-05 14:00 EET. Nothing was started or repaired.
- The current Fundamentals journal is COMPLETED / PASSED / NOT_REQUIRED. This
  establishes its recorded publication state; it does not close the separate
  concurrent Fundamentals blocker investigation.
- ext4 was mounted read/write with `errors=remount-ro`; capacity was ample. Kernel
  observations include existing WSL boot PCI/9p/network messages, retained in host
  evidence. A separate same-day kernel search found no ext4 error, block I/O error,
  aborted-journal or read-only-remount messages. No offline filesystem check or
  repair was attempted.

No live D1 reference was found in the current journal, active manifest, runtime
configuration, tracked runtime source, user/system service definitions or StockCore
package search. Historical documentation references remain. This negative live
reference result does **not** discharge copied journals, receipts or original-input
retention requirements.

## D1 ownership and actual closeout proof

| Group | Exact owner | Closeout and retained evidence |
| --- | --- | --- |
| D1-A `temp/pb_future_reconciliation_20261029` | `P/B-OWNERSHIP-FUTURE-AUTO-RECONCILIATION-1` | PASSED closeout binds `b5a20b642ff7867f09121efe0c2ccf02017f42e3`; 800 historical focused tests; successful copied TMUS publication, native outer publication backup cleanup, repeat no-op and before/after live preservation |
| D1-B `temp/pb_no_safe_changes_20261029` | `P/B-FUTURE-NO-SAFE-CHANGES-INTEGRATION-FIX` | PASSED closeout binds `038a38c682234ecc0946435cedaf2d27b8a17c73` and source commit `09ad246ce3d5335c06a164a86bd4864313a86043`; 274 historical focused tests; safe financial STOPPED adapter, copied TMUS publication/cleanup and repeat no-op |

Owning reports:
[future reconciliation](fundamentals_v4/pb_ownership_future_auto_reconciliation_2026-10-29.md)
and [safe no-changes integration](fundamentals_v4/pb_ownership_safe_no_changes_integration_fix_2026-10-29.md).
The retained harnesses explicitly call their projects disposable, but neither
closeout enumerates exact snapshots released from generation, receipt and restart
obligations. This task does not reinterpret that wording as a release of every
referenced byte.

The measured hashes match the owning reports:

| Group | `copy_result.json` SHA-256 | `test_results.json` SHA-256 |
| --- | --- | --- |
| D1-A | `23fa8d38d8f9aa4a2be10a256807cd5cb13b6afcabd80357e4b3db6c1b81b5cb` | `6d43136163397635eafb7e7491d538a28fbc7b123d712c815cafe82bb2a2ba24` |
| D1-B | `24886b96e5372ec7b37787b9d65f75b3bde2cf8289985e497842ddfdcc826c1f` | `434f80070d812ce28944fd3a879b4115ed92b05a98b4c1410ec48214adae8c19` |

Both successful outer rehearsals retain equal structured `before.json` and
`after.json` states. D1-A's initial nested attempt remains FAILED_OR_STALE with
`PB_FUTURE_TEST_SOURCE_DRIFT`; the later corrected rehearsal passed. A separate
`current_copy_085354` is interrupted, with a zero-length `osakedata.db` and a
1,024-byte rollback journal. These are independently classified, not covered by
an assumption that every child attempt passed.

## Exact retirement decision

The [exact D1 manifest](g_ops_rehearsal_cleanup_2026_11_manifest.tsv) lists **83
retained paths**: 68 main files and 15 associated sidecars. Each row records its
canonical absolute path, device, inode, link count, type, logical/allocated sizes,
owner, classification and retention reason. The richer ignored JSON manifest adds
sidecar identity/state, JSON reference keys, generation obligations and evidence.
All D1 paths are regular files, canonically confined and have link count 1. No
allocation is double-counted. Filename extension was supplemented by SQLite header
inspection; the empty interrupted main has no valid SQLite header.

| Group | Nonempty mains | Extra empty main | Allocated main bytes | Protected mains | Uncertain mains | Qualified / removed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| D1-A | 42 | 1 | 78,548,733,952 | 27 | 16 | 0 / 0 |
| D1-B | 25 | 0 | 49,735,733,248 | 15 | 10 | 0 / 0 |
| Total | 67 | 1 | 128,284,467,200 | 42 | 26 | 0 / 0 |

The 67 previously reported main files and allocated bytes are reconciled exactly;
the additional interrupted main consumes zero allocated bytes. D1-A's nine
sidecars allocate 454,656 bytes; D1-B's six allocate 311,296 bytes. All 15 are
UNCERTAIN and retained with their parents. Full D1 main-plus-sidecar allocation is
128,285,233,152 bytes. **Expected qualified yield: 0 bytes. Actual recovered:
0 bytes. Unlink attempts: 0.**

The file-specific decisions use these concrete gates:

- **33 copied current/previous generation mains: PROTECTED.** Existing copied
  active pointers and old-generation journal role bindings still resolve them.
  The task expressly excludes current/previous publication generations. For each
  successful ownership Test, `pb_ownership_future.production()` additionally opens
  the copied completed journal, resolves its active generation and hashes the three
  roles before accepting the receipt. Deleting these roles would break that native
  validator even while preserving the receipt's JSON and checksum.
- **Nine copied journal-owned backup mains: PROTECTED.** The nested Test receipts
  record cleanup **eligibility**, not completed acceptance/deletion. Native cleanup
  on the outer copied publication did remove its own three backups in each successful
  rehearsal; that does not accept the nested Test backups or failed attempt. This
  task does not invoke `run_acceptance_cleanup` to force acceptance of snapshots or
  modify any copied acceptance state.
- **26 other mains, including the empty interrupted main: UNCERTAIN.** These are
  copied market/taxonomy inputs, review queues, inactive canonical candidates and
  interrupted setup. Some paths are implicit in the harness rather than literal
  JSON fields. They represent the dated original source/queue state and the failed
  drift case; there is no proved equivalent retained source plus a discharged
  exact-input reproducibility/restart obligation. A checksum identifies missing
  bytes but cannot recover them. The present live source has advanced since October
  29 and is not a proved substitute. Nonempty WAL and rollback-journal artifacts
  are retained; no checkpoint, SQLite connection or recovery was attempted.

The closeout evidence proves completed behavior, but not that compact reports
replace all these obligations. Under the requested fail-closed contract no file
crosses into QUALIFIED_FOR_RETIREMENT. No owner-specific snapshot retirement
mechanism was found in the reviewed harnesses/native cleanup. An exact-file unlink
procedure was therefore neither armed nor executed. Historical receipts and paths
were not rewritten to manufacture eligibility.

## Preservation and reference verification

The preservation inventory records 7,471 files across D1/D2, live `data/`,
`fundamental_reports/`, runtime configuration, operational locks and Python source
in `rawcandle/`, `services/` and `scripts/`. It compares path sets, device/inode,
links, sizes, allocated blocks, mtime/ctime and database headers; non-database
evidence at most 20 MB also receives SHA-256. This bounded audit does not claim a
full byte hash of every large source/database/archive or an offline integrity test.

Separately, 21 positive checks verify actual bytes or structured bindings: six
live current/previous role hashes, three current live Test candidate hashes, two
copied Test receipt fingerprints, their two completed-journal hashes, six copied
Test published-role hashes and two historical before/after comparisons. All pass.
These checks use file reads and no SQLite connections.

The live journal SHA-256 is
`91fadb71f55be7bad2107db8948744abb17a1a7494bfb3d64d78fe2d155c1e72`.
Active generation: `current_rebuild_2a684ef130c6a540de4adc560ab171ad`.
Previous generation: `payload_repair_c76f86e26cbc7735_99b4b068a24f`.
Both generations' provider/canonical/analysis roles exist and match retained
expected hashes. The current journal's three Test candidates and its additional
relative analysis-candidate reference resolve inside protected D2-C. Historical
`.preparing` paths in verification metadata are not current role resolution paths;
role resolution follows the generation ID and role filenames.

Independent postflight at **19:34:24 EET** found **zero changes across all 7,471
files**, including the D1/D2 path sets, main/sidecar identities, live database
metadata/headers, journal, configurations, source and publication evidence. The
21 positive checks passed again and their recorded results match the first pass.
Final host observations at 19:34:35 found the same service properties, free native
locks, absent taxonomy sentinel and no project descriptors/mappings. SC HEAD and
clean status were unchanged. No operational invariant is repaired or waived by
this audit; the pre-existing failed stock scheduler remains an operational concern.

| Current live database | Logical bytes, unchanged | Device / inode, unchanged |
| --- | ---: | --- |
| `data/osakedata.db` | 2,035,113,984 | 2096 / 88025 |
| `data/analysis.db` | 13,756,264,448 | 2096 / 68290 |
| Active generation `fundamentals_provider.db` | 968,331,264 | 2096 / 241063 |
| Active generation `fundamentals_v4.db` | 749,371,392 | 2096 / 241062 |
| Active generation `fundamentals_analysis.db` | 912,351,232 | 2096 / 241061 |

## D2 bounded review, no deletion authority

| Group | Mains | Allocated main bytes | Current qualification and exact next scope |
| --- | ---: | ---: | --- |
| D2-A `temp/fundamentals_legacy_rebaseline_20261030` | 15 | 26,531,532,800 | Six generation roles protected; nine other mains uncertain. First later review: `native_rehearsal/{provider,canonical,analysis}.db` and `lifecycle_project/fresh_test/{provider,canonical,analysis}.db` (6 files, 5,260,197,888 bytes), checking their native receipt consumers and retained equivalent inputs before considering the larger project inputs/queue. |
| D2-B `temp/fundamentals_bmra_neov_targeted_20261030` | 7 | 19,610,288,128 | Three copied generation roles protected; four others uncertain. The exact `unresolved_preservation_project/inactive_candidates/provider.db` is a later owner-review target (968,335,360 allocated bytes), together with the preserved source/queue dependency analysis. Hold during current Fundamentals investigation. |
| D2-C `temp/fundamentals_current_state_rebuild_20261030` | 30 | 94,616,240,128 | All protected. The live journal directly names `native_test_final/provider.db`, `canonical.db` and `downstream/analysis_candidate.db`. No cleanup scope recommended until its owner explicitly closes the live Test and recovery obligations. |

D2-A/B's **46,141,820,928 bytes** are a bounded read-only review pool, not safely
recoverable space. All D2 mains total 140,758,061,056 bytes; sidecars are additional.
There are **zero conclusively retirement-qualified D2 bytes in this task**.
No direct D2-A/B reference occurs in the current live publication journal, but
historical/durable report references remain. D2-A's durable completed manifest and
D2-B's sealed STOP_UNRESOLVED_SOURCE_VERSION manifest enumerate compact evidence;
neither is a proof that all copied DB bytes may be lost. D2-B's historical STOP
must not be presented as the current operating acceptance state: later rebuild
evidence exists and the current blocker investigation belongs to another task.
No Fundamentals review row or accepted status was queried through a write-capable
workflow or changed to enable cleanup.

## Disk measurements and Windows distinction

Initial ext4 observation: total 1,081,101,176,832 bytes, used 691,271,393,280,
available to this user **334,837,428,224 bytes**. The durable pre-preservation
snapshot at 19:28:46 recorded available 334,834,290,688 and total free blocks
389,826,646,016 bytes. `f_bfree` includes blocks unavailable to an ordinary user;
`df` available corresponds to `f_bavail`.

| Measurement (EET) | ext4 used bytes | ext4 user-available bytes |
| --- | ---: | ---: |
| Initial 19:25:37 | 691,271,393,280 | 334,837,428,224 |
| Preservation baseline 19:28:46 | 691,274,530,816 | 334,834,290,688 |
| Preservation postflight 19:34:24 | 691,283,247,104 | 334,825,574,400 |
| Final host measurement 19:34:35 | 691,288,735,744 | 334,820,085,760 |

The preservation-window available-space delta was **−8,716,288 bytes**. The final
host delta from the initial observation was **−17,342,464 bytes**. Generated audit
evidence and other host activity consume space; neither delta is cleanup recovery.
Read-only final directory allocation measured `temp/` at 312,108,564,480 bytes,
`data/` at 111,097,053,184 bytes and `backups/` at 86,979,088,384 bytes. These are
inventory measurements, not additional retirement scopes.

Windows API measurement at 19:29:45: D: total 1,000,186,310,656, free
**253,469,466,624 bytes**. `GetCompressedFileSizeW` measured the physical allocation
of `D:\WSL\Ubuntu-22.04\ext4.vhdx` as **724,118,274,048 bytes** (724.118 GB),
equal to its current logical Windows file length. This is a fresh measurement,
not the prior approximately 717.04 GB figure. Linux `stat` agrees, but the Windows
API is the host allocation evidence. Final Windows measurement at **19:34:36 EET**
returned the same D: free bytes, VHDX logical length and physical allocation.

An unlink would release ext4 allocation only after remaining links/connections no
longer retain it. Those free ext4 blocks could be reused within WSL. Windows NTFS
free space and a dynamically allocated VHDX's physical size are separate measures;
Linux deletion alone is not a promise of equal immediate host reclaim. Here no
files were deleted, so **Linux bytes recovered and host reclaim caused by this
cleanup are both zero**. Small free-space changes are measurement/activity/evidence
overhead, not deletion yield. No VHDX shutdown, compaction, trim operation, DiskPart,
sparse-mode/configuration change or swap deletion occurred. A separate later
host-space review may be useful after a substantive qualified Linux cleanup; no
host reclamation command is prescribed or executed here.

## Evidence, validation and remaining decision

Large machine evidence is Git-ignored under
`temp/g_ops_rehearsal_cleanup_20261104/`: `audit.py`, `host_capture.py`,
`verify_references.py`, `before.json`, `after.json`, `retirement_manifest.json`,
`retirement_ledger.json`, `postflight.json`, `host_before.json`, `host_after.json`,
`operational_references_before.json`, `operational_references_after.json`, reference
search results and Windows measurements. Preserve these with the original owner
evidence. The committed TSV is the exact retained D1 file manifest; generated logs,
databases and large inventories remain outside Git.

SHA-256 bindings for the final evidence:

- Committed TSV: `9e62392823397e66f1ce52f2685148a120e3a474bd53656a447301872b3c0636`.
- Full ignored manifest: `085f2f9065bbaedf729c59b8dd635a5bc1e2b360e7e019b6e71f50a67a4cd73b`.
- Retention/outcome ledger: `5a0564b7b2bc2e7e0e7ae904a6714971a89860070cbc74193b86f6fb82a9f54f`.
- Postflight: `f1cf1fd3fc1a4b34da7ce8c0c9809149663c5159162612277f602d6b5f49cbe4`.

Validation is bounded read-only inventory/reference/hash checking, manifest
reconciliation, postflight comparison and documentation/Git checks. Historical
800/274 test results are identified as historical; no production workflow, provider
acquisition or full test suite was run for this documentation-only task. No new
permanent test was necessary.

The remaining material decision is an owning-task, exact-snapshot retention
disposition: which original source/queue bytes must remain reproducible, which
copied receipt validators must continue to work, and which interrupted/failed
attempts have no remaining restart/recovery obligation. Current/previous
generations and journal-owned backups remain outside this task's deletion scope.
This is not a request to repeat the already-granted conditional deletion authority;
the missing element is conclusive retention evidence. The
[lifecycle proposal](g_ops_rehearsal_storage_lifecycle_proposal.md) describes a later
owner-driven way to provide it without changing current cleanup policy.

Production DB writes: **NO**. Provider requests: **NO**. Services/schedulers started
or modified: **NO**. Full suite: **NO**. WSL/VHDX compaction: **NO**. Push: **NO**.
