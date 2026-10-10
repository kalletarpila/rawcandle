# P1.8D — Completed exact P1.7 receipt-bound acceptance cleanup

Selected run: `publication_drain_20261009T175136Z_e99387cf`. **Acceptance PASS / cleanup COMPLETED**. New explicit operator YES was obtained after fresh Stage 1 validation, followed by unchanged post-YES validation under the existing Production/scheduler locks. The existing acceptance action deleted exactly **3 rollback backups / 2,627,518,464 bytes**. **0 selected backups / 0 bytes remain**. All previous blocked attempts are preserved below.

## Fresh Stage 1 baseline and authorization

Stage 1 completed at `2026-10-10T10:08:59.859142+00:00`. Source HEAD: `f17a527180193b219edd4b71cf3d0af882476f10` (P1.8C.1). Source was unchanged throughout this runtime phase. The pre-existing mutable-journal worktree difference, untracked active pointer/generation files and unrelated research files were preserved and excluded from this documentation commit.

Fresh historical inspector result: **ELIGIBLE / PUBLICATION_DRAIN**. Exact role ownership, three-file inventory, backup paths/hashes/sizes, SQLite integrity, source/published manifests, healthy active generation, direct-successor lineage and clean recovery all passed. There were no unexpected files, symlinks or contradictory receipts. Receipt identity remained stable during inspection. The identical Stage 1/Stage 2 receipt file snapshot was `{"ctime_ns": 1791617111419649337, "device": 2096, "inode": 253444, "mode": 33060, "mtime_ns": 1791617111401910932, "size": 5555}`.

- Receipt fingerprint: `8edadb2a770d55db80b5a76dcebed5093a0985c5d0aeb3b25628033bf6438769`.
- Receipt file SHA-256: `62f484e149e3717cb628de32e3fe939c2c3fa4c73e63135d859b48a8aa9c19d4`.
- Canonical receipt path: `/home/kalle/projects/rawcandle/fundamental_reports/publication_drains/publication_drain_20261009T175136Z_e99387cf/publication_drain_terminal_receipt_v1.json`.
- Bound operation SHA-256: `afd87308c73ed29262f6debdde90ddc092d889ab1382fe04997495b8326125d1`.
- OLD/source generation: `refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`.
- Published generation: `publication_drain_20261009T175136Z_e99387cf`.
- OLD manifest fingerprint: `0cc331f59dfefbf58adb09d8467048e392e95dda24cbe3cb1ac3d54fe8debc3f`.
- P1.7 published manifest fingerprint: `ff44c14a9d2a3834bd1bc0b6e2e4da86870b58839279ced82eced69447c13d1a`.
- Active generation: `refresh_20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc`.
- Active manifest fingerprint: `5758df86d14ce0c4bfe9db1aa649534e2e3fc72f0650bdcda9e4f7e1ba05a366`.
- Canonical journal run: `20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc`; operation `REFRESH_FUNDAMENTALS`.
- Journal state/step: `COMPLETED` / `COMPLETED`; activation `ACTIVATED_AND_VERIFIED`; postflight `PASSED`; recovery `NOT_REQUIRED`.

Direct-successor proof: the current clean refresh journal names the exact P1.7 published generation/manifest/roles as OLD and the current active generation as NEW. The receipt proves P1.7 terminal completion; current journal evidence supplies only the successful successor/current safety proof. Selected backups are absent from current recovery references.

The operator was shown the exact three-file allowlist below and asked to authorize only this selected run, receipt fingerprint, receipt file SHA-256, and **3 / 2,627,518,464 bytes** through the existing locked action. The displayed scope excluded any other backups, generation deletion or publication/authority changes and stated that receipt/journal/lineage/inventory changes invalidate consent.

The operator then explicitly replied **YES** in this conversation. Authorization was recorded at `2026-10-10T10:16:14.059951+00:00` for `interactive_user`. No earlier YES was reused.

## Exact authorized and deleted allowlist

| Role | Exact rollback path | Bytes | Verified SHA-256 | OLD source binding |
| --- | --- | ---: | --- | --- |
| provider | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/provider.db` | 968331264 | `fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981` | `/home/kalle/projects/rawcandle/data/fundamentals_generations/refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771/fundamentals_provider.db` |
| canonical | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/canonical.db` | 749371392 | `996deb198513b94e22888dbbb11b8139698b68cf98201a5df4d9bb8cd30a1845` | `/home/kalle/projects/rawcandle/data/fundamentals_generations/refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771/fundamentals_v4.db` |
| analysis | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/analysis.db` | 909815808 | `9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c` | `/home/kalle/projects/rawcandle/data/fundamentals_generations/refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771/fundamentals_analysis.db` |

Before: **3 / 2,627,518,464 bytes**. Deleted: **3 / 2,627,518,464 bytes**. Remaining: **0 / 0 bytes**. The selected empty backup directory was removed by the existing contract. No manual unlink or separate deletion implementation was used.

## Stage 2 and existing locked action

The existing `production_lock` acquired both the Production kernel lock and scheduler lock before post-YES revalidation. Stage 2 completed at `2026-10-10T10:17:09.675124+00:00` and matched Stage 1 exactly for HEAD/worktree state, active generation/manifest, canonical journal, receipt reference/fingerprint/bytes/file-identity snapshot, operation, OLD/published manifests, backup ownership/hash/size/inventory, sibling inventories, generation inventories, protected hashes, watermark, authority census and Review Queue state.

Only `run_acceptance_cleanup.accept_run_and_cleanup_backups` performed deletion. Its supported reentrant Production-lock option retained the already-held locks continuously from fresh revalidation through cleanup and postflight. The action repeated its own eligibility, receipt, operation, lineage, inventory and integrity checks, including the final canonical receipt reread immediately before its existing deletion loop.

Existing action result: **COMPLETED**. Audit timestamp: `2026-10-10T10:17:39Z`. Post-cleanup verification completed at `2026-10-10T10:17:40.655537+00:00`. No source edits, pytest or full suite were needed or performed.

## Persisted receipt-bound cleanup evidence

Existing atomic cleanup artifact:

`/home/kalle/projects/rawcandle/fundamental_reports/publication_drains/publication_drain_20261009T175136Z_e99387cf/backup_cleanup.json`

File SHA-256: `e2a49e9288f1e902e075e5923a2028b8b0ad4e92f826eb2663cc63bb3401531f`.

The persisted JSON equals the returned action result and binds both `run_id` and `source_production_run_id` to the exact selected run, `run_kind=PUBLICATION_DRAIN`, the exact three deleted paths, recorded and verified backup hashes/sizes, integrity checks, total bytes, COMPLETED journal state and unchanged live databases. Its `terminal_receipt` is exactly the identity revalidated before deletion:

```json
{
  "file_sha256": "62f484e149e3717cb628de32e3fe939c2c3fa4c73e63135d859b48a8aa9c19d4",
  "operation_sha256": "afd87308c73ed29262f6debdde90ddc092d889ab1382fe04997495b8326125d1",
  "path": "/home/kalle/projects/rawcandle/fundamental_reports/publication_drains/publication_drain_20261009T175136Z_e99387cf/publication_drain_terminal_receipt_v1.json",
  "published_generation_id": "publication_drain_20261009T175136Z_e99387cf",
  "receipt_fingerprint": "8edadb2a770d55db80b5a76dcebed5093a0985c5d0aeb3b25628033bf6438769",
  "run_id": "publication_drain_20261009T175136Z_e99387cf",
  "run_kind": "PUBLICATION_DRAIN",
  "schema_version": 1,
  "source_generation_id": "refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771"
}
```

Receipt binding: **PASS**. Hash verification before deletion: **true**. Every backup SQLite quick check was `ok` with zero foreign-key errors. `live_databases_unchanged=true`; `backup_directory_removed=true`.

Post-cleanup read-only inspection returns **ALREADY_CLEANED / Accepted / backups cleaned**. Its `backup_count=3` and `bytes_freed=2627518464` refer to the recorded deletion, not remaining files. Actual selected inventory is zero.

## Exact collateral and Production proof

Bounded before/after metadata inventories covered the selected backup directory, every sibling backup-run entry under the explicit backup root, all 13 generation-root entries, the full contents of the three relevant immutable generations, and selected operation evidence. No unrelated large trees were hashed.

- The only backup-root entries that disappeared were the three authorized files and their now-empty selected directory.
- All **49 other backup inventory entries** matched exactly; other backup directories/files changed: **0**.
- All **13 generation-root entries** matched; the OLD, P1.7 published and active generation inventories matched exactly. Immutable generations deleted: **0**.
- Selected operation-directory inventory retained every original file unchanged. Its only addition was the existing `backup_cleanup.json` audit.
- All **22 protected file hashes/sizes** matched at cleanup postflight; all original audit evidence remained present.
- Active generation before and after: `refresh_20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc`. Active manifest unchanged.
- Current journal byte content and semantics unchanged; no acceptance journal rewrite occurred.
- Receipt fingerprint, bytes, canonical path and immutable file identity unchanged.


Compact metadata inventory fingerprints before/after cleanup were identical:

| Inventory | Canonical fingerprint |
| --- | --- |
| Other backup entries | `aa429299fa905dc4bbac97a989382db9d1a887c738565902234391cf62ed23c1` |
| All generation-root entries | `ee41683e2bd3ba05c323ff804db40b6bf1fc92bfc13c1eea81cab5f9d8407a1c` |
| `refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771` contents | `46a4e9f55a9fcc5606f1e2aba00dbc8eeae2036dd17b3c801228008c97f526f8` |
| `publication_drain_20261009T175136Z_e99387cf` contents | `ca14282d174af636d8dfc9f3648ea49e0fd290e77c0717a39f4705e6a5f21b10` |
| `refresh_20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc` contents | `b14b03c9d0c3ff639f3d29a0b99df092ef88f8fb515071f838eb7a65d1a704ef` |

The protected byte hashes below are identical before and after cleanup. The acceptance document itself was subsequently updated with this authorized completion section; all earlier content remains verbatim below. No other protected artifact was modified by the task.

| Protected artifact | SHA-256 before and after cleanup |
| --- | --- |
| `data/fundamentals_generations/refresh_20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc/fundamentals_provider.db` | `aed20dab5493fae71db086e163710bb3cd8c694d84b1713f32338cb7e2ef79d9` |
| `data/fundamentals_generations/refresh_20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc/fundamentals_v4.db` | `ca339cfd927c645116614610ed65f4d24edd2b5d0d0458ffb64ca728b22210b4` |
| `data/fundamentals_generations/refresh_20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc/fundamentals_analysis.db` | `0acdbc93f46c070e49a32b15db7a0506db966a27e9740708d6089ca9b9d715c6` |
| `data/fundamentals_active_generation.json` | `a70eed876a80bd48ba0702a4654e3ec4596a34ba542db2b562d2b2ce06340138` |
| `data/.fundamentals_admin_publication_journal.json` | `fc960171c2d30b2c358903b811a9c596d81c5c84c30efa1f554c151cbc37f5ce` |
| `fundamental_reports/fundamentals_refresh_review_queue.db` | `84c18a698ef541a355950c91805ba0e949c9dd4d1a1d4d7d991a7bebc5d3e15b` |
| `scheduler_config.json` | `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894` |
| `forecast_scheduler_config.json` | `67e55b992b6144306b8b96a23157d4879490256c3af1d267f3852da5f1587e79` |
| `fundamental_reports/publication_drains/publication_drain_20261009T175136Z_e99387cf/result.json` | `afd87308c73ed29262f6debdde90ddc092d889ab1382fe04997495b8326125d1` |
| `docs/fundamentals_v4/review_proposals/historical_publication_review_proposal_v1.ea28d203681fa6c331ef3ef1741d80908f7520fd1c3924e9703284c313614657.json` | `6ca99cbc6aeb05ec15fd0927a0c008c9f6add54229ed705b0654c81f89891786` |
| `docs/fundamentals_v4/review_approvals/historical_publication_review_approval_v1.0d82b233adec0e0d85a6e1ad568b72d061881103dd2442c0922b42b1786bf651.json` | `77571dfad2b9d5b6b3a0601df6718b68cf93b2d5f150c898f0141db4039a8387` |
| `docs/fundamentals_v4/reviewed_evidence_handoffs/historical_publication_approved_handoff_v1.289eca58761068d8106ca628db65fe3454aa1dc16f178f7bfb975f67ce6a5d81.json` | `2468472a8497fe7dfab12362938eb3f9f6c2a0a2dd85830e52db1a44d64bf9cd` |
| `docs/fundamentals_v4/reviewed_evidence_handoffs/reviewed_cases.18f6edef3e6e4826b93d55bb9692d67992796b86d371e3a726e63af1d43f853a.json` | `18f6edef3e6e4826b93d55bb9692d67992796b86d371e3a726e63af1d43f853a` |
| `docs/fundamentals_v4/reviewed_publication_plans/historical_publication_policy_plan_v3.f40cd95cb7a0ad49acc94ea63ebd2d2e87a63e63ed542d52a6668fd69f054d70.json` | `6c6d05c835ce6c286ff37583aab966f6f2d9f4c92d46aaa16ce970ae1ab150d2` |
| `docs/fundamentals_v4/review_execution_authorizations/historical_publication_execution_authorization_v1.1b8b82f46b7c224ac97993ffbb10d7ce15603c937396d123065fd035f530133d.json` | `d08a4836044e2ba1b9ac470774f0b1fb9035fd8c6657d7ee4779c61f8838c36b` |
| `docs/fundamentals_v4/fundamentals_v4_historical_publication_p17_execution.md` | `0bc2c23a4d308f4d22697dc51a00cfe03c49bb7dc38dbcc85666e2a5cfd324c2` |
| `docs/fundamentals_v4/fundamentals_v4_historical_publication_p17_results.csv` | `1bc6bca3d221f518dd79542063f1f22fc276cf85c3a9dffd5502809c48d24e46` |
| `docs/fundamentals_v4/fundamentals_v4_publication_drain_run_acceptance_adapter.md` | `56adb9a85882ff8722430ad7a2e840552380e7e7bca339c3b979310cae45618e` |
| `fundamental_reports/publication_drains/publication_drain_20261009T175136Z_e99387cf/publication_drain_terminal_receipt_v1.json` | `62f484e149e3717cb628de32e3fe939c2c3fa4c73e63135d859b48a8aa9c19d4` |
| `docs/fundamentals_v4/fundamentals_v4_historical_publication_p17_acceptance.md` | `b7be25ad5173ebb649b6e6d7ca7f7a9518e8050caa25ddb83ed2d361d23b7a1e` |
| `docs/fundamentals_v4/fundamentals_v4_publication_drain_terminal_receipt.md` | `a946e67a189ea33b134cb0fee95d0197ce2be091adb499b68286524b40115d23` |
| `docs/fundamentals_v4/fundamentals_v4_publication_drain_cleanup_receipt_binding.md` | `f1736335bc3a71cd21f306b22f5b5f2648578fa12eaa856b41bc44f90c6a5640` |

Authority census before/after: VERIFIED **12,979**; UNRESOLVED **770**; NOT_FOUND **1,870**; AMBIGUOUS **628**. Active database byte identity also proves financial contents and publication authority unchanged.

Provider watermark before/after: **2026-10-09**; successful refresh `20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc`, completed `2026-10-10T04:31:12Z`. The full `sharadar_refresh_state` row matched.

Review Queue semantic state before/after:

| Table | Rows | Semantic fingerprint |
| --- | ---: | --- |
| `pb_ownership_review` | 0 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `refresh_review_queue` | 6 | `a2539327f15a8f08dbbd371d793b81a7cf90af20fbae0796a23bdde3db7b0139` |
| `refresh_review_queue_audit` | 38 | `3fcc23654bda603887e0f5607c30a414e63592bd27151384c7b003408d692adb` |

Review Queue bytes and semantics, both scheduler configuration hashes, provider watermark, active pointer, current journal and publication evidence all matched. Policy V1 and resolver source were not changed. Existing lock owner metadata is part of the normal Production/scheduler locking protocol; no scheduler configuration or publication state was changed.

## Final acceptance state and next backlog work

P1.7 is accepted; the exact selected rollback backups are cleaned. The operation report, immutable terminal receipt, OLD/published/current generations, proposal, approval, durable handoff, plan, execution authorization, execution results and all prior phase reports remain auditable. The cleanup audit is a runtime artifact under its existing ignored report directory and is not repository-owned or force-added to Git. Only this acceptance documentation belongs in the commit. Nothing is pushed.

Recommended next backlog work: resume review of the remaining historical publication holds under their separate evidence and authorization workflow. This completed cleanup grants no authority for other backups, generations or publication cases.

---

## Earlier P1.8D and P1.8/B blocked attempts — preserved history

# P1.8D — Stopped before authorization: cleanup audit lacks terminal receipt binding

Selected run: `publication_drain_20261009T175136Z_e99387cf`.
Required terminal receipt fingerprint: `8edadb2a770d55db80b5a76dcebed5093a0985c5d0aeb3b25628033bf6438769`.

**STOPPED before the cleanup authorization gate. No authorization was requested, no acceptance action was invoked, and no backup was deleted.**

## Contract review finding — 2026-10-10

Inspected HEAD: `052af16df9e179c5bc1174af0cd1dbaf15e0f0f1` (P1.8C). Source matches that implementation; the pre-existing mutable journal, untracked generation/pointer files and unrelated research files remain outside this documentation change.

P1.8D section I.4 requires the cleanup audit artifact to bind the exact terminal receipt fingerprint. The current `_accept_run_and_cleanup_backups_locked` evidence dictionary in `rawcandle/fundamentals/admin/run_acceptance_cleanup.py` records the selected run ID, deleted files, verified backup hashes/sizes, integrity, byte total and journal state. It does **not** record the terminal receipt fingerprint, receipt file hash or receipt reference. The P1.8C adapter validates the historical receipt, but its normalized return value also does not carry receipt identity to the cleanup evidence writer.

Thus even a successful existing cleanup action cannot produce the receipt-bound audit required by this task. A prior ELIGIBLE inspection cannot establish that missing output contract. No extra runtime audit file, manual cleanup, or post-hoc alteration of the existing cleanup record was used to work around it.

P1.8D explicitly requires: “If a source defect is discovered, STOP and make it a separate implementation phase.” This finding triggers that instruction before Stage 1 completion. Fresh full runtime eligibility and collateral inventories were not performed after the finding; the earlier P1.8C ELIGIBLE result is historical evidence only and is not treated as fresh authorization readiness.

## Retained state

The exact selected receipt was loaded and its fingerprint validated against the required value. The selected backup directory still contains exactly the three regular, non-symlink role files:

| Role | Bytes |
| --- | ---: |
| provider | 968331264 |
| canonical | 749371392 |
| analysis | 909815808 |
| **Total** | **2627518464** |

Deleted: **0 files / 0 bytes**. Remaining: **3 files / 2,627,518,464 bytes**. No selected `backup_cleanup.json` exists. These presence/size checks do not replace the full hash/integrity/lineage revalidation required before any future authorization request.

Production/runtime mutations by this attempt: **none**. Source changes: **none**. No pytest or full suite was run. Only this acceptance documentation was updated; all earlier blocked attempts below are preserved.

## Required separate implementation phase

Add receipt identity propagation and receipt-fingerprint binding to the existing publication-drain cleanup audit, preserving normal Admin behavior and the existing deletion boundary. Test the persisted exact binding and rejection of receipt identity changes before deletion. Do not delete real backups during that implementation phase.

Then restart P1.8D Stage 1 with fresh current-state, lineage, exact backup and collateral inventories; ask the specified explicit YES/NO authorization question only after all gates pass. Previous YES responses and the earlier ELIGIBLE result must not be reused.

---

## Earlier P1.8B and P1.8 blocked attempts — preserved history

# P1.8B — Acceptance blocked after normal Production advancement

Selected run: `publication_drain_20261009T175136Z_e99387cf`. Fresh eligibility: **NOT_ELIGIBLE**. Acceptance result: **FAIL / STOPPED before cleanup**. The exact failed gate is **`PUBLICATION_DRAIN_JOURNAL_RUN_MISMATCH`**. No acceptance action was invoked, no audit state was recorded and **all three selected backups remain intact**. P1.7 publication remains a successful completed run; this rejection concerns cleanup eligibility under the current journal-binding contract.

## Fresh current baseline and failed gate

Checked at `2026-10-10T09:14:05.791245+03:00` (Europe/Helsinki). HEAD: `7416beb5e86a8f23d97a0efca4436ed88bf8e71f`. The worktree’s modified runtime journal, untracked active-generation files and unrelated PE research script/PNG were preserved and excluded from this documentation commit.

Current active generation before and after this task: `refresh_20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc`. Active manifest fingerprint: `5758df86d14ce0c4bfe9db1aa649534e2e3fc72f0650bdcda9e4f7e1ba05a366`.

The canonical journal now belongs to normal refresh `20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc`, rather than the selected P1.7 publication drain. It is `COMPLETED`, activation `ACTIVATED_AND_VERIFIED`, postflight `PASSED`, rollback/recovery `NOT_REQUIRED`. The updated default `inspect_cleanup_eligibility(selected_run)` returned `NOT_ELIGIBLE / PUBLICATION_DRAIN_JOURNAL_RUN_MISMATCH`. Its zero `backup_count`/`bytes_freed` fields are rejection defaults; the verified actual inventory below remains three files.

P1.8A explicitly requires the canonical journal to identify the selected run and the active manifest to agree with that publication generation. Its previous read-only ELIGIBLE result was not reused. This task did not modify the adapter, substitute a historical journal, rewrite a result, roll back Production or invoke `accept_run_and_cleanup_backups`. The stop is required by P1.8B and the current acceptance contract.

Current provider watermark: `2026-10-09`; latest successful normal refresh `20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc`, completed `2026-10-10T04:31:12Z`. Current authority census: VERIFIED 12,979; UNRESOLVED 770; NOT_FOUND 1,870; AMBIGUOUS 628. These are the fresh baseline after normal Production advancement, not changes caused by this task.

Selected P1.7 operation report remains `status=SUCCESS`, `journal_state=COMPLETED`, rollback NOT_REQUIRED, with its successful role postflight and published generation recorded. The preserved P1.7 execution report records postflight PASSED, activation ACTIVATED_AND_VERIFIED and recovery NOT_REQUIRED. These historical facts do not replace the required current canonical-journal match. Operation report SHA-256: `afd87308c73ed29262f6debdde90ddc092d889ab1382fe04997495b8326125d1`.

## Exact selected backup inventory

| Role | Exact path | Bytes | Verified SHA-256 |
|---|---|---:|---|
| analysis | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/analysis.db` | 909815808 | `9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c` |
| canonical | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/canonical.db` | 749371392 | `996deb198513b94e22888dbbb11b8139698b68cf98201a5df4d9bb8cd30a1845` |
| provider | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/provider.db` | 968331264 | `fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981` |

All three files are regular, nonsymlink files and the selected directory has no unexpected contents. Recorded source paths bind them to the OLD P1.7 generation; SHA-256 and size match the selected operation’s role records. All three SQLite quick checks return `ok`, with zero foreign-key errors.

Before: **3 files / 2,627,518,464 bytes**. Deleted: **0 files / 0 bytes**. Remaining: **3 files / 2,627,518,464 bytes**. Selected directory remains intact. Cleanup audit `backup_cleanup.json`: **NOT_CREATED**.

## Post-attempt invariants

Fresh before/after hashes and sizes match for active provider/canonical/analysis DBs, pointer, terminal journal, Review Queue and its existing WAL/SHM, scheduler configurations, operation report, proposal, approval, handoff and semantic support, immutable plan, execution authorization and P1.7/P1.8A evidence. Canonical byte identity proves unchanged financial contents, publication authority and authority census; provider byte identity proves unchanged watermark. Queue state was recorded read-only and its files remain byte-identical.

Compact path/size/mtime/inode inventories restricted to backup and generation roots match exactly before and after. Other backup directories changed: **0**. Immutable generations deleted: **0**. The OLD P1.7 and published P1.7 generations, current active generation and all audit artifacts remain present. No unrelated runtime artifact was deleted.

| Active/protected artifact | SHA-256 before and after |
|---|---|
| `/home/kalle/projects/rawcandle/data/fundamentals_generations/refresh_20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc/fundamentals_provider.db` | `aed20dab5493fae71db086e163710bb3cd8c694d84b1713f32338cb7e2ef79d9` |
| `/home/kalle/projects/rawcandle/data/fundamentals_generations/refresh_20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc/fundamentals_v4.db` | `ca339cfd927c645116614610ed65f4d24edd2b5d0d0458ffb64ca728b22210b4` |
| `/home/kalle/projects/rawcandle/data/fundamentals_generations/refresh_20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc/fundamentals_analysis.db` | `0acdbc93f46c070e49a32b15db7a0506db966a27e9740708d6089ca9b9d715c6` |
| `/home/kalle/projects/rawcandle/data/fundamentals_active_generation.json` | `a70eed876a80bd48ba0702a4654e3ec4596a34ba542db2b562d2b2ce06340138` |
| `/home/kalle/projects/rawcandle/data/.fundamentals_admin_publication_journal.json` | `fc960171c2d30b2c358903b811a9c596d81c5c84c30efa1f554c151cbc37f5ce` |
| `/home/kalle/projects/rawcandle/fundamental_reports/fundamentals_refresh_review_queue.db` | `84c18a698ef541a355950c91805ba0e949c9dd4d1a1d4d7d991a7bebc5d3e15b` |
| `/home/kalle/projects/rawcandle/scheduler_config.json` | `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894` |
| `/home/kalle/projects/rawcandle/forecast_scheduler_config.json` | `67e55b992b6144306b8b96a23157d4879490256c3af1d267f3852da5f1587e79` |

Acceptance mechanism inspected: the updated default `run_acceptance_cleanup.inspect_cleanup_eligibility`; its existing locked `accept_run_and_cleanup_backups` action was **NOT CALLED** because eligibility failed. Journal changed: NO. Source changed: NO. Pytest/full suite: NOT RUN. Nothing was pushed.

Historical publication-run acceptance after a newer canonical journal requires separately designed durable terminal/recovery lineage evidence. That implementation is outside this runtime task. All selected backups must remain retained until an established contract can safely prove eligibility.

---

## Earlier P1.8 blocked attempt — preserved history

The following is the earlier P1.8 record, before P1.8A added publication-drain support. Its dated baseline and schema rejection are historical; the current P1.8B result is the journal-binding rejection above.

Selected run: `publication_drain_20261009T175136Z_e99387cf`. Acceptance result: **FAIL / NOT_ELIGIBLE**. **No backup was deleted and no acceptance state was recorded.** The existing contract does not support this publication-drain report shape; P1.8 requires stopping rather than manually deleting backups or changing source.

## Existing mechanism and failed gate

Inspected `FundamentalsAdminUIService.accept_run_and_cleanup_backups` and its existing `run_acceptance_cleanup.inspect_cleanup_eligibility` / `accept_run_and_cleanup_backups` implementation. No cleanup/delete function was called. The read-only eligibility checks returned:

- Default Admin UI run root (`fundamental_reports/admin_runs`): `NOT_ELIGIBLE`, reason `CLEANUP_RUN_DIRECTORY_INVALID`; this selected operation is stored under `fundamental_reports/publication_drains`.
- Explicit selected publication-drain report root, with current active role paths: `NOT_ELIGIBLE`, reason **`Run is not a Production update`**. The required `mode=PRODUCTION_APPLY` field is absent.

The publication-drain result uses `apply=true`, `status=SUCCESS`, `journal_state=COMPLETED`; the acceptance implementation requires `mode=PRODUCTION_APPLY`, `outcome=COMPLETED` and publication/postflight evidence in its expected result schema. It also obtains immutable-generation source ownership from an embedded `journal`, which this report does not contain. These are contract integration gaps, not a failed P1.7 publication. No report was rewritten or wrapped to bypass the gate. The inspector’s zero backup count on rejection is not an inventory count; the actual inventory below remains three files.

## Current and selected-run state

Inspected HEAD: `13de79ae0d51d9e5e4991e33ec4ba26ae55cd6b0`; checked at `2026-10-09T19:22:07.561032+00:00`. Current active generation before and after: `publication_drain_20261009T175136Z_e99387cf`. Manifest fingerprint: `ff44c14a9d2a3834bd1bc0b6e2e4da86870b58839279ced82eced69447c13d1a`. Production had not advanced past P1.7; no historical-active-generation exception was needed or invented.

Selected run terminal evidence: `COMPLETED`; postflight: `PASSED`; activation: `ACTIVATED_AND_VERIFIED`; rollback/recovery: `NOT_REQUIRED`. The current terminal journal belongs to this selected run and agrees with the successful operation result and published generation. All three active DB and backup SQLite quick checks passed with zero foreign-key errors. Selected published role hashes match the operation postflight. Backup ownership is explicitly bound by each recorded role/source/path/hash/size to the OLD generation; exact inventory contains only the three expected files, with no symlinks or unexpected entries.

OLD generation retained: `/home/kalle/projects/rawcandle/data/fundamentals_generations/refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`. Published P1.7 generation retained: `/home/kalle/projects/rawcandle/data/fundamentals_generations/publication_drain_20261009T175136Z_e99387cf`. Neither generation nor the active pointer was modified.

Provider watermark: `2026-10-08`; latest successful normal refresh: `20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`, completed `2026-10-09T04:27:27Z`. Watermark unchanged.

## Exact retained backup allowlist

| Role | Exact path | Bytes | Verified SHA-256 |
|---|---|---:|---|
| analysis | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/analysis.db` | 909815808 | `9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c` |
| canonical | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/canonical.db` | 749371392 | `996deb198513b94e22888dbbb11b8139698b68cf98201a5df4d9bb8cd30a1845` |
| provider | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/publication_drain_20261009T175136Z_e99387cf/provider.db` | 968331264 | `fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981` |

Before: **3 files / 2,627,518,464 bytes**. Deleted: **0 files / 0 bytes**. Remaining: **3 files / 2,627,518,464 bytes**. The selected directory remains intact. Backup hashes match recorded P1.7 evidence.

## Protected-state verification

Before/after hashes and sizes match for active provider/canonical/analysis roles, active manifest, terminal journal, Review Queue (including existing WAL/SHM), scheduler configurations, operation result, proposal, approval, durable handoff and semantic reference, immutable plan, execution authorization receipt and P1.7 report/result CSV. Canonical byte identity proves publication authority and financial state unchanged. Recursive filesystem metadata inventories restricted to the backup and immutable-generation roots match before/after; no other backup directory, generation or unrelated runtime artifact was deleted.

| Active/protected core artifact | SHA-256 before and after |
|---|---|
| `/home/kalle/projects/rawcandle/data/fundamentals_generations/publication_drain_20261009T175136Z_e99387cf/fundamentals_provider.db` | `fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981` |
| `/home/kalle/projects/rawcandle/data/fundamentals_generations/publication_drain_20261009T175136Z_e99387cf/fundamentals_v4.db` | `a67c996aadfaa7e600b88d6d9e31804bb30a784b182ff37ae23c8756ff949c34` |
| `/home/kalle/projects/rawcandle/data/fundamentals_generations/publication_drain_20261009T175136Z_e99387cf/fundamentals_analysis.db` | `9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c` |
| `/home/kalle/projects/rawcandle/data/fundamentals_active_generation.json` | `73cdace134b7d33069cf5b7f1e7dfe283ae5348a2b52742297102838eb1253aa` |
| `/home/kalle/projects/rawcandle/data/.fundamentals_admin_publication_journal.json` | `a45cf8349978c76cd1f5e1cb82b24e13e008f463a48d865d5ee2484beba4a3f8` |
| `/home/kalle/projects/rawcandle/fundamental_reports/fundamentals_refresh_review_queue.db` | `84c18a698ef541a355950c91805ba0e949c9dd4d1a1d4d7d991a7bebc5d3e15b` |
| `/home/kalle/projects/rawcandle/scheduler_config.json` | `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894` |
| `/home/kalle/projects/rawcandle/forecast_scheduler_config.json` | `67e55b992b6144306b8b96a23157d4879490256c3af1d267f3852da5f1587e79` |
| `/home/kalle/projects/rawcandle/fundamental_reports/publication_drains/publication_drain_20261009T175136Z_e99387cf/result.json` | `afd87308c73ed29262f6debdde90ddc092d889ab1382fe04997495b8326125d1` |

[Existing operation report](/home/kalle/projects/rawcandle/fundamental_reports/publication_drains/publication_drain_20261009T175136Z_e99387cf/result.json) remains available and byte-identical. P1.7 audit artifacts and its publication operation record are preserved. No Admin Run History record for this selected ID exists under the default Admin root; this task did not create, hide or remove one. Runtime acceptance evidence `backup_cleanup.json` was not created because eligibility failed.

Full test suite: **NOT RUN**. Pytest: **NOT RUN**. Source changes: **NONE**. Only read-only runtime validation and the requested acceptance document were produced.

## Required follow-up

A separate implementation phase is needed to integrate publication-drain run discovery and its successful generation/journal evidence with the existing Admin acceptance contract, including tested exact backup ownership, clean-journal and integrity gates. This runtime task does not implement that adapter, normalize historical run evidence, weaken gates or manually remove files. Retry the existing acceptance action only after that integration is implemented and reviewed.

Acceptance remains blocked; all three rollback backups are intact. Nothing was pushed.
