# Phase 13H.1 Fundamentals Administration UI

## Scope

Phase 13H.1 adds a Flet/FastAPI administration surface to the existing scheduler
control panel. The UI exposes the three Phase 13G administration operations:

- Add Tickers
- Check/Update Sector and Industry
- Check/Update Taxonomy

The implementation is intentionally thin. UI code calls
`rawcandle.fundamentals.admin.ui_service.FundamentalsAdminUIService`, and that
service delegates to the existing Python administration APIs. The UI does not
open production databases, construct SQL, or perform business mutations.

## Routes

- `/fundamentals` remains the company snapshot report page.
- `/fundamentals/admin` is the new administration page.
- `/fundamentals/admin/reports/{run_id}/operation_report.md` downloads the
  exact operation report artifact from a safe admin run directory.

The admin report download route uses the same FastAPI/Flet application and
download-button pattern as the existing Fundamentals report download flow.

## Operation Report

Each UI-triggered admin run is finalized with:

- `operation_report.md`
- an updated `artifact_manifest.json` entry with size and sha256

The operation report is assembled from durable run artifacts such as
`result.json`, `request.json`, `progress_status.json`, and
`progress_events.jsonl`. It is written atomically and redacted before it is
published. Existing older runs without `operation_report.md` remain visible in
history, but the UI does not fabricate downloadable reports for them.

## Production Safety

Phase 13H.1 acceptance does not execute production mutation. Production-capable
buttons are present only as UI controls over backend confirmation contracts.
Copy-only apply and protected production apply remain enforced by the existing
Phase 13G backend functions.

The focused acceptance tests use fixture run directories and injected backend
functions. They do not modify `data/fundamentals_v4.db`,
`data/fundamentals_analysis.db`, `data/fundamentals_provider.db`,
`data/osakedata.db`, or `data/analysis.db`.

## Verification

Focused tests added in this phase cover:

- operation report generation, redaction, manifesting, and safe download
- service delegation through the backend boundary
- run history report availability
- all three UI operations being visible
- durable progress callback rendering
- existing Fundamentals report download behavior remaining unchanged

Full-suite verification is required before the phase is considered closed.
