# Scheduler Full workflow Run History grouping

One scheduler Full workflow now appears as one default Run History row. The existing **Show technical and legacy runs** checkbox reveals its exact underlying stages, with Scheduler provenance and a parent reference in the row tooltip. Stored historical records are preserved.

## Actual 2026-10-12 / 2026-10-13 reproduction

Read-only inspection used the eight real `fundamental_reports/admin_runs/<run_id>/result.json` records and their requests. Each execution has four separate Administration records. The parent has `mode=FULL_WORKFLOW`, `trigger_source=SCHEDULER`, a final outcome/summary, and a `stages` array containing explicit `stage`, `run_id` and report references.

| Date | Record | Exact run ID |
| --- | --- | --- |
| 2026-10-12 | Full workflow | `20261012T022054Z_refresh_fundamentals_d00eb7239fed_full_workflow_68114f5f` |
| 2026-10-12 | Preview | `20261012T022054Z_refresh_fundamentals_02e46c09eb2d` |
| 2026-10-12 | Test on copies | `20261012T022129Z_refresh_fundamentals_ed1f9548aa17_test` |
| 2026-10-12 | Production update | `20261012T023210Z_refresh_fundamentals_ed1f9548aa17_production_ddcb7101` |
| 2026-10-13 | Full workflow | `20261013T041843Z_refresh_fundamentals_d00eb7239fed_full_workflow_0538b308` |
| 2026-10-13 | Preview | `20261013T041843Z_refresh_fundamentals_569ddc7da416` |
| 2026-10-13 | Test on copies | `20261013T041920Z_refresh_fundamentals_3d9f10e1f3f2_test` |
| 2026-10-13 | Production update | `20261013T042603Z_refresh_fundamentals_3d9f10e1f3f2_production_25d220d5` |

Each parent `stages[].run_id` names its three exact child records above. No child `parent_run_id` or separate workflow correlation ID is needed. Additional corroborating evidence exists: parent `test_run_id`, Test `bound_preview_run_id`, Production `test_run_id`, and matching bound Preview fingerprints. Grouping uses the explicit parent stage references, not timestamp proximity, calendar day, operation label, adjacency or changed counts.

Both historical Test results actually contain `trigger_source=MANUAL`; their request artifacts omit trigger provenance. Parent, Preview and Production result artifacts contain `SCHEDULER`. The missing badge is therefore a stored provenance defect, not a rendering-only omission.

The current stored authoritative changed count is **4 on Oct 12** and **2 on Oct 13**. The Oct 12 value differs from the task's illustrative observation; it is preserved rather than forced to 2.

## Exact provenance root cause and future fix

`FundamentalsAdminUIService.full_workflow` forwarded the trigger to Refresh Preview and Production, but not to `_copy_apply_unlocked`. `refresh_copy_runtime.run_apply` had no trigger parameter and hard-coded `MANUAL` in both successful and failed Test results.

The workflow now forwards its explicit trigger through `_copy_apply_unlocked` to the Refresh Test runtime. The runtime accepts and validates `MANUAL`/`SCHEDULER`, writes it into the newly created request, and uses it in successful and failed results. Standalone manual Test calls default to `MANUAL`, even if an operator selects an older scheduler Preview. No trigger is guessed from that Preview or nearby history.

These changes affect provenance metadata only; Preview binding, source revalidation, candidate execution, gates, locks, publication, cleanup and resolver behavior are unchanged.

For old records, the history cursor inherits Scheduler display provenance only when a valid scheduler Full workflow explicitly references that child. The old stored `MANUAL` result remains unchanged. Technical entries expose `provenance_inherited=true` for that display correction, while already-correct child provenance remains marked as stored.

## Default selection and standalone safeguards

`AdminHistoryCursor` builds a cursor-local index of the explicit stage references of valid visible scheduler Full workflow parents. A linked child must have:

- Exactly one unambiguous parent/stage reference.
- Matching child result/run-directory ID.
- Matching parent operation type.
- The expected mode for Preview, Test on copies or Production update.
- An ordinary valid Administration classification.

Only a proven child is omitted from default history. The parent stays an Administration run with its own final outcome, count, timestamp and actions. No new run category or visibility toggle is introduced.

Standalone manual Preview/Test/Production, scheduler Preview-only and unassociated scheduler Production rows remain visible. Missing, hidden, corrupt, manual or contradictory parents do not suppress their stages. Ambiguous references and mode/operation/run-ID contradictions leave the child visible. Only stages already explicitly referenced by a persisted parent qualify; unproven/in-flight records are not guessed into a group.

## Technical view and actions

The existing technical/legacy checkbox includes both parent and child records plus the existing legacy/evidence categories. Every proven scheduler child displays the existing `[Scheduler]` Operation label. Its category tooltip includes `workflow_parent=<exact_run_id>` and `scheduler_provenance=stored/inherited`, keeping the flat table and existing columns.

Parent details and downloads continue to target its own workflow artifact (`workflow_report.md`). Each technical child continues to target its own `operation_report.md`. Hide-only history deletion remains record-specific. No child Production cleanup action is attached to the Full workflow parent; child controls retain their existing semantics in technical view.

## Counts, time, paging and refresh

Existing workflow count selection is unchanged: Refresh Full workflow uses `terminal_summary.changed_ticker_count`, falling back to `source_summary.effective_changed_known` under the existing contract. Child counts are never summed. The parent displays its own authoritative completion timestamp: Oct 12 `2026-10-12T02:41:58Z`, Oct 13 `2026-10-13T04:35:56Z`.

The cursor retains existing newest-first durable-run-ID ordering. Proven children are filtered **before** appending a visible entry and before consuming page capacity. `fill(8)`, `fill(16)` and `fill(24)` therefore fill visible rows rather than leaving pages sparse after a renderer-level hide.

Legacy records have no child back-reference, so the minimal safe strategy indexes the existing canonical `_full_workflow` parent directories once per cursor. This name is a discovery hint from the workflow writer's stable-run-ID contract; payload kind, Scheduler origin and exact stage references determine grouping. Nonconforming/unproven evidence remains visible. The index reads workflow parent projections, not every ordinary history result. Parent and child projections share the existing cursor cache and are read at most once per cursor. Ordinary non-workflow history retains its existing incremental read counts. No persistent history index or storage migration is introduced.

Explicit refresh creates a new cursor/index and discovers newly persisted parent/stage references. Checkbox changes also rebuild the cursor. Session snapshot behavior, lazy route loading and the previous stale-cursor refresh fix remain intact.

## Focused validation

Only the directly relevant history groups and one scheduler Full workflow regression group were run:

```
python3 -m pytest -q tests/test_run_history_scheduler_grouping.py \
  tests/test_fundamentals_run_history_continuations.py \
  tests/test_fundamentals_admin_ui.py \
  tests/test_fundamentals_refresh_scheduler_full_workflow.py
```

Result: **91 passed**.

Coverage includes exact parent/child grouping, all three hidden stages, technical provenance inheritance, standalone manual stages, scheduler Preview-only/Production-only, conflicting or absent references, parent final outcomes, authoritative unsummed count, newest-first visible 8/16/24 paging, cache reuse, synchronous/deferred refresh, stale cursor behavior, legacy toggle, parent/child details and downloads, hide-only semantics, future trigger forwarding, and persisted Test provenance on synthetic failure. Existing UI and scheduler lock/config/history regressions are included. No full suite was run.

Real read-only post-change history shows **two default rows** for the two executions and **eight technical rows**, all with Scheduler provenance. Both historical Test rows have the exact correct parent reference and inherited display marker. No Production workflow was executed to validate the UI.

## Production and history invariance

Before/after SHA-256 comparison passed for **127 protected files**: active provider/canonical/analysis databases, active pointer, canonical journal, Review Queue, both scheduler configuration files, and every file in the eight inspected real run directories. The set of **260 history directories** was unchanged.

Financial contents, publication authority, provider watermark, Review Queue, scheduler configuration, runtime reports and stored history are unchanged. No real Production update, history deletion, historical report rewrite or backup cleanup occurred. Policy V1 and resolver code were not edited. All execution tests use temporary synthetic roots/mocks. Pre-existing unrelated worktree changes remain outside the scoped commit; nothing is pushed.
