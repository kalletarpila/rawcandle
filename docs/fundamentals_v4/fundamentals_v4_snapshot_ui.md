# Fundamentals Snapshot UI

## Purpose

The RawCandle Scheduler UI has a top-level **Fundamentals** page for manually generating one or more `CURRENT_REVISED_COMPANY_SNAPSHOT_V1` Markdown reports. The page uses results already present in RawCandle. It does not fetch provider data or refresh canonical, TTM, Score, Lifecycle, Valuation, Delta, Relative Position, or Diagnostic Flag results.

RawCandle uses Flet in web-browser mode. Scheduler, Taxonomy, and Fundamentals are top-level tabs in the same application. Their stable application routes are `/scheduler`, `/taxonomy`, and `/fundamentals`; `/` opens Scheduler.

## Start the UI

```bash
./start_stock_update_ui
```

The default URL is `http://127.0.0.1:8555`. Select the Fundamentals tab or open `/fundamentals` in the Flet application.

## Generate a report

The form contains:

- **Tickers**: one or more tickers separated by commas, whitespace, or both. Newlines count as whitespace.
- **Report date**: an ISO `YYYY-MM-DD` date. It defaults to the current calendar date in the Scheduler configuration timezone, normally `Europe/Helsinki`.
- **Replace an existing different report**: explicit overwrite authorization, off by default.
- **Generate report**: invokes the RawCandle snapshot service directly without constructing a shell command.

Ticker tokens are trimmed and normalized to uppercase. Empty tokens are ignored, duplicates are removed after normalization, and first-appearance order is retained. For example, `nvda, vrt NVDA crmd` is processed as `NVDA`, `VRT`, `CRMD`. Every token is then validated with the existing Company Snapshot ticker contract.

A request may contain at most 25 unique tokens. The limit protects the synchronous local UI from accidental large submissions. Oversized requests fail as a whole and are never silently truncated. An empty parsed set is also rejected.

Reports are always written to:

```text
/home/kalle/projects/rawcandle/fundamental_reports
```

The filename contract is `{TICKER}_{YYYY-MM-DD}.md`. The browser cannot select an output directory or provide a filesystem path.

One report date and one overwrite choice apply to the whole request. Each ticker is attempted independently through the existing Company Snapshot V1 API, in normalized first-appearance order. A failed, invalid, not-ready, or overwrite-required ticker does not block later tickers, and successful files are not rolled back. Publication uses the existing atomic per-file writer:

- a missing target returns `CREATED`
- byte-identical content returns `NO_CHANGE`
- different existing content is preserved unless replacement is explicitly selected
- authorized replacement returns `OVERWRITTEN`

The batch summary shows requested, created, overwritten, unchanged, and not-generated counts. The result table contains one row per unique token with its ticker, status, filename when available, concise message, and download action when an existing report is intentionally offered. Validation and generation errors are mapped to safe messages; technical exceptions are logged server-side.

## Recent reports

The page lists the ten newest valid report files from the fixed report directory. It scans only that directory and includes only non-symlink regular Markdown files matching the exact report filename contract. Malformed names, invalid dates, directories, symlinks, and unrelated files are ignored. Ordering is deterministic by modification time and filename. Every listed report has a download action.

The RawCandle-owned `/fundamentals/reports/{filename}` endpoint serves the exact existing Markdown bytes with the original filename as an attachment. Downloading does not regenerate, refresh, or alter a report. A preserved existing file is also available after `OVERWRITE_REQUIRED`; the failed replacement is never served.

The endpoint is restricted to `/home/kalle/projects/rawcandle/fundamental_reports`. It accepts only a basename matching `{TICKER}_{YYYY-MM-DD}.md`, validates the ticker and real calendar date with the same shared function used by Recent reports, resolves the target inside the fixed directory, and serves only an existing regular non-symlink file. Absolute paths, parent traversal, path separators, null bytes, malformed or unrelated files, directories, and symlinks receive a generic not-found response without filesystem details.

## Data and safety contract

The UI calls `FundamentalsSnapshotUIService`, which validates browser inputs and delegates all assembly, rendering, fingerprinting, filename construction, and publication to the existing Company Snapshot V1 implementation. Production SQLite sources retain their existing `mode=ro`, immutable and `query_only` behavior. The only write is the requested Markdown report.

Reports generated through the UI include Company Snapshot V1's three-point valuation-multiples section. This presentation addition does not change batch processing, `NO_CHANGE`, recent-report filtering, or download security; a download still returns the exact generated Markdown bytes.

Repeated identical requests converge through the existing atomic writer. The generate action is disabled while a request is running, but backend atomic publication remains authoritative if requests overlap.

## SwingMaster reference

The SwingMaster `ui_fundamental_pipeline` was inspected read-only. Its snapshot browser presents a download icon and opens a browser URL for the selected file. RawCandle follows that user-facing interaction but uses a stricter RawCandle-owned download route instead of SwingMaster's broad Flet asset serving. RawCandle does not copy its CLI command builder, process executor, CSV snapshot implementation, ZIP creation, folder launcher, market workflow, or update controls. The implementation resides entirely in RawCandle and depends only on RawCandle's Company Snapshot V1 API.

## Known limitations

- Generation remains manual and synchronous, with at most 25 unique tickers per request.
- The page does not schedule reports, upload ticker files, save watchlists, generate a full universe, or update financial data.
- Reports are currently revised history, not original point-in-time reconstructions.
- The download route serves existing reports only; it is not a report-generation API.
