# Fundamentals operational clarity and history paging — 2026-10-29

Task: `FUNDAMENTALS-UI-OPERATIONAL-CLARITY-FINAL`, including PHASE K2 (`Show more`).

## Bounded findings

The audit covered the existing administration UI, retained-history cursor/projections and deferred loader, Preview report wording, operational-decision schema, and directly relevant tests. No financial/review/publication policy or broad artifact investigation was undertaken.

The false Preview failure came from `final_status_message`: its generic Preview fallback treated REVIEW_REQUIRED as failed, although the refresh Preview had completed and returned a valid structured decision. The backend status/outcome and authorization were already correct. The old pending banner described an older source/candidate signal as pending Fundamentals changes and did not distinguish the latest completed comparison's effective impact. Run-history rows exposed technical results without their operational meaning.

The newest retained data differs from the prompt's historical examples: the latest visible manual Preview is `20261029T164949Z_refresh_fundamentals_5fc2aa1a7e10`, with **164 discovery candidates**, **0 effective changes**, **0 safe publishable changes**, **2 local reviews**, and **0 global blockers**. The discovery count includes source-change candidates, not only known/current-universe tickers, so the UI deliberately does not label all 164 as known Fundamentals changes. Queued reevaluations can also add comparison work independently of discovery; the discovery count is not relabelled as the total evaluated population.

## Preview and no-safe-changes wording

`run_presentation.py` adds pure operational wording from existing structured fields. Completed Refresh Previews distinguish technical failure, global/authorization blockers, local review, no publishable changes, and safe changes ready for Test. Current no-safe-change wording is:

> Preview completed — no new publishable changes
>
> No new financial changes need publication. FDX, RRC remain separate review items. They did not block safe peer changes.

The existing decision code, Test reason `NO_SAFE_CHANGES_TO_PUBLISH`, REVIEW_REQUIRED outcome, gates, and raw decision remain unchanged and accessible in Details/audit. No backend code is renamed or normalized into a new persistence state. The report presentation helper now supplies the correct Refresh Preview headline; existing retained report files are not rewritten by this task. Other operations' existing result wording is preserved.

The UI-service DTO carries Preview presentation rows alongside its original status, outcome, payload/fingerprint, and authorization fields. The primary view uses the concise rows while Details retains technical rows and a nested exact operational-decision JSON view. A real technical error still renders failure. Global blockers, blocked safe peer work, unresolved Test prerequisites, postflight/recovery/cleanup problems, and failed/stale ownership results remain actionable.

## Source relevance and landing

History entries project source-scan counts from their already-loaded result payloads. The landing chooses the latest visible retained Refresh Preview/Full Workflow in the existing bounded history page, including manual Preview results. It shows:

```text
Latest source scan: 164 source-change candidates flagged for comparison
Relevant Fundamentals changes: 0 · Publishable safe changes: 0
Separate review items: 2
```

Discovery uses the structured unique-source-ticker field, effective changes use the existing effective-change count, and safe/review counts use the operational decision with existing summary-field fallbacks. Missing/non-integer counts say `not recorded`; no effective-change count is repurposed as discovery work. The native scheduler's pending-refresh contract is unchanged. A retained-history read error remains visible rather than falling back to a stale all-clear.

Landing publication wording is `Safe publication within Full Workflow: automatic`, avoiding an invented independent publication switch. A safely stopped financial workflow reads `Last workflow: No new safe financial changes to publish`; STOPPED and all native codes remain in Details/history. The run-history top summary is one line labelled `Latest Full Workflow`, with ownership outcome and current review count, rather than duplicating the full technical block.

Fresh queue data has FDX/RRC in **RETRY_REEVALUATION**, not newly OPEN. Existing actionability therefore correctly yields **0 immediate operator reviews**, **2 reviews waiting on provider/workflow**, and **0 deep reviews requiring action**. The UI now explicitly shows the waiting population rather than falsely equating zero immediate actions with no retained review work. Both cases and their existing permitted actions/evidence remain available. No state is changed to force the prompt's older count of two immediate actions.

The latest visible retained Full Workflow is `20261029T114501Z_refresh_fundamentals_d00eb7239fed_full_workflow_3b1e190f`: financial STOPPED / NO_SAFE_CHANGES; ownership `SKIPPED_UNSAFE_FINANCIAL_WORKFLOW`, published 0. It is displayed faithfully, not replaced with an older/hidden COMPLETED/published-1 example. Financial no-op wording does not assert ownership success or retroactively authorize skipped work. Existing history hiding/filtering semantics are preserved.

## Operational meaning and urgency

Refresh run-history Result keeps the technical result on its first line and adds operational meaning plus an Action line underneath. The modestly wider Result column avoids adding another wide table column. Existing typed fields, not prose/status alone, determine the interpretation:

| Structured evidence | Presentation category / action |
| --- | --- |
| Exact NO_SAFE_CHANGES decision, safe 0, global 0, Test false with the native no-safe-change reason, Production NOT_APPLICABLE | Safe financial no-op; no immediate corrective Full Workflow action |
| Completed Preview with local held reviews, no global blocker and explicit peer-not-blocked evidence | REVIEW_WHEN_APPROPRIATE; review separately |
| Safe changes and existing Test authorization | Ready for Test on copies; existing stage gates remain authoritative |
| Explicit completed publication | Publication successful; published ticker count where recorded |
| Global blocker, explicit blocked peer work, technical/contract failure, unresolved required authorization, postflight/recovery/cleanup failure | ACTION_REQUIRED |
| Bare STOPPED / REVIEW_REQUIRED without sufficient structured evidence | Meaning/urgency not recorded; inspect Details, without inventing a criticality classification |

The categories are temporary presentation values only. A safe financial STOPPED remains STOPPED in audit, and local reviews remain separate from financial progression. Existing ownership outcome is included independently, including a publication count when present. Non-Refresh history entries are not assigned guessed urgency from an unrelated contract.

Completed accounting-boundary records now appear under the collapsed `Accounting-boundary history / audit (1)` heading. APPROVED is visible after expansion, not as a standalone current-looking line. WFRD evidence, fingerprints, bindings, and raw JSON are intact.

## Show more: reproduction, cause, and small fix

The native cursor's data paging was **working**: it returned 8 then 16 correctly ordered retained rows. A concrete synchronous UI reproduction showed `sync initial 8 updates 0` followed by `sync more 16 update_delta 0`: the callback changed server-side controls without explicitly updating the page. Native service paths can mask this through incidental review/settings refresh updates; the callback itself was not reliably requesting a redraw.

The fix is presentation-only: the synchronous Show more path now explicitly calls `page.update()` after loading. It ignores clicks while disabled/loading or already exhausted. The deferred path still uses the existing load controller and completion update. There is no cursor, offset, persistence, ordering, cleanup, or artifact-retention redesign.

The initial limit remains 8 and increases by 8. The same cursor is reused for additional pages. Existing technical/legacy filter changes reset/reload the cursor and limit; selection remains valid when still present. Show more hides on exhaustion. No load-everything API is introduced. The existing metadata catalogue and legacy parent-link index are retained; additional operational/source meaning reuses cached projections rather than adding artifact scans.

Fixtures cover normal and deferred continuation 8 → 16 → 24 → 25, exhausted control state, newest-first order, no duplicates, visible redraw, technical filtering and reset, valid selection preservation, byte-for-byte retained-fixture preservation, and bounded initial projections. A source-equivalence test proves `AdminHistoryCursor` itself is unchanged. Deferred tests use the repository's existing inline-worker test convention; the live replay below uses headless synchronous controls rather than a browser event loop.

## Staged workflow and progress preservation

Direct Preview, Test on copies, Production, and the primary Full Workflow action remain available through their existing paths. Status/outcome, capability checks, Preview/Test binding, signatures, and authorization code are unchanged. Tests prove the current no-safe-change Preview does not expose Test/Production, while an authorized safe Preview exposes Test and Production still requires its existing prerequisites.

Preview Progress details were **not changed**. Source-equivalence tests compare `render_progress`, `progress_callback`, `on_progress_scroll`, `on_preview`, `on_copy_apply`, `on_production_apply`, and `apply_capabilities` against the task-start commit. Retained stage events are replayed in their original order/format; all nine completed stages, expanded Preview details, and original event/result file hashes are verified. No stage is renamed, filtered, collapsed, or rewritten.

## Current-state read-only replay

Result: **PASS**. The replay uses real read-only history/queue/config/policy methods, recovery disabled, existing admin/production exclusion locks and a shared scheduler read lock. Native Preview is **not** invoked: it would update the queue. Instead, the latest retained Preview DTO/events are replayed into the real Flet controls. No live workflow/publication/review operation is called.

Verified:

- REVIEW REQUIRED landing; automatic safe publication wording; 0 immediate / 2 reevaluation-pending provider reviews; deep action count 0.
- Latest source counts 164 candidates / 0 effective / 0 safe / 2 separate reviews, with no pending-Fundamentals-changes label.
- Native Preview REVIEW_REQUIRED retained, primary text says completed/no new publishable changes, FDX/RRC separate and nonblocking; Test unavailable, Production disabled.
- Latest visible safe STOPPED Full Workflow remains STOPPED and noncritical for financial corrective action; ownership skipped outcome remains visible and unchanged.
- Initial visible history 8; Show more visibly loads 16, preserving prefix/order/selection without duplicates; technical filter reloads 8 and pages to 16, then switching back restores the default first page.
- Completed boundary status stays inside collapsed audit; current provider review records remain visible.
- All 9 original Preview stages replay unchanged; native result/progress files remain byte-identical.
- Full captured runtime/source baseline is unchanged except intentional UI page/service code fingerprints. Current backup inventory is **50 files**, unchanged during replay; no backup deletion was performed by this task.

This task re-established its own fresh baseline rather than reusing prior workstream counts/hashes. The visible state differences above are retained external state. Local reproduction/test/replay evidence is under ignored `temp/fundamentals_operational_clarity_20261029/`, excluded from the commit.

## Tests and safety

Focused modules cover operational clarity/paging, final-polish UI, operational presentation, administration UI/service, safe-no-change ownership guards, Refresh Full Workflow decisions, and the deferred loader. Regression checks include immutable native outcomes/reason codes, critical precedence, missing counts, local nonblocking review, ready Test behavior, technical-result visibility, compact summaries, source-equivalent progress/stage/cursor code, and no rendering/history mutation. Only focused tests were run; no full suite.

Final result: **210 passed in 21.71 seconds**, with:

```text
tests/test_fundamentals_operational_clarity.py
tests/test_fundamentals_ui_final_polish.py
tests/test_fundamentals_operational_presentation.py
tests/test_fundamentals_admin_ui.py
tests/test_pb_ownership_safe_no_changes.py
tests/test_fundamentals_admin_refresh_full_workflow.py
tests/test_deferred_ui.py
```

No backend decision/review semantics, persisted reason codes, scheduler behavior/configuration, ownership policy/publication, cleanup, generation lifecycle, journal/recovery, WFRD, source repair, publication authority, or historical freeze policy changed. No runtime DB, queue, journal, active generation, scheduler config, audit record, progress artifact, or backup was written by this task. Only task-owned UI/presentation/service shaping, tests, and this report are committed; runtime, temp, copied-project, OHLCV/research, and unrelated worktree artifacts are excluded. No push.
