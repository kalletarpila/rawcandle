# Ownership publication participation in locked rollback cleanup

2026-10-28, Europe/Helsinki. Task: P/B-OWNERSHIP-ROLLBACK-CLEANUP-INTEGRATION-1. Governing [publication](pb_ownership_publication_ge_rtx_t_2026-10-28.md), publication commit `925a3a3a558eb425824145492c8bea52271b51bd`, and [backup acceptance](pb_ownership_rollback_backup_acceptance_2026-10-28.md), original stop commit `6a34dbadd08c88c119fb83a9a2aa8544004c0b34`.

## Reproduction and exact cause

Before source edits, the locked read-only audit again proved the exact successful publication, healthy active roles, unchanged complete Review Queue, three valid backups and 2,629,734,400 bytes. Default `inspect_cleanup_eligibility` returned `NOT_ELIGIBLE / CLEANUP_RUN_DIRECTORY_INVALID`; diagnostic inspection with the native ownership lane parent returned `NOT_ELIGIBLE / CLEANUP_EVIDENCE_INVALID:result.json`. This was reproduced at 2026-10-28T21:42:58.633961+02:00–21:43:45.663669+02:00. No deletion occurred during reproduction.

The generic cleanup owner searched direct admin runs and the publication-drain sibling, then required a standard `result.json`. Native ownership publication instead writes `preview.json` and `completed_journal.json` under `admin_runs/pb_ownership_publications/<operation-id>`. Its completed immutable-generation lifecycle already contained the required role provenance and terminal evidence, but had no adapter into acceptance. This was an evidence-location and evidence-shape compatibility gap, not a failed financial publication.

## Bounded integration

Only `rawcandle/fundamentals/admin/run_acceptance_cleanup.py` changes in production source. `_run_dir` adds the established ownership lane as one explicit candidate root; multiple matches remain ambiguous and are rejected. `_load_acceptance_result` dispatches native ownership receipts to a read-only adapter. Standard Production and current/historical publication-drain adapters retain their original behavior.

The adapter returns an in-memory view in the existing cleanup abstraction: operation/run identity, terminal journal, OLD/current generation, exact role backup mapping, postflight and NOT_REQUIRED recovery. It never fabricates or writes a standard Production result. The existing shared inspector, manifest validator, locked acceptance function, unlink loop, idempotence and audit writer continue to own selection and deletion. There is no new cleanup endpoint, parallel deleter, ticker special case or generation-ID allowlist.

The native `backup_cleanup.json` audit adds the ownership run kind, OLD/NEW generation IDs, exact preview hash and completed-journal content hash. The audit is written beside the native preview/completed receipt and survives backup deletion. The publisher, financial policy, ownership approvals, queue, journal schema and generation-retention policy are unchanged.

## Safety and recovery-release conditions

An ownership owner is eligible only when all of the following hold:

- Native preview operation, preview ID, candidate-generation ID, canonical journal operation/run/new generation and requested owner agree exactly; preview fingerprint is valid and equals the journal's frozen refresh-set fingerprint.
- Canonical journal equals the native completed archive. The existing generation-source validator requires COMPLETED current step/state, PASSED postflight, NOT_REQUIRED recovery and ACTIVATED_AND_VERIFIED generation activation.
- Current active manifest equals the published generation manifest and journal's NEW manifest; the retained OLD manifest equals its journal evidence and preview source generation. OLD and NEW paths are distinct, expected generation directories, with no symlinked generation directory.
- All role maps contain exactly provider/canonical/analysis. Per-role current paths, OLD paths and backup paths match authoritative journal/generation bindings. Filenames cannot escape their generation directory.
- Preview selected case IDs and candidate/approval/record hashes agree with the completed journal's exact ownership scope and artifact pin. No implicit case selection occurs.
- Every selected backup, OLD role and current role passes read-only SQLite quick/FK checks; actual size/hash matches manifest, preview and journal fingerprints. Selected backups have no WAL/SHM/journal sidecars and cannot alias OLD/current role files through a hard link. The existing manifest validator also rejects symlinks or ownership/path mismatches.
- The backup owner's immediate `.db` inventory is exactly the three role filenames. Coexisting publication evidence is preserved and is never selected by filename search.
- Journal, manifests, preview and completed receipt are reread after validation. The shared locked owner reconstructs and compares the adapted evidence immediately before the deletion boundary and performs its existing selected-backup/live-integrity checks.

**Historical ownership release remains unsupported.** A later journal, changed active generation, missing completed receipt, rollback/recovery state, missing role, extra role, altered backup, ambiguous root or failed integrity check rejects eligibility. No older ownership receipt is silently preferred over the canonical journal. Healthy terminal evidence releases the automatic rollback dependency only after all current-generation/provenance checks pass.

Lock ownership is unchanged: the UI entry takes its operation lock; the public acceptance function takes the normal Production and scheduler locks, using nonblocking exclusion. Existing lock-order checks and active-operation refusals remain effective. There is no override/bypass in the live invocation.

Deletion semantics remain the shared mechanism's sequential exact-path unlinks. The backup directory is removed only if empty, so evidence subdirectories survive. A failure is surfaced; this integration does not introduce transactional filesystem deletion or manual completion of a partial cleanup. No generation file is a deletion target.

## Focused regression evidence

The compatibility/lifecycle group passed **324 tests in 166.60 seconds**, covering:

- `tests/test_fundamentals_admin_run_acceptance_cleanup.py`
- `tests/test_publication_drain_run_acceptance.py`
- `tests/test_publication_terminal_receipt.py`
- `tests/test_full_workflow_cleanup_delegate.py`
- `tests/test_fundamentals_pb_ownership_publication.py`
- `tests/test_provider_payload_workflow.py`
- `tests/test_wfrd_production_candidate_parity.py`
- `tests/test_fundamentals_admin_production_transaction.py`

The final-source focused run passed **31 tests in 59.79 seconds**: all 29 new native ownership cleanup tests plus the two Production/source-repair envelope compatibility cases. These overlap the two compatibility cases above; total distinct tested cases is 353. The new tests publish real native ownership fixtures into isolated project generations, then use public inspection/acceptance on those copies. No live DB is a pytest fixture.

The matrix covers successful normal Production, a source-repair operation in the existing standard cleanup envelope, native ownership success, failed/nonterminal state, failed postflight, required recovery, owner/generation/role mismatch, extra and missing roles, ambiguous provenance, changed active/live/OLD state, sidecars/symlinks/hard links, changed receipt at the delete boundary, real Production lock conflict, already missing backups, idempotent repeat acceptance, unrelated backups and evidence preservation. Existing source-repair publication and full OLD-generation recovery tests also pass. WFRD candidate/review application compatibility is exercised without reopening the live WFRD workstream.

The source-repair envelope compatibility test does not claim that the earlier payload-repair operation's retained native evidence is a standard cleanup receipt. This phase adds only native ownership receipt adaptation; it grants no cleanup eligibility or deletion authority to those unrelated payload-repair backups.

Commands and raw test logs are retained at `/tmp/pb_ownership_cleanup_compatibility_tests.log` and `/tmp/pb_ownership_cleanup_final_tests.log`. Full suite: **not run**. No shared-core regression required expanding beyond the named cleanup/publication/recovery tests.

## Exact live acceptance

The exact selection, execution outcome, before/after inventory, remaining-file count and financial/queue/manifest invariance are recorded in the updated [acceptance report](pb_ownership_rollback_backup_acceptance_2026-10-28.md). The task itself authorizes the exact three backups if all gates pass; no additional YES is required. OLD/current generations and all unrelated backups remain outside the deletion scope.
