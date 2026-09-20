# Phase 13G.3.5 - Refresh Full Workflow and Scheduler Discovery

## 1. Outcome

Phase 13G.3.5 succeeded in fixture and read-only scheduler acceptance. Refresh Fundamentals now supports a manual full workflow and optional scheduler Preview discovery through the same backend. Unattended Test and Production remain structurally unavailable to the scheduler.

## 2. Generic Workflow Adapter

`WorkflowOperationAdapter` contains only operation identity, label, normalized request identity, trigger source, and the three existing stage callables. `run_operation_workflow` owns durable stage progression and reporting. Add Tickers and Refresh wrappers retain their domain-specific inputs and summaries; no Refresh business logic moved into orchestration.

## 3. Refresh Full Workflow

The UI action calls the existing Refresh Preview, Test on copies, and Production update implementations in order. Production therefore retains source rechecks, candidates, validation, storage preflight, backups, journal, postflight, rollback, and recovery without duplicated code.

## 4. NO_CHANGE Behavior

Preview `NO_CHANGE` completes the workflow successfully after one stage. Test, Production, backup, candidate rebuild, and journal are not invoked. The report states: `No relevant Sharadar fundamentals changes were found. No database updates were required.`

## 5. Stop/Failure Semantics

Only Preview outcome `COMPLETED` with its bound payload/fingerprint can authorize Test. Review, incomplete discovery, source trust failure, or any other Preview outcome stops fail-closed. Test failure stops before Production and requires a fresh Refresh chain. Production failure is propagated; `RETRY_REQUIRED` stops without an automatic retry or workflow restart.

## 6. Child Reports

Each invoked child keeps its normal `result.json`, progress/status, `operation_report.md`, technical evidence, exit code, and manifest. The parent stores child run IDs and report references but does not copy child event streams or inline child reports.

## 7. Workflow Report

Every workflow writes `workflow_result.json` and concise `workflow_report.md`. Refresh reports trigger, outcome, duration, final stage, source counts, classification counts, child stage table, provider/canonical/first-public impact, V2/RP/RV, watermark, postflight, rollback/recovery, warnings, and child report paths.

## 8. Workflow Durability

Parent result, progress status, progress events, heartbeat, current stage, child IDs, normalized request identity, trigger, timestamps, stop reason, retry state, warnings, and report references are persisted under the standard Admin run directory. Page refresh therefore reads durable workflow state rather than relying on memory.

## 9. UI State

Fresh Refresh state enables Preview and Run full workflow. Manual Preview disables full workflow for that chain and may enable Test. Successful Test enables Production. While a workflow runs all actions are disabled. Full-workflow `NO_CHANGE` or success resets to fresh state. Scheduler Preview evidence never authorizes manual Production.

## 10. Trigger Source

Manual workflow and manual child stages persist `MANUAL`. Scheduler Preview persists `SCHEDULER`. Trigger source is presentation/audit metadata and is excluded from request/source semantic fingerprints and change classification.

## 11. Scheduler Discovery

`run_scheduler_refresh_discovery` invokes the normal Refresh Preview backend with `trigger_source=SCHEDULER`. Its interface exposes no Test, Production, or full-workflow callable. Outcomes normalize to `NO_CHANGE`, `CHANGES_FOUND`, or `FAILED`, with normal Preview run/report references.

## 12. Scheduler Policy

Configuration key `fundamentals_refresh_preview_enabled` follows the existing scheduler config model and defaults to `false`, including when absent from an older config. There is no scheduler Production flag. No cadence was added; when enabled, discovery runs as a post-step of the already configured scheduler invocation.

## 13. Pending Refresh Visibility

The Admin service finds the latest scheduler-triggered Refresh Preview with effective known changes and exposes timestamp, known changes, new quarters, revisions, removals, unknown tickers, run ID, report path, and `production_authorized=false`. The Admin page shows a concise pending-changes status and history marks scheduler-triggered runs.

## 14. Scheduler Concurrency

Scheduler Preview uses the same filesystem Admin operation lock as manual Preview/Test/Production and both full workflows. The surrounding stock scheduler lock/status also blocks concurrent production writers through existing guards. Publication safety is inspected before Preview; unresolved recovery is surfaced as a failed/deferred scheduler section. No new lock hierarchy was introduced.

## 15. Recovery Interaction

Manual full workflow reaches the unchanged Production backend. Prior incomplete publication recovery therefore returns `RETRY_REQUIRED`, stops the current parent, and requires a fresh workflow. Recovery failure remains globally fail-closed. Scheduler discovery does not attempt writes or obscure a nonterminal/failed journal.

## 16. Cleanup Policy

Preview creates no candidates. Existing Test, Production, rollback, and recovery cleanup contracts remain responsible for their journal-bound candidates. Workflow tests verify no candidates, backups, or journal are created by `NO_CHANGE`; child terminal cleanup and nonterminal-backup preservation remain covered by 13G.3.4 journal regressions.

## 17. Add Tickers Regression

The public Add Tickers `run_full_workflow` wrapper, stage behavior, reporting integrity stop, expected no-history continuation, retry behavior, dirty-Git warning, reports, input clearing, and 25-ticker validation remain unchanged. Its focused and broad regressions passed.

## 18. Publication Journal Regression

Refresh full workflow does not modify journal implementation or bypass Production. Happy publication, role-boundary rollback, crash recovery, recovery failure, retry-required behavior, terminal journal behavior, and terminal candidate cleanup all passed in the broad regression.

## 19. Reports

Manual full workflow adds only its lightweight parent report. Scheduler discovery retains the normal domain-centric Refresh Preview report with Trigger metadata. Scheduler totals are fields in the existing `stock_update_scheduler_summary_*.json` generated from `ScheduledStockUpdateRunResult`; no parallel scheduler summary file exists.

The scheduler section records Preview timestamp, normalized result, published baseline, discovered source tickers, effective changed known tickers, all required classification counts, Preview run ID/report, and concise message.

## 20. Runtime

Focused workflow/UI tests completed 77 tests in 10.88 seconds. The broad 422-test Admin, scheduler, provider, canonical, V2, RP, and RV regression completed in 177.47 seconds. Real full-workflow runtime remains the sum of its unchanged child stages.

## 21. Production Safety

No real Refresh full workflow, scheduler Preview, Test, or Production was run against production during development. Fixture scheduler tests were isolated. Final size/mtime and SHA checks confirm the production provider, canonical, and analysis databases are unchanged; read-only market/taxonomy DB size/mtime also remain unchanged. Production Refresh state did not advance.

## 22. Scheduler Enablement State

Capability exists but is disabled. The production `scheduler_config.json` omits `fundamentals_refresh_preview_enabled`, which resolves to the safe default `false`. Enabling it later permits Preview only. Unattended Test/Production/full workflow are unavailable.

## 23. Tests

- Focused final workflow/UI set: `77 passed, 0 skipped, 0 failed`.
- Scheduler config/runner focused set: `129 passed, 0 skipped, 0 failed`.
- Broad required regression: `422 passed, 0 skipped, 0 failed`.
- Touched-module `py_compile`: passed.
- `git diff --check`: passed.

Regression evidence includes two consecutive scheduler Previews against one unchanged published watermark. The second retained the prior historical revision and added the new quarter. Both left Refresh state unchanged. Separate candidate-only/publication acceptance proves only successful Production publication advances the provider baseline.

## 24. Remaining Issues

There is no material 13G.3.5 blocker. Scheduler discovery has no notification delivery beyond existing summary/history visibility. Operational enablement and cadence choice remain explicit operator decisions. Reader-atomic three-file generation activation remains outside this phase.

## 25. Next Phase

A later phase may evaluate unattended scheduler Test/Production only after manual operational history, notification policy, periodic full archive reconciliation, MRQ overlay impact, or reader-atomic generation activation. None is enabled here.

## 26. Git

The intended closure commit is `feat: add refresh workflow and scheduler discovery`. It is not pushed.
