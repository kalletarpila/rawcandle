# Fundamentals Full Workflow parent-evidence performance fix — 2026-11-11

## Scope and result

This is an infrastructure change, with isolated native financial acceptance and a file-backed performance benchmark. No live financial workflow, publication, review action or recovery was performed. The pending baseline-integrity implementation remains undeployed. Recovery correction `9ed344e3` is retained without modification.

The starting checkout was `a9e314f2dad990101e7b830f9530db9eede9b5cb`. The previous stopped baseline-integrity report was already untracked and is excluded from this task's implementation commit, along with its archived patch and generated/runtime state.

## Verified cause and handoff trace

The earlier receipt records **1,048,639,647 bytes in each** of the parent `workflow_result.json` and `result.json` files. Approximately 2.1 GB was the aggregate rewrite per event, rather than one parent file's size. Its Test Preview-binding event was timestamped 13:31:56Z and reached the outer callback at 13:34:45.076873Z, a 169.076873-second interval.

The exact causal chain in the starting code was:

1. `full_workflow.run_operation_workflow` calls `_load_result` after each child adapter returns. That function fully reads and decodes native child `result.json`.
2. `stage_decision` attaches the child's operational decision to the parent. The decision includes complete `held_items`, with nested review/change/source evidence, rather than just counts or references.
3. `child_progress` forwards native events to `emit`. `emit` synchronously calls `persist` before invoking the outer callback.
4. `persist` passes the same accumulated parent result to `AdminRunWriter.write_json` twice: once for `workflow_result.json`, once for `result.json`.
5. Each call independently runs recursive redaction (`_safe`), `json.dumps`, and the existing atomic write/flush/fsync/replace helper. The whole evidence tree is traversed and encoded twice, including on forwarded stage/heartbeat events.
6. The next financial stage still loads and validates its native Preview receipt. The parent's decoded copy does not replace or help that binding operation.

There were additional avoidable child-result decodes: `FundamentalsAdminUIService._finalize` regenerated a native operation report through `write_operation_report`, even when a durable report already existed; report creation from `AdminRunWriter.write_manifest` also reread a result that the child already owned in memory.

The historical 169-second callback interval encompasses the synchronous progress append/persistence path. JSON decoding for the bound Preview occurs after that initial binding progress callback returns. Historical subcomponent timings were not retained, so this report does not attribute all 169 seconds specifically to JSON encoding, filesystem writing, or fsync. The disposable benchmark separately instruments redaction, JSON serialization, and atomic file writing on the actual parent persistence path. It confirms repeated whole-parent processing, with redaction dominant in the old synthetic case.

Test revalidation does **not** forward a per-ticker callback for every source row. No multi-day runtime estimate based on thousands of such callbacks is used.

## New control-state and child-artifact contract

New parent results declare `FUNDAMENTALS_WORKFLOW_REFERENCES_V1`. They contain stage/control status, timestamps, ordered event sequence, exact totals, compact failure/review samples, retry/completion information and verified references. Presentation samples contain at most 24 items; counts are computed over the complete native child data. Long review descriptions cannot remove the boolean classification fields or change STOP totals. Reports explicitly identify truncated item samples and retain native detail links.

Large provider histories, ticker changes, review context and candidate diagnostics remain in the native child files. The parent no longer deserializes those result files to record completion or carry them into the next stage.

`workflow_evidence.py` defines fixed artifact kinds and canonical names:

| Kind | Native location inside the exact child run |
| --- | --- |
| RESULT | `result.json` |
| SUMMARY | `workflow_child_summary.json` |
| PREVIEW / Refresh | `refresh_preview.json` |
| PREVIEW / Add Tickers | `phase13d_preview_payload.json` |
| PREVIEW / Remove Tickers | `remove_tickers_preview.json` |
| REPORT | `operation_report.md` |
| NOOP_SCOPE | `workflow_noop_scope.json`, when required |

References bind child ID, kind, operation, canonical relative path, byte size, SHA-256, and applicable semantic fingerprint/completion outcome. They cannot supply arbitrary filesystem paths or substitute one artifact type for another. Symlinked children/artifacts, path traversal, missing artifacts and identity mismatches fail closed.

The child writes its bounded summary only after the original result is durable. Its existing artifact manifest binds RESULT, SUMMARY and completion STATUS bytes and sizes. The parent verifies these receipts, native child ID/mode/outcome, completion status and exact Preview path/fingerprint before progressing. RESULT/PREVIEW/SUMMARY references are rechecked at the relevant Test/Production handoffs. Missing summaries declared by a modern manifest cannot silently downgrade to legacy loading.

Normal summary/history reads consume small metadata and manifest/size checks; they do not hash or deserialize multi-gigabyte child results. Authorization handoffs perform full file hashing. Explicit detailed evidence remains available in the original child files and reports, and can be verified with `verify_reference` against the recorded kind/run ID/hash. A large child report is linked instead of copied wholesale into the parent appendix.

`AdminRunWriter` computes child presentation aggregates while the native child already has its full result. Its report writer can reuse that same in-memory result rather than decoding another copy; the temporary reference is released after manifest creation. The UI reuses existing native reports instead of regenerating them during child-to-parent handoff.

## Financial and P/B authority

The native Test still receives the original Preview path and semantic fingerprint, and still performs `PREVIEW_BINDING` and source revalidation. Production still receives the original Preview identity and exact Test run ID and performs its native revalidation/publication/postflight. Provider/canonical calculations, safe/held/global partition proof, review approvals, replacement authorization, immutable generation, journal, rollback and recovery implementations were not changed.

A parent display sample is not a new financial or ownership receipt. The existing P/B safe-no-op precondition explicitly checks the complete held/problem lists. For that case, the native child writes a minimal, complete scope sidecar pinned to its exact RESULT. At the explicit ownership eligibility boundary, `ownership_eligibility_view` verifies the references and supplies the full scope to the **unchanged** `financial_result_allows_ownership_reconciliation` predicate. It never reconstructs scope from display samples. Corruption/missing scope is ineligible. Small legacy adapters use their exact verified original result at this boundary without modifying their files. Ordinary ownership policy and its independent active-generation/journal/source checks remain unchanged. Coverage includes zero, one and 75 local holds, including tampered scope rejection.

## Progress and interruption safety

The existing `progress_status.json`, progress events and heartbeat files remain in use. A parent event writes compact snapshots and ordered append-only events. An RLock serializes concurrent forwarded events; sequence numbers make their ordering explicit. `workflow_result.json` is the parent control snapshot; `result.json` remains its small compatibility mirror for existing readers. There is no parallel workflow engine or new database.

The existing same-filesystem temporary write, flush/fsync and atomic replacement contract is retained. A partial snapshot is never exposed as complete. A stage completion is recorded only after the native child returns and its completed evidence is verified. Parent COMPLETED requires a verified successful final child.

Keyboard interruption records STOPPED/INTERRUPTED, retaining completed child evidence. Abrupt interruption preserves the last durable state; it does not manufacture Test/Production receipts. Progress-file incompleteness does not trigger financial recovery. Native journal recovery remains the separate authority, including OLD restoration and fresh `RETRY_REQUIRED` behavior.

## Legacy compatibility and UI

Historical files are not rewritten or migrated. Small legacy JSON remains readable directly. Large native legacy pretty-printed JSON is projected with fixed-size line fragments and bounded retained metadata; full historical financial trees are not materialized. Details continue through native report/artifact access. Large non-native/custom JSON layouts without a supported summary are rejected rather than guessed as authorization evidence.

Existing 8/16/24 newest-first lazy history pagination, scheduler/manual grouping, action-first review presentation, STOP/error distinctions, report download links, cleanup delegation and scheduler completion reporting are covered by focused regressions. This task does not apply the pending preserved-history hiding/N/M/CSV patch or redesign the UI.

An actual read-only scan of the current runtime history returned the newest eight rows with the original mode/outcome/counts. It took 85.624 seconds and raised process maximum RSS from 46,912 to 49,984 KiB. Legacy streaming scans therefore remain slow on first access, while avoiding the previous enormous decoded objects. Historical interrupted RUNNING records remain unmodified; this is not a claim that the paused baseline-integrity workflow completed. The runtime manifest, journal and queue hashes were unchanged by this read.

## Synthetic performance acceptance

Reproduce with:

```bash
PYTHONPATH=. PYTHONDONTWRITEBYTECODE=1 venv/bin/python tests/fundamentals_parent_evidence_benchmark.py
```

The benchmark pins the old orchestration source at `a9e314f2dad990101e7b830f9530db9eede9b5cb`, instruments the real `run_refresh_full_workflow` parent persistence, and runs the current orchestration with generated native-style child artifacts. The 2 GiB body is streamed to a file in 64 KiB chunks; no multi-gigabyte Python dictionary is allocated. Financial end-to-end correctness is covered separately by native database fixtures.

| Case | Child bytes | Updates | Largest control during updates (B) | Total snapshot bytes/event (B) | Median event (s) | Preview-return to Test-entry (s) | Traced allocation peak (B) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| legacy_16mib | 16,778,599 | 3 | 16,779,948 | 33,560,210.00 | 1.069925 | 2.195811 | 50,452,113 |
| compact_64kib | 66,919 | 100 | 4,537 | 9,405.98 | 0.020022 | 0.045891 | 1,380,614 |
| compact_2gib | 2,147,485,031 | 100 | 4,539 | 9,409.98 | 0.029570 | 1.310560 | 2,346,539 |

The event-byte measure sums both compatibility snapshots and the small progress snapshot. Final compact parent results are approximately 13 KiB, with a 340-byte progress snapshot. The small and 2 GiB cases differ by only four bytes/event in the measured run. There were zero reads of the large child during progress updates or normal UI/history reads. Child evidence was not rewritten by those updates.

The old 16 MiB case spent approximately 2.881 seconds redacting, 0.156 seconds serializing JSON and 0.135 seconds in atomic writing across three progress events. The new 2 GiB case spent approximately 0.209, 0.051 and 1.470 seconds respectively across 100 events. These are instrumented synthetic totals under tracemalloc, not a decomposition of the historical live delay.

Hash verification at stage boundaries remains proportional to child file size; stage transitions are not claimed to be constant time. Native Test still loads its original bound Preview once, and native child result generation still writes its authoritative evidence. No production-runtime speedup is claimed from this synthetic measurement.

## Targeted and disposable qualification

**534 distinct targeted cases PASS.** Overlapping batches are deduplicated; all selected receipts have zero failures/errors. The full repository suite was not run.

| Passing batch | Cases | Seconds |
| --- | ---: | ---: |
| `acceptance_final.xml` | 79 | 41.47 |
| `counts_fix.xml` | 14 | 10.32 |
| `final_native.xml` | 32 | 172.80 |
| `contracts.xml` | 251 | 216.68 |
| `ui_qualified.xml` | 103 | 100.38 |
| `scheduler_final.xml` | 79 | 20.74 |
| `other_qualified.xml` | 21 | 272.21 |

The selected native fixtures isolate provider/canonical/analysis, active manifests, journals, queues, market/taxonomy inputs and all run artifacts. They exercise the existing production path, including immutable generation activation, rather than a replacement workflow.

| Required scenario | Evidence |
| --- | --- |
| A — successful Preview → Test → Production → postflight | Native Refresh parity and actual isolated immutable-generation activation |
| B — safe peers plus ordinary local holds | Native YYAI and MRQ quarantine parity; held authority unchanged |
| C — true global STOP | Native global-review case stops before Test |
| D — missing/tampered child | Native generation fixtures reject altered/deleted Preview before Test; role hashes unchanged |
| E — interrupted atomic control write | Native completed Preview survives; previous parent JSON remains valid and cannot claim completion |
| F — post-boundary rollback | Native ordinary OLD-generation rollback with exact role/backup verification |
| G — crash recovery | Native immutable crash/activation-intent recovery restores OLD and requires fresh retry |

Development failures exposed metadata fields that the first projection needed to retain (including native rehearsal modes and review-hold completion), and a missing-report wording compatibility issue. These were corrected and affected suites rerun. Several older test fixtures lacked current provider capture attestation; declared synthetic full SF1 results now pass through the actual HTTP acquisition boundary. An unusable fiscal identity remains rejected by the existing BASE capture gate. Stale history-label and scheduler stub expectations were updated to the current action-first/public result contract. No product capture rule, financial approval or recovery logic was relaxed to make tests pass.

## Fresh runtime non-mutation evidence

The before/after audit acquires the existing UI operation, production and scheduler locks; it checks each active role against the active manifest and verifies the completed healthy journal. The starting watermark was `2026-10-28` and active generation `current_rebuild_2a684ef130c6a540de4adc560ab171ad`. The audit also hashes WFRD accounting-boundary and P/B queue records.

| Runtime file | Bytes | Before SHA-256 |
| --- | ---: | --- |
| `fundamentals_provider.db` | 968,331,264 | `14a032489577c079607e16986380076986ab8206ed1d96aa135700499432de4f` |
| `fundamentals_v4.db` | 749,371,392 | `2178d467a12a601e9554353fea8a3f8354444cb9347be000c3dca6c13b3e0a6d` |
| `fundamentals_analysis.db` | 912,351,232 | `6feb14748b4088096d96287d7f3b1c812faed4dc8e2352a81b390d8b86d11d8f` |
| `fundamentals_active_generation.json` | 1,387 | `82afaa462cc12ef41616c10d3ad011bac266b452cca02e6abea605c8d5b97097` |
| `.fundamentals_admin_publication_journal.json` | 589,170 | `91fadb71f55be7bad2107db8948744abb17a1a7494bfb3d64d78fe2d155c1e72` |
| `fundamentals_refresh_review_queue.db` | 882,065,408 | `913c454dcc93dafa706ab00c42f6a6f921f56cf93b17a59fb2c4187c61ef1355` |
| `scheduler_config.json` | 1,972 | `f4ba4fc0fde48e3ac82f5314353556ae35a0327a2e568b41abf9c759c35bb8a3` |
| `osakedata.db` | 2,038,648,832 | `7f9b347f90e4eb70f9439e50105d5d03e00fa37f6c1142280d04fa85fabb61c1` |
| `analysis.db` | 14,199,291,904 | `5e05b5a875d417a38c3a34e4f58dc8f6d4f609d5d77363d6b319c992fba54865` |

**Runtime audit PASS**, last full comparison at `2026-11-11T14:59:20.457788+00:00`. All nine protected files, generation identity, watermark, WFRD boundary records and P/B records match the starting audit exactly. Journal remains COMPLETED / PASSED / NOT_REQUIRED. Native locks were acquired for both checks. No concurrent runtime drift was observed and no runtime financial or review mutation was performed. Lock-owner text and temporary evidence are the only task maintenance state outside source/tests/docs.

## Remaining work and archived baseline rollout

The baseline-integrity rollout remains **undeployed and incomplete**. Its patch is `temp/fundamentals_baseline_integrity_hold_20261111/implementation.patch`, SHA-256 `d96975901b5dd818faaa4f52612b7300ff83d9d0f8664a745bc6a64286ede5cf`. This task neither reapplies it nor reuses its previous Preview/Test authorization.

For a later rollout: rebase the archived implementation over this infrastructure commit, retain the new child summary/reference/no-op scope contract, and reconcile overlapping Full Workflow/UI changes rather than overwriting them. Repeat current runtime/generation/recovery/source classification, baseline-specific targeted and disposable acceptance, and UI acceptance. Obtain the subsequent task's explicit live authorization and run a fresh native Preview/Test/revalidation/Production. Previous 1,170/408/171/0 counts are historical observations, not targets. Provenance repair remains a separate reviewed workstream.

This commit includes only performance infrastructure, directly relevant tests/benchmark code and this report. Runtime DBs, manifest/generations, journal, queue/audit, scheduler config, temporary benchmark data, archived baseline patch, backups, OHLCV/StockCore and other pre-existing worktree files are excluded. No push.

## Closing acceptance

Source, targeted regressions, native disposable A–G, large-evidence performance, legacy/UI/scheduler compatibility and runtime safety gates PASS. All accepted task-owned implementation/tests/documentation are included in the local performance-fix commit. The exact commit hash is reported in the final response; no push is performed. The pending baseline-integrity rollout remains undeployed.
