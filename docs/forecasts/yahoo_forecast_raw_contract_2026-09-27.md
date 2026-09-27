# Yahoo Forecast Raw Contract (2026-09-27)

## Scope and decision

This phase freezes a fixture-backed V1 contract for Yahoo Finance
`quoteSummary/earningsTrend`. It is not a production adapter or persistence
implementation. No database, scheduler, OHLCV workflow, dependency, or
Fundamentals contract was changed.

The contract is based on yfinance 0.2.66 source inspection, three compact real
response fixtures, two synthetic contract fixture files, and safely paced live
observations of NVDA, AAPL, AMZN, NUE, ADBE, and BB. Two observation rounds
were made for each symbol; no deliberate rate-limit or server-error requests
were attempted.

## 1. Raw response envelope

All six successful responses had this shape:

```text
quoteSummary
  result: [
    earningsTrend
      maxAge: 1
      defaultMethodology: "gaap" | "nongaap"
      trend: [...]
  ]
  error: null
```

The top-level object contained only `quoteSummary`. `quoteSummary` contained
`result` and `error`; the sole result object contained only
`earningsTrend`. No response-level symbol, provider observation timestamp,
consensus update timestamp, target identifier, or hidden target identity was
observed.

yfinance calls the endpoint with `formatted=false`, but Yahoo still returned
`fmt` and, for integer/large-number wrappers, often `longFmt`. The adapter
must not interpret `formatted=false` as a raw-only response guarantee.

The live invalid-symbol check produced a Yahoo 404 body with
`quoteSummary.result=null` and an error object containing code `Not Found`.
yfinance's analysis scraper caught the HTTP exception and returned `None`,
confirming that classification must happen at or below the raw transport
boundary.

## 2. Row and field inventory

Every sampled response had four rows in order `0q, +1q, 0y, +1y`. Every row
had `maxAge`, `period`, `endDate`, `growth`, `earningsEstimate`,
`revenueEstimate`, `epsTrend`, and `epsRevisions`.

| Section | Fields |
|---|---|
| `earningsEstimate` | `avg`, `low`, `high`, `yearAgoEps`, `numberOfAnalysts`, `growth`, `earningsCurrency` |
| `revenueEstimate` | `avg`, `low`, `high`, `yearAgoRevenue`, `numberOfAnalysts`, `growth`, `revenueCurrency` |
| `epsTrend` | `current`, `7daysAgo`, `30daysAgo`, `60daysAgo`, `90daysAgo`, `epsTrendCurrency` |
| `epsRevisions` | `upLast7days`, `upLast30days`, `downLast7Days`, `downLast30days`, `downLast90days`, `epsRevisionsCurrency` |

Numeric values were wrappers with `raw` and `fmt`. Analyst counts, revision
counts, and revenue amounts also had `longFmt`. Currencies were direct
strings. `maxAge` appeared at module and row level with value 1.

All observed currencies were USD. Analyst counts are section-specific: AAPL
and BB show that EPS and revenue analyst populations can differ.

## 3. Required versus optional fields

"Observed stable" does not mean "safe to require" for an undocumented API.

| Path | V1 treatment |
|---|---|
| `quoteSummary` | Required object; wrong/missing type is schema mismatch. |
| `quoteSummary.error` | Null/absent for success; structured error is classified first. |
| `quoteSummary.result` | Required non-empty list for data/no-data parsing. |
| `result[0].earningsTrend` | Required object. |
| `earningsTrend.trend` | Required list; empty list is valid no-data. |
| row `period` | Required string; unknown values are preserved. |
| row `endDate` | Required ISO `YYYY-MM-DD` string. |
| `defaultMethodology` | Optional metadata; preserve absent/null/text state. |
| row sections and fields | Optional individually; preserve field state. |
| currency fields | Optional text; never infer USD. |
| `maxAge`, `fmt`, `longFmt` | Non-semantic; excluded from V1 hash. |
| unknown fields | Excluded from V1 hash but reported as schema drift. |

An empty `trend` is `VALID_NO_DATA` only inside a structurally valid success
envelope. Missing or wrong-type `trend` is never no-data.

## 4. Null, empty, and zero contract

| State | Meaning | Fixture example |
|---|---|---|
| `FIELD_ABSENT` | Key or optional parent is absent. | Synthetic field-state fixture. |
| `EMPTY_OBJECT` | Key is present with `{}`. | `epsRevisions.downLast90days` in every sampled row. |
| `EXPLICIT_NULL` | Key or semantic `raw` is JSON null. | Synthetic fixture. |
| `NUMERIC_ZERO` | Semantic number is exactly zero. | AAPL `downLast7Days.raw=0`. |
| `NUMERIC_VALUE` | Semantic number is finite and non-zero. | AAPL EPS average 1.97754. |

Text metadata uses `TEXT_VALUE`. Booleans are not numbers. Canonicalization
never converts absent, empty, or null to zero. A null `fmt` accompanying
`raw: 0` remains `NUMERIC_ZERO` because formatting is non-semantic.

## 5. Growth-field semantics

The three source paths are separate V1 metrics:

1. `earningsEstimate.growth`: placement and sampled arithmetic support
   year-over-year EPS consensus growth, approximately `avg/yearAgoEps - 1`.
   Store as `EARNINGS_ESTIMATE_GROWTH`.
2. `revenueEstimate.growth`: placement and sampled arithmetic support
   year-over-year revenue consensus growth, approximately
   `avg/yearAgoRevenue - 1`. Store as `REVENUE_ESTIMATE_GROWTH`.
3. Row-level `growth`: yfinance calls this `stockTrend`, but neither the raw
   response nor inspected code defines its calculation. It differs materially
   from EPS growth for AAPL and AMZN. Store as `YAHOO_ROW_GROWTH` with
   `SEMANTICS_UNRESOLVED`.

All three are decimal ratios in the sampled raw values. Never derive or
substitute one for another.

## 6. Methodology findings

`defaultMethodology` is module-level at
`result[0].earningsTrend.defaultMethodology`, not a trend-row field. This
corrects the prior audit's initial inspection.

It was a string in all six responses:

- `gaap`: AAPL, AMZN
- `nongaap`: NVDA, NUE, ADBE, BB

yfinance does not transform, expose, validate, or define it. V1 preserves the
lowercase token verbatim and its absent/null/text state. The vocabulary is not
assumed exhaustive, and no local GAAP/normalized mapping is introduced.

## 7. Repeated-observation findings

Two safely paced rounds were made for all six symbols. Every symbol had an
identical full raw JSON hash, identical row order, identical endDate sequence,
and identical key shape between rounds.

ADBE's collision reproduced: `0q`, `+1q`, and `0y` all used
`2026-11-30`; the two quarterly targets collide even after target type is
included. AAPL consistently used nominal month ends while canonical
Fundamentals periods use 52/53-week Saturday ends. No timestamp or hidden target
identifier appeared. Short-interval stability is not a provider guarantee or a
consensus change timestamp.

## 8. Error and result contract

Acquisition and fiscal-link outcomes are separate dimensions.

| Result | Contract |
|---|---|
| `SUCCESS_WITH_DATA` | Valid success envelope and non-empty trend; canonicalize/hash. |
| `VALID_NO_DATA` | Valid success envelope and empty trend; no estimate rows. |
| `PROVIDER_SYMBOL_UNAVAILABLE` | Explicit Yahoo not-found response. |
| `RATE_LIMITED` | HTTP 429 or `YFRateLimitError`; never no-data. |
| `TRANSIENT_5XX` | HTTP 500-599/transport equivalent; retry outside parser. |
| `MALFORMED_OR_SCHEMA_MISMATCH` | Invalid JSON, container, required row identity, or date. |
| `AMBIGUOUS_TARGET` | Successful acquisition that cannot link uniquely; linker status. |

Persistence later refines successful data to `SUCCESS_CHANGED` or
`SUCCESS_UNCHANGED` by prior semantic hash. The unavailable-symbol fixture is
based on an observed Yahoo 404 body. 429 and 503 cases are synthetic; neither
was intentionally induced.

## 9. Fixture inventory

All fixtures are under `tests/fixtures/forecasts/yahoo/`.

| Fixture | Origin and purpose |
|---|---|
| `success_with_data_aapl.real_compact.json` | Real compact shape, distinct growth fields, same date across quarter/year, empty object, zero. |
| `ambiguous_target_adbe.real_compact.json` | Real compact reproducible quarterly date collision and order. |
| `success_sparse_bb.real_compact.json` | Real compact sparse/different EPS and revenue analyst counts. |
| `result_cases.synthetic.json` | No-data, observed/compacted unavailable symbol, synthetic 429/503, malformed trend. |
| `field_states.synthetic.json` | The five semantic field states. |

The real fixtures retain only fields needed by the contract. They contain no
headers, cookie, crumb, session data, or unrelated Yahoo modules. They are
2026-09-27 snapshots, not market-value goldens to refresh routinely.

## 10. Canonical semantic payload specification

The executable reference is `tests/yahoo_forecast_contract.py`:

```text
contractVersion: "yahoo_earnings_trend_v1"
defaultMethodology: FieldState
rows: [
  occurrenceIndex: source list position
  providerHorizon: source period
  providerEndDate: normalized ISO date
  topLevelGrowth: FieldState
  earningsEstimate: fixed field map -> FieldState
  revenueEstimate: fixed field map -> FieldState
  epsTrend: fixed field map -> FieldState
  epsRevisions: fixed field map -> FieldState
]
```

Rules:

- Preserve row order and assign zero-based `occurrenceIndex`.
- Preserve horizon verbatim; do not remap moving labels.
- Parse/re-emit `endDate` as strict ISO `YYYY-MM-DD`.
- Normalize numeric raw values to minimal base-10 strings without exponent,
  locale separators, trailing fractional zeros, or negative zero.
- Represent absent, empty, null, zero, non-zero, and text explicitly.
- Keep analyst counts and all three growth paths separate.
- Include module-level methodology.
- Exclude `fmt`, `longFmt`, `maxAge`, `error:null`, transport metadata,
  adapter version, provider symbol, and unknown fields from semantics.

Unknown fields still produce adapter diagnostics. A later semantic expansion
requires a new contract version rather than silent hash changes.

## 11. Semantic hash specification

Serialize the canonical payload as ASCII-safe JSON with recursively sorted
object keys, compact separators, no whitespace, and list order preserved.
Compute lowercase SHA-256 hex over those bytes.

Formatting or `maxAge` changes do not change the hash. Semantic values, field
states, methodology, horizon, endDate, row order, or occurrence changes do.
JSON object key order does not. `contractVersion` participates in the hash.

## 12. Raw payload retention recommendation

Choose **C: canonical payload plus optional short-retention raw evidence**.

- Persist canonical semantic payload/hash long-term for changed snapshots.
- In pilot/early production, retain exact successful raw modules and error
  bodies for a configurable initial 30 days, deduplicated by raw hash.
- Retain compact repository fixtures indefinitely.
- Keep long-term schema-drift names and fetch diagnostics, but never cookie,
  crumb, headers, or unrelated quoteSummary modules.

This supports V1 replay and parser debugging with a reasonable footprint. Any
longer raw retention is an explicit operational decision; no licensing
conclusion is made here.

## 13. Target identity implications

The prior recommendation is confirmed with one refinement: `endDate` is
evidence, never identity and never sufficient for quarter linkage.

- Quarter: `company_id + FISCAL_QUARTER + expected fiscal year + quarter`;
  attach canonical `quarter_id` later.
- Annual: `company_id + FISCAL_YEAR + fiscal_year`.
- Unresolved provider row:
  `snapshot_id + provider_horizon + provider_end_date + occurrence_index`.

`endDate` can constrain candidates, describe cadence, support tolerance
matching, and detect drift. It cannot replace company identity, distinguish
ADBE `0q` from `+1q`, equal every 52/53-week canonical end, or remain stable
as a moving identity. Occurrence is an audit discriminator, not stable
cross-snapshot fiscal identity. The future linker must be versioned and return
`AMBIGUOUS_TARGET` rather than guess.

## 14. Remaining unresolved questions

- Authoritative semantics of row-level `growth`.
- Full methodology vocabulary and definitions beyond observed tokens.
- A live valid-symbol/no-analyst empty trend; no-data remains synthetic.
- Live 429/5xx payloads, deliberately not induced.
- Consensus change time; only fetch time is available.
- Cause and duration of ADBE's duplicate quarterly endDate.
- Final operational raw-evidence retention period.

## 15. Exact next-phase recommendations

1. Promote the test reference into a small production-neutral parser module.
2. Add a transport result that preserves HTTP status/error body and catches
   `YFRateLimitError` before yfinance converts errors to `None`.
3. Report schema drift against this inventory.
4. Add only genuinely observed no-data/new-methodology fixtures during pilot.
5. Implement `forecasts.db` after parser/result API acceptance, with separate
   fetch outcomes and canonical change-only snapshots.
6. Implement fiscal linkage separately with unresolved/ambiguous outcomes.
7. Pilot these six symbols serially before scheduler or universe expansion.

## Verification

`pytest -q tests/test_yahoo_forecast_raw_contract.py` passed 13 tests covering
real fixtures, field states, classifications, hash invariance/sensitivity,
strict dates, ADBE ambiguity, and separate analyst counts.
