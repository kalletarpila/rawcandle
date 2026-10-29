# Fundamentals review action-first UX — 2026-10-29

Task: `FUNDAMENTALS-REVIEW-UX-ACTION-FIRST`.

The provider-history and quarterly ownership surfaces now show current work first, explain the reason and next action, and place terminal evidence in collapsed history. This change affects presentation only.

## Previous usability problems

Provider rows exposed technical classifications and unavailable approval controls without explaining the operational choice. In particular, FDX and RRC were correctly blocked from retained-history approval but gave little guidance beyond an eligibility tooltip. The ownership surface displayed a long list of published/superseded observations, including disabled approval/hold controls, even when current policy counts were zero.

## Shared model and authoritative inputs

`rawcandle/fundamentals/admin/review_presentation.py` supplies an immutable `ReviewPresentation` and shared current/history grouping. Its fields include status, classification, reason, reason codes, urgency, next action/explanation, terminal/history flag, allowed actions, and blocked-action reason. It performs no evaluation, database access, persistence, or state transition.

| Presentation fact | Existing authority |
| --- | --- |
| Provider current/history | Queue status; only `RESOLVED` is terminal |
| Wait/Retry availability | Queue `OPEN_STATUSES`, `SUPPORTED_ACTIONS`, and `BLOCKED_ACTIONS` contract |
| Provider approval availability | Existing per-action backend eligibility booleans and reasons |
| Provider explanation | Structured reason codes, with existing explanation/summary fallback |
| Ownership current/history | Persisted status; only `PUBLISHED` and `SUPERSEDED` enter history |
| Ownership controls | Existing OPEN/classification and APPROVED/AUTO_CONTINUED publication-eligibility conditions |
| Automatic/manual/deep explanation and counts | Existing current V1 policy diagnostics and enabled flag |

Status answers what state the case is in; classification describes the issue; reason explains why it appears; next action describes an existing available step. Structured codes receive concise labels without changing eligibility. Canonical codes, exact source/fiscal evidence, decisions, and stored observations remain available through details/tooltips. No ticker-specific logic is used.

Urgency is separate from current/history membership. Waiting or reevaluation-pending provider reviews remain current but have no immediate operator urgency. APPROVED and AUTO_CONTINUED ownership cases remain current pending controlled publication; they are never treated as completed history. An enabled, freshly diagnosed automatic OPEN candidate remains visible without implying mandatory manual approval. Unknown states remain current and details-only.

## Provider-history behavior

FDX shows an OPEN review, the human classification “Published source observation missing,” and the explanation that an interior published source key disappeared. RRC shows the same current classification with the distinct same-fiscal source-key replacement explanation. Both display `Action required: YES / REVIEW`, the backend retained-history incompatibility reason, and guidance to Wait for Providers or Retry reevaluation after source data changes; persistent evidence can be inspected through the existing Info control.

Unavailable approval controls are hidden. They do not become available because of a human-readable explanation. Wait/Retry appears only for states/actions supported by the existing queue contract. Neither action grants approval. Eligible retained-history, fiscal-revision, or true-removal confirmation still uses its existing confirmation path and backend validation.

The existing provider history checkbox is now explicitly labelled “Include resolved provider history.” When requested, resolved rows appear in a collapsed `Resolved / provider history` group with evidence access and no visible mutation controls. Current rows precede history, with operator attention first. No FDX/RRC state was changed.

## Quarterly P/B behavior

The main list contains current nonterminal rows, ordered by urgency. Manual/deep and held current cases remain visible; valid current manual approval/hold/publication controls retain their prior conditions and confirmation callbacks. Automatic decisions remain distinguishable from operator approvals, including in stored evidence.

`PUBLISHED` and `SUPERSEDED` rows appear only under collapsed `Resolved / published history`. They show simple terminal status/next-action language and no approval, hold, or publication buttons. Each history card retains collapsed technical evidence; historical classifications are explicitly labelled historical. Stored historical `current_pb_status` is preserved as evidence rather than represented as a live current P/B result.

The status field shows attention counts or a clear zero-state alongside the current enabled flag, V1 policy version, and unchanged automatic/manual/deep counts. If current diagnostics contain cases without persisted review rows, the UI shows a read-only warning and diagnostic details rather than a false all-clear or invented approval controls. It does not register those cases or reconcile the queue.

## Safety and validation

No backend review policy, classification, eligibility, financial formula, scheduler behavior/configuration, ownership publication/cleanup, provider history, source repair, publication authority, WFRD, or Full Workflow implementation changed. Existing action callbacks still perform their existing confirmations and backend checks. Rendering cannot approve, reopen, supersede, publish, delete, relabel, or mutate a review.

Focused regression command used the repository virtual environment with bytecode disabled and these modules:

```text
tests/test_fundamentals_review_action_first.py
tests/test_fundamentals_admin_ui.py
tests/test_fundamentals_admin_refresh_review_queue.py
tests/test_fundamentals_pb_new_quarter_review.py
tests/test_pb_ownership_auto_continuation.py
tests/test_fundamentals_pb_ownership_publication.py
```

Result: **277 passed in 151.92 seconds**. The 28 action-first tests were additionally rerun after a final diagnostic wording clarification: **28 passed in 8.86 seconds** (not additional unique coverage). Coverage includes incompatible reason shapes, backend action availability, manual/deep/pending/unknown states, generic terminal TMUS/AMT/BA/DHR/GE shapes, history grouping, zero-state/policy counts, missing queue rows, technical details, rendering purity, existing confirmations, queue contracts, and native P/B publication/recovery regressions on isolated fixtures. The full suite was not run.

## Current-state read-only UI replay

Real Flet controls were built using real read-only service methods; startup recovery was disabled, and mutation entry points were replaced with failing guards. Only queue refresh/history/detail controls were exercised. The successful replay held the existing read-open preflight locks and compared source/runtime fingerprints before and after.

| Observation | Result |
| --- | --- |
| Current provider reviews | FDX and RRC, both OPEN, blocked approval explained, permitted Wait/Retry visible |
| Resolved provider history | 6 rows, collapsed when included, mutation buttons hidden |
| Current ownership rows | 0 |
| Ownership policy | Enabled; `PB_ORDINARY_AUTO_CONTINUATION_V1`; automatic 0 / manual 0 / deep 0 |
| Ownership headline | `No action required` |
| Ownership history | 13 rows: 10 PUBLISHED, 3 SUPERSEDED; collapsed; no action buttons |
| Technical codes and source evidence | Preserved in details/tooltips |
| Runtime/source baseline comparison | Unchanged except the intentionally edited UI code fingerprint |
| Backup file inventory | All 53 retained files unchanged |

The active generation was `pb_ownership_719201a6f6f4497bb6a3e1ada35b81b6`, provider watermark `2026-10-28`, journal COMPLETED with postflight PASSED and recovery NOT_REQUIRED. No live workflow, publication, approval, queue write, financial DB write, active-generation change, scheduler-config change, journal write, or backup deletion was invoked. Existing runtime/unrelated worktree artifacts remain excluded from the source commit.

Local evidence is under ignored `temp/fundamentals_review_ux_20261029/`: initial/final fingerprints, read-only data, test logs, replay script, and replay result. It is excluded from the commit. A later replay attempt correctly failed before reading/rendering because an independent Stockcore daily Yahoo run held the shared scheduler lock; no process was stopped or lock bypassed.

Final closeout used read-only fingerprint inspection, without invoking a workflow or acquiring/overriding that scheduler lock. `closeout.json`/`closeout.log` confirm that the full runtime/source baseline still matches the original snapshot, with only the intentional UI code fingerprint changed. This is a separate non-mutation check, not a claim that the lock-blocked replay executed. The successful earlier replay and the final 28-test wording regression provide the rendering evidence.

## Remaining limits

Validation uses the real headless Flet control tree, not a running desktop/browser screenshot. Provider history still uses the existing opt-in checkbox before its collapsed group appears. The separate accounting-boundary panel (one retained review in this state) is unchanged and remains identified separately in the provider status. Unregistered diagnostic cases expose existing read-only evidence only; this presentation phase does not introduce a registration or investigation workflow.
