# Forecast Persistence V1 Implementation (2026-09-27)

## 1. Module boundaries

The first production foundation is implemented under `rawcandle/forecasts/`:

- `contracts.py`: provider-family parsing, field states, canonical payloads,
  semantic hashes, and schema-drift diagnostics.
- `transport.py`: raw Yahoo quoteSummary requests through yfinance's shared
  `YfData` session/cookie/crumb machinery, forecast-specific pacing, bounded
  retries, and acquisition classification.
- `schema.py`: the standalone `forecasts_v1` SQLite contract and explicit
  migration function.
- `repository.py`: immutable fetch history, change-only snapshots, normalized
  family records, raw evidence, run accounting, and point-in-time queries.
- `service.py`: synchronous per-symbol collection across selected families;
  universe selection and scheduling remain outside this boundary.
- `rawcandle/cli/run_forecast_migrations.py`: an explicit operator command. It
  requires `--db`; no production path is assumed or implicitly created.

Yahoo Finance is persisted as provider `YAHOO_FINANCE`. yfinance and its
version are adapter metadata only. No OHLCV, Fundamentals, analysis, scheduler,
or production database module is imported by the forecast domain.

## 2. Transport and result contract

`YahooForecastTransport` requests exactly one relevant module for each family:

| Family | Yahoo module |
|---|---|
| `FISCAL_ESTIMATE` | `earningsTrend` |
| `PRICE_TARGET` | `financialData` |
| `EARNINGS_HISTORY_REFERENCE` | `earningsHistory` |

It calls `YfData.get` directly instead of yfinance's Analysis normalizers. This
retains HTTP status, parsed provider body, exact raw body, raw SHA-256, and
provider error details before DataFrame/empty-result normalization can lose
them. Cookie, crumb, session objects, and headers are never returned or stored.

`YahooRawResult` records request/fetch timestamps, symbol, family, HTTP status,
acquisition status, error class/code/message, raw payload/body/hash, and attempt
count. Classifications are:

- `SUCCESS_WITH_DATA`
- `VALID_NO_DATA`
- `PROVIDER_SYMBOL_UNAVAILABLE`
- `RATE_LIMITED`
- `TRANSIENT_FAILURE`
- `MALFORMED_OR_SCHEMA_MISMATCH`

Defaults are effectively serial: `max_concurrency=1`, a process limiter with a
0.5-second minimum request-start interval, 30-second timeout, and two retries.
Retry delay is bounded by attempt count using exponential backoff. Configuration
allows deliberate adjustment without coupling to OHLCV pacing.

## 3. earningsTrend parser

The production parser preserves the frozen
`yahoo_earnings_trend_v1` contract and matches the fixture reference:

- module-level `defaultMethodology`;
- source row order and zero-based `occurrenceIndex`;
- verbatim provider horizon and strict ISO provider endDate;
- EPS/revenue estimates, analyst counts, currencies, trends, revisions;
- separate earnings growth, revenue growth, and `YAHOO_ROW_GROWTH` paths;
- `FIELD_ABSENT`, `EMPTY_OBJECT`, `EXPLICIT_NULL`, `NUMERIC_ZERO`,
  `NUMERIC_VALUE`, and `TEXT_VALUE`.

`YAHOO_ROW_GROWTH` remains source-path-specific and semantically unresolved.
No fiscal year/quarter is inferred.

Unknown module, row, and section fields are excluded from V1 semantics but are
emitted as schema-drift paths and persisted with fetch/snapshot diagnostics.

## 4. Canonical and hash contract

All families use deterministic compact JSON with recursively sorted object
keys. Numeric raw values become finite, minimal base-10 strings; negative zero
becomes zero. Dates are normalized to ISO and list order is preserved.

`fmt`, `longFmt`, `maxAge`, transport fields, adapter metadata, provider symbol,
and unknown fields do not enter the semantic payload. SHA-256 is computed over
the canonical ASCII JSON bytes. Each family has an explicit contract version:

- `yahoo_earnings_trend_v1`
- `yahoo_price_target_v1`
- `yahoo_earnings_history_reference_v1`

Formatting-only changes therefore do not create snapshots. Semantic state,
value, order, methodology, horizon, or date changes do.

## 5. forecasts.db schema

The schema is defined in source and is not applied to the production path by
this change. Tables are:

| Table | Responsibility |
|---|---|
| `forecast_schema_version` | Database contract version. |
| `forecast_run` | One explicit acquisition invocation, scope, status, counters. |
| `forecast_fetch` | Every family/security attempt and its terminal outcome. |
| `forecast_snapshot` | Immutable, deduplicated canonical semantic content. |
| `forecast_estimate` | Queryable normalized earningsTrend metrics. |
| `forecast_price_target` | Current/low/high/mean/median target observations. |
| `forecast_earnings_history_reference` | Secondary Yahoo EPS estimate/actual/surprise evidence. |
| `forecast_raw_evidence` | Deduplicated short-retention raw module/error body. |

The operator command is:

```bash
python -m rawcandle.cli.run_forecast_migrations --db data/forecasts.db
```

It must be run explicitly in a later production step. Tests invoke it only
against temporary paths.

Company/security IDs are nullable logical references. They are not SQLite
foreign keys into Fundamentals databases. `identity_key` prefers security ID,
then company ID, and otherwise a normalized provider-symbol route. This avoids
making ticker permanent identity while permitting pre-integration acquisition.

## 6. Fetch and change-only snapshots

Every attempt inserts one `forecast_fetch`. For valid semantic data the
repository compares the canonical hash with the latest successful snapshot for
the same provider, family, and identity at or before the fetch timestamp.

- Equal hash: `SUCCESS_UNCHANGED`, reference the prior snapshot, insert no
  normalized records.
- Different hash: `SUCCESS_CHANGED`, create or content-addressably reuse an
  immutable snapshot, and insert normalized records only for new content.
- Failed fetch: persist diagnostics/evidence, never alter prior snapshots.
- Valid no-data: persist `VALID_NO_DATA` with no snapshot. It is an explicit
  provider observation, not a deletion of historical rows.

Snapshots are unique by provider, family, logical identity, and content hash.
`first_fetch_id` is a deferred foreign key so snapshot and first fetch remain
atomic in one transaction.

## 7. Price-target semantics

`financialData` is canonicalized independently from fiscal estimates. The
semantic values are `currentPrice`, `targetLowPrice`, `targetHighPrice`,
`targetMeanPrice`, and `targetMedianPrice`, exposed as current/low/high/mean/
median. `financialCurrency` is preserved as a field state.

Price-target snapshots have their own hash and normalized rows. They use the
security/company identity and observation knowledge time; they have no fiscal
target identity and are never mixed with `forecast_estimate` rows.

## 8. Earnings-history reference semantics

`earningsHistory.history` preserves source order, provider period, normalized
quarter date, module methodology, currency, EPS estimate, EPS actual, EPS
difference, and surprise percentage.

Rows are forced to authority `YAHOO_PROVIDER_REFERENCE`. They are evidence for
future QA/reconciliation only. No code reads or writes Fundamentals actuals,
and Yahoo EPS actual never becomes canonical financial data.

## 9. Point-in-time queries

`ForecastRepository.as_known_at` normalizes the requested timestamp to UTC and
selects the latest successful knowledge observation at or before it.

- `SUCCESS_CHANGED`/`SUCCESS_UNCHANGED`: follow the immutable snapshot and
  return normalized family records.
- `VALID_NO_DATA`: return the successful fetch with no snapshot/records.
- failures and rate limits remain operationally queryable in `forecast_fetch`
  but do not erase or supersede prior known semantic state.
- before the first successful observation: return no result.

Fetch time is explicitly RawCandle's knowledge timestamp. It is not claimed to
be Yahoo's consensus-change timestamp.

## 10. Raw-evidence retention

Canonical payload, semantic hash, schema-drift diagnostics, and fetch
diagnostics are long-term records. Raw successful module bodies and provider
error bodies are optionally retained, deduplicated by raw hash, with a default
30-day `retain_until_utc` target.

No cleanup automation is included. The retention duration is repository/
transport configuration for a future operator workflow. No unrelated modules,
request headers, cookie, crumb, or session secrets are persisted.

## 11. Identity boundary

This phase accepts existing `company_id` and `security_id` from its caller but
does not resolve or mutate Fundamentals identity. It creates no company master,
ticker alias, provider identity, CIK, fiscal anchor, or canonical quarter.

Provider symbol remains routing/evidence. A symbol-only identity is explicitly
the unresolved fallback and can later be reconciled by the accepted
Fundamentals identity resolver.

## 12. Remaining fiscal-linker work

The following is intentionally absent:

1. Resolve Yahoo aliases as-of acquisition time to existing security/company.
2. Map provider horizon/endDate evidence to expected fiscal year/quarter using
   versioned Fundamentals fiscal rules.
3. Preserve ambiguous/unresolved outcomes, including ADBE's duplicate endDate.
4. Later attach realized `canonical_quarter_id` without creating future
   Fundamentals quarters.
5. Add no-look-ahead reconciliation against Fundamentals publication dates.

All fiscal estimate rows currently have null future-link fields and
`link_status='UNLINKED'`.

## 13. Remaining work before scheduling

1. Run a reviewed explicit migration against `data/forecasts.db`.
2. Add a small manual six-symbol pilot command around transport/repository.
3. Confirm live no-data and additional provider error behavior.
4. Measure pacing, retry, raw-retention volume, and schema drift over time.
5. Add operational raw-evidence cleanup with dry-run/reporting.
6. Decide whether forecast failure should affect a future scheduler's overall
   status; it must remain independent from OHLCV success.
7. Only then add a separate daily scheduler step.

Universe-wide acquisition, recommendations, upgrades/downgrades, benchmark
growth, LTG, analyst-level estimates, and research models remain out of scope.

## 14. Tests executed

Targeted tests:

```bash
pytest -q tests/test_yahoo_forecast_raw_contract.py \
  tests/test_forecast_persistence_v1.py \
  tests/test_forecast_acquisition_service.py
```

Result: 30 passed. Coverage includes frozen-parser parity, field states, hash invariance and
sensitivity, schema drift, all acquisition classes, bounded rate-limit retry,
non-JSON error evidence, migration/idempotency, database constraints,
changed/unchanged snapshots, failure/no-data behavior, as-of boundaries, price
targets, earnings-history reference authority, and raw-evidence deduplication.
