# 13G.3.83 — Test/Production visibility in Run History

Date: 2026-10-08. Result: **PASS — current real-artifact discovery validated;
missing explicit history Refresh fixed**.

The supplied hypothesis of a Test/Production discovery or classification defect
does **not** reproduce with current source and the actual persisted artifacts.
A fresh default history query already returns Production, Test and Preview as its
three newest rows, each Completed, 17 changed tickers, Administration run.
No parser, mode whitelist, execution or publication change was warranted.

## Evidence and separate causes

Only the three specified manual run directories, the existing 2026-10-08 scheduler
history entries and targeted history/UI code/contracts were investigated.

| Stage | Durable Administration run ID | Started UTC | Completed/displayed UTC |
|---|---|---|---|
| Preview | `20261008T173613Z_refresh_fundamentals_f8b949dda174` | 17:36:13 | 17:36:51 |
| Test on copies | `20261008T173737Z_refresh_fundamentals_b97b94e0bcf7_test` | 17:37:37 | 17:49:30 |
| Production update | `20261008T175341Z_refresh_fundamentals_b97b94e0bcf7_production_aec4c4b9` | 17:53:41 | 18:04:46 |

All times are from `result.json` on 2026-10-08; no directory mtime or fabricated
timestamp is substituted. Each row links to its own directory's
`operation_report.md`. The Test report records Production authorization
`AUTHORIZED / MATCHING_SUCCESSFUL_TEST_VALIDATED`. The Production report records
COMPLETED, postflight PASSED and the already-published generation/watermark.
Those are historical facts; this investigation did not execute either operation.

**Test:** its timestamped directory matches `_ADMIN_RUN_ID`; structured result mode
`COPY_ONLY_APPLY` is already in `_ADMIN_MODES[REFRESH_FUNDAMENTALS]` and maps to
“Test on copies”. Its valid request/result files are neither technical nor corrupt.
`summary_counts.effective_changed_known` is 17. No filtering, deduplication or
parent suppression excludes it from a fresh query.

**Production:** its durable operation directory exists separately from the active
generation `refresh_…`. The operation result mode `PRODUCTION_APPLY` is already
supported and maps to “Production update”. Its result has no embedded `request`,
but history correctly reads the separate valid `request.json`; this is not a
discovery defect. Its authoritative changed-known count is 17, not the canonical
quarter count. No generation-derived or fabricated history row is needed.

**Reproduced shared UI defect:** `AdminHistoryCursor` enumerates candidate directory
names once and caches projections. `DeferredLoadController` intentionally reuses a
LOADED route. If the view loads after Preview but before continuation artifacts
arrive from another session/process, neither Test nor Production exists in that
cursor's candidate snapshot. A fresh service query sees both, while the existing
view retains Preview. Returning to the loaded route does not rescan. The existing
performance contract promises explicit Refresh, but this page had no such control;
filter toggling or rebuilding the page were the available workarounds.

The original browser session and loaded source version are not retained, so its
exact causal history cannot be proven from durable run artifacts. In particular,
current `apply_result` already forces refresh after same-page operations. We do not
claim that current discovery drops all continuation runs, or that the original
omission was conclusively caused by this cache path. The bounded regression proves
and fixes the current stale-session recovery gap without inventing a parser defect.

## Bounded UI fix

`dev_tools/fundamentals_admin_page.py` now exposes **Refresh run history** beside the
Run history title. It invokes the existing `refresh_history(force=True)` path:
invalidate this route's deferred generation, create a fresh cursor, reset the visible
limit to eight and reload using the currently selected technical filter. The button
is disabled during deferred loading and re-enabled on success/error.

Loaded-route reuse and incremental Show more remain unchanged. The fix introduces
no eager history load, polling, broader directory scan, new classification, alternate
artifact layout or changes to Preview/Test/Production execution. It does not require
turning on Show technical and legacy runs.

## Existing identity, filter and deletion safety

The deterministic row identity remains the durable Administration run directory ID.
Preview, Test and Production have three different IDs, so they remain distinct.
Several artifacts within one directory do not create multiple rows. Generation,
journal and backup evidence are not extra logical Production operations. Technical
and legacy evidence stays hidden by default and remains available with the filter ON.
The existing scheduler Full workflow parent and scheduler Preview child presentation
is unchanged; no new parent/child suppression or grouping is introduced.

The cursor retains deterministic newest-first run-ID ordering and bounded projection
reads. The initial eight and subsequent 16/24 visible rows include the continuation
runs normally. Refresh resets to eight; Show more continues the new cursor.

Existing controls provide details and exact operation-report download for each
manual stage. History deletion uses `AdminRunHistory.hide_run`, which records only
the ID in `.hidden_runs.json`; it retains operation artifacts as audit evidence.
It does not delete financial generations, rollback backups or publication journals.
Backup cleanup is a separate existing action and was not executed or changed.
Deletion tests operate only on temporary fixtures, never the live history registry.

## Validation

Real-artifact read-only validation used the actual default service with startup
recovery disabled and the actual Admin component with the existing headless page
adapter. The default first eight rows already included the three real manual stages
before this fix. After the UI fix, initial load and explicit Refresh include them
once each, newest first, with correct times/modes/results/counts/category/report
paths. Info and download callbacks resolve each correct operation report. The
technical filter preserves all three; the scheduler Full workflow row remains
correct. No browser session or active-generation deletion was performed.

New compact regression fixtures retain the real manual chain's IDs, modes and
timestamps, including Production's separate request layout. They verify discovery,
normal/technical filtering, uniqueness, scheduler parent presentation, late-arriving
Test/Production in synchronous and deferred UI paths, info/download controls,
8/16/24 paging/reset and hide-only Production deletion. Deferred tests use the
existing deterministic inline thread bridge; the existing deferred-controller group
checks loading deduplication, stale-generation rejection and disconnect safety.

```sh
pytest -q tests/test_fundamentals_run_history_continuations.py tests/test_deferred_ui.py
# 7 passed in 8.78s
pytest -q tests/test_fundamentals_admin_ui.py -k 'history or download'
# 19 passed, 40 deselected in 8.78s
```

**26 targeted/regression tests passed.** Existing history tests additionally cover
bounded parsing without rereads, legacy/corrupt/symlink behavior, equal timestamps,
cross-page ordering and safe report routing. No full suite or broad Fundamentals
execution group was run. Syntax checks and `git diff --check` passed.

## Production invariance and commit scope

Pre/post SHA-256 comparisons passed for active provider/canonical/analysis roles,
active manifest, publication journal, operational Review Queue, scheduler config,
market/taxonomy files and existing WAL state, and ownership registries. Thus financial
state, watermark, Review Queue, P/B, scores and scheduler configuration remain intact.
The already-active generation remains
`refresh_20261008T175341Z_refresh_fundamentals_b97b94e0bcf7_production_aec4c4b9`.
No refresh, provider request, publication/recovery, scheduler operation or live
history hiding/deletion was executed.

The [compact validation CSV](fundamentals_v4_run_history_test_production_visibility_validation.csv)
records the actual three rows, artifact/report hashes and protected live hashes.
Detailed temporary evidence remains under `/tmp/history_visibility_*` outside Git.
Only the bounded UI change, focused tests, report and CSV are committed. Existing
unrelated worktree changes are preserved. Nothing is pushed.
