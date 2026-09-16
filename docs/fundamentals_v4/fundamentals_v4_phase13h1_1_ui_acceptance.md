# Phase 13H.1.1 Fundamentals Administration UI Acceptance

Primary outcome:

`OUTCOME A — FUNDAMENTALS ADMINISTRATION UI VERIFIED END TO END AND READY FOR CONTROLLED USE`

## Scope

Phase 13H.1.1 verified and hardened the Phase 13H.1 Fundamentals Administration UI without running any production mutation. The inspected surface was the Scheduler/Fundamentals application plus the `/fundamentals/admin` administration route and `/fundamentals/admin/reports/{run_id}/operation_report.md` safe download route.

Baseline commit required by the prompt: `e762668`.

## Application Startup

Live smoke command:

```bash
python3 -c "import uvicorn; from dev_tools.stock_update_scheduler_ui import create_scheduler_web_app; uvicorn.run(create_scheduler_web_app('scheduler_config.json'), host='127.0.0.1', port=8568, log_level='info')"
```

The app started through `create_scheduler_web_app('scheduler_config.json')`, served `/fundamentals/admin` with HTTP 200, served the admin operation report through the safe run-history route with HTTP 200, and shut down cleanly. The first sandboxed localhost curl attempt could not connect despite a healthy uvicorn startup log; the same localhost-only smoke succeeded outside the sandbox.

Evidence root:

`fundamental_reports/admin_runs/phase13h1_1_acceptance`

## Navigation

The Scheduler UI top-level tabs remain:

- Scheduler
- Taxonomy
- Fundamentals
- Fundamentals Admin

Route selection remains stable for `/`, `/scheduler`, `/taxonomy`, `/fundamentals`, `/fundamentals/admin`, and unknown routes. The Fundamentals Admin tab loads from the same Flet application factory as the scheduler.

## Operations

The UI exposes three independent operations:

- `ADD_TICKERS`
- `CHECK_UPDATE_SECTOR_INDUSTRY`
- `CHECK_UPDATE_TAXONOMY`

The page now displays operation-specific guidance. Add Tickers notes that provider network is disabled unless explicitly allowed and that the batch is one operation. Sector/Industry states that an empty ticker scope means a full operational-universe scan from `ticker_meta`. Taxonomy states that `dc_ecosystem` is the current primary lane and that `ec_taxonomy` remains a read-only readiness lane unless the backend authorizes a safe write contract.

## Preview And Apply Safety

Apply buttons now require a current preview payload and preview fingerprint. Material input changes invalidate the preview and disable both Copy Apply and Production Apply until Preview is run again. The material signature includes operation type, tickers/scope, market, taxonomy domain, candidate path, candidate version, protected-production-preview flag, and provider-network flag.

Production confirmation remains backend-enforced; this phase did not enable or bypass any production write path.

## Progress And History

History loading now fails closed if the durable history root is unavailable. History rows expose an inspect action that loads the selected run's operation, status, terminal outcome, stage number, completed-stage count, heartbeat age, and unified-report availability into the page. Running runs show a "Still working" status, and incomplete/unavailable runs are labelled without throwing.

Progress artifacts verified in controlled runs:

- `progress_stages.json`
- `progress_status.json`
- `progress_events.jsonl`
- terminal `result.json`
- `artifact_manifest.json`
- `operation_report.md`

## Summary And Report

The on-screen summary remains compact and includes operation, mode, outcome, duration when available, preview fingerprint, counts, progress, downstream invocation counts, rollback state, warnings/blockers, and next action when present.

`operation_report.md` was strengthened with plain-language sections for:

- executive summary
- run identity and duration
- request
- summary counts
- per-item results
- before/after changes
- source and provenance
- work performed and downstream
- snapshot results
- warnings and blockers
- write boundary
- databases read and written
- backup and rollback
- scheduler handling
- progress timeline
- next required action
- cleanup and retained artifacts
- technical appendix

Secrets and authenticated URL tokens remain redacted.

## Download Proof

The backend finalizes `operation_report.md` and includes it in `artifact_manifest.json` with SHA-256. The UI download button targets only:

`/fundamentals/admin/reports/{run_id}/operation_report.md`

Live route proof:

- `/fundamentals/admin` returned HTTP 200.
- `/fundamentals/admin/reports/phase13h1_1_acceptance/operation_report.md` returned HTTP 200.
- Content-Type was `text/markdown; charset=utf-8`.
- Content-Disposition was `attachment; filename="operation_report.md"`.
- Downloaded bytes exactly matched the stored artifact.
- Stored SHA-256 and downloaded SHA-256 both equaled `414887916786a7d4a24393a371f41b3fe4ad155223e4688ed0b8ac420221de48`.

Regression tests cover invalid run IDs, path traversal, URL-encoded traversal, wrong artifact names, missing reports, malformed manifests, symlink reports, and the existing Fundamentals company-report download route.

## Production Immutability

Production checks were read-only and bounded to identities directly relevant to the UI:

- active Fundamentals package in `data/fundamentals_analysis.db`
- active Relative Position snapshots in `data/fundamentals_analysis.db`
- active Relative Valuation snapshot in `data/fundamentals_analysis.db`
- active `dc_ecosystem` taxonomy version in `data/analysis.db`
- active non-Datacenter `ec_taxonomy` version count in `data/analysis.db`

Pre/post comparison result: `unchanged=true`.

No production add ticker, sector/industry update, taxonomy update, package/RP/RV refresh, production backup, scheduler stop, or scheduler write was executed.

## Tests

Focused and targeted tests:

```bash
pytest -q tests/test_fundamentals_admin_ui.py
pytest -q tests/test_fundamentals_admin_ui.py tests/test_fundamentals_admin_progress.py tests/test_fundamentals_snapshot_ui.py tests/test_stock_update_scheduler_ui.py
python3 -m compileall -q rawcandle/fundamentals/admin dev_tools/fundamentals_admin_page.py tests/test_fundamentals_admin_ui.py
git diff --check
```

The retained Phase 13H.1 full-suite result remains applicable for broader repository coverage because Phase 13H.1.1 changed only local UI rendering, report generation, safe download regression tests, and history failure handling. No shared production authorization logic or economic calculation path was changed.

## Limitations

Browser screenshot acceptance was not captured because `playwright` is not installed in this environment. The closest supported rendered acceptance was the Flet control-tree test path plus live FastAPI route smoke.

In-process `fastapi.testclient` and `httpx.ASGITransport` hung on `FileResponse` in this environment, so automated route regression uses the actual FastAPI endpoint callable and the live acceptance proof uses uvicorn plus curl.

## Next Phase

Proceed to the next controlled Phase 13H UI phase with the scheduler still treated as production-adjacent infrastructure. Keep production writes behind backend authorization, preview fingerprint matching, and explicit confirmation.
