# G-OPS-04 acceptance and recovery evidence

**PARTIAL: destructive cleanup and automatic release BLOCKED by historical EC
parity/recovery uncertainty. No full backup image was deleted.**

Starting HEAD `160c34d1a566650cfa176d07afbbcd55e2bd2f2a`, branch
`chore/ignore-backups`. The local task commit is the final HEAD; its exact hash
and final status are recorded in ignored `temp/g_ops_04/commit_receipt.json`.
No RawCandle AGENTS.md exists in this checkout or its applicable ancestors.
StockCore AGENTS.md and its G-OPS-01 disk/lifecycle evidence were inspected as
read-only reference, without importing StockCore production logic.

The current EC scope is DATACENTER / DC_TAXONOMY_FULL_V2_1 / DC_SWING_OHLC_V2.
Read-only current checks found all four DC/EC fact heads and canonical watermark
heads aligned through **2026-10-23**, no catchup interval, active validated taxonomy,
and publication safety COMPLETED/unblocked. The publication journal is COMPLETED,
postflight PASSED, rollback NOT_REQUIRED. Historical legacy/report watermarks
remain outside the four canonical EC source-layer acceptance gates, as documented
by the October 3 catchup; they are not silently advanced by this task.

Read-only coverage passed all **25 trading dates, September 21–October 23**.
Parity passed only the latest six dates (October 16,19,20,21,22,23). The other
**19 dates, September 21–October 15, failed**: **15,269 semantic and 2,033
required-lineage mismatches**, with zero operational-metadata drift. Results:
`temp/g_ops_04/current_range_parity.json` and `parity_summary.json`.

Examples: September 21 ecosystem index_value is DC 789.4268184194938 versus EC
792.494027974008. September 22 Backup power synthetic eligible_count is 9 versus
5; synthetic_open is 247.2843943341193 versus 249.812472628538. October 7–15 has
107 required-lineage differences per date even where semantics match. These are
not the permitted unmapped diagnostic warnings. Current DC synthetic/index
source_run_id describes full history through October 23; old EC history still
carries earlier run vintages. A full-history DC recomputation paired with rolling
EC refresh is a plausible cause, **not a proven root-cause conclusion**. No
calculation definition, loader scope or data was changed to force parity.

This triggered the user's STOP condition before generating any nonempty deletion
allowlist or executing the cleanup proposal. Original COMPLETE receipts, aligned
latest heads and the successful six-date recovery drill do not discharge the
older historical-vintage obligations. The exact per-image unresolved dependencies
are recorded in the inventory. A durable same-scope retention hold prevents
future successful rolling operations from silently deleting relevant recovery
images while this remains unresolved.

The October 25 scheduler source service is failed with a Fundamentals
FULL_WORKFLOW global blocker. Its summary records no Production invocation;
EC was SKIPPED / NO_EC_CATCHUP_NEEDED, retry false and backup NONE. The October 24
EC bridge completed, coverage/parity accepted, zero mismatches, four watermarks,
even though the later Fundamentals phase failed. Source-only scheduler status,
EC acceptance and Fundamentals recovery were evaluated separately. No
Fundamentals repair, provider call or production rerun was performed.

## Independent bounded recovery qualification

The retained October 24 pre-write Analysis image passed SHA-256, quick_check and
exact full-schema comparison. Existing `assess_backup_schema_compatibility`
also qualified its critical application schema against the live database.
An independent **EC-only** restore copied all 16 EC tables and their maintained
indexes into one bounded audit database, with a 256 MiB limit. Every initial
table's complete row count and deterministic content digest matched the image;
all foreign-key dependencies were internal to that copied EC scope. Integrity
and foreign keys passed.

Using only the retained image's DC sources, the existing four EC fact loaders
then replayed **October 16,19,20,21,22,23** into that isolated database, replacing
the operation's ordinary overlap dates. Every date passed fact parity with zero
mismatches. Normal canonical watermark advancement restored all four heads to
October 23; final integrity and foreign keys passed. Peak final file size was
**138,723,328 bytes**, rather than another 13 GB Analysis copy. Connections closed
and this exact owned scratch file was removed after preserving the receipts.
The generated script's initial final-report date-column/watermark filter was
corrected; no production replay was involved. Full evidence, including original
copy digests, loader results and finalization, is `temp/g_ops_04/recovery.json`.

This proves a present ordinary EC rollback/replay path, not a blind whole-system
restore. Never replace the live Analysis database during this task. A future
actual recovery requires its own explicit operation scope:

1. Exclude production/scheduler/taxonomy writers using the existing owner locks;
   verify image SHA/integrity/schema, accepted-generation bindings and any later
   accepted changes before choosing full-image or scoped EC recovery.
2. For ordinary EC recovery, restore the compatible EC scope from the retained
   image into an isolated candidate, including ecosystem/taxonomy/entity/member,
   watchlist, signal-run and watermark dependencies. Qualify its exact content
   and foreign keys as in this bounded drill. Preserve live non-EC Analysis state.
3. Replay the required overlap from the image's corresponding DC sources with
   explicit V2, or separately qualify newer accepted DC sources. Run coverage,
   parity, duplicate/lineage and canonical watermark validation before acceptance.
4. Preserve later accepted non-EC data, Fundamentals generations/pointers and
   publication receipts. A full Analysis file replacement would revert unrelated
   technical/report state and must first preserve/reconcile those later changes;
   this task does not authorize that replacement. Do not rewind scheduler status,
   blindly reset an active generation or point its manifest at an EC backup.

The pre-write image has the matching DC state needed to recover the latest
accepted EC operation without providers. Current independent Fundamentals
recovery points remain untouched. The bounded latest-operation drill does **not** determine which older historical
images retain a necessary distinct recovery or investigation capability. Those
23 images remain BLOCKED_UNCERTAIN; separate named weighting-migration rollback
points remain protected.
The absent August pre-taxonomy image is a separate historical full-reversal
reference gap, reported in the maintenance backlog; no current daily image is
misrepresented as that earlier point.

## Tests and isolation

**170 focused tests passed** across:

- `tests/test_ec_backup_retention.py` (30 lifecycle cases).
- Existing backfill CLI, refresh CLI and scheduler-runner regression groups.

Coverage includes accepted COMPLETE and accepted EC under overall PARTIAL/FAILED,
actual EC partial/failure/cancellation, interrupted/unknown owners, active flock
and real open-file protection, explicit reuse/reopened recovery, superseded
retirement, same-second creation collision, unknown files/scopes, symlink/hardlink
and sidecar safety, idempotence, unlink failure/retry, interrupted retirement,
failed-copy scratch disposal, persistent scope-hold protection even after a
successful EC phase, and isolated existing-cleanup coexistence. The
scheduler regression proves the final summary exists and retention is invoked
before the existing Production/scheduler lock exits. Production SQLite write
isolation and byte-preservation guards in the existing test harness passed.
An initial collision fixture crossed a clock second; the fixture now pins the
filename deterministically. No production backfill was used for testing.

`bash -n scripts/rawcandle_temp_cleanup.sh` and `git diff --check` passed.
**Full suite: NO.** No push, provider calls, source/Fundamentals/forecast data
writes, production publication, taxonomy or mathematical changes, schedule/time
changes, VHD compaction, Restic operation or unrelated directory cleanup.

The 12 initial unrelated worktree entries are preserved and excluded from the
commit. Final filesystem/configuration/StockCore preservation and disk measurements
are recorded in [execution](g_ops_04_cleanup_execution.md), with detailed runtime
identity checks under ignored `temp/g_ops_04/`.
