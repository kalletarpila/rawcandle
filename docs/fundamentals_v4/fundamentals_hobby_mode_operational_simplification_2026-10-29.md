# Fundamentals operational simplification — 2026-10-29

Task: `FUNDAMENTALS-HOBBY-MODE-OPERATIONAL-SIMPLIFICATION`.

The landing page now answers whether current attention is needed, offers one Refresh Fundamentals / Full Workflow action, and separates lightweight Review from Deep Review evidence. Existing backend authorization, policy, publication, rollback, and recovery remain authoritative.

## Bounded audit and prior complexity

The audit covered the administration page, its UI service/result DTO, the completed action-first/guidance helper, native Full Workflow result fields, boundary-review read contract, and their directly relevant tests. No broad repository scan or new policy investigation was performed.

Previously, the landing surface exposed individual operation stages, a provider review table, a raw accounting-boundary JSON block, ownership reviews, and run history together. Retained-history and ownership dialogs put fingerprints/bindings directly in the confirmation text. Full Workflow progress opened technical lines automatically, while the final primary message alone did not explain mixed financial and ownership outcomes.

| Information | New placement |
| --- | --- |
| Current operational level, review counts, automatic settings, latest retained workflow, next action | Primary landing summary |
| Refresh Fundamentals Full Workflow | One primary action; same existing service owner, no added confirmation |
| Other operations, Preview/Test/Production stages | Collapsed Advanced section; existing controls and guards retained |
| Current provider and ordinary ownership reviews | Review section with action-first cards/rows and unchanged action eligibility |
| Existing deep ownership policy cases and boundary reviews | Deep Review section; exact recorded status and existing controls |
| Conditional persistent source-history investigation | Ticker-labelled advice and expandable full retained evidence in Deep Review |
| Fingerprints, receipts, generations, bindings, raw records | Expandable evidence/technical details and existing downloadable reports/artifacts |
| Terminal/resolved reviews and run history/cleanup | Collapsed secondary history sections; no terminal approval/hold controls |

## One presentation model, three levels

`operational_presentation.py` defines `NORMAL`, `REVIEW`, and `DEEP_REVIEW`, pure review routing, compact structured workflow presentation, and the landing summary. It performs no database reads/writes, evaluation, authorization, or state transitions. The existing `ReviewPresentation` remains the source for current/history membership, urgency, reasons, and allowed actions.

- **NORMAL:** known healthy current status with no current action, no publication safety block, and no unresolved workflow anomaly. COMPLETED/NO_CHANGE and the existing `SAFE_FINANCIAL_NO_OP` precondition can display clean outcomes. Running state is shown only from the local in-progress operation or an existing retained workflow's running status. Missing/unreadable status is not presented as an all-clear.
- **REVIEW:** existing current actionable provider or ordinary ownership cases. Wait/Retry, permitted lightweight approvals, pending publication, and hold controls keep their prior rules. Waiting/pending current cases remain current without invented urgency. Current diagnostic cases lacking persisted rows still produce warnings/counts; no review is created by rendering.
- **DEEP_REVIEW:** the explicit existing ownership `DEEP_REVIEW/BLOCKED` partition, recorded accounting-boundary reviews, publication/recovery blocks, technical failures, reporting-integrity errors, or explicit postflight/cleanup anomalies. Existing deep ownership cards and their permitted controls move to this section; they are not hidden or converted into a new state.

The backend does not provide an authoritative persisted “this OPEN source replacement has now lasted long enough” transition. Therefore the UI does **not** infer persistence from age, repeated timestamps, or OPEN alone. FDX/RRC stay in lightweight Review with their established staged path. Deep Review offers conditional investigation advice using their structured codes, without escalating or changing their review state.

The saved accounting-boundary item is `APPROVED`. That saved status alone is neither a new approval request nor proof of terminal publication. The UI preserves it exactly, routes its evidence to Deep Review, and says to inspect the recorded status/evidence. It does not claim a global block solely from the presence of the record, request another approval, or invent a PUBLISHED transition. This retained-record limitation is deliberately visible rather than resolved by frontend guessing.

## Automatic operation and lightweight review

The normal workflow button selects REFRESH_FUNDAMENTALS and invokes the existing guarded `full_workflow` callback once. Preview, Test on copies, financial publication, and ownership auto-continuation still run only through their existing owner and native checks. Opening the page, loading settings/history, or rendering a summary does not run them.

Automatic publication is described as automatic **within Full Workflow**; it is not an independent new scheduler or publication switch. The existing scheduler configuration and V1 flag are read, never changed. P/B enabled/disabled and current automatic/manual/deep counts remain visible. Individual stages and other operations remain available under Advanced with the same authorization and confirmation conditions.

Retained-history comments and quarterly approval operator/note fields remain explicitly optional where their backend accepts blanks. The hold reason, explicit observation checkbox, and separate publication operator/confirmation remain required where the existing backend requires them. Fingerprints are supplied through existing bound callbacks, not manual copy/paste. Exact observation evidence and publication Preview evidence remain expandable inside the dialogs.

FDX retains `INTERIOR_SOURCE_KEY_REMOVAL`: Wait for Providers, Retry after later source changes, investigate source history manually if still unresolved. RRC retains `SAME_FISCAL_SOURCE_KEY_REPLACEMENT`: the same staged path plus comparison of old/new source bindings and financial payload if replacement persists. Retained-history incompatibility and hidden approval controls remain unchanged.

## Full Workflow outcome presentation

The UI-service DTO adds a presentation-only `operational_summary`, derived from retained structured result fields. Native results, report generation, summary rows, status/outcome, retry authorization, and publication rules are unchanged.

The primary result shows the financial outcome/publication flag, financial review count, ownership status/publication count/manual/deep counts, explicit anomalies, action requirement, and next step. A financial STOPPED with the orchestrator's `SAFE_FINANCIAL_NO_OP` remains visibly **STOPPED — safe no-op (NO_SAFE_CHANGES)**, independently of ownership COMPLETED/publication. Unknown publication/review metadata is labelled not recorded. Actual failed/stopped stages, failures, postflight/recovery, and cleanup anomalies remain primary attention signals.

Full Workflow progress is compact while running, with its detailed log collapsed. Completed workflow progress also collapses. The original message, full summary rows, technical errors, paths, fingerprints, report hash, and downloadable reports remain accessible in Details/history. Non-workflow preview/progress behavior and native direct retry controls remain intact. A UI execution exception or unreadable history cannot silently leave a healthy landing summary.

## Current-state read-only replay

Real Flet controls were rendered using real read-only service methods, current configuration, retained history, queue data, and current policy diagnostics. Startup recovery was disabled and mutating entry points were replaced by failing guards. Only refresh/history/detail display controls were exercised.

Observed current state:

| Surface | Result |
| --- | --- |
| P/B V1 flag | Enabled; current automatic/manual/deep partition 0/0/0 |
| Current ownership action | None; ownership status says No action required |
| Lightweight Review | FDX OPEN and RRC OPEN; incompatible approval still hidden; staged Wait/Retry guidance intact |
| Deep Review | One saved APPROVED accounting-boundary record, exact evidence retained; FDX/RRC conditional investigation guidance available |
| Ownership history | 13 collapsed records: 10 PUBLISHED and 3 SUPERSEDED; no terminal action controls |
| Provider history | 6 resolved records, opt-in and collapsed |
| Latest retained workflow | Financial STOPPED with safe NO_SAFE_CHANGES precondition; ownership COMPLETED, published 1 (historical result, not a publication executed by this task) |
| Active generation / watermark | `pb_ownership_719201a6f6f4497bb6a3e1ada35b81b6` / `2026-10-28` |
| Journal/postflight/recovery | COMPLETED / PASSED / NOT_REQUIRED |

The landing correctly shows two current lightweight reviews and one retained accounting-boundary Deep Review item rather than claiming the entire administration is action-free. Healthy zero-review NORMAL behavior was separately tested with fixtures.

Replay compares the complete captured source/runtime baseline against a fresh pre-change snapshot, allowing only the intentional administration page/UI-service code fingerprint changes, and compares again after rendering. All retained financial/runtime state and all 53 backup files remained unchanged. Shared read locking for the scheduler and exclusive admin/production locks exclude RawCandle writers without stopping the independent Stockcore reader. No mutating workflow or production gate is invoked by this inspection.

Local test/replay evidence is under ignored `temp/fundamentals_hobby_mode_20261029/`, excluded from the commit. The replay covers the headless Flet control tree, not a desktop screenshot.

Final replay result: **PASS**, including the final section labels and evidence placement; no runtime mutation.

## Focused tests

The broader focused run passed **436 tests in 197.36 seconds** across these modules:

```text
tests/test_fundamentals_operational_presentation.py
tests/test_fundamentals_review_action_first.py
tests/test_fundamentals_admin_ui.py
tests/test_fundamentals_admin_refresh_review_queue.py
tests/test_fundamentals_admin_full_workflow.py
tests/test_fundamentals_admin_refresh_full_workflow.py
tests/test_fundamentals_pb_new_quarter_review.py
tests/test_fundamentals_pb_ownership_publication.py
tests/test_pb_ownership_auto_continuation.py
tests/test_pb_ownership_future.py
tests/test_pb_ownership_safe_no_changes.py
tests/test_pb_ownership_presentation.py
```

After presentation refinements and additional edge cases, affected UI/workflow/safe-no-op/presentation regressions passed **236 tests in 29.50 seconds**. The final UI closeout passed **122 tests in 9.83 seconds**, including two extra error-path cases. These overlapping runs cover **441 distinct test cases**; repeated executions are not counted as new coverage. A final section-label assertion also checks that UI control counts are not presented as review-case counts. Coverage includes normal zero-state, successful/no-change/mixed results, running without a final artifact, unavailable configuration/history, review ordering/history, optional fields, required hold/publication confirmation, staged source guidance, deep routing/evidence access, failures/postflight/recovery/cleanup visibility, native publication/cleanup/idempotency and policy regressions on isolated fixtures. There is no live publication test against production. The full suite was not run.

## Safety, exclusions, and remaining limits

No financial or review policy, approval compatibility, immutable-generation lifecycle, journal, rollback/recovery, exact source binding, cleanup owner, P/B V1, ownership publication, provider history, WFRD semantics, repair/publication authority, scheduler locking/configuration, or Full Workflow authorization changed. New service methods only read settings/retained results; the existing execution method is unchanged.

No Refresh Production, ownership publication, review approval/write, financial DB write, active-generation/journal mutation, or backup deletion was performed. Runtime DBs/queues/journal/generations, scheduler config, temp evidence, OHLCV/research outputs, and unrelated worktree artifacts remain excluded from the source commit.

The latest workflow summary uses the existing bounded history page and cache; if no retained Full Workflow is available there, it says so rather than scanning all artifacts. Running is not inferred from lock files or elapsed time. Snapshot status refresh is explicit and also refreshed through normal retained-history loading; there is no background polling process. Deep source-investigation guidance does not add an investigation/repair workflow. The existing approved boundary record is not automatically retired by presentation.

Final operational-presentation/section-label confirmation: **26 passed in 7.03 seconds**, with no additional source changes afterward.

**Historical freeze policy is not implemented.** No behavior for `period_end <= 2024-12-31`, diagnostic retention, or reviewed historical repair changes in this task. Presentation operates on existing current/history fields and retains full evidence, so a later explicit freeze-review contract can be surfaced without changing this backend-independent model.
