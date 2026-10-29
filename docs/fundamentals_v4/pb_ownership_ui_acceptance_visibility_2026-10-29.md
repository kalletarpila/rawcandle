# P/B ownership acceptance visibility — 2026-10-29

Task: **P/B-OWNERSHIP-UI-ACCEPTANCE-VISIBILITY**. Previous visibility: PARTIAL, as recorded in the [first live publication acceptance](pb_ownership_first_live_auto_publication_acceptance_2026-10-29.md), commit `77590f5fdbb5e39d83a45a053a808a73b0784707`. This change improves presentation only. PB_ORDINARY_AUTO_CONTINUATION_V1, eligibility, financial authorization, native publication/rollback/recovery, cleanup rules, source repair, WFRD, publication authority and P/B calculation remain unchanged.

## Change and authoritative sources

Previously, Markdown showed ownership counts and artifact paths without the final ticker/generation/cleanup details. The normal UI summary and history also returned early with financial operational-decision rows, omitting the ownership result.

One shared `pb_ownership_presentation.ownership_summary_rows` projection now supplies Full Workflow Markdown, the service's normal UI summary and Run history details. Existing Flet summary controls display these rows; no Review Queue/widget redesign or new actions were introduced. Preview/Test paths remain in the report, while the compact UI avoids full evidence blobs and fingerprints. Diagnostic SHA-256 values in failure reasons are replaced with a reference to detailed artifacts; original structured evidence is preserved.

| Displayed field | Structured source |
| --- | --- |
| Policy enabled/version, financial precondition/outcome/reason | Existing `ownership_auto` fields |
| Ownership status and six counts | Existing `status`, `evaluated`, `auto_continued`, `manual_review`, `deep_review`, `published`, `failed_stale` |
| Published ticker(s) | Successful native publication's `published_tickers`, taken from its validated selected cases |
| Decision type(s) | Successful native publication's `decision_types`, taken from selected approvals' `decision_type` or records' explicit `approval_mode` |
| Live generation, publication status, postflight | Existing native `publication.generation_id`, `outcome`, `postflight` |
| Queue state | Native success return's `queue_state=PUBLISHED`, after the existing queue transaction completes |
| Recovery | Native success return's `recovery`, copied from its already available journal's `rollback_recovery_state` |
| Cleanup status | Existing cleanup `cleanup_outcome`/`status`, with existing `cleanup_status` fallback |
| Deleted backup count / bytes | Existing `cleanup.files_deleted` length and `cleanup.bytes_freed`; unknown values are not invented |
| Preview/Test details | Existing `preview_path` and `test_receipt` |

The only publication-module change adds four small return fields after the existing successful lifecycle: `published_tickers`, `decision_types`, `queue_state`, `recovery`. The existing future workflow already forwards this publication dictionary into its normal result. No publication step, write, gate, exception handling, decision creation, recovery or cleanup behavior changed. No new database, persistence mechanism or evidence blob was added.

For historical results without those display fields, the projection reads only the run's retained **native live** Preview/completed-journal JSON. It checks publication/generation/case IDs, artifact identity, complete native Preview fingerprint and the cleanup receipt's journal fingerprint where recorded. Native fingerprints include run-local fields; the view uses the same exact JSON hashing convention. It does not read databases, use the copied Test's generation as the live generation, parse prose, rewrite historical results or fabricate missing facts. Missing/mismatched artifacts produce an explicit details-unavailable indication.

## Outcome semantics

- Financial STOPPED / SAFE_FINANCIAL_NO_OP remains visible with FDX/RRC quarantine evidence, independently of ownership success. COMPLETED and NO_CHANGE financial outcomes remain supported.
- A completed publication shows ticker, AUTO_CONTINUED, generation, PUBLISHED, postflight and recovery. Cleanup is a separate row. A successful publication with cleanup STOPPED still displays publication success and unresolved cleanup/reason; it is not relabelled as publication failure.
- NO_AUTO_CANDIDATES explicitly reports no publication in this run. Disabled, copy-Test-only and failed/stale runs do not invent a live generation or cleanup. Manual/deep-only partitions retain readable counts and review holds.
- Existing scheduler concise reporting is unchanged; its whitelist excludes the UI metadata/evidence. No scheduler configuration changed.

## Accepted live result replay

**PASS.** Retained Full Workflow `20261029T123240Z_refresh_fundamentals_d00eb7239fed_full_workflow_0e892e90` rendered through the real Markdown renderer, UI service `_finalize`, history summary and Flet summary controls. The following appeared directly:

```text
Policy: enabled — PB_ORDINARY_AUTO_CONTINUATION_V1
Financial precondition: SAFE_FINANCIAL_NO_OP; financial workflow: STOPPED
Ownership status: COMPLETED
Published: TMUS — AUTO_CONTINUED
Ownership publication: COMPLETED / PUBLISHED
Ownership generation: pb_ownership_719201a6f6f4497bb6a3e1ada35b81b6
Postflight: PASSED
Recovery: NOT_REQUIRED
Cleanup: COMPLETED — 3 backups / 2.63 GB (2,630,086,656 bytes freed)
Evaluated 1 | Automatic 1 | Manual 0 | Deep 0 | Published 1 | Failed/stale 0
```

Preview/Test details remained in Markdown, and FDX/RRC remained visible separately. TMUS appears only as retained replay evidence; production display logic has no ticker-specific rule.

The Flet controls were exercised headlessly with a replay-only service returning the already-rendered response. No desktop/browser session or live workflow was launched. Startup recovery was disabled for the real read-only service calls. Original run JSON and original saved Markdown remained byte-identical. Historical downloaded Markdown is preserved; the replayed improved report is saved only in excluded temporary evidence. Newly generated reports use the improved renderer, and history/UI summaries can display the retained result through its bound JSON artifacts.

## Validation and runtime safety

**279 focused tests passed:** 22 display/metadata/replay tests (11.28s) and 257 directly relevant existing UI, Full Workflow, scheduler, future-ownership, safe-no-op, publication/recovery and cleanup regressions (138.01s). Tests cover generic/multiple tickers, field/count/link visibility, financial outcome separation, no-publication states, failed/stale and cleanup-stop behavior, missing/mismatched legacy receipts, exact run-local fingerprint handling, no database reads for display, unchanged inputs, real Flet summary controls, native copied-fixture metadata and bounded scheduler output. **Full suite: not run.**

Before/after read-only safety checks confirmed identical live financial roles, active manifest/generation, provider watermark (2026-10-28), queue contents, journal, market/taxonomy main/WAL inputs and enabled scheduler configuration. All 53 retained production backup files and metadata remained unchanged. No real Refresh/ownership Production, decision, queue mutation, generation activation, journal update, configuration write or backup deletion occurred. Native lifecycle regression tests operated only on isolated fixtures/copies. The expected bound source-code fingerprint change is the publication module's additive return metadata, not financial runtime mutation.

Excluded working evidence: `temp/pb_ui_visibility_20261029/` — `test_results.json`, `replay_result.json`, `runtime_verification.json`, `before.json`, `after.json`, `live_replay.md`, `live_replay_ui.txt`, `live_replay_history.txt` and focused logs. Only bounded source, tests and this report belong to the commit. Runtime databases, journals, generation files, scheduler configuration, copied projects and unrelated OHLCV/research artifacts remain excluded. No push.
