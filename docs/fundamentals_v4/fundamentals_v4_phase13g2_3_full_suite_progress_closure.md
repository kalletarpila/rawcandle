# Phase 13G.2.3 Full-Suite Closure and Long-Run Progress Contract

Date: 2026-09-15

Outcome: `OUTCOME A — BATCH ADD TICKERS CLI CLOSED, FULL SUITE GREEN, AND SHARED LONG-RUN PROGRESS CONTRACT READY`

Production writes were not authorized and were not performed.

## Baseline

Required prior commits were present:

- `470072e262bf9ef55b648fb8d9aaaf69eac8d952` - Phase 13G.1 administration foundation.
- `b1cbaaeb47314b451a33393ca9422a8464aa9482` - Phase 13G.2 Batch Add Tickers foundation.
- `2d48214e71e57622ca2c28d6390e6cb81f751dd0` - Phase 13G.2.1 downstream adapter finding.
- `56512861b10f50a408af3dcb41730789356869f6` - Phase 13G.2.2 generic Batch Add Tickers downstream adapter and copy-only acceptance.

The retained Phase 13G.2.2 acceptance evidence remains authoritative for ARM, the ten-ticker batch, repeat no-change behavior, rollback restoration and the economic fingerprint `58537b24927a2bc334a481ab11aa5d028676fea4b28100feef1217397cf06280`.

## Full-Suite Failures Closed

`tests/test_fundamentals_v4_company_snapshot_phase9f.py::test_v2_report_formats_values_and_restores_context`

- Failed expectation: hard-coded `n=2199` in the rendered NVDA Snapshot report.
- Current production-shaped source produced `n=2201` for `FUNDAMENTAL_SCORE` and `n=2249` for `ABSOLUTE_VALUATION_SCORE`.
- Resolution: the test now derives expected universe peer counts from the authoritative assembled snapshot rows and still asserts that the rendered report contains those exact counts.
- Cause: stale mutable production-data coupling, not a report-formatting regression and not caused by Phase 13G.2.2.

`tests/test_phase13f3_ticker_transition.py::test_enhanced_listing_population_resolves_former_transition_tickers`

- Failed behavior: accepted successor tickers such as `VAI`, `NXH`, `VMRK`, `IA` and `NMAD` were present as current tickers but were not annotated with transition resolution evidence.
- Resolution: `enhanced_listing_population` now resolves transition rows by both historical ticker and current successor ticker, while preserving the true historical ticker in the audit row.
- NXH remains separated from bankrupt BBBY/BBBYQ by the accepted provider identity and lineage evidence.
- Cause: implementation lookup gap exposed by current production-shaped data, not a reason to change identity or transition rules.

## RV Identity Reconciliation

Read-only evidence is retained in:

- `fundamental_reports/admin_runs/phase13g2_3_closure/production_readonly_pre.json`
- `fundamental_reports/admin_runs/phase13g2_3_closure/production_readonly_post.json`
- `fundamental_reports/admin_runs/phase13g2_3_closure/production_readonly_comparison.json`

The authoritative reader is `rawcandle.fundamentals.admin.rv_identity.active_relative_valuation_identity`, which reads:

```sql
relative_valuation_active_snapshot
JOIN relative_valuation_snapshot USING(snapshot_id)
```

Current production identity in `data/fundamentals_analysis.db`:

- active RV model fingerprint: `76c2974108b2c5085b7dfa102acd4bb04eea36a5267bbdb1930a2bc7dc8cb35e`
- active RV snapshot ID: `1f360f0b2dfd8e06eaffd3edcffaf87b604e59a63d0b0e272823b46fada02f6b`
- as-of date: `2026-09-12`
- created/completed/activated timestamp: `2026-09-13T00:00:00Z`
- active result fingerprint: `9c642e80b06fdbb8c6e703a46a6bda2c7031bc270fbd195b0a3acd7cdeba30f3`
- active source fingerprint: `af0e480b64d57bfc8f65fe2ddf9777cfdf5d7b8afbb801bcf95aaea44ebc61ee`

The earlier `76c297...` evidence was a mislabeled active model fingerprint, not a snapshot ID. The active snapshot ID is `1f360...`. No production RV state change was needed.

## Progress Contract

Added shared administration progress support in `rawcandle.fundamentals.admin.progress`.

The durable contract writes, per run:

- `progress_stages.json` - declared deterministic stage order.
- `progress_status.json` - atomically replaced current status.
- `progress_events.jsonl` - append-only progress events and heartbeats.

Each event includes run ID, operation type, stage ID, stage number, total stages, state, message, timestamps, elapsed run/stage seconds, heartbeat time, optional item/row counts, warnings, errors, rollback state and percent only when a real denominator is known. Secret redaction is applied before writing status or events.

Batch Add Tickers declares 19 stages:

`PREFLIGHT`, `PREVIEW_VALIDATION`, `SOURCE_RESOLUTION`, `IDENTITY_AND_UNIVERSE`, `PROVIDER_STAGING`, `CANONICAL_REBUILD`, `TTM_REBUILD`, `STRUCTURAL_DEPENDENCIES`, `PACKAGE_CALCULATION`, `PACKAGE_APPLY`, `RELATIVE_POSITION`, `RELATIVE_VALUATION`, `DEPENDENCY_ATTACHMENT`, `SNAPSHOT_SMOKE`, `NO_CHANGE_VERIFICATION`, `FINAL_VALIDATION`, `ROLLBACK`, `CLEANUP`, `COMPLETED`.

`IDENTITY_AND_UNIVERSE` is intentionally emitted before `PROVIDER_STAGING` for the generic adapter because provider observation staging needs the copy-lane canonical/security identities first. The stable vocabulary remains shared; this operation's declared order reflects the real write dependency.

The CLI now prints flushed progress lines on stderr, for example:

```text
[1/19] PREFLIGHT - RUNNING - 00:00 elapsed - 0/1 items - Recording Batch Add Tickers preview request.
```

`--quiet-progress` preserves JSON-only stdout behavior.

The UI-ready reader is `AdminRunHistory.progress(run_id)`. It returns current status, current stage, declared stage count, completed stage count, heartbeat age, terminal outcome and artifact names while preserving traversal and symlink protections.

## Verification

Focused compile:

```text
python3 -m compileall rawcandle/fundamentals/admin/progress.py rawcandle/fundamentals/admin/rv_identity.py rawcandle/fundamentals/admin/history.py rawcandle/fundamentals/admin/batch_add_tickers.py rawcandle/cli/run_fundamentals_admin_add_tickers.py rawcandle/fundamentals/phase13f3_ticker_transition.py
```

Focused progress and Batch Add Tickers tests:

```text
pytest -q tests/test_fundamentals_admin_progress.py tests/test_fundamentals_admin_batch_add_tickers.py
19 passed in 122.89s
```

Adjacent admin tests:

```text
pytest -q tests/test_fundamentals_admin_foundation.py tests/test_fundamentals_admin_batch_add_tickers.py tests/test_fundamentals_admin_progress.py
32 passed in 123.08s
```

Previously failing tests:

```text
pytest -q tests/test_fundamentals_v4_company_snapshot_phase9f.py::test_v2_report_formats_values_and_restores_context
1 passed in 15.87s

pytest -q tests/test_phase13f3_ticker_transition.py::test_enhanced_listing_population_resolves_former_transition_tickers
1 passed in 10.10s
```

Targeted structural/admin regressions:

```text
pytest -q tests/test_phase13b_foundation.py tests/test_phase13d_backend.py tests/test_phase13f4_2_acceptance.py tests/test_structural_break_contract.py
46 passed in 8.11s
```

Targeted Snapshot, transition, RP/RV and production-isolation regressions:

```text
pytest -q tests/test_fundamentals_v4_relative_position_phase4c.py tests/test_fundamentals_v4_relative_position_persistence.py tests/test_fundamentals_v4_relative_valuation_engine.py tests/test_fundamentals_v4_relative_valuation_production.py tests/test_fundamentals_v4_company_snapshot.py tests/test_fundamentals_v4_company_snapshot_phase9f.py tests/test_phase13f3_ticker_transition.py
140 passed in 65.24s
```

Full active suite:

```text
/usr/bin/python3 -m pytest -q
2999 passed, 14 deselected, 8 warnings in 901.13s
exit_code=0
```

Full-suite evidence:

- Log: `fundamental_reports/admin_runs/phase13g2_3_closure/full_suite_rerun/pytest_full.log`
- Heartbeat: `fundamental_reports/admin_runs/phase13g2_3_closure/full_suite_rerun/heartbeat.jsonl`
- Atomic exit code: `fundamental_reports/admin_runs/phase13g2_3_closure/full_suite_rerun/exit_code.txt`
- Summary: `fundamental_reports/admin_runs/phase13g2_3_closure/full_suite_rerun/summary.json`

An earlier runner attempt under `full_suite/` was interrupted because its heartbeat loop could block behind pytest stdout buffering. It is retained as incomplete runner evidence and is not used as a pass.

## Production Safety

Protected DB paths checked read-only:

- provider: `data/fundamentals_provider.db`
- canonical: `data/fundamentals_v4.db`
- analysis: `data/fundamentals_analysis.db`
- market: `data/osakedata.db`
- taxonomy: `data/analysis.db`

Pre/post comparison:

- active package unchanged: `true`
- active Relative Position pointer unchanged: `true`
- active Relative Valuation identity unchanged: `true`
- `PRAGMA quick_check`: `ok` for all protected DBs
- foreign-key violations: `0` for all protected DBs
- read-only probe mtimes unchanged: `true` for all protected DBs

## Disk Hygiene

Filesystem free space before verification: approximately `569G` available under both the repo and `/tmp`.

Retained evidence size:

```text
156K fundamental_reports/admin_runs/phase13g2_3_closure
```

Removed phase-owned temp diagnostic directory:

- `/tmp/phase13g23_diag_snapshot` - `28K`

Retained earlier Phase 13G.2.2 evidence:

- `/tmp/phase13g22_accept` - `1.6M`

No Phase 13G.2.3 copied databases, WAL, SHM or journal files are retained.

## Handoff

Batch Add Tickers now has a reusable long-run progress contract, CLI progress output, durable machine-readable progress artifacts and a safe UI-ready reader. Full-suite evidence is green and protected production logical state is unchanged.

The justified next phase is the separately authorized production apply guard and handoff work. It should rely on the clean-tree guard, the clarified RV identity reader and the retained Phase 13G.2.2 economic evidence rather than rerunning the multi-lane acceptance unnecessarily.
