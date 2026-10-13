# Full workflow cleanup delegates to the exact Production child

Refresh Fundamentals Full workflow parents now surface their exact Production child's acceptance/cleanup state. The parent remains a workflow record and never owns rollback backups, cleanup evidence or acceptance state. No real cleanup was executed in this phase.

## Reproduction and root cause

Read-only inspection of the five persisted scheduler parents dated 2026-10-09 through 2026-10-13 reproduced `NOT_ELIGIBLE / Run is not a Production update` for every parent. Their child results completed successfully and had their own valid cleanup states.

There were two causes: Run History rendered cleanup controls only for rows whose stage was `Production update`; selecting a parent called `cleanup_eligibility(parent_id)` directly, which passed `mode=FULL_WORKFLOW` to the existing Production-only inspector. That inspector correctly rejected the parent. The backend was not defective: only the Production child owns the backups.

The exact existing parent `stages` array identifies one `stage=Production update` record with its `run_id`. This relation, rather than the date/count/run-name suffix, is now the cleanup selection authority.

## Exact resolution and ownership

`FundamentalsAdminUIService.resolve_cleanup_target` requires:

- Parent mode `FULL_WORKFLOW`, operation `REFRESH_FUNDAMENTALS`, and exact result/directory run ID.
- Exactly one explicit Production update stage reference; a recorded failed/non-completed stage cannot delegate.
- An existing regular child result in its exact safe run directory, with matching run ID and operation.
- Child `mode=PRODUCTION_APPLY` and `outcome=COMPLETED`.

Missing, duplicate, self-referencing, mismatched, failed, symlinked or unsafe child references fail closed. A workflow without Production never receives an active cleanup delegation. Ordinary standalone Production selection retains its existing target and backend path.

The resolver reads only the selected parent and its explicitly named child. It does not search sibling runs, infer relationships from time/count/suffix or copy reports. The service adds `cleanup_target_run_id` and `workflow_parent_run_id` as transient selection provenance; the child's own `run_id`, inspector status and evidence remain authoritative.

## UI states and selected details

For visible Refresh Full workflow rows:

| Child inspector state | Parent presentation |
| --- | --- |
| ELIGIBLE | Existing acceptance/cleanup icon, operating on the child |
| ALREADY_CLEANED | Existing disabled Backups cleaned indicator |
| NOT_ELIGIBLE / missing or invalid target | No destructive action; details explain the state |

Zero retained backups do not create an acceptance requirement: the existing child inspector determines applicability. No cleanup status or inventory is fabricated from workflow report prose.

The selected details remain the parent's workflow summary/progress. A separate cleanup status identifies the exact Production child, state, verified retained/deleted count and acceptance availability. For already-cleaned children, it identifies the child `backup_cleanup.json`. Rejected inspector defaults are not displayed as a verified zero-backup inventory; they are marked not verified.

Parent info and downloads still open the workflow artifact. Parent hide/delete remains parent-record-specific. Technical child info/download and its own cleanup control retain their child targets. Only cleanup selection delegates.

## Explicit authorization and revalidation

Opening the parent action reruns resolution and the existing child inspector without using cached relationship evidence. Its confirmation identifies both the Full workflow parent and the exact Production child, child eligibility, exact backup count/bytes and paths. Historical terminal receipt identity, when supplied by the existing inspector, is included without reconstructing or weakening it.

Confirmation passes the child ID, parent context and displayed eligible state to the service. Under the existing UI operation lock, the service freshly resolves the parent reference, requires the same child, reruns child eligibility and rejects changed applicability, inventory or receipt state. A changed child reference is rejected rather than authorizing the new child. Already-cleaned child state follows the existing idempotent child path.

Only the existing `run_acceptance_cleanup.accept_run_and_cleanup_backups(child_id)` boundary performs deletion. Its Production/scheduler locks, final verification, exact role/path/hash/size ownership, journal/recovery/generation/receipt gates and SQLite checks are unchanged. The cleanup audit is written only in the child directory. No parent cleanup audit or parallel acceptance mechanism is added.

This layer treats current and historical inspector evidence as opaque authoritative child evidence. It does not duplicate acceptance policy, invent journal exceptions or impose a current-generation-only restriction.

## Bounded performance and view consistency

History listing/grouping itself does not inspect cleanup eligibility. Rendering checks only visible Production rows and Refresh Full workflow parents, using the existing per-page cleanup cache. The resolver reuses the cursor's parent/child projections where available. At most the exact selected child's result is read when uncached; no new broad history scan is introduced.

Eligibility is needed to decide whether the visible action is genuinely available, so the existing inspector is invoked per visible relevant row. Confirmation always forces a fresh read. A 24-workflow fixture proves only 8/16/24 visible children are inspected as those pages are requested, with no sparse pages or hidden-child page consumption.

After cleanup, cached cleanup presentation is invalidated and visible parent/child representations reload the child's state. If a technical child action is used while its parent is selected, the parent details also regain the exact delegated identity and cleaned evidence. Explicit history refresh clears cleanup presentation caches as well as the cursor, so external child cleanup is reflected. Existing grouping, Scheduler provenance, newest-first order, legacy toggle and stale-cursor behavior remain intact.

## Real recent-run read-only validation

The following are exact persisted `stages[].run_id` relationships, with results confirmed through the updated service and unchanged child inspector:

| Date | Parent run ID | Production child run ID | Child status | Actual retained backups | Parent UI state |
| --- | --- | --- | --- | ---: | --- |
| Oct 9 | `20261009T041942Z_refresh_fundamentals_d00eb7239fed_full_workflow_93987c90` | `20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771` | ALREADY_CLEANED | 0 | Cleaned indicator |
| Oct 10 | `20261010T042320Z_refresh_fundamentals_d00eb7239fed_full_workflow_8552c42c` | `20261010T043039Z_refresh_fundamentals_f430ff5db759_production_e44c51cc` | ELIGIBLE | 3 | Child cleanup action |
| Oct 11 | `20261011T022057Z_refresh_fundamentals_d00eb7239fed_full_workflow_39c2cf5b` | `20261011T023241Z_refresh_fundamentals_a5d42147ca13_production_f0648359` | ELIGIBLE | 3 | Child cleanup action |
| Oct 12 | `20261012T022054Z_refresh_fundamentals_d00eb7239fed_full_workflow_68114f5f` | `20261012T023210Z_refresh_fundamentals_ed1f9548aa17_production_ddcb7101` | ALREADY_CLEANED | 0 | Cleaned indicator |
| Oct 13 | `20261013T041843Z_refresh_fundamentals_d00eb7239fed_full_workflow_0538b308` | `20261013T042603Z_refresh_fundamentals_3d9f10e1f3f2_production_25d220d5` | ELIGIBLE | 3 | Child cleanup action |

The Oct 9/12 cleanup records predate this task. Their inspector's historical deleted count is not a retained-backup count; actual file existence was checked separately. This phase inspected only: it did not accept, delete or rewrite any real child or parent evidence.

## Focused validation

```
python3 -m pytest -q tests/test_full_workflow_cleanup_delegate.py \
  tests/test_run_history_scheduler_grouping.py \
  tests/test_fundamentals_run_history_continuations.py \
  tests/test_fundamentals_admin_run_acceptance_cleanup.py \
  tests/test_fundamentals_refresh_scheduler_full_workflow.py
# 89 passed
```

Coverage includes parent ELIGIBLE/ALREADY_CLEANED/NOT_ELIGIBLE controls, exact child-only inspector/backend calls, parent-oriented details, explicit authorization inventory/identity, changed reference/eligibility/inventory/receipt rejection, current/historical evidence passthrough, absent/ambiguous/failed/mismatched/unsafe children, standalone and technical behavior, parent/child downloads, hide-only semantics, idempotence, refresh after external child cleanup, technical-child cleanup updating selected parent, grouping, bounded 8/16/24 paging and stale cursors.

A tiny synthetic SQLite cleanup invokes the unchanged deletion boundary, verifies exactly three selected backups disappear, only a child cleanup audit exists, the parent result stays byte-identical, and repeated parent selection uses child idempotence. No test deletes real backups. One directly relevant scheduler Full workflow regression group and the existing acceptance/cleanup regression group passed. No full suite was run.

## Production invariance and scope

Before/after SHA-256 checks matched for **130 protected files**: active provider/canonical/analysis databases, pointer/journal, Review Queue, scheduler configurations and all inspected parent/Production-child runtime artifacts. All history directory names remained unchanged. A bounded metadata inventory of **57 backup entries** also matched exactly.

No real acceptance or cleanup, Fundamentals Production execution, financial/publication authority mutation, watermark change, Review Queue mutation, scheduler configuration change, history rewrite, report rewrite or backup deletion occurred. The core acceptance/cleanup backend is unchanged. Unrelated pre-existing worktree changes remain excluded from the scoped source/test/documentation commit. Nothing is pushed.
