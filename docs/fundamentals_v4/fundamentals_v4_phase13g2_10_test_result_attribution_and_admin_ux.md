# Phase 13G.2.10: Test Result Attribution and Administration UX

## Outcome

Phase 13G.2.10 corrected Add Tickers Test-on-copies result attribution and
standardized the user-facing Preview, Test, and Production reporting. No model
formula, source authority, eligibility rule, or production publication guard
was changed.

## Proven root cause

The original Test run `20260919T112547Z_add_tickers_8bbcda32e218_apply`
successfully created new canonical identities and completed the full V2 rebuild.
Its durable `copy_apply_technical.json`, accepted preview, and snapshot reports
identify the separately built candidate analysis database and contain successful
candidate results for new tickers, including FULL results for CCJ, GDS, and GFS
and a LIMITED result for CRWV.

The reporting call nevertheless used `lane.paths.analysis_db`. That path was the
analysis database copied before the rebuild. The rebuild deliberately wrote a
fresh, separate `candidate_analysis_db`; snapshot smoke correctly used that
candidate, but ticker reporting did not. New company IDs existed in the copied
canonical database but had no rows in the stale pre-rebuild analysis copy, so
Score, Lifecycle, Valuation, RP, and RV appeared unavailable. Existing tickers
often appeared correct only because their company IDs already had rows in that
old analysis database.

The fix preserves candidate canonical identity resolution and points Test
after-state analysis lookup at the exact `candidate_analysis_db` returned by the
full rebuild. It does not assume that SQLite row IDs can be transferred between
unrelated rebuilt databases.

## Identity contract

- Preview describes identity and V2 availability from the preserved
  pre-operation state.
- Test resolves ticker identity from the completed copy-lane canonical database
  and reads analysis from that Test run's completed candidate analysis database.
- Production resolves ticker identity and analysis from the validated final
  production databases after publication and postflight.
- Ticker remains the stable lookup input into the existing canonical identity
  mechanism; no parallel identity system was introduced.

## Read-only production evidence

Current production was queried read-only after the already completed Production
run. It confirms these representative outcomes:

| Ticker | Score | Lifecycle | Valuation | RP V2 | RV |
| --- | --- | --- | --- | --- | --- |
| CCJ | FULL | READY / SCALING | FULL | 6 results | Not eligible |
| GDS | FULL | READY / DECLINING | FULL | 8 results | Not eligible |
| GFS | FULL | READY / TRANSITION | FULL | 8 results | Not eligible |
| CBRS | NOT_READY | NOT_READY | NOT_READY | 0 results | Not eligible |
| CRWV | LIMITED | NOT_READY | FULL | 4 results | Not eligible |

CCJ's lifecycle evidence carries the technical reason
`CLASSIFIED_TRANSITION` while its persisted final state is `SCALING`; reporting
uses the persisted final state and retains the reason in structured evidence.
The production query also confirmed AG as an existing-ticker control with FULL
Score and Valuation, READY / SCALING Lifecycle, RP results, and FULL RV.

No historical operation report was rewritten.

## Reporting integrity

Test and Production reporting now distinguishes model readiness from reporting
failure. A missing or ambiguous after-state canonical identity, an analysis
database lookup error, or a resolved company with no Score, Lifecycle, and
Valuation rows produces structured `REPORTING_INTEGRITY_ERROR` evidence and an
explicit `Reporting integrity error` line. It no longer silently turns this
condition into five unrelated `Not available` values.

The reporting layer remains downstream of publication. Reporting failures do
not alter transaction ordering, atomic replacement, postflight, or rollback.

## User-facing reporting

Normal Test and Production details now use concise values such as:

- `Score V2: FULL`
- `Score V2: LIMITED - missing Revenue Growth, Operating Margin Direction`
- `Score V2: NOT_READY - TTM core inputs unavailable`
- `Lifecycle: READY - Transition`
- `Lifecycle: NOT_READY - source availability date missing`
- `Valuation V2: NOT_APPLICABLE - unsupported financial model`
- `RP V2: 8 results (2 ecosystem) - READY`
- `RP V2: 8 results (2 ecosystem) - READY; some peer groups too small`
- `RP V2: 0 results - source measure not eligible`
- `RV: Not eligible`

Raw Score reason JSON remains in the structured per-ticker result as
`technical_reason`; it is no longer emitted in normal ticker details. Existing
technical run artifacts remain unchanged and available for audit.

Test and Production reports include an `Analysis Outcome` section with actual
counts for Score, Lifecycle, Valuation, RP result availability, RV status, and
any reporting-integrity errors. This analytical summary is separate from the
Administration operation outcome. Preview does not include it.

## Preview and Production wording

Preview details show `Existing V2 analysis` for an existing ticker with V2
state, `No existing V2 analysis` for an existing canonical ticker without it,
and `Not calculated during Preview` for a new ticker. A zero-review Preview says
`Next step: run Test on copies.`; a Preview with review items first directs the
user to resolve them.

The Production summary has one non-duplicated result line:

`Added: N. Existing tickers included in rebuild: N. Source-data updates: N. No source change: N.`

This keeps source changes distinct from mandatory full-analysis recomputation.

## UI state contract

| State | Preview | Test on copies | Production update |
| --- | --- | --- | --- |
| Initial valid input or input changed | Enabled | Disabled | Disabled |
| Preview running | Disabled | Disabled | Disabled |
| Preview success | Available | Enabled | Disabled |
| Test running | Disabled | Disabled | Disabled |
| Test success | Available | Visible and disabled | Enabled, primary action |
| Test failure | Existing safe retry contract | No Production authorization | Disabled |
| Production running | Disabled | Disabled | Disabled |
| Production success | Reset for empty input | Disabled | Disabled |

Changing ticker input invalidates the bound Preview and Test authorization.
Successful Production clears the completed ticker batch. Backend Preview/Test
fingerprint, input, source-state, lock, and transaction guards remain the
authoritative controls.

## Tests and acceptance

Focused fixtures cover a newly created candidate identity with FULL, LIMITED,
genuine NOT_READY, and Valuation NOT_APPLICABLE outcomes; WATCH_ONLY taxonomy
with no ecosystem RP expectation; existing-ticker behavior; explicit reporting
integrity failure; concise rendering; Preview semantics; aggregate analysis
outcomes; and UI stage transitions.

The Add Tickers end-to-end copy-lane regression deliberately creates a separate
candidate analysis database. It proves that a new ticker resolves a real FULL
result from that candidate immediately after Test on copies. This test would
fail with the former stale analysis path.

Validation commands and results:

- `pytest -q tests/test_fundamentals_admin_ticker_reporting.py`: 9 passed,
  0 skipped, 0 failed.
- `pytest -q tests/test_fundamentals_admin_batch_add_tickers.py::test_preview_test_and_guarded_production_rehearsal_complete_end_to_end`:
  1 passed, 0 skipped, 0 failed.
- `pytest -q tests/test_fundamentals_admin_ui.py`: 35 passed, 0 skipped,
  0 failed.
- `pytest -q tests/test_fundamentals_admin_*.py`: 179 passed, 0 skipped,
  0 failed.
- `pytest -q tests/test_fundamentals_v4_full_rebuild.py tests/test_fundamentals_v4_relative_valuation_source.py tests/test_fundamentals_v4_operating_income_v2_persistence.py`:
  22 passed, 0 skipped, 0 failed.

The focused acceptance performed Preview and Test-on-copies behavior only; no
real Production update was initiated. The transaction test's production stage
is an isolated rehearsal against temporary fixture databases, not production.

## Production safety and cleanup

Production provider, canonical, analysis, and market databases were hashed
before and after the work. Production inspection used SQLite read-only mode.
No taxonomy or `ticker_meta` value was changed, no production rebuild or update
was run, and no rollback backup was removed.

Test-owned temporary databases are managed by pytest temporary directories and
were removed by the test runner. The prior real run's lightweight reports and
JSON evidence were retained. No material unresolved issue remains in this
phase's scope.
