# P1.8C.1 — Bind historical terminal receipts into the existing cleanup audit

Selected run: `publication_drain_20261009T175136Z_e99387cf`.

This implementation carries the validated historical receipt identity through inspection, locked revalidation and the existing `backup_cleanup.json` writer. No real cleanup authorization is requested and no real cleanup is executed. P1.8D must restart with fresh checks and a new explicit YES before any real deletion.

## Reproduced P1.8D gap

Starting HEAD: `5a3d5d57bae0c0f18cd7c15ac80d9e8b69aadc56`. The preceding P1.8C implementation was `052af16df9e179c5bc1174af0cd1dbaf15e0f0f1`.

Before source changes, real read-only inspection of P1.7 returned `ELIGIBLE / PUBLICATION_DRAIN`, three backups and 2,627,518,464 bytes, but no terminal receipt identity. The actual data flow was:

1. `_publication_drain_result` loaded and validated the historical terminal receipt and built a normalized terminal journal view.
2. Its returned normalized result contained the run/journal view without receipt identity.
3. `inspect_cleanup_eligibility` returned the run, backup inventory and journal state without receipt identity.
4. `_accept_run_and_cleanup_backups_locked` rebuilt the normalized result and wrote a fixed cleanup evidence dictionary after successful deletion/integrity checks. That dictionary omitted receipt fingerprint, receipt file hash and receipt reference.

Thus a successful cleanup would not have recorded which exact immutable receipt justified deletion. The P1.8D stop was required; no hypothetical cleanup was executed to reproduce it.

## Receipt identity and canonical reference

The existing acceptance module now has a small `_historical_receipt_identity` reader. Its canonical path is the recognized fixed v1 filename under the resolved exact selected run directory:

```
fundamental_reports/publication_drains/<run_id>/publication_drain_terminal_receipt_v1.json
```

The reader requires the selected directory/run ID, regular read-only receipt file, recognized filename/version, no symlink ancestors or receipt, exactly one recognized receipt, and a valid canonical fingerprint. It recomputes the canonical fingerprint and exact file SHA-256 from the file; it does not trust caller-supplied identity or previous reports.

The compact `terminal_receipt` object contains:

| Field | Meaning |
| --- | --- |
| `schema_version` | Receipt schema/version, currently 1 |
| `run_kind` | `PUBLICATION_DRAIN` |
| `run_id` | Exact selected receipt/run ID |
| `path` | Absolute canonical selected-run receipt path |
| `receipt_fingerprint` | Recomputed canonical receipt fingerprint |
| `file_sha256` | Recomputed exact receipt byte SHA-256 |
| `operation_sha256` | Receipt-bound final operation report SHA-256 |
| `published_generation_id` | Selected published generation ID |
| `source_generation_id` | Selected OLD/source generation ID |

An additional small `terminal_receipt_file_identity` snapshot carries device, inode, size, modification/change times and mode during inspection/revalidation. This detects even identical-byte file replacement and read-only mode changes. It is compared in memory, exposed alongside inspector identity, and deliberately omitted from the durable audit; receipt identity remains reproducible from its canonical path, bytes and contents rather than machine-specific inode metadata.

File identity and hash are checked around receipt reading. The existing terminal receipt validator still proves operation/run/scope/generation/backup binding and exact healthy direct-successor lineage. The adapter rereads receipt identity after those potentially expensive checks and rejects any change during validation. Arbitrary receipt identity fields from an operation report are removed from the normalized result and cannot become trusted audit evidence.

The pre-existing bounded reconstruction-only in-memory candidate argument remains available to validate a receipt before exclusive publication. Public inspection and cleanup never supply that argument and must read the actual canonical file.

## Propagation and pre-delete ordering

Only the historical-receipt publication-drain path adds receipt identity to the normalized result and inspector output.

The existing public locked acceptance action remains the sole deletion boundary:

1. Acquire the existing Production lock and inspect eligibility.
2. Reread and normalize the operation/receipt/current lineage. Compare receipt identity and file snapshot to the eligible inspection; reject differences.
3. Perform the existing exact backup ownership, inventory, hash/size and SQLite checks, and current live database checks.
4. Reread the full operation/receipt/lineage again and compare the complete normalized result, including receipt identity/snapshot.
5. Recheck current journal state, then reread and compare the canonical receipt immediately before the existing deletion loop.
6. Delete only the existing validated selected rollback allowlist, verify live databases unchanged, and atomically write the existing completed cleanup artifact with the receipt identity from that final reread.

No new cleanup command, registry, sidecar audit or lower-level public deletion path is introduced. No generation, publication report, receipt or other audit file enters the deletion allowlist.

Receipt fingerprint, bytes, file identity, path, existence, mode, run, operation, generation, backup, duplicate and symlink contradictions reject before unlinking. Existing current journal/recovery, exact lineage and backup integrity gates remain required.

## Additive cleanup audit schema

The existing cleanup evidence has no whole-artifact schema version that needs changing. Historical receipt-based cleanup adds only top-level `run_id`, `run_kind` and the compact `terminal_receipt` object above. All existing evidence fields remain, including `source_production_run_id`, exact deleted files, recorded/verified backup hashes and sizes, byte total, integrity and journal state.

The audit object is populated from the final canonical reread, not a remembered fingerprint or the earlier P1.8C report. The existing atomic `write_text_atomic` writer and write ordering remain unchanged: a completed cleanup record is written only after all selected deletions and unchanged-live-database checks succeed.

Partial deletion semantics remain the existing contract: an unlink failure propagates immediately; remaining files are retained and no completed cleanup audit is written. This phase adds no partial-deletion transaction mechanism or automatic continuation. A focused test injects failure on the second selected unlink and verifies that no receipt-bound success audit is produced.

Existing completed cleanup records remain readable. Synthetic historical cleanup is idempotent through the existing `ALREADY_CLEANED` path, preserving the persisted receipt binding.

## Compatibility

- Historical publication drain: receipt identity is required, exposed and durably recorded; all P1.8C historical safety gates remain.
- Current-run publication drain: the canonical journal path retains P1.8A behavior. No receipt is forced, even when one is available, and its ordinary cleanup audit keeps the prior structure.
- Normal Admin Production acceptance: no publication receipt metadata or new publication audit fields are added. Existing normal Admin cleanup and history behavior remain compatible.
- Publication receipt generation/finalization code, Policy V1 and resolver semantics are not changed.

## Focused tests

Only the requested directly relevant groups were run:

```
python3 -m pytest -q tests/test_publication_terminal_receipt.py \
  tests/test_publication_drain_run_acceptance.py \
  tests/test_fundamentals_admin_run_acceptance_cleanup.py
# 155 passed
```

The 74 terminal receipt tests, 48 publication-drain acceptance tests and 33 Admin acceptance tests cover:

- Inspector identity fields and exact persisted audit binding, hash/fingerprint reproduction, operation and generation references.
- Successful synthetic historical cleanup, exact three-file deletion allowlist, protected generations/reports/receipt, and idempotence.
- Changes after initial locked inspection and before final validation: invalid fingerprint, whitespace bytes, missing/renamed receipt, identical-byte replacement, symlink file/ancestor, duplicate, run/operation/generation/backup contradiction, valid resealed contents and writable mode.
- Last pre-delete reread rejecting a change after full validation and the final journal check.
- No audit or deletion after rejected eligibility/identity; no completed receipt-bound audit after partial unlink failure.
- Unchanged current-run publication and normal Admin audit structure, plus all existing acceptance regressions.

No full suite or additional execution regression group was run. Receipt generation/finalization code was not touched; its existing cases within the terminal receipt group also passed.

## Real P1.7 read-only validation

Updated real `inspect_cleanup_eligibility` returned **ELIGIBLE / PUBLICATION_DRAIN**, terminal journal COMPLETED, exact backup count **3**, estimated cleanup bytes **2,627,518,464**, and this identity:

```json
{
  "schema_version": 1,
  "run_kind": "PUBLICATION_DRAIN",
  "run_id": "publication_drain_20261009T175136Z_e99387cf",
  "path": "/home/kalle/projects/rawcandle/fundamental_reports/publication_drains/publication_drain_20261009T175136Z_e99387cf/publication_drain_terminal_receipt_v1.json",
  "receipt_fingerprint": "8edadb2a770d55db80b5a76dcebed5093a0985c5d0aeb3b25628033bf6438769",
  "file_sha256": "62f484e149e3717cb628de32e3fe939c2c3fa4c73e63135d859b48a8aa9c19d4",
  "operation_sha256": "afd87308c73ed29262f6debdde90ddc092d889ab1382fe04997495b8326125d1",
  "published_generation_id": "publication_drain_20261009T175136Z_e99387cf",
  "source_generation_id": "refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771"
}
```

The inspector also returned the small file-identity snapshot used to detect replacement during locked cleanup. The canonical receipt remains the original 5,555-byte mode-0444 artifact. Its fingerprint and file hash agree exactly with P1.8C. Its operation hash, selected run and OLD/published generations passed actual historical validation; the current direct successful successor remains `refresh_20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc`.

Only the real inspector was called. The real `accept_run_and_cleanup_backups` action was **not** called. No real cleanup authorization was requested, no selected backup was deleted, and no selected `backup_cleanup.json` exists. Inspector `bytes_freed` is an estimate; actual freed bytes are **0**.

## Production invariance

Fresh before/after byte hashes and sizes matched for 20 protected files: active provider/canonical/analysis databases, active pointer, canonical mutable journal, Review Queue, both scheduler configurations, selected operation report, proposal, approval, durable handoff, semantic evidence, immutable v3 plan, execution authorization, execution report/results, prior adapter report, terminal receipt and acceptance report. The three selected backup file hashes/sizes also matched their fresh baseline, with exact inventory still **3 files / 2,627,518,464 bytes**.

Current active generation is unchanged: `refresh_20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc`. Byte identity of the active databases proves financial contents, publication authority and provider watermark unchanged. Review Queue, scheduler, active pointer, canonical journal, selected receipt and protected audit evidence are unchanged. Policy V1 and resolver code were not edited. All real runtime work was read-only; no generation or other backup deletion occurred.

Only the acceptance source module, focused terminal receipt tests and this report belong in the commit. Pre-existing runtime journal/generation/pointer and unrelated research changes remain excluded. Runtime validation output stays outside the repository-owned audit contract; no runtime audit or metadata sidecar was created.

## Exact P1.8D restart

This phase fixes the audit propagation blocker, not cleanup authorization. Restart P1.8D Stage 1 from fresh current Production state, with receipt fingerprint `8edadb2a770d55db80b5a76dcebed5093a0985c5d0aeb3b25628033bf6438769`, exact receipt file SHA-256/path above, operation report, direct-successor lineage, clean current recovery, exact three-role backups and bounded collateral inventories.

If all gates pass, present the exact selected deletion allowlist and ask the P1.8D explicit YES/NO question. Do not reuse earlier YES responses or this read-only ELIGIBLE result. After a new YES, repeat the critical state and identity checks; changed lineage, journal or inventory makes authorization stale. Use only the existing locked acceptance action, verify the persisted cleanup audit contains this exact receipt identity, and prove exact three-file deletion with no collateral changes. If eligibility fails, stop and retain backups.
