# First frozen result-publication export and daily-OHLC downstream

Date: 2026-09-29

Projection rule: `result_publication_daily_research_v1`

Decision: `RESULT_PUBLICATION_DOWNSTREAM_INTEGRATION_READY`

## 1. Retained artifacts

The first named FY2025+ production research export is retained as three adjacent runtime artifacts:

```text
exports/result_publication/result_publication_daily_research_fy2025plus_2026-09-29.csv
exports/result_publication/result_publication_daily_research_fy2025plus_2026-09-29.metadata.json
exports/result_publication/result_publication_daily_research_fy2025plus_2026-09-29.yahoo-observations.json
```

They are intentionally ignored by Git under the existing `exports/` policy. Their SHA-256 hashes are:

| Artifact | SHA-256 |
|---|---|
| CSV | `76c6b5bb01e0849fbdfcc76058f6e14a997d84d86d332f75275c31a9b4d7cf52` |
| Metadata | `547e7b2c52212d61a0d3de227577a16182ba2d0d4183c236e9af1d3f891bf5a3` |
| Yahoo observations | `1042bfe59ca3be579c0e59b80f9d47b7a54edb7869996c3063dcdc04068053ce` |

The CSV has 13,352 data rows plus its header. It excludes `UNUSABLE` by construction.

## 2. Yahoo provenance

The retained Yahoo artifact is the reviewed FY2025+ observation set used by the prior full validation. It has artifact version `result_publication_yahoo_observations_v1`, 655 deduplicated observations, no provider errors, and source scope `FY2025+ current 651 AMBIGUOUS quarters reviewed 2026-09-29`.

The final export ran in `frozen` mode from the retained path above. It did not call Yahoo live. A preflight run from the source artifact produced the same CSV SHA-256 as the final retained-path run.

## 3. V2 provenance

The reviewed input is:

```text
data/research/result_publication/v2_candidates_initial_result_sec_semantic_v2_research_2026-09-29.json
```

Its SHA-256 is `922b8b829da8fdc4107fefb80ff2708fd5b456a9148f7c4ca444be530f1d92e1`. All 83 accepted rows passed the implemented preflight against current quarter-scoped SEC evidence before either export run.

## 4. Reproduced counts

The final frozen Yahoo plus reviewed V2 run evaluated 16,210 FY2025+ quarters:

| Status | Count |
|---|---:|
| `EXACT` | 12,782 |
| `HEURISTIC_HIGH` | 570 |
| `HEURISTIC_MEDIUM` | 0 |
| `UNUSABLE` | 2,858 |
| Exported usable | 13,352 |

There was no count drift from the accepted result. Downstream wiring proceeded only after this gate passed.

## 5. Reproducibility metadata

The sidecar records generation time, projection version, database paths and hashes, frozen Yahoo path/hash/row count, V2 path/hash/row count, FY and identity filters, evaluated/exported rows, all status counts, and output path/hash.

The retained CSV is reproducible from the recorded `fundamentals_v4.db` and `osakedata.db` snapshots, the adjacent Yahoo artifact, the reviewed V2 artifact, projection version, and filters. The primary filter is FY2025+ with `include_unusable=false` and no ticker or company restriction.

## 6. Representative row QA

| Quarter | Status/method | Publication/session | First full day | Canonical | Warning |
|---|---|---|---|---|---|
| AAPL 2026-Q3 | EXACT / canonical | 2026-07-30 AFTER | 2026-07-31 | yes | none |
| NVDA 2027-Q2 | EXACT / canonical | 2026-08-26 AFTER | 2026-08-27 | yes | none |
| CF 2025-Q1 | HIGH / same effective day | intentionally unset | 2025-05-08 | no | research warning |
| ABG 2025-Q1 | HIGH / Yahoo-near-unique | 2025-04-29 PRE | 2025-04-29 | no | research warning |
| ORN 2025-Q3 | HIGH / Yahoo-near-unique | 2025-10-29 PRE | 2025-10-29 | no | research warning |
| DTE 2025-Q1 | HIGH / V2 strong initial | 2025-05-01 PRE | 2025-05-01 | no | research warning |
| GSIT 2026-Q2 | HIGH / V2 strong initial | 2025-10-30 AFTER | 2025-10-31 | no | research warning |

CF confirms that downstream uses the projected first-full-day directly and does not invent an exact timestamp for same-effective-day ambiguity.

## 7. Downstream consumer

No existing narrow result-publication daily-OHLC consumer was present. The smallest explicit consumer was added in:

```text
rawcandle/research/result_publication_daily_ohlc.py
```

`ResultPublicationResearchDataset` parses one retained CSV into stable `(company_id, fiscal_year, fiscal_quarter)` identities. It accepts only `EXACT`, `HEURISTIC_HIGH`, and `HEURISTIC_MEDIUM`. An `UNUSABLE` row is rejected even if a wrongly composed source file contains one.

## 8. Public API

```python
dataset = ResultPublicationResearchDataset.load(export_path)
publication = dataset.require(company_id, fiscal_year, fiscal_quarter)
window = dataset.get_ohlc_window(
    ohlc_db,
    company_id,
    fiscal_year,
    fiscal_quarter,
)
```

`get()` provides optional lookup. `require()` provides strict lookup. Every result retains status, method, canonical flag, rule version, warning, ticker, and first-full-day provenance.

## 9. Event-boundary semantics

`first_full_post_result_trading_date` is the sole practical event boundary. The consumer never parses or reinterprets `canonical_timestamp_utc`.

OHLC lookup requires an exact `(ticker, first_full_post_result_trading_date)` row. A boundary later than available OHLC is returned as `PENDING_OHLC`. A missing historical boundary is rejected as `BOUNDARY_NOT_IN_OHLC_CALENDAR`; there is no nearest-calendar-date fallback. A legitimate null projected boundary is preserved as `BOUNDARY_UNAVAILABLE`.

## 10. Sample OHLC join

The retained export and production `osakedata.db` produced:

| Quarter | Previous | Boundary | Next | Availability |
|---|---|---|---|---|
| AAPL 2026-Q3 | 2026-07-30 | 2026-07-31 | 2026-08-03 | AVAILABLE |
| NVDA 2027-Q2 | 2026-08-26 | 2026-08-27 | 2026-08-28 | AVAILABLE |
| DTE 2025-Q1 | 2025-04-30 | 2025-05-01 | 2025-05-02 | AVAILABLE |
| ABG 2025-Q1 | 2025-04-28 | 2025-04-29 | 2025-04-30 | AVAILABLE |

These are observed trading dates. AAPL demonstrates that the next row after Friday is Monday without calendar-date fabrication.

## 11. Tests

Fourteen focused downstream tests cover retained-style parsing, stable identity, EXACT and HIGH lookups, provenance, defensive UNUSABLE rejection, missing and duplicate quarters, exact OHLC join, pending and missing-boundary behavior, no write API, deterministic reload, and malformed exports.

Together with the relevant export, service, and projection tests, 50 tests passed. Unrelated Fundamentals score, valuation, and DC tests did not run.

## 12. Performance

The final retained frozen export completed in 11.30 seconds. Loading all 13,352 retained rows took 0.048109 seconds. Four production OHLC windows took 0.000845 seconds in one measured representative batch. This is trivial relative to daily research workloads.

## 13. Safety

The consumer opens `osakedata.db` through SQLite URI `mode=ro`, enables `query_only`, closes the connection after each requested window, and exposes no persistence API. CSV loading performs no database access.

Before and after hashes remained:

- `fundamentals_v4.db`: `9c1c14be2f52165f93d4c9d30aba8bb64fc5489e37190ed9fb672ffa993caaad`;
- `forecasts.db`: `8fc6785ce83f8a94a0cb80be8d1514e6a9f3ea1d42ac33b9d2081f83ffc9cd42`.

Canonical `quick_check` and forecast `quick_check` returned `ok`; canonical foreign-key check returned no rows. Authority counts, evidence counts, forecast rows, scheduler files, and systemd files were unchanged. The path is strictly `research export -> daily-OHLC consumer`; it cannot write to canonical authority, `v4_quarter`, forecasts, analysis authority, or scheduler state.

## 14. Limitations

- The runtime export bundle is retained locally but ignored by Git under current policy; retention and backup outside Git remain operational responsibilities.
- The loader deliberately supports only this CSV contract, not arbitrary JSONL or generic datasets.
- It returns one previous and one next observed OHLC day; it is an integration proof, not an event-study engine.
- It uses the exported ticker. Historical ticker-range disambiguation remains upstream in the publication service.
- A newly available OHLC day requires a newly generated export before a previously null projected boundary can become populated.

## 15. Next step

Use the named retained CSV explicitly in the first event-window research job. Pin and verify its sidecar/output hash before loading, keep `UNUSABLE` excluded, and stratify results by `research_status`, `research_method`, and `is_canonical`. Do not feed derived event dates or study outputs back into Fundamentals, forecasts, or scheduler state.

Gate: `RESULT_PUBLICATION_DOWNSTREAM_INTEGRATION_READY`.
