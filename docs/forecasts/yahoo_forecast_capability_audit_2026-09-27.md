# Yahoo Forecast Capability Audit (2026-09-27)

## Scope and conclusion

This was a read-only, targeted audit of the current Yahoo/yfinance path and the
Fundamentals V4 identity and fiscal contracts. No source, database, scheduler,
or production state was changed. The live spike used six symbols and did not
persist response data.

The installed yfinance transport can be used behind a forecast adapter, but
RawCandle does not currently have a reusable Yahoo transport/pacing layer. The
existing pacing is OHLCV-loop policy, not a shared client. Forecast collection
should therefore be a separate daily workflow with its own provider adapter,
request limiter, retry/backoff, result classification, and point-in-time store.
Yahoo remains the provider identity; yfinance is only the transport/adapter.

## 1. Current relevant implementation

- `requirements.txt` declares `yfinance>=0.2.60`; the installed version tested
  was 0.2.66.
- `main.py` creates `yf.Ticker(ticker)` and injects it into
  `services/stock_update_service.py`. The service deliberately has no yfinance
  import and calls only `stock.history(...)` through the injected object.
- `services/stock_update_service.py` owns fixed OHLCV loop sleeps: 0.1 seconds
  after a history range, 0.1/0.25 seconds after a ticker, and 5 seconds after
  each 500 tickers. Exceptions are flattened to per-ticker error strings.
- Other direct, independent yfinance callers exist for sectors, splits,
  blackout events, and legacy/backfill price retrieval. They do not share a
  RawCandle Yahoo client.
- The stock scheduler enters through `RawCandleApp._run_stock_update_via_service`.
  Forecasts are not represented in scheduler configuration or orchestration.

## 2. Existing Yahoo provider reuse assessment

There are two distinct layers:

1. **yfinance transport (reusable behind an adapter):** a process singleton
   `YfData`, one shared curl-cffi session, Chrome impersonation, persistent
   Yahoo cookie cache, shared cookie/crumb guarded by a lock, basic/CSRF cookie
   strategies, consent handling, and one retry using the alternate cookie
   strategy after HTTP >= 400. A second 429 raises `YFRateLimitError`.
2. **RawCandle OHLCV policy (not reusable as transport):** fixed sleeps tied to
   history ranges, inserted row counts, ticker completion, and 500-ticker
   batches. It has no shared request clock, exponential backoff, jitter,
   response-aware retry, HTTP classification, or forecast-safe result type.

Answer to architectural question A: **not cleanly as-is**. Reuse yfinance's
session/cookie/crumb machinery, but place it behind a new generic Yahoo gateway
and forecast adapter. Do not call the OHLCV service or inherit its row-count
sleep semantics. A process-level Yahoo limiter may later be shared by OHLCV and
forecast adapters, but workflow orchestration and persistence must remain
separate.

## 3. Existing forecast-related code and artifacts

No forecast/consensus schema, `forecasts.db`, Yahoo Analysis adapter, or code
using `earningsTrend`, `earningsEstimate`, `revenueEstimate`, `epsTrend`,
`epsRevisions`, or `growthEstimates` was found in the targeted repository
search. Existing references to "forecast" are explanatory disclaimers in the
Fundamentals presentation/valuation documentation and renderer.

yfinance is already used and installed. `yahooquery` was not found. The current
Fundamentals provider abstraction contains a generic `ProviderObservation`, but
the production provider database is a reported-financial contract with a
closed provider enum and should not be stretched into a forecast history store.

## 4. Fundamentals V4 identity and fiscal linkage contract

The relevant production contract in `data/fundamentals_v4.db` is:

- `company(company_id, company_key, ...)`: permanent company identity.
- `security(security_id, company_id, current_ticker, valid_from, valid_to, ...)`:
  security identity; ticker is current routing metadata.
- `ticker_alias(security_id, ticker, provider, valid_from, valid_to, ...)`:
  time/provider-aware ticker resolution.
- `provider_security_identity(provider, provider_security_id, security_id,
  provider_ticker, ...)`: preferred provider-to-security mapping.
- `company_cik(company_id, cik_normalized, ...)`: company-level SEC identity;
  useful for corroboration, not Yahoo routing.
- `company_fiscal_year_anchor(company_id, fiscal_year, fiscal_year_start, ...)`
  and `company_fiscal_calendar_profile`: fiscal calendar evidence.
- `v4_quarter`: canonical realized quarter. Its natural uniqueness contract is
  `(company_id, fiscal_year, fiscal_quarter)` and its surrogate is `quarter_id`.
  `period_end`, `source_availability_date`, and `first_public_result_date` are
  distinct attributes. `first_public_result_date` is the appropriate realized
  result availability boundary for later no-look-ahead joins.

Current production counts observed were 2,547 companies, 2,560 securities,
2,575 ticker aliases, 2,557 provider-security identities, 2,542 CIK mappings,
and 89,893 canonical quarters. All six spike symbols resolved uniquely to a
company/security and a Sharadar permanent identifier.

Forecast acquisition should resolve the Yahoo symbol to `security_id` and
`company_id` at fetch time and persist both plus the provider symbol used.
Ticker must never be the permanent key.

## 5. Yahoo capability spike

The spike ran on 2026-09-27 through yfinance 0.2.66's existing
`quoteSummary/earningsTrend` path. AAPL, NVDA, AMZN, and NUE were requested;
ADBE was added for a 52/53-week non-calendar fiscal year and BB for a
non-calendar, lower-coverage case. All six returned HTTP-successful data with
four rows (`0q`, `+1q`, `0y`, `+1y`). Values below are live observations, not a
stable provider contract.

| Symbol | Yahoo endDate by horizon (0q, +1q, 0y, +1y) | EPS analysts | Revenue analysts | Key observation |
|---|---|---:|---:|---|
| NVDA | 2026-10-31, 2027-01-31, 2027-01-31, 2028-01-31 | 43, 41, 51, 53 | 44, 41, 53, 58 | Quarter/annual targets legitimately share an endDate. |
| AAPL | 2026-09-30, 2026-12-31, 2026-09-30, 2027-09-30 | 27, 21, 39, 40 | 27, 19, 40, 40 | Nominal month-end differs from canonical 52/53-week period ends. |
| AMZN | 2026-09-30, 2026-12-31, 2026-12-31, 2027-12-31 | 43, 41, 50, 52 | 45, 43, 55, 57 | Row growth materially differs from EPS growth. |
| NUE | 2026-09-30, 2026-12-31, 2026-12-31, 2027-12-31 | 7, 5, 6, 11 | 10, 9, 12, 14 | Lower coverage and very wide forward ranges. |
| ADBE | 2026-11-30, 2026-11-30, 2026-11-30, 2027-11-30 | 29, 29, 34, 36 | 27, 22, 34, 35 | `0q` and `+1q` collide on target kind and endDate. |
| BB | 2026-11-30, 2027-02-28, 2027-02-28, 2028-02-29 | 6, 5, 6, 7 | 4, 4, 6, 7 | Sparse but complete four-horizon response. |

ADBE's latest canonical reported period was FY2026 Q3 ending 2026-08-28, while
Yahoo used nominal 2026-11-30 dates. AAPL similarly uses nominal month ends
while canonical quarters end on Saturdays. Provider `endDate` is therefore a
target hint, not an exact canonical `period_end` equality key.

## 6. Raw Yahoo versus public yfinance interfaces

Raw Yahoo `earningsTrend.trend[]` was materially richer than the normalized
DataFrames:

| Semantics | Raw Yahoo | yfinance public estimate DataFrames |
|---|---|---|
| `period`, `endDate` | Both present | `period` retained as index; `endDate` dropped |
| `defaultMethodology` | Module-level field; later contract phase observed `gaap`/`nongaap` | Dropped |
| currency | Per-section fields (`earningsCurrency`, `revenueCurrency`, `epsTrendCurrency`, `epsRevisionsCurrency`) | Dropped |
| raw vs formatted value | `raw`, `fmt`, sometimes `longFmt` | Only `raw` retained |
| empty vs zero | Distinct (`{}` versus `{raw: 0, fmt: null, ...}`) | Empty fields dropped; zero retained only if field exists |
| estimate ranges/counts | Present | Retained |
| top-level row growth | Present | Available only through `growth_estimates.stockTrend` |
| section-specific growth | Present | Retained in earnings/revenue estimate frames |
| rows | Provider list | `_get_periodic_df` takes only the first four rows |

Consequently, answer to question C is **yes**: the normalized API is lossy for
RawCandle. It is convenient for tabular consumption but cannot be the sole
ingestion source. The adapter should preserve a canonicalized raw response (or
all source fields required to reconstruct it) before normalization.

The public `growth_estimates` call made a second request for industry, sector,
and index trend modules. In this sample it returned stock and index values plus
an index-only `LTG` row; sector and industry values were absent. These benchmark
growth series should not be in V1 because they add a request and have different
identity/coverage semantics.

## 7. Exact field and semantic findings

Each trend row exposed:

- `period`: moving provider label (`0q`, `+1q`, `0y`, `+1y`), not identity.
- `endDate`: provider's nominal fiscal target end; useful evidence, not always
  the issuer's exact canonical period end and not unique.
- `defaultMethodology`: the initial spike inspected this at the wrong level.
  The follow-up raw-contract phase found it on the `earningsTrend` module, with
  observed values `gaap` and `nongaap`; it is not a trend-row field.
- `earningsEstimate`: `avg`, `low`, `high`, `yearAgoEps`,
  `numberOfAnalysts`, `growth`, and `earningsCurrency`.
- `revenueEstimate`: `avg`, `low`, `high`, `yearAgoRevenue`,
  `numberOfAnalysts`, `growth`, and `revenueCurrency`.
- `epsTrend`: `current`, `7daysAgo`, `30daysAgo`, `60daysAgo`, `90daysAgo`,
  and `epsTrendCurrency`.
- `epsRevisions`: `upLast7days`, `upLast30days`, `downLast7Days`,
  `downLast30days`, an empty `downLast90days` in every sampled row, and
  `epsRevisionsCurrency`.
- top-level `growth`: the stock trend consumed by yfinance growth estimates.

All sampled currencies were USD. Revenue values were unscaled raw currency
units; EPS values were currency per share; growth values were decimal ratios;
analyst and revision fields were integer counts. The source provides no general
unit object, so these semantics must be assigned by field contract and retained
with the source currency.

Top-level growth is not safely interchangeable with
`earningsEstimate.growth`: AAPL and AMZN had differences, including AMZN `0y`
0.1364 versus EPS growth 0.7963 and `+1y` 0.2856 versus -0.1845. Persist them as
separate metrics with explicit source paths.

## 8. Failure and rate-limit implications

Acquisition must classify, not flatten, these outcomes:

| Status | Required interpretation |
|---|---|
| `SUCCESS_UNCHANGED` | Valid response; semantic canonical hash equals prior successful snapshot. Record fetch, reference prior snapshot. |
| `SUCCESS_CHANGED` | Valid response; hash differs. Record fetch and immutable snapshot/estimates. |
| `VALID_NO_DATA` | HTTP/provider success with a recognized symbol and structurally valid empty trend. Do not confuse with parser failure. |
| `PROVIDER_SYMBOL_UNAVAILABLE` | Explicit Yahoo quote error/not-found for the requested alias. |
| `TRANSIENT_FAILURE` | Timeout, DNS, connection reset, or retryable 5xx. |
| `RATE_LIMITED` | 429 or `YFRateLimitError`; apply cooldown/backoff and preserve the event. |
| `SCHEMA_MISMATCH` | JSON malformed or required envelope/field types changed. Preserve safe diagnostics; do not record as no-data. |
| `AMBIGUOUS_TARGET` | Forecast data valid but fiscal target cannot be linked uniquely. Store provider observation without a canonical link. |

yfinance retries once by switching cookie strategy for any HTTP >= 400; this is
authentication/session recovery, not general retry policy. There is no
exponential backoff. The analysis scraper also converts some HTTP errors to
`None`, which can collapse failures into empty DataFrames. The adapter must use
the raw response boundary and map exceptions/envelope errors before exposing a
normalized result.

One serial request per security per day is operationally plausible (about
2,560 current securities), but **not proven safe with the current pacing
infrastructure as-is**. At 0.25 seconds minimum spacing the ideal request time
alone is about 11 minutes, before retries. Use one earningsTrend request per
symbol, a shared monotonic limiter, bounded exponential backoff with jitter,
429 cooldown, checkpointed/resumable runs, and configurable concurrency that
defaults to one. Scheduling should remain independent from OHLCV.

## 9. Recommended provider-adapter boundary

Define a forecast-specific interface such as:

```text
YahooTransport.fetch_quote_summary(symbol, modules) -> RawHttpResult
YahooForecastAdapter.fetch(symbol) -> ForecastFetchResult
ForecastTargetLinker.link(result, identity_as_of, fiscal_contract) -> links
ForecastRepository.record(fetch_result, links) -> fetch/snapshot outcome
```

`YahooTransport` owns the yfinance session, cookie/crumb behavior, timeout,
pacing, retry/backoff, and HTTP diagnostics. `YahooForecastAdapter` validates
the Yahoo envelope and preserves source paths and null/empty distinctions.
Identity resolution, fiscal linkage, hashing, and persistence remain outside
transport. Neither adapter imports nor calls OHLCV orchestration. Persist
`provider='YAHOO_FINANCE'` (or the project's chosen canonical Yahoo name) and
record `adapter='yfinance'` plus its version separately.

## 10. Recommended initial V1 metrics

V1 should ingest only the single-call `earningsTrend` data:

- EPS consensus: average, low, high, analyst count, year-ago EPS, EPS growth.
- Revenue consensus: average, low, high, analyst count, year-ago revenue,
  revenue growth.
- EPS trend: current, 7/30/60/90-days-ago.
- EPS revisions: up/down over 7 and 30 days; retain 90-day source fields when
  present but do not convert absence to zero.
- Stock/top-level growth as a distinct metric.
- Provider horizon, endDate, methodology, currency, source field path, and
  explicit null/empty state for every observation.

Defer benchmark industry/sector/index growth, LTG, price targets, and downstream
forecast models. They require extra requests or different target semantics.

## 11. Recommended forecast target identity

`0q/+1q/0y/+1y` must never be the permanent key. The stable resolved identity
is:

- quarter forecast: `(company_id, target_type='FISCAL_QUARTER', quarter_id)`
  once a canonical quarter exists, with expected fiscal year/quarter retained;
- annual forecast: `(company_id, target_type='FISCAL_YEAR', fiscal_year)`;
- unresolved provider observation: immutable `(snapshot_id, provider_horizon,
  provider_end_date, occurrence_index)` plus `link_status`, never falsely
  promoted to canonical identity.

Provider `endDate` plus the Fundamentals fiscal contract is necessary but not
always sufficient. It should generate candidates by target type, fiscal
anchors, known cadence, and a documented date tolerance. ADBE proves duplicate
quarterly candidates can share an endDate; 52/53-week issuers prove exact date
equality is wrong. The linker must use acquisition time and the latest accepted
canonical quarter to interpret moving horizons, persist its rule version and
evidence, and return `AMBIGUOUS_TARGET` rather than guess.

Future quarters do not yet have `v4_quarter.quarter_id`. Store the forecast-side
expected `(company_id, fiscal_year, fiscal_quarter)` and later attach the
canonical `quarter_id` when Fundamentals creates it. Do not pre-create or alter
Fundamentals quarters for forecasts.

## 12. Recommended daily acquisition semantics

Create one run per scheduled invocation and one fetch row per attempted
security. Resolve identity and provider alias as of run time, fetch raw Yahoo
once, validate and canonicalize only semantic fields, then hash deterministically.
Always record the fetch outcome. Create a new immutable snapshot only for a
valid changed payload; point unchanged fetches at the prior snapshot. A later
successful no-data response is an observation, not deletion of prior history.

For an "as known at X" query, select the latest successful fetch at or before X
and follow its snapshot reference. Failed fetches must remain visible but must
not erase the last known forecast. Store both attempted/fetched timestamp and
provider observation timestamp if Yahoo later exposes one; do not infer that
the consensus changed exactly at fetch time.

When joining to realized results, require `snapshot.fetched_at_utc <` the
chosen evaluation cutoff and use `v4_quarter.first_public_result_date` (or a
stricter research cutoff) to prevent look-ahead leakage.

## 13. Proposed `data/forecasts.db` logical schema

No schema was created. Recommended logical tables:

```text
forecast_run
  run_id PK, provider, adapter, adapter_version, started_at_utc,
  completed_at_utc, scope_json, status, counters_json

forecast_fetch
  fetch_id PK, run_id FK, company_id, security_id, provider_symbol,
  requested_at_utc, fetched_at_utc, status, http_status, attempt_count,
  error_class, error_code, diagnostic_json, content_hash,
  snapshot_id nullable FK

forecast_snapshot
  snapshot_id PK, provider, company_id, security_id, provider_symbol,
  first_fetch_id FK, first_seen_at_utc, content_hash, schema_version,
  canonical_payload_json, raw_payload_json,
  UNIQUE(provider, company_id, content_hash)

forecast_estimate
  estimate_id PK, snapshot_id FK, provider_horizon, target_type,
  provider_end_date, provider_methodology, occurrence_index,
  expected_fiscal_year nullable, expected_fiscal_quarter nullable,
  canonical_quarter_id nullable, link_status, link_rule_version,
  link_evidence_json, metric, statistic, value_numeric nullable,
  value_text nullable, value_state, currency nullable, unit,
  analyst_count nullable, source_path,
  UNIQUE(snapshot_id, provider_horizon, occurrence_index, metric, statistic)
```

Cross-database IDs are logical references and cannot be enforced by SQLite
foreign keys unless Fundamentals is attached. Record the V4 identity contract
version/link evidence and validate references in application checks. The
change-only snapshot model preserves point-in-time knowledge through fetch
rows without duplicating identical estimate payloads daily.

## 14. Risks and unresolved semantic questions

- Yahoo is an undocumented, mutable provider API; fields and access behavior
  can change without notice.
- Yahoo exposes no consensus publication timestamp in this module. Fetch time
  is a conservative knowledge timestamp, not the true change time.
- `defaultMethodology` had an observed `gaap`/`nongaap` vocabulary in the
  follow-up raw-contract phase, but Yahoo's authoritative definition and any
  wider vocabulary remain undocumented in the inspected code.
- Top-level growth semantics are demonstrably not always EPS growth; retain the
  native path and avoid relabeling until independently documented.
- Nominal `endDate` may collide or differ from issuer period ends. ADBE's
  duplicate quarterly endDate requires an ambiguity path and further repeated
  observations before final linker rules.
- Valid no-data versus symbol-unavailable/schema-change needs fixture capture
  from explicit examples before production implementation.
- Provider aliases for Yahoo are not currently populated as a dedicated
  `provider_security_identity`; initial routing needs a reviewed alias policy.
- Raw payload retention policy (size, compression, and potential licensing)
  needs a decision before implementation.

## 15. Recommended implementation phases

1. Freeze result/status contracts and capture redacted fixtures for success,
   no-data, invalid symbol, 429, 5xx, malformed envelope, and ADBE ambiguity.
2. Build/test a generic Yahoo transport wrapper around yfinance's session with
   a shared limiter, bounded retries, diagnostics, and no OHLCV dependency.
3. Implement the raw earningsTrend adapter and deterministic semantic hashing.
4. Create `data/forecasts.db` migrations and repository tests for immutable
   fetch/snapshot history and as-of queries.
5. Implement identity resolution and a versioned fiscal target linker that
   permits unresolved/ambiguous targets and later canonical reconciliation.
6. Pilot the six audited symbols daily, measure unchanged rate, latency, 429s,
   target drift, and no-data behavior; then expand gradually.
7. Add a separate scheduler step only after pilot acceptance. Keep forecast
   failure non-destructive and operationally independent of OHLCV updates.

## Audit evidence

Files inspected are limited to the Yahoo callers/service path, scheduler
entrypoints, yfinance's installed analysis/data modules, Fundamentals provider
and schema contracts, relevant tests found by targeted search, and read-only
schema/rows from `data/fundamentals_v4.db`. Commands were targeted `rg`, `sed`,
`git status --short`, `sqlite3 -readonly`, and small Python/yfinance inspection
and live-spike commands. No test suite was run because no executable code was
changed; the capability commands themselves completed successfully.
