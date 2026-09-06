# Fundamentals Snapshot UI

## Purpose

The RawCandle Scheduler UI has a top-level **Fundamentals** page for manually generating one `CURRENT_REVISED_COMPANY_SNAPSHOT_V1` Markdown report at a time. The page uses results already present in RawCandle. It does not fetch provider data or refresh canonical, TTM, Score, Lifecycle, Valuation, Delta, Relative Position, or Diagnostic Flag results.

RawCandle uses Flet in web-browser mode. Scheduler, Taxonomy, and Fundamentals are top-level tabs in the same application. Their stable application routes are `/scheduler`, `/taxonomy`, and `/fundamentals`; `/` opens Scheduler.

## Start the UI

```bash
./start_stock_update_ui
```

The default URL is `http://127.0.0.1:8555`. Select the Fundamentals tab or open `/fundamentals` in the Flet application.

## Generate a report

The form contains:

- **Ticker**: trimmed and normalized to uppercase. It accepts the same ticker character contract as the snapshot writer.
- **Report date**: an ISO `YYYY-MM-DD` date. It defaults to the current calendar date in the Scheduler configuration timezone, normally `Europe/Helsinki`.
- **Replace an existing different report**: explicit overwrite authorization, off by default.
- **Generate report**: invokes the RawCandle snapshot service directly without constructing a shell command.

Reports are always written to:

```text
/home/kalle/projects/rawcandle/fundamental_reports
```

The filename contract is `{TICKER}_{YYYY-MM-DD}.md`. The browser cannot select an output directory or provide a filesystem path.

Publication uses the existing atomic writer:

- a missing target returns `CREATED`, displayed as `GENERATED`
- byte-identical content returns `NO_CHANGE`
- different existing content is preserved unless replacement is explicitly selected
- authorized replacement returns `OVERWRITTEN`, displayed as `GENERATED`

The result area shows the normalized ticker, report date, filename, fixed output path, publication outcome, and a shortened report-content fingerprint. Validation and generation errors are mapped to safe messages; technical exceptions are logged server-side.

## Recent reports

The page lists the ten newest valid report files from the fixed report directory. It scans only that directory and includes only non-symlink regular Markdown files matching the exact report filename contract. Malformed names, invalid dates, directories, symlinks, and unrelated files are ignored. Ordering is deterministic by modification time and filename.

The Scheduler UI assets root is the configured scheduler log directory. Phase 8A therefore does not expose report files through a new static mount and does not provide an Open or Download action. The safe filename and local path are shown instead.

## Data and safety contract

The UI calls `FundamentalsSnapshotUIService`, which validates browser inputs and delegates all assembly, rendering, fingerprinting, filename construction, and publication to the existing Company Snapshot V1 implementation. Production SQLite sources retain their existing `mode=ro`, immutable and `query_only` behavior. The only write is the requested Markdown report.

Repeated identical requests converge through the existing atomic writer. The generate action is disabled while a request is running, but backend atomic publication remains authoritative if requests overlap.

## SwingMaster reference

The SwingMaster `ui_fundamental_pipeline` was inspected read-only. RawCandle adopts its useful UX ideas of a compact ticker action and a small generated-file listing. RawCandle does not copy its CLI command builder, process executor, CSV snapshot implementation, broad asset download behavior, ZIP creation, folder launcher, market workflow, or update controls. The implementation resides entirely in RawCandle and depends only on RawCandle's Company Snapshot V1 API.

## Known limitations

- Generation is manual and single-company only.
- The page does not schedule reports, run batch generation, or update financial data.
- Reports are currently revised history, not original point-in-time reconstructions.
- Recent reports are metadata only; browser download is not exposed in Phase 8A.
- Flet tab routes identify application state; this UI is not a separate REST service.
