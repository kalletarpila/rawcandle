# P1.8C — Durable publication-drain terminal acceptance evidence

Selected run: `publication_drain_20261009T175136Z_e99387cf`.

Result: immutable terminal receipt reconstructed deterministically and created; updated read-only inspection **ELIGIBLE**. All **3 backups / 2,627,518,464 bytes** remain. No real cleanup or cleanup acceptance record was performed. This phase does not authorize cleanup.

## Evidence gap and reproduced stop

Before the adapter changes, inspection reproduced `NOT_ELIGIBLE / PUBLICATION_DRAIN_JOURNAL_RUN_MISMATCH`. The canonical journal belongs to normal refresh `20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc`, with active generation `refresh_20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc`.

P1.7's operation report retains successful 85-key execution, generation IDs, role verifications, backups, scope, and rollback NOT_REQUIRED. It does not embed its full terminal canonical journal. The missing per-run artifact was an immutable binding of terminal COMPLETED step/state, activation, postflight, recovery, and that journal's completion-time hash to the exact report, scope, generations, and rollback files. A later COMPLETED journal cannot establish those old terminal facts.

The current journal gate therefore needed additional historical evidence. It was not safe to ignore a mismatched run ID or interpret SUCCESS alone as terminal/recovery proof.

## Receipt contract and immutable storage

Implementation: `rawcandle/fundamentals/admin/publication_terminal_receipt.py`.

Schema/version: integer `schema_version=1`; `run_kind=PUBLICATION_DRAIN`.

Canonical storage convention:

```
fundamental_reports/publication_drains/<run_id>/publication_drain_terminal_receipt_v1.json
```

The fixed versioned sibling filename enforces one artifact per operation directory. Contents carry a canonical SHA-256 `receipt_fingerprint`. Any other matching versioned receipt sibling makes historical loading fail closed, including identical duplicate files. The directory is an explicitly selected report directory and is never scheduler input or active-generation state.

The existing immutable reviewed-artifact writer writes a temporary file, flushes/fsyncs it, makes it mode 0444, exclusively hard-links the complete file into place, removes the temporary name, and fsyncs the parent directory. Existing files are never overwritten. Publication and loading reject symlink files/directories/ancestors. The runtime report directory remains git-ignored; this receipt is intentionally not repository-owned. Its exact identity and evidence pins are retained here.

The receipt binds:

- Exact run ID, operation path and byte SHA-256.
- OLD/published generation IDs, manifest paths and canonical manifest fingerprints.
- Reviewed plan fingerprint, exact writable membership fingerprint/count, context-only count, and scope fingerprint.
- COMPLETED journal state and step; ACTIVATED_AND_VERIFIED; PASSED postflight; rollback/recovery NOT_REQUIRED.
- Exactly provider/canonical/analysis role records: OLD sources, selected backup paths/hashes/sizes, and published paths/hashes/sizes.
- Completion-time canonical journal SHA-256, optional separate execution authorization fingerprint, timestamp, proof references, and receipt fingerprint.

No databases, raw logs, full mutable journal, or executable inputs are copied into the receipt.

## Future finalization and failure semantics

`run_backlog_drain` creates the receipt under its existing publication lock after successful activation, postflight verification, durable terminal journal completion, and final operation-report persistence. The receipt hashes the final persisted JSON bytes; JSON tuple/list normalization is accounted for. Report bytes are not subsequently rewritten to advertise the auxiliary receipt.

Integration covers reviewed-plan publication drains, the family supported by P1.8A acceptance and possessing the required plan/membership/context evidence. Ordinary unreviewed/partial drains retain their existing behavior and do not acquire invented plan fingerprints or successful acceptance receipts. No normal Admin acceptance path receives a receipt.

Receipt creation reuses all current-run P1.8A verification gates, verifies the plan binding, and rejects failed, restored, incomplete activation, failed postflight, nonterminal, and recovery-required states. Duplicate creation rejects.

An auxiliary receipt failure leaves the completed financial publication successful. The returned result explicitly reports `terminal_acceptance_evidence.status=UNAVAILABLE`; a best-effort `terminal_acceptance_error.json` preserves the error without altering the finalized operation report or rolling back publication. Historical cleanup remains unavailable without valid terminal evidence. Current-run acceptance can still use its own canonical journal through the unchanged P1.8A checks.

## Historical acceptance and lineage

`run_acceptance_cleanup._publication_drain_result` chooses between two paths:

1. Canonical journal belongs to the selected run: all existing P1.8A checks remain required.
2. Canonical journal belongs to another run: load exactly one immutable selected-run receipt and require its full binding before applying the same selected backup/source/published-generation checks.

Historical support is deliberately limited to an **explicit direct successful successor**. The current terminal journal must name the selected published generation as its exact OLD generation, with identical manifest, directory, role paths, and published role hashes. Its operation must be normal refresh or publication drain; its NEW generation must differ. Its active pointer, NEW manifest, directory, role paths, hashes, sizes, replacement verification/state and SQLite integrity must agree. Current state/step, activation, postflight, and rollback/recovery must all be clean terminal values.

This proves the transition selected published generation → current active generation through the existing successful journal contract. It does not use timestamps, a generation-name comparison, or a generic assertion that a newer generation is safe. A rollback to an older generation, an intermediate generation with missing lineage, or any unknown ancestry rejects. More distant descendants require additional retained lineage evidence and are outside this bounded implementation.

Every selected backup path is also prohibited anywhere in the current journal, so current recovery cannot depend on these files. Selected OLD and published manifests must still match their receipt fingerprints. The published databases remain independently verified even though they are no longer active.

The exact selected 3-role inventory, ownership, source paths, hashes, sizes, SQLite checks, absence of extras/symlinks, scope, operation, and receipt linkage remain mandatory. Current journal and active pointer are reread to detect changes during inspection. The receipt supplies a small in-memory terminal view for the existing adapter; neither journal nor historical report is rewritten.

Normal Admin `PRODUCTION_APPLY` acceptance is unchanged. The only deletion boundary remains the existing locked `accept_run_and_cleanup_backups` implementation, including its repeated validation immediately before deletion. Generation directories and operation/receipt artifacts never enter its deletion manifest.

## Exact P1.7 bounded backfill

`reconstruct_p17` accepts no alternate run or arbitrary terminal facts. It pins two committed audit blobs by commit, path, and byte SHA-256:

| Proof | Git commit | Blob SHA-256 |
| --- | --- | --- |
| P1.7 execution report | `13de79ae0d51d9e5e4991e33ec4ba26ae55cd6b0` | `0bc2c23a4d308f4d22697dc51a00cfe03c49bb7dc38dbcc85666e2a5cfd324c2` |
| Original P1.8 acceptance audit | `a219365188a44afe0374dd1aac88ced2b38f0d10` | `c5f7af1d9bccba52defbbf1aaaa1cc728e7feadf162e64e61a06581486afbaff` |

The first explicitly records COMPLETED, ACTIVATED_AND_VERIFIED, PASSED, and rollback/recovery NOT_REQUIRED for P1.7. The second records its terminal journal byte hash `a45cf8349978c76cd1f5e1cb82b24e13e008f463a48d865d5ee2484beba4a3f8`. This hash is retained audited evidence, not a recomputation from an available old journal. The old full journal is not reconstructed or archived.

Additional fixed evidence:

| Binding | Value |
| --- | --- |
| Final P1.7 operation SHA-256 | `afd87308c73ed29262f6debdde90ddc092d889ab1382fe04997495b8326125d1` |
| Plan fingerprint | `f40cd95cb7a0ad49acc94ea63ebd2d2e87a63e63ed542d52a6668fd69f054d70` |
| Plan byte SHA-256 | `6c6d05c835ce6c286ff37583aab966f6f2d9f4c92d46aaa16ce970ae1ab150d2` |
| Writable membership fingerprint | `deeb4247ea48ab89c76f22ea1de78d1437a9a4de726172fda5ecbfa30a502234` |
| Execution authorization fingerprint | `1b8b82f46b7c224ac97993ffbb10d7ce15603c937396d123065fd035f530133d` |
| OLD manifest fingerprint | `0cc331f59dfefbf58adb09d8467048e392e95dda24cbe3cb1ac3d54fe8debc3f` |
| Published manifest fingerprint | `ff44c14a9d2a3834bd1bc0b6e2e4da86870b58839279ced82eced69447c13d1a` |

The full policy plan is validated, including its approved evidence extension. Execution authorization fingerprint, explicit YES, publication/apply authorization, exact keys, membership, handoff, approval, proposal, and OLD generation binding must agree. The approved handoff is `289eca58761068d8106ca628db65fe3454aa1dc16f178f7bfb975f67ce6a5d81`; evidence approval is `0d82b233adec0e0d85a6e1ad568b72d061881103dd2442c0922b42b1786bf651`. All 85 writable keys and 116 context-only keys are derived from the pinned plan. Full historical safety/backup verification runs before publication of the candidate receipt.

OLD generation: `refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`.
Published generation: `publication_drain_20261009T175136Z_e99387cf`.

Two complete reconstructions with the same recorded backfill timestamp `2026-10-10T07:24:13Z` produced identical receipts. Backfill then exclusively created:

```
/home/kalle/projects/rawcandle/fundamental_reports/publication_drains/publication_drain_20261009T175136Z_e99387cf/publication_drain_terminal_receipt_v1.json
```

- Receipt fingerprint: `8edadb2a770d55db80b5a76dcebed5093a0985c5d0aeb3b25628033bf6438769`.
- Receipt file SHA-256: `62f484e149e3717cb628de32e3fe939c2c3fa4c73e63135d859b48a8aa9c19d4`.
- Mode: 0444; exactly one receipt.

The later canonical journal supplies only the successful direct-successor/current safety proof. It is never used as P1.7 terminal authority.

## Real read-only validation and Production invariance

Updated `inspect_cleanup_eligibility` returned:

```
status: ELIGIBLE
run_kind: PUBLICATION_DRAIN
journal_state: COMPLETED
backup_count: 3
bytes_freed: 2627518464
```

`bytes_freed` is the inspector's estimate; actual freed bytes are **0**. No real call to `accept_run_and_cleanup_backups` occurred. No `backup_cleanup.json` exists for P1.7.

| Retained role | Bytes | SHA-256 |
| --- | ---: | --- |
| provider | 968331264 | `fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981` |
| canonical | 749371392 | `996deb198513b94e22888dbbb11b8139698b68cf98201a5df4d9bb8cd30a1845` |
| analysis | 909815808 | `9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c` |

Byte hashes/sizes were compared to the retained pre-change snapshot for all three current Production databases, active pointer, canonical journal, Review Queue, both scheduler configurations, P1.7 operation report, original proposal/approval/handoff/semantic evidence/plan/execution authorization, execution report/results, and P1.8A adapter report. All matched. All selected backup bytes also matched, with exact inventory still 3 / 2,627,518,464 bytes.

Consequently publication authority, financial logical state, watermark, Review Queue, scheduler configuration and active generation are unchanged. The only new real operational artifact is this terminal receipt. Policy V1 and resolver implementation were not edited. Unrelated pre-existing worktree changes remain outside the commit.

## Focused validation

No full suite was run.

```
python3 -m pytest -q tests/test_publication_terminal_receipt.py \
  tests/test_publication_drain_run_acceptance.py \
  tests/test_fundamentals_admin_run_acceptance_cleanup.py \
  tests/test_reviewed_publication_plan.py
# 161 passed

python3 -m pytest -q tests/test_publication_terminal_receipt.py
# 41 passed after final receipt-binding/path hardening
```

Coverage includes deterministic schema/fingerprint, immutable/exclusive creation, symlink rejection, current-run acceptance, actual reviewed publication integration, candidate/activation/postflight failure suppression, rollback/recovery suppression, auxiliary creation failure preserving SUCCESS, historical acceptance after advancement, tampered/resealed/missing/duplicate evidence, operation/plan/membership/generation/manifest/backup path/hash/size contradictions, dirty current recovery, backup dependency, unknown/rollback lineage, current database corruption, and synthetic deletion through the unchanged boundary only. Existing publication-drain acceptance, normal Admin acceptance and reviewed execution/recovery regressions passed. The exact real P1.7 deterministic reconstruction and updated inspection were separately measured read-only; Production fixtures were not added to pytest.

## P1.8D next step

Explicitly authorize acceptance of this exact P1.7 run bound to receipt fingerprint `8edadb2a770d55db80b5a76dcebed5093a0985c5d0aeb3b25628033bf6438769`, then freshly inspect under the existing Production lock and invoke only the existing acceptance/cleanup function. Delete only the three verified selected rollback files, record existing cleanup evidence, and recheck invariance. If the current journal, lineage, receipt, report, generations, or backup inventory no longer passes, stop and retain all backups. This phase performs none of those cleanup actions.
