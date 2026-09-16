# Phase 13H.1.2 Fundamentals Administration UI Simplification

Primary outcome:

`OUTCOME A — FUNDAMENTALS ADMINISTRATION UI SIMPLIFIED AND READY FOR DAILY USE`

## Before And After

Before this phase, the Fundamentals Administration tab behaved like a maintenance form: all operation fields were visible at once, preview payload paths and fingerprints were editable, the production confirmation token was exposed, and the initial page showed large empty Result/Summary/Progress panels.

After this phase, the page follows a daily-use flow:

1. Select operation.
2. Enter only the fields relevant to that operation.
3. Preview.
4. Review a concise summary.
5. Apply only when the backend capability allows it.
6. Confirm production updates through a dialog.
7. Follow compact progress.
8. Read the final summary.
9. Download the full operation report.

## Operation-Specific Controls

Add Tickers shows the operation selector, market, ticker input, guidance text, Preview, and post-preview actions. It hides taxonomy, candidate CSV/version, preview payload, preview fingerprint, production token, protected-preview switch, and network checkbox.

Sector/Industry shows the operation selector, market, guidance that the full active universe is checked, and Preview. It does not require ticker input and explains that `data/osakedata.db.ticker_meta` is authoritative.

Taxonomy shows the operation selector, taxonomy-domain selector, domain guidance, and Preview. Candidate CSV/version are not shown in the normal current-state/no-change path.

## Add Tickers Network Contract

For UI-triggered Add Tickers preview, `network_allowed=True` is always passed to the service. The visible network opt-in checkbox was removed from the form. The UI text states that provider network access is enabled automatically when local data is insufficient.

Automated tests stub provider behavior and do not make external provider requests. The CLI `--allow-network` contract was not changed.

## Internal Preview State

The UI now keeps preview payload path, preview fingerprint, and production confirmation token internal. The old controls still exist only as hidden read-only technical controls for compatibility and diagnostics; they are not part of the normal user-facing form.

Material input changes clear the saved preview state, mark the summary stale, hide report actions, and disable Apply until a new Preview is run.

## Confirmation Workflow

Production Apply opens a confirmation dialog. Closing or cancelling the dialog does not start the operation. Confirming passes the backend-required confirmation token internally through the existing service boundary.

## Progress And Summary

The initial page no longer displays large empty Result, Summary, or Progress boxes. Preview, Progress, Final Summary, and Report sections become visible only when relevant.

The final summary is concise and leaves the full technical record to `operation_report.md`.

## Run History

History now defaults to user-relevant administration runs. Acceptance/test evidence, maintenance/cleanup evidence, and legacy evidence are hidden unless `Show technical and legacy runs` is enabled.

Primary history rows show time, operation, result, count, category, and actions. Long mode/run identifiers are kept in tooltips or selected-run details.

## Report And Download

The unified `operation_report.md` remains the complete durable record. It now includes a Provider Network section when the result/request records network state, including allowed/used/request-count/source-resolution fields without secrets.

Live download proof for this phase:

- UI command: `python3 dev_tools/stock_update_scheduler_ui.py --config scheduler_config.json --port 8571`
- UI route: `/fundamentals/admin`
- Download route: `/fundamentals/admin/reports/phase13h1_2_ui_simplification/operation_report.md`
- UI/API port arrangement: the Flet app and FastAPI/download endpoint are served by the same uvicorn app and port in this repository command.
- Download SHA-256: `6e603d7866380e1327eabc0114e9f0b8112073f30478556a5a682069320fb090`

## Tests

Focused/targeted tests:

```bash
pytest -q tests/test_fundamentals_admin_ui.py
pytest -q tests/test_fundamentals_admin_ui.py tests/test_fundamentals_admin_progress.py tests/test_fundamentals_snapshot_ui.py tests/test_stock_update_scheduler_ui.py
python3 -m compileall -q rawcandle/fundamentals/admin dev_tools/fundamentals_admin_page.py tests/test_fundamentals_admin_ui.py
git diff --check
```

Full active suite was not rerun because this phase changed local UI presentation, UI-managed state, history presentation, and report rendering only. Backend authorization, production paths, routing contracts, and economic calculations were not materially changed.

## Production Immutability

Production verification was read-only and bounded:

- `data/fundamentals_analysis.db`: active package, active RP, active RV
- `data/analysis.db`: active `dc_ecosystem`, non-Datacenter `ec_taxonomy` active count

Pre/post comparison result: `unchanged=true`.

No production ticker add, Sector/Industry update, taxonomy update, package/RP/RV refresh, backup, or scheduler mutation was executed.

## Limitations

Automated browser screenshots were not captured because Playwright is not installed in this environment. The live app was started through the supported command, the route/download path was tested by HTTP, and the rendered control tree was verified by repository tests.

The test environment has no graphical browser, so `xdg-open` cannot open the local UI automatically. The server still starts and serves the route normally.

## Next Phase

Proceed to the next controlled Phase 13H work with backend authorization remaining authoritative and production writes still gated by preview fingerprint matching plus explicit confirmation.
