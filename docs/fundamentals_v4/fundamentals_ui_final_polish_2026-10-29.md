# Fundamentals UI final polish — 2026-10-29

Task: `FUNDAMENTALS-UI-FINAL-POLISH`.

This presentation-only follow-up separates current operator work from completed evidence, corrects the approved accounting-boundary record's contribution to landing severity, compacts review/history rows, and puts human summaries before raw technical evidence.

## Landing severity and active versus completed evidence

Previously, every saved accounting-boundary record contributed one active Deep Review item, including WFRD's already `APPROVED` record. The boundary-specific presentation route now treats APPROVED/RESOLVED/PUBLISHED/SUPERSEDED as completed operator work and places their exact records in history/audit. OPEN, STALE, REJECTED, and unknown unresolved statuses remain Deep Review attention items. This changes neither the stored status nor any backend transition or publication entitlement.

In particular, **APPROVED accounting-boundary evidence does not assert PUBLISHED**, and this display rule does not apply to pending P/B ownership approval. Ownership APPROVED/AUTO_CONTINUED remain current pending publication under the existing action-first rules. Genuine current deep ownership diagnostics/cases, publication safety blocks, and workflow failures continue to elevate severity and retain their evidence/controls.

The current landing now shows `REVIEW REQUIRED`, current reviews requiring action 2, deep reviews requiring action 0, and `Next action: Review current exceptions.` Conditional FDX/RRC investigation guidance does not create an active Deep Review item. With no genuine current deep work, the Deep Review section says `No deep review action required` rather than displaying approved evidence as new work.

## Section order and empty containers

After the landing summary/actions, the secondary sections are ordered:

1. Run history and cleanup evidence
2. Review — current exceptions
3. Deep Review — exceptional evidence
4. Advanced — administration tools and workflow stages
5. Technical details, when actual result content exists

Transient preview/progress/final results remain primary when an operation is actually run. Other operations and individual workflow stages remain available under the renamed Advanced section, with their original callbacks, confirmations, and authorization guards. Run-history loading, report downloads, cleanup controls, and cleanup semantics are unchanged.

The top-level Technical details accordion is hidden before any result content is available. A real result makes it available, initially collapsed, with existing errors, summary rows, artifact paths, and hashes intact. Empty review-history containers are hidden. The Deep Review capability remains available with its compact explicit zero-state.

## Provider review compaction and selection

Current provider rows wrap to available space. Their body uses separate short fields instead of a single paragraph-heavy table cell: concise Reason, Recommended now, Then, conditional persistent investigation, and Approval availability. First/last timestamps and run identifiers are no longer primary columns; they remain in retained evidence. Technical reason-code hover blocks and the long binding tooltip are removed. Exact codes and bindings remain accessible through selected Details/raw evidence.

FDX uses the structured interior-key code: interior source key disappeared → Wait for Providers → Retry after later provider/source refresh → investigate source history manually if unresolved. RRC uses the structured same-fiscal replacement code and the stronger old/new source-binding and financial-payload comparison advice. No ticker-specific production logic or prose parsing is used. Missing/unavailable actions are not recommended as available, and the existing backend eligibility still controls all action icons and confirmation callbacks.

Selected evidence is hidden initially. Explicit Info selection reveals `Evidence for <ticker>`, a human summary, and nested raw/legacy technical evidence. Refresh updates an existing selection to its current retained data or hides it if the item leaves the visible population. No automatic selection, queue action, or persistence is introduced.

## Current P/B work versus audit history

The Quarterly P/B ownership review list now contains current nonterminal work only. With no current cases, it shows No action required and concise policy/count information. Existing manual, held, deep, and pending-publication cases retain their current placement/actions; deep ownership cases remain in Deep Review.

Recent PUBLISHED/SUPERSEDED ownership rows move into collapsed `Ownership history / audit` under Run history and cleanup evidence. Rows are compact: ticker · stored status · recorded decision (or short historical classification) · authoritative terminal date. Historical factor-change labels do not say that new review is required. Terminal rows have no approval, hold, or publication buttons; individual evidence remains expandable.

Resolved provider history also lives under Run history, using the existing opt-in history checkbox. Completed accounting-boundary evidence has its own history/audit entries there, preserving exact recorded status, proposal/decision fingerprints, receipt bindings, source identities, and the full raw record. The latest retained Full Workflow summary, publication/ownership history, existing report navigation, and cleanup evidence are consequently grouped together without merging backend contracts.

The existing two-calendar-month review-history cutoff is unchanged. Filtering and compact date display now share the same pure terminal-date function. Provider resolution/publication timestamps and exact P/B publication/supersession authority remain the basis; first_seen never becomes a cutoff. Unknown/ambiguous dates still keep records visible, and current work is never hidden by age. Approved boundary review history is not recast as terminal financial publication to manufacture a timestamp.

## Evidence: summary first, raw JSON second

`review_evidence_presentation.py` supplies pure structured summaries and compact labels. Ownership summaries show, where present: ticker/status/decision, ownership type, old/new provider factor, old/new shares and delta, publication generation, postflight, recovery, cleanup, and action requirement. Absent publication facts are not inferred from status or prose.

Provider summaries expose the operational reason/path and approval availability. Boundary summaries show recorded review status, ticker, ARQ identity/labels, MRQ historical/current bindings, and whether operator review is still required. Publication Preview summaries retain the selected scope and existing validation facts.

Each evidence view places the complete current raw JSON beneath a nested collapsed `Raw technical evidence / JSON` panel. Values, proposal/decision fingerprints, source bindings, and stored evidence are preserved; raw-data equality is tested against input records. The selected provider view also retains its previous detailed technical text inside that nested level. No raw evidence is removed from backend/artifacts or rewritten by rendering.

## Focused validation

**182 tests passed in 9.43 seconds**, covering:

```text
tests/test_fundamentals_ui_final_polish.py
tests/test_fundamentals_review_action_first.py
tests/test_fundamentals_operational_presentation.py
tests/test_fundamentals_recent_history.py
tests/test_fundamentals_admin_ui.py
tests/test_fundamentals_pb_ownership_publication.py::test_admin_ui_separate_publication_preview_and_confirmation
```

The 19 new parameterized cases cover completed versus unresolved boundary routes, FDX/RRC-only landing severity, next action, section order/titles, empty/nonempty technical content, generic compact provider fields, removed hover blocks, exact codes/raw data, explicit selection and clearing, terminal-free current P/B work, compact collapsed audit rows, exact nested JSON, publication/generation/postflight/recovery/cleanup summaries, pending ownership states, and genuine deep policy controls. Existing tests were adjusted for the authorized grouping/labels; eligibility, callback, confirmation, calendar-cutoff, and rendering-purity assertions remain.

Subsequent focused confirmations passed **96 tests in 7.01 seconds** for compact labels/history/action-first behavior and **46 tests in 7.33 seconds** for final polish/operational/publication-confirmation behavior. These overlap the 182 cases and are not additional unique coverage. Final polish history tests use a fixed UTC date. The full suite was not run. No live workflow or publication was used as a test.

The final diagnostic-summary closeout passed **22 tests in 6.99 seconds**; current policy diagnostics also use human summaries before nested raw JSON. The final read-only replay passed again after that presentation adjustment.

## Current-state read-only replay

Result: **PASS**, using real Flet controls with real read-only service methods, startup recovery disabled, and mutating entry points guarded against invocation. The replay holds existing admin/production exclusion locks and a shared scheduler read lock; it neither runs a workflow nor overrides another process's lock.

| Check | Current result |
| --- | --- |
| Landing | REVIEW REQUIRED; 2 current reviews; 0 deep reviews requiring action; Review current exceptions |
| Provider reviews | FDX/RRC OPEN; compact structured guidance; permitted Wait/Retry unchanged; approval unavailable |
| Current P/B | No action required; enabled V1; automatic/manual/deep 0/0/0; no terminal rows |
| Active Deep Review | No deep review action required; no APPROVED WFRD record presented as current work |
| Audit history | 13 compact terminal ownership rows, 6 opt-in resolved provider rows, 1 exact APPROVED boundary record |
| Evidence | Human summaries precede nested collapsed JSON; equality with current source records verified |
| Selection/details | No initial selection; ticker-labelled explicit selection works; empty top-level Technical details hidden |
| Top-level order | Run history, Review, Deep Review, renamed Advanced, conditional Technical details |
| Runtime/backups | Captured runtime/source baseline unchanged except intentional UI code fingerprint; all 53 backup files unchanged |

All currently retained terminal review rows are within the existing cutoff; deterministic recent-history tests verify older rows remain omitted and old active rows remain visible. Active generation remains `pb_ownership_719201a6f6f4497bb6a3e1ada35b81b6`, watermark `2026-10-28`, journal/postflight/recovery COMPLETED/PASSED/NOT_REQUIRED. Read-only local evidence is under ignored `temp/fundamentals_final_polish_20261029/`, excluded from the commit. Validation covers the headless control tree rather than a browser screenshot.

## Safety and limitations

No provider/ownership review eligibility, retained-history compatibility, Wait/Retry behavior, review transitions, P/B V1 policy, native ownership publication, cleanup, immutable generations, journal/recovery, Full Workflow, scheduler config/locking, WFRD semantics, source repair, publication authority, or historical freeze behavior changed. APPROVED boundary evidence is operator-completed history only at the presentation layer.

No Refresh Production, ownership publication, approval, queue write, database/journal/generation/config mutation, or backup deletion was performed. All older audit evidence/artifacts remain stored. Native service/orchestration files are unchanged by this task. Runtime DBs/queues/journal/generations, configuration, temp evidence, copied projects, OHLCV/research outputs, and unrelated worktree artifacts remain excluded from the commit. No push.
