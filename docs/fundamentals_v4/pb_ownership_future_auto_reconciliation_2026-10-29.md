# Future P/B ownership automatic reconciliation — 2026-10-29

Task: **P/B-OWNERSHIP-FUTURE-AUTO-RECONCILIATION-1**. Governing contract: [PB_ORDINARY_AUTO_CONTINUATION_V1](pb_ownership_auto_continuation_policy_2026-10-28.md), implemented in `f9a912d387e9b1848c3a88e5aae2fe733255beff`; successful six-case rollout: `a645b5cba5dc4c5a0027ca4019acb75c411a3aec`.

## Previous behavior and enablement point

Before these changes, successful financial Refresh Production called `RefreshReviewQueue.sync_ownership(...)` in `refresh_production.py` without an `auto_continue` argument. Its default was, and remains, `False`. The ordinary detector created OPEN reviews, and no automatic ownership decision or ownership publication followed. Scheduler and manual Refresh Full Workflow already shared `FundamentalsAdminUIService.full_workflow` and `run_refresh_full_workflow`. Financial Preview/Test did not automatically approve ownership. This disabled path was identified before implementation and remains the fallback.

The shared UI-service entry now runs one ownership segment after the financial Full Workflow reports COMPLETED or NO_CHANGE. It uses the newly accepted immutable generation, never a prediction of financial changes from an earlier Preview. A failed/stopped financial workflow skips the segment. A NO_CHANGE financial result can still have a safe pending ownership continuation; successful ownership publication makes the overall workflow COMPLETED. An ownership failure is reported separately and cannot undo a healthy completed financial publication.

`pb_ownership_future.FutureOwnershipWorkflow` orchestrates the existing V1 evaluator, the existing inactive approval/candidate builder and `OwnershipPublicationWorkflow`. It introduces no alternative publisher, no formula, provider-source normalization, policy threshold or ticker-specific eligibility rule.

## One configuration switch

`scheduler_config.json`: **`pb_ownership_auto_continuation_enabled`**, strictly Boolean. Scheduler configuration parsing/validation/serialization preserves it. Older configurations without the field default to `False`, retaining the previous manual behavior. The deployment configuration is enabled only after the acceptance checks below. Manual Full Workflow reads the same configuration; scheduler passes its validated value into the same service. Diagnostic Preview remains read-only.

The scheduler's outer Production/scheduler locks are reused only through the existing process-local `production_lock(allow_reentrant=True)` contract, which verifies the exact lock path and scheduler log directory. The native ownership publisher and cleanup entry support this nesting. Copy projects use their own locks; no shared kernel lock is bypassed, deleted or inferred free from owner text. Isolated test run roots do not implicitly acquire live sources: they require an explicitly injected ownership runner.

## Ownership Preview, Test and Production

1. **Preview:** fresh detector cases are evaluated by unchanged `pb_ownership_auto.evaluate`. The artifact partitions AUTO_CONTINUE, MANUAL_REVIEW and DEEP_REVIEW/BLOCKED. Each item carries its ticker, case/source observation and content hash, prior review, policy version, provider factor, shares deltas, warnings and hypothetical P/B/reconstruction evidence. AUTO_CONTINUE is a policy recommendation; no human approval is represented. The existing hypothetical P/B envelope remains labelled by its HYPOTHETICAL identity. Preview is bound to active generation/manifest/role hashes, queue content, journal, market/taxonomy inputs including WAL, configuration, code and as-of date; a second source read must match.
2. **Test on copies:** all three roles, market, taxonomy and queue are copied into a separate project. Normal review synchronization and the installed automatic inactive-candidate builder execute exactly the selected policy decisions. The native ownership publisher prepares and activates a copied immutable generation and runs postflight/P/B checks. Native cleanup eligibility must pass. A fingerprinted Test receipt retains the exact source, decisions, selection, candidate hashes and completed copied-journal identity. Original sources must remain unchanged.
3. **Production:** the exact successful receipt, copied terminal journal and copied published role hashes must still match. Source and fresh Preview are rebuilt before any real automatic decision. Only the tested selected decisions enter the existing native ownership Preview/publication lifecycle, including immutable generation preparation, verified rollback backups, durable journal, final source gates, activation, postflight and recovery. Automatic decision evidence has `decision_type=AUTO_CONTINUED`, the V1 policy and no operator/note. `SYSTEM:SCHEDULER` or `SYSTEM:MANUAL` identifies the automated publishing action, separately from approval evidence.
4. **Cleanup:** only that successful ownership publication's exact journal-owned backups are passed to the existing acceptance/cleanup owner. Its PASSED/NOT_REQUIRED, provenance and recovery-independence checks remain authoritative. Cleanup failure retains the healthy publication and reports STOPPED cleanup. Unrelated financial Refresh backups are governed by their existing contract.

Successful ownership publication is terminal. A second reconciliation detects no new case for the same accepted binding and creates no duplicate decision or publication. Stale evidence or a failed publication remains visible for inspection/retry through the existing review/publication controls; the integration does not relax a gate to force completion.

## Exceptional guards and manual fallback

V1 remains unchanged. Incomplete/full-payload gaps, absent/null/nonordinary factors, factor/category/security/provider identity changes, ambiguous or duplicate observations, unresolved provider history/source-repair reviews, corporate-action conflicts, ADS/ADR interpretation, missing equity/usable price, failed Decimal P/B reconstruction, stale/tampered evidence, explicit holds and accounting-boundary/deep-review conditions cannot enter the automatic selection. Exceptional items remain visible. Corporate-action coverage incompleteness and dated quarterly shares remain explicit V1 warnings, not newly introduced guarantees.

Manual approval remains available with literal explicit confirmation and exact candidate/evidence binding. Operator and note remain optional for this ownership approval contract. Historical decisions are not bulk converted. The disabled switch leaves normal financial reconciliation's manual ownership path intact and adds no automatic artifacts, decisions or publication.

## UI and scheduler reporting

Review Queue shows the switch/policy and automatic/manual/deep counts, with per-case policy warnings. Existing AUTO_CONTINUED labels and automatic evidence remain distinct from operator approval; automatic cases require no operator input. Existing manual hold/approval controls remain available. No Review Queue redesign is included.

Full Workflow reports link to the detailed ownership Preview and Test receipt. The scheduler exposes only `enabled`, `policy_version`, `status`, `evaluated`, `auto_continued`, `manual_review`, `deep_review`, `published`, `failed_stale` and cleanup status. Detailed evidence stays in the run artifacts.

## Fresh runtime and current-state copy validation

The interrupted attempts' observations are historical. On resumption, the latest completed normal scheduler run was inspected directly: `logs/stock_update_scheduler_summary_20261029T023006Z.json`, completed **2026-10-29 07:59:04 Europe/Helsinki**, overall OK. Its shared Fundamentals Full Workflow `20261029T053015Z_refresh_fundamentals_d00eb7239fed_full_workflow_7b6f2ce0` completed Production `20261029T054405Z_refresh_fundamentals_4c3b99953d00_production_a7f5b976`; FDX/RRC remained quarantined. These normal external changes are preserved.

The separately resolved current active generation was `pb_ownership_6afe669f1166421bbd0e20f66fff3d07`; actual provider watermark **2026-10-28**. The current journal was COMPLETED, postflight PASSED, recovery NOT_REQUIRED. It records the later native six-case ownership publication. The current queue contained nine PUBLISHED cases, the three retained SUPERSEDED GE/RTX/T historical rows, and one OPEN case. Six published cases retained AUTO_CONTINUED evidence; GE/RTX/T retained their operator approvals. Full state and current V1 partition were read again after the subsequent interruption and compared to the fresh baseline, without relying on pre-interruption hashes.

Fresh current partition: **1 evaluated / 1 AUTO_CONTINUE (TMUS) / 0 MANUAL_REVIEW / 0 DEEP_REVIEW/BLOCKED**, no blocking reasons. TMUS was rediscovered through the generic detector, not selected by ticker. Its factor was 1.0 and hypothetical P/B **2.785747495928854**, reconstructing at 50-digit Decimal precision. Warnings: CORPORATE_ACTION_COVERAGE_INCOMPLETE and QUARTERLY_SHARES_ARE_A_DATED_APPROXIMATION. This is current evidence only; future runs must evaluate their own source again.

**Current-state copy validation: PASSED.** The disposable rehearsal used the actual shared Full Workflow service with an explicit NO_CHANGE financial adapter, avoiding unnecessary network acquisition/financial publication while exercising the real ownership segment. The disabled pass left the copied queue unchanged. The scheduler-triggered pass exercised the exact source-bound Test receipt, native publication and cleanup under the outer Production/scheduler lock. Its automatic approval retained V1 evidence without operator/note; only TMUS was selected.

| Copy-only result | Value |
| --- | --- |
| Evaluated / automatic / manual / deep | 1 / 1 / 0 / 0 |
| Auto-continued / published / failed or stale | 1 / 1 / 0 |
| Native publication | `pb_ownership_fb74384f1ea94d9aad271f86a1856fcc`, COMPLETED / PASSED |
| Native cleanup | COMPLETED; exactly 3 backups, 2,630,086,656 bytes freed |
| Second reconciliation, manual trigger | NO_AUTO_CANDIDATES; evaluated 0, decisions 0, publications 0; queue unchanged |
| GE/RTX/T and six prior published cases | Exact original rows and history preserved; no reopening, duplicate or republication |
| Other reviews/source repairs | Unchanged |
| Canonical financial/schema/publication-authority content | Unchanged outside the two native ownership tables |
| Actual live runtime throughout rehearsal | Unchanged; no live reconciliation/publication |

One earlier disposable setup lacked the live taxonomy database's existing empty WAL file. The source guard rejected the read-created empty WAL as drift after the copied Test publication, before any outer-project decision. Database hashes were unchanged. The rehearsal setup was corrected to preserve the exact live empty-WAL state; the strict implementation guard and policy were unchanged. The final complete rehearsal passed from a freshly revalidated source.

Evidence: `temp/pb_future_reconciliation_20261029/current_copy_084355` (`before.json`, `live_readonly_preview.json`, `after.json`, `result.json` and native run artifacts), summarized in `temp/pb_future_reconciliation_20261029/copy_result.json` and `copy_final.log`. Heavy copies and machine evidence remain outside Git. All nine protected queue rows/history, every nonselected review, source-repair table and canonical financial/publication-authority content were compared independently. Live roles, manifest, journal, watermark, queue, market/taxonomy inputs and configuration were unchanged throughout.

## Tests, activation and disable procedure

**800 focused tests passed**, with no full suite run. Completed modules were retained across the interruptions: 294 tests in future integration, scheduler runner/config, admin/scheduler Full Workflow, V1 auto-continuation, quarterly ownership review and P/B reporting; 149 tests in native ownership publication, ownership cleanup and payload completeness. The remaining six modules completed after the final reboot: **357 passed in 207.95 seconds**, covering provider-payload repair workflow, WFRD accounting-boundary review and production parity, native run-acceptance cleanup, drain acceptance and terminal receipts. Interrupted partial-module output was not counted; those modules were rerun to completion. No policy/source integration code changed between these runs.

Runtime-only test evidence: `temp/pb_future_reconciliation_20261029/test_results.json`, with `focused.log`, `remaining_focused.log` and `final_focused.log`. The 13 new integration tests include exact copy/Test/Production/cleanup reuse, source/receipt/selection/hold drift rejection, disabled mode, explicit holds, strict Boolean configuration, both manual and scheduler triggers under the native outer lock, financial failure skipping ownership, concise reporting and second-reconciliation idempotency.

Activation requires all checks and the current-state rehearsal to pass. Read-open nonblocking UI, Production and scheduler kernel locks must all be free; taxonomy must be inactive, journal terminal/PASSED/NOT_REQUIRED, no preparing generation and exact baseline invariance. While retaining those locks, change only the one Boolean configuration field and validate/read it back. Do not invoke a live reconciliation merely to enable the switch. Compare financial roles, manifest, journal, watermark, queue, market/taxonomy and protected reviews before/after. A legitimate active workflow or any state drift stops enablement.

**Live enablement: PASSED / ENABLED at 2026-10-29 12:02:23 Europe/Helsinki (10:02:23 UTC).** All acceptance checks passed first. The final nonblocking native lock checks, inactive taxonomy check, terminal journal/recovery check, no-preparing-generation check and exact source/partition revalidation passed. Locks remained held through the one-field atomic configuration update and read-back. Both scheduler configuration and manual Full Workflow's shared configuration reader returned `True`.

Only `pb_ownership_auto_continuation_enabled` changed. **No live reconciliation or publication was invoked. TMUS remains OPEN and unpublished.** The nine prior publications and complete queue/history/source-repair state remain unchanged. Current diagnostic partition remains 1 automatic / 0 manual / 0 deep. Active generation remains `pb_ownership_6afe669f1166421bbd0e20f66fff3d07`, provider watermark 2026-10-28 and journal COMPLETED / PASSED / NOT_REQUIRED. Roles, manifest, journal, market/taxonomy main/WAL inputs and financial/source-authority content match the fresh pre-enablement baseline exactly. No WFRD or source-repair decision changed.

| Live immutable role, unchanged before/after | SHA-256 |
| --- | --- |
| Provider | `0f23acbd064d1859fa1d9f71996d1eb4979a9cdbac2db1d805a774d4215770f1` |
| Canonical | `7568f70b89441b46bb97879cc534394e91c5dc250c3f10b0a43a31e8a9530273` |
| Analysis | `b1fef5fd8eb651e0337c9f6128b1e068df2999873da158c653b45fff42223327` |

Configuration SHA-256 changed from `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894` to `10e7c91e357ffaaacf56785a0bec064a95eaf21a84eb5592642be79fef1dab2b`. Active manifest SHA-256 stayed `6ef1d0904072082d1ef6620cfb0c933e8d8fc9d67c244c77d09e87f3a3bec98b`; journal SHA-256 stayed `0d46ca98798c4852ec863c5bb835277d0d980ef37f5acbb06b21b240a260972e`.

Runtime-only activation evidence: `temp/pb_future_reconciliation_20261029/enablement.json`, SHA-256 `f47fbd0cca33dc46b09950b3cb2c5f5e8bd0cbc04ea74761ec8cb957aec83b24`, plus `enablement.log` and the fresh/reboot baseline receipts. Copy-result SHA-256: `23fa8d38d8f9aa4a2be10a256807cd5cb13b6afcabd80357e4b3db6c1b81b5cb`; test-result SHA-256: `6d43136163397635eafb7e7491d538a28fbc7b123d712c815cafe82bb2a2ba24`. The source commit excludes all machine evidence and runtime state.

Quick disable: while no workflow is active and the same safety guards pass, set `pb_ownership_auto_continuation_enabled` to `false` in `scheduler_config.json` through validated configuration handling. Subsequent normal Full Workflows use the previous manual ownership path. No source rollback or historical review migration is needed; already published immutable generations and their audit records remain governed by the native lifecycle.

## Scope and next phase

Only bounded orchestration, lock nesting support, switch, reporting/UI, focused tests and this document belong to the source commit. Runtime journal, active-generation files, queue/database files, manifests, copied projects, test/rehearsal logs/reports, backups and all pre-existing OHLCV/research artifacts remain excluded. The existing machine-local `scheduler_config.json` is Git-ignored; its operational switch is changed locally, while the configuration field/validation and shared behavior are versioned. No publication-authority/SEC resolver, WFRD accounting policy, P/B formula or provider-semantics changes. Nothing is pushed.

Next hobby-mode phase: observe the first normally scheduled enabled Full Workflow, verify its policy counts and native publication/cleanup receipt, and review only the remaining exceptions. Do not run an extra live publication to demonstrate activation.
