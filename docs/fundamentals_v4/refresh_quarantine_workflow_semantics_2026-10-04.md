# Refresh quarantine and workflow stop semantics

Date: 2026-10-04

Decision: `CURRENT_STOP_BEHAVIOR_IS_INTENDED_CONTRACT`

## Observed case and decisive distinction

Reviewed Preview: `20261004T132346Z_refresh_fundamentals_bee6f4d28686`.
Read-only result/Preview artifacts show:

- safe_changes = 0; effective_changed_known = 0;
- held_for_review = 1; global_blockers = 0;
- NO_EFFECTIVE_CHANGE = 20; NOT_IN_CANONICAL_UNIVERSE = 100;
- future_test_authorized = false; outcome = REVIEW_REQUIRED.

KO is TICKER_LOCAL_REVIEW / PROVIDER_ANOMALY_SUSPECTED and remains OPEN.
Its candidate financial consequence is retained prior state, not an approved source
replacement. This investigation does not decide whether its missing source rows
are legitimate, approve retention, or change its evidence.

The case is NOT a held ticker stopping other safe effective changes. There are
zero such changes. The partition's safe_tickers field also includes non-mutating
classifications, so its length must not be confused with safe_changes.

## Exact stop path and history

`refresh_review_queue.partition_changes` separates safe classifications, proven
local holds and global blockers. `refresh_fundamentals.run_preview` derives
replacement only from safe classifications in REFRESH_REPLACEMENT_CLASSES.

The outcome order is explicitly:

1. Global blockers -> REVIEW_REQUIRED.
2. Nonempty safe replacement set -> COMPLETED, even with local holds.
3. No replacements but local holds -> REVIEW_REQUIRED.
4. Neither -> NO_CHANGE.

future_test_authorized additionally requires a manual Preview, a nonempty safe
replacement set, no global blockers, complete discovery and publication-date gates.
`full_workflow.run_operation_workflow` stops when Preview is not COMPLETED with
bound path/fingerprint, and separately checks future_test_authorized. Its NO_CHANGE
branch completes after Preview without Test/Production.

`refresh_copy_runtime.revalidate_bound_source` independently refuses an empty safe
replacement set. Thus merely bypassing the parent gate cannot safely authorize
this case under the existing contract.

The same four-way outcome order already exists in original quarantine commit
`bbe9b68e`, not just in current HEAD. The accepted contract in
`fundamentals_v4_phase13g3_44_refresh_review_queue.md` says local holds do not block
SAFE UPDATES; its acceptance fixture contains two safe revisions plus one hold.
The original full-workflow contract also avoids Test/Production on no-op refreshes.
There is no contract requiring publication of an unchanged generation when only
review items remain. No workflow-gate regression is proven.

## Review taxonomy

| Existing class | Financial consequence | Workflow behavior | Later mutation |
|---|---|---|---|
| GLOBAL_BLOCKING_REVIEW | Cannot prove isolation or accepted-state safety | Stops regardless of safe peers | Resolve global uncertainty first |
| Proven ticker-local unsafe candidate change | Reject/quarantine proposed values; retain entire accepted ticker state | Safe peers may proceed; unproven locality becomes global | Evidence-bound review required before applying held values |
| TICKER_LOCAL_REVIEW with safe retention | No held ticker provider/canonical financial mutation | Continue if safe replacement peers exist; review-only Preview stops | OPEN review remains; approval is not needed to update safe peers |
| Non-mutating/informational classifications | NO_EFFECTIVE_CHANGE or excluded unknown-universe ticker | Not replacement authorization; no-op branch only if no holds/global blockers | Separate existing identity/add-ticker workflow where applicable |

These are interpretations of existing classes, not new enums or resolver rules.
The proven-local fiscal revision class added in phase 13G.3.55 also quarantines
unapproved provider changes and preserves prior ARQ-backed canonical financial state.

## Downstream safety and exact binding

Test and Production re-fetch/reclassify held tickers and bind the entire source
evidence plus partition fingerprint to the exact Preview. Expansion/shrinkage,
held-to-safe transition or locality drift requires a fresh Preview; no new source
response may silently substitute for the bound partition.

Only safe replacement histories enter provider replacement. Held companies remain
unaffected in the canonical rebuild, which checks unexplained changes outside safe
company IDs. Existing quarantine evidence verifies provider/canonical financial
preservation. V2/RP/RV recomputes from accepted retained state and current shared
inputs, not unreviewed held provider values. Derived peer-relative outputs may
legitimately change; quarantine is not a freeze of derived analysis.

The candidate-publication integration remains unchanged: core candidate validation,
bounded enrichment, final integrity/hash/manifest, activation. This review introduces
no alternate Production path and no post-activation write.

## Queue lifecycle and LITS

KO's stored queue row is OPEN with operator_action NULL and no resolution timestamp.
No approval or queue update was performed here.

LITS is RESOLVED with ACCEPT_RETAINED_HISTORY. Its first referenced Preview,
`20261001T041556Z_refresh_fundamentals_6bca53782d6c`, had 18 safe changes,
three local holds AND one global blocker. Its REVIEW_REQUIRED result cannot be
attributed to local holds alone. This is a narrow lifecycle check, not a data review.

Phase 13G.3.51 approval is not just queue clearing: it authorizes retention of an
exact evidence set for that ticker, consumed through normal Preview/Test/Production.
It is not prerequisite permission for unrelated safe peers to proceed. Approval
and subsequent production-consumption semantics are unchanged.

## Validation

Five narrowly selected existing tests passed:

- Preview review never invokes Test;
- NO_CHANGE completes after Preview without writes;
- real copy Full Workflow quarantines YYAI while publishing two safe tickers;
- global review stops fail-closed;
- Test rejects a tampered safe/held partition.

The safe+hold fixture verifies OPEN queue visibility, held provider/canonical
financial fingerprints, normal downstream recomputation and safe peer publication.
No unrelated score/valuation/DC suites or full suite were run.

Latest production Preview artifacts were copied to
`/tmp/rawcandle_ko_workflow_replay_ev8lovts` and replayed through the existing parent
workflow with forbidden Test/Production callbacks. Result: STOPPED after Preview;
neither callback was invoked. No live acquisition or production workflow was run.
The replay reproduces the authorization decision, not a new KO source-evidence review.

Current pre/post hashes matched for active provider/canonical/analysis, forecasts
and the operational review queue. Production financial DB writes: 0. Forecast DB
writes: 0. Scheduler/systemd changes: 0. Existing unrelated worktree changes retained.

## Reporting and recommendation

No source, gate, status, queue or binding change is made. The generic stop headline
mentions review but does not explain the decisive zero safe-change count. The
Preview's generic recommended-next-action text must not be read as authorization:
future_test_authorized=false and backend source-binding gates are authoritative.
These are reporting limitations, not proof of the hypothesized quarantine defect.

Next operator action: review KO-specific persisted evidence separately, approving
only an exact supported operator action if justified, then run a fresh normal
Preview. If safe effective changes appear, local OPEN holds already permit those
changes to continue. If the desired policy is instead a successful no-op outcome
WITH open reviews, request that explicit status-policy change separately; do not
force Test/Production of an unchanged generation.
