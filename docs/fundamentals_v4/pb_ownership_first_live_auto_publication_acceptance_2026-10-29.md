# First enabled live P/B ownership publication — acceptance, 2026-10-29

**Acceptance: PASSED. Workstream closure: READY.** The first real enabled Full Workflow automatically continued and published **TMUS** through the existing ownership lifecycle. Its current queue state is PUBLISHED; native postflight passed, recovery is NOT_REQUIRED and cleanup completed. A fresh read-only detector/evaluator found zero current cases and no repeat of the accepted binding. No source change, new workflow/publication, approval, queue synchronization, recovery or cleanup action was performed by this audit.

Scope: **PB_ORDINARY_AUTO_CONTINUATION_V1**, [future-reconciliation implementation](pb_ownership_future_auto_reconciliation_2026-10-29.md) (`b5a20b642ff7867f09121efe0c2ccf02017f42e3`) and [safe-no-changes integration fix](pb_ownership_safe_no_changes_integration_fix_2026-10-29.md) (`09ad246ce3d5335c06a164a86bd4864313a86043`, report commit `038a38c682234ecc0946435cedaf2d27b8a17c73`). Audit completed **2026-10-29 14:56:43 Europe/Helsinki / 12:56:43 UTC**. All conclusions below come from freshly inspected authoritative JSON, database contents, generation manifests and native receipts, rather than counts or the earlier likely-ticker observation.

## Exact live run and lifecycle binding

Exactly one retained manual Full Workflow matched STOPPED / NO_SAFE_CHANGES, SAFE_FINANCIAL_NO_OP and evaluated/automatic/published counts 1/1/1:

- Full Workflow: **`20261029T123240Z_refresh_fundamentals_d00eb7239fed_full_workflow_0e892e90`**.
- Financial child Preview: `20261029T123240Z_refresh_fundamentals_62a26be6b398`. Financial Preview finished at **14:34:57 Helsinki**. Safe financial changes 0, global blockers 0, FDX/RRC local quarantines; financial Production not entered, financial production database writes 0. Financial STOPPED / NO_SAFE_CHANGES / NO_SAFE_CHANGES_TO_PUBLISH remained intact.
- Ownership precondition: **SAFE_FINANCIAL_NO_OP**. Independent ownership result: COMPLETED; evaluated 1, automatic 1, published 1, manual 0, deep 0, failed/stale 0.
- Ownership automatic decision: **14:37:25 Helsinki**. Native postflight/publication completion: **14:38:48 Helsinki**. Native cleanup completion: **14:39:20 Helsinki**. These are the independent ownership timestamps; the parent's financial completion timestamp is not used as the ownership completion time.
- Test-copy publication: `pb_ownership_55e6db6d7e774fd4806c38e644c68f8d`.
- Actual live ownership publication and NEW active generation: **`pb_ownership_719201a6f6f4497bb6a3e1ada35b81b6`**.
- Exact OLD generation: **`pb_ownership_6afe669f1166421bbd0e20f66fff3d07`**.

Let `W` be `fundamental_reports/admin_runs/20261029T123240Z_refresh_fundamentals_d00eb7239fed_full_workflow_0e892e90`, and `P` be `fundamental_reports/admin_runs/pb_ownership_publications/pb_ownership_719201a6f6f4497bb6a3e1ada35b81b6`.

| Authoritative artifact | SHA-256 |
| --- | --- |
| `W/workflow_result.json` | `82e603f40fab20118c360c05bf958c6a4e63aeb5d7b2388258e86b114dd8aa85` |
| `W/ownership_auto/preview.json` | `1730fb05ac9809ecea193ce17af7f4f6f596bbd18a1b54dda5e2297527336903` |
| `W/ownership_auto/test/test_receipt.json` | `93418d3c9b7555bc87d4c2b0f1449a0656529e2f5695890881b120bc10e4c55d` |
| `P/preview.json` | `c8dc4024b81f06a9d78fb9c8a2ba3fa56ed53d2e5a7d8c91095dc95f77f2664a` |
| `P/completed_journal.json` | `c5ee3175638d781cb28af0cb9e7f4e1f559f23e940b4abc7ea59639738e55526` |
| `P/backup_cleanup.json` | `f23f0dc281eb21c24976804b0321f6e2bc7d0f0026141c964866b47edf4ec11c` |

The future Preview and Test fingerprints, exact source object, selected case and full V1 decision match. The copied native Test's journal is terminal/PASSED/NOT_REQUIRED; its current published role hashes match the Test receipt's candidates. Its native Preview contains the same exact case and policy decision as live Production. Test and live approval timestamps/record hashes naturally differ; the tested decision/source/selection is identical, and the actual live approval/record is separately pinned by the native Production Preview and durable journal. Test-copy generation identity is not confused with the live generation.

## Published automatic case

The actual selected ticker is **TMUS**, established independently from Preview case/source metadata, Test selection, native Production selection, queue/history and the active canonical artifact.

| Identity/evidence | Exact value |
| --- | --- |
| Case ID | `b9c5df399be8ccbba7733c6d5d8de803cbb4b0423a033f9323ac3893b827eb01` |
| Accepted source observation | `5c3509b1da2c47dcb5601ac1e534b8009ab20dbb1767b7650fb8e0dbf4ffdc86` |
| Source content hash | `4a7accb5bf72d7a6519a406f76c6b1d52fc265f6a1087e7ea2921cb91dac4cb1` |
| Candidate hash | `b43fe8b8250a7e958a198b57be0a0a1877686bf1c367e08642add0ce8decafb5` |
| Complete approval hash | `b6d67ebc0f1a0d0ce360eeaaa82f98d611beb6330729ddd494aeb54a0d30688a` |
| V1 decision/evidence fingerprint | `084d21fdd4fe670134fcff369e8ec7fe5b49be0865838c332082033c26763c29` |
| Published ownership record hash | `66b815a066be960a2e6a9df22f1930d89a9eaaabc0441476b4d8fab6a0a99dbf` |
| Published registry artifact SHA-256 | `2cb37e131cc8e46a8f311bb13d244164137841b18d580294114af292acda2e4c` |

Decision type/approval mode: **AUTO_CONTINUED**. Policy: **PB_ORDINARY_AUTO_CONTINUATION_V1**. Approval has no operator or note, and the published record has no fabricated operator/operator_note. `SYSTEM:MANUAL` identifies the automated publishing action, not a human ownership approval. Prior interpretation was REVIEWED_SUPPORTED / ORDINARY_COMMON / OPERATOR_CONFIRMED for 2026-Q2, reviewed 2026-10-07. The before-decision ownership-table fingerprint matches the retained historical baseline where this case was OPEN. The new decision binds the accepted 2026-Q3 source, preserving that reviewed unit interpretation.

The original inactive approval candidate and exported registry still exist under `fundamental_reports/admin_runs/pb_ownership_candidates/<case ID>/2cb37e131cc8e46a8f311bb13d244164137841b18d580294114af292acda2e4c/`. Their embedded/exported artifact matches the pinned registry and published record. Inactive `canonical.db` file SHA-256: `f33921082540495cb07d9b259921fedc368867ef0b829b6202e2c06ed8b44d95`. This candidate is retained evidence, not the active publication role.

Live queue state is **PUBLISHED**, retaining the exact automatic approval and journal-bound publication metadata. Audit event **87** is the only AUTO_CONTINUED event for this case; event **88** is its only PUBLISHED event. Exactly one top-level live native completed publication receipt selects this case. The source observation's complete payload still matches V1 completeness evidence. Current P/B is **2.785747495928854**, status OK / AUTO_CONTINUED_QUARTER. At 50-digit Decimal precision, price 148.0800018310547 × accepted shares 1,059,272,571 / parent equity USD 56,307,000,000 reconstructs `2.7857474959288546665713623528158133091800309020193`. Normal V1 quarterly-share approximation and incomplete-action-coverage warnings remain applicable.

## Immutable publication, postflight and cleanup

The active manifest exactly equals the journal's prepared NEW manifest. Every active role hash equals both native Preview candidate hashes and journal candidate fingerprints. The journal records GENERATION_POINTER activation, ACTIVATED_AND_VERIFIED, terminal **COMPLETED**, postflight **PASSED**, recovery **NOT_REQUIRED**. Current journal and archived completed journal are identical. No preparing generation or nonterminal active publication journal exists. OLD generation files are retained and still match the verified OLD/backup hashes.

| Role | OLD SHA-256 | NEW SHA-256 |
| --- | --- | --- |
| Provider | `0f23acbd064d1859fa1d9f71996d1eb4979a9cdbac2db1d805a774d4215770f1` | Same |
| Canonical | `7568f70b89441b46bb97879cc534394e91c5dc250c3f10b0a43a31e8a9530273` | `84987b23f13e8d42801b9a0304fe35adb9e4c198a2c78adc7bcaafefbbd8208e` |
| Analysis | `b1fef5fd8eb651e0337c9f6128b1e068df2999873da158c653b45fff42223327` | Same |

The embedded ownership registry changed from **72 to 73 records**, exactly `merge_artifact(OLD, [the selected live TMUS record])`. Every prior record is unchanged. Independently recomputed canonical schema/table digests outside the two native ownership tables match OLD, NEW and the native Preview's financial invariant. This includes financial rows/provenance, publication authority and WFRD accounting-boundary state. Provider and analysis are byte-identical.

Cleanup is already **COMPLETED** and was not rerun. Its preview hash and completed-journal identity bind exactly this publication. Its deletion set is precisely the journal-owned `analysis.db`, `canonical.db` and `provider.db` under `backups/fundamentals_admin_production/pb_ownership_719201a6f6f4497bb6a3e1ada35b81b6/`: **3 files, 2,630,086,656 bytes freed**. Pre-deletion verified hashes, sizes, quick checks and foreign-key checks match the retained OLD immutable roles. The three files and now-empty owned directory are absent. All **53 unrelated backup files** still exactly match the earlier retained inventory, including paths, sizes, inodes, nanosecond mtime/ctime and symlink status. No unrelated backup deletion or metadata change was found.

Actual provider watermark remains **2026-10-28**. The native ownership journal's generic `new_source_watermark=2026-10-29` is populated from the ownership Preview's as-of date by the existing ownership transaction adapter; it does not update `sharadar_refresh_state`. Byte-identical provider roles and a direct current watermark read prove no financial source-watermark advancement.

## Terminal state, idempotency and collateral preservation

The fresh **read-only** `FutureOwnershipWorkflow.preview` computes the current detector/evaluator partition without calling queue synchronization or native publication Preview. Result: **evaluated 0 / AUTO_CONTINUE 0 / MANUAL_REVIEW 0 / DEEP_REVIEW/BLOCKED 0**. No case for the same accepted binding remains. No live decision was created to demonstrate idempotency.

- GE/RTX/T and AMT/BA/DHR/GM/PNR/PSA remain PUBLISHED with exact original case, approval, publication and historical evidence. The three superseded GE/RTX/T historical rows remain unchanged. No reopening, duplicate decision or republication occurred.
- Nonselected ownership rows and audit rows match the exact queue snapshot retained by this run's copied Test. All other review/source-repair tables match that snapshot. Source-repair decisions/history and WFRD state did not change.
- FDX/RRC remain OPEN and quarantined, with identical evidence, scope, reasons, review context and resolution fields. Compared with the pre-run baseline, the only changed columns are expected financial Preview bookkeeping: `last_seen_at_utc` advanced from 11:47:10Z to 12:34:57Z and `last_seen_run_id` changed to `20261029T123240Z_refresh_fundamentals_62a26be6b398`. These updates precede ownership and are already present in the copied Test's queue. They are not approvals or ownership-publication collateral changes.
- `pb_ownership_auto_continuation_enabled=true` remains unchanged. Configuration SHA-256 still is `10e7c91e357ffaaacf56785a0bec064a95eaf21a84eb5592642be79fef1dab2b`. Market/taxonomy main/WAL inputs and installed policy/source code match the publication's exact bound sources.

Read-only audit preflight used existing kernel locks without recovery, owner rewriting or queue mutation. Before/after role, manifest, journal, input, queue-content, configuration and backup-inventory snapshots match exactly. Only this report and excluded temporary audit evidence were written. No pytest or full suite was run because source was unchanged; acceptance used **36 direct read-only consistency/invariance checks** plus the bound native Test/publication/postflight/cleanup evidence.

## UI operability finding and closure

**UI acceptance visibility: PARTIAL.** Review Queue's **Include resolved** view exposes the ticker and PUBLISHED status. Full Workflow shows ownership policy/precondition, status/counts and Preview/Test artifact paths. The live ticker, live generation and terminal postflight/recovery/cleanup details exist in authoritative JSON/native receipts, but are not presented together in the Full Workflow ownership summary; the manual publication dialog's generation display is not the unattended Full Workflow acceptance view. The smallest useful later improvement is one compact ownership-result line with ticker, AUTO_CONTINUED → PUBLISHED, live generation and cleanup result, linked to the native completed journal/cleanup receipt. No UI implementation is included here.

**The future P/B ownership auto-continuation workstream can now be closed: READY.** The first normal live run independently demonstrated the enabled V1 decision, safe financial no-op sequencing, immutable controlled ownership publication, native cleanup and terminal/idempotent state with all required collateral invariants intact. Remaining UI visibility is a separate small UX improvement, not a publication-correctness blocker. No source defect requiring another implementation phase was found. No extra live run or cleanup is needed for acceptance.

Excluded runtime evidence: `temp/pb_first_live_acceptance_20261029/{before.json,after.json,fresh_readonly_preview.json,result.json}`. Result SHA-256: `abdaf5ccbcb68578aa4ee19f2946104a921e73487bb80f6b26fd57c879926323`; fresh readonly Preview SHA-256: `81f9e43a2aad34269ef48515572d1099776578e417f59906f254863abab2bc5c`. Only this documentation file belongs to the acceptance commit; DBs, queue, journals, generation files, backups, copied projects, logs and unrelated OHLCV/research files remain excluded. No push.
