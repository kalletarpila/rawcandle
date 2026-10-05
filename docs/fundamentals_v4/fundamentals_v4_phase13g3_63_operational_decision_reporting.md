# Phase 13G.3.63: Operational decision reporting

Date: 2026-10-05 (Europe/Helsinki)
Starting HEAD: 8d679a91e68ddf8a7aefa05e7edd8d87f7af8214.

## Observed problem and authoritative source

A Preview with zero safe changes, one local hold and no global blockers could
be described as stopped because a ticker required review, with generic advice
to proceed to Test. The hold was real, but there were no publishable peer changes
for it to block. Item review state is not workflow authorization.

Local review/quarantine state and workflow authorization are separate concepts. A local hold does not imply that it blocked publishable peer changes.

Recommended actions are rendered from authoritative backend workflow authorization and must never recommend Test when future_test_authorized is false.

The authoritative Preview inputs are its existing safe replacement set,
review_partition held/global lists, and future_test_authorized. The existing
manual-trigger, complete-discovery and publication-date gates are unchanged.
The decision helper does not authorize execution; it presents those decisions.
The normal Full Workflow stage progression and publication gates are unchanged.

## Decision schema

New backend artifacts carry operational_decision at top level, and also inside
refresh_preview for Preview evidence. The shared builder is
rawcandle.fundamentals.admin.refresh_operational_decision:

```text
schema_version = 1
authoritative_stage
safe_effective_changes
held_item_count, held_items
global_blocker_count, global_blockers
test_gate: authorized, reason_code
production_gate: state, reason_code
decision_code, decision_text
recommended_action_code, recommended_action_text
local_hold_blocked_safe_changes
```

The gate field names avoid the existing generic secret-redaction rule for
authorization-named fields. No secret-redaction rules were weakened. Reports use
"Production authorization state" to preserve the displayed state through text
redaction. Persistence/read-back is covered by regression tests.

Technical Preview failures retain diagnostic text with unknown safe-change
count when classification was not completed. Technical failures take precedence
over holds, global blockers and ordinary business-decision text.

## Test and Production semantics

- No safe changes: no Test or Production required; Production NOT_APPLICABLE,
  reason NO_SAFE_CHANGES_TO_PUBLISH. Local holds remain independently open.
- Safe changes with backend Test authorization: RUN_TEST. Local holds do not
  block peers; Production NOT_EVALUATED, reason TEST_MUST_COMPLETE_FIRST.
- Safe changes without backend Test authorization: REVIEW_TEST_GATE and the
  actual backend prerequisite reason, never RUN_TEST.
- Global blockers: RESOLVE_GLOBAL_BLOCKER, Production NOT_AUTHORIZED with
  GLOBAL_BLOCKER_PRESENT. Holds are not the workflow-level blocking reason.
- Technical failure: REVIEW_TECHNICAL_FAILURE, Production NOT_AUTHORIZED.
- Completed Test: reuse load_production_authorization against durable bound
  Preview/Test/source-binding artifacts. Only this existing gate's successful
  validation yields AUTHORIZED/MATCHING_SUCCESSFUL_TEST_VALIDATED. Validation
  denial is exposed as NOT_AUTHORIZED with its existing reason; no second
  Production authorization policy was implemented. A legacy completed Test
  without new decision evidence cannot invent authorization facts.
- Production result: latest stage decision records completion or actual failure.
  AUTHORIZED describes the checked evidence binding, not a promise that later
  source-revalidation, lock, recovery or publication checks will pass.

local_hold_blocked_safe_changes is false for local holds in the accepted peer
quarantine path, including zero-safe-change runs. With no local hold it is null,
rendered NOT_APPLICABLE. No global blocker is attributed to a local hold.

## Reports, UI and history

Preview, Test, Production and Full Workflow reports render a shared
"## Operational Decision" section immediately after Executive Summary. It shows
safe changes, held items, global blockers, Test authorization/reason, Production
state/reason, local-hold blocking meaning, decision and next action.

Full Workflow terminal_summary and root result contain the latest decision.
New terminal headlines and recommended actions come from that object, not item
counts. Technical stage failures replace an older successful decision; diagnostic
and child-stage evidence remain available. Reporting-integrity stops also retain
technical semantics.

Item-level local-hold advice is "Review this ticker separately. It remains
quarantined." Global item advice addresses its review evidence. Neither row
instructs Test independently of the workflow gate.

FundamentalsAdminUIService exposes the same operational_decision on its result.
Existing summary controls render shared backend rows, with no new UI gate logic
or duplicate decision counters. Historical rendering without a decision retains
its existing fallback; old reports are not rewritten. New terminal summaries
remain usable after child evidence directories are unavailable, without markdown
parsing or eager child loading to recover the decision.

## Focused validation

Decision-unit and integration tests cover:

- Zero safe changes with zero, one and multiple holds.
- Safe changes with/without holds and authoritative Test permission/denial.
- Global blockers with zero/nonzero safe changes and alongside holds.
- The invariant that false Test authorization cannot yield RUN_TEST.
- Preview technical failure, Test failure, stale binding and latest-stage authority.
- Production NOT_EVALUATED, NOT_APPLICABLE, NOT_AUTHORIZED and AUTHORIZED.
- Item advice, persisted decision read-back, self-contained terminal results,
  UI rendering from backend data and legacy rendering.
- Existing quarantine, binding, reporting and UI regressions.

Passing selections (86 tests total; not repository-wide):

1. tests/test_refresh_operational_decision.py,
   tests/test_fundamentals_admin_refresh_full_workflow.py and selected
   tests/test_fundamentals_admin_refresh_preview.py: 55 passed, 27 deselected.
2. Relevant Fundamentals Admin UI/history/report subset: 15 passed, 44 deselected.
3. Production authorization/report and review-quarantine subset:
   12 passed, 107 deselected.
4. Exact isolated parity fixtures for local hold plus peers, global blocker and
   stale Test source binding: 4 passed.

The legacy YYAI fixture was explicitly set to existing review_years=0 for its
hold-specific test. Under today's accepted three-year policy its old prefix is
legitimately age-exempt and no longer produces a hold. This test-only override
does not alter production classification or default policy. Its later hold-only
Preview verifies the zero-safe-change regression against the actual backend.

Initial focused failures found secret redaction of gate fields, the old
fixture-policy mismatch and generic child messages hiding technical decisions;
all were corrected locally and rerun. Compile/import
validation and git diff --check passed. The full suite was not run.

## Safety and boundaries

No live refresh or scheduler was executed. Workflow fixtures used isolated
temporary databases/fake providers. Production provider/canonical/analysis
files, operational Review Queue, active-generation pointer, publication journal
and scheduler configuration were checked by pre/post SHA-256 and unchanged.
No active-generation mutation, backup deletion, systemd/timer change or push.
No phase-owned large runtime files were created in the repository.

Result-publication authority/resolver, 100 retry cap, uncapped NEW_THIS_REFRESH,
60-day horizon, manual drain, persistent-open handling, review approval actions,
quarantine classification, immutable activation and recovery remain unchanged.
Pre-existing dirty runtime artifacts are excluded from the source/tests/docs
commit and left in place.
