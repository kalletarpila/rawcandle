# Forecast Operator Pilot

Date: 2026-09-27

## 1. CLI commands

The reviewed manual workflow is exposed through one explicit module:

```bash
python -m rawcandle.cli.forecasts migrate
python -m rawcandle.cli.forecasts acquire --symbols AAPL ADBE AMZN BB NVDA NUE
python -m rawcandle.cli.forecasts link --run-id RUN_ID
python -m rawcandle.cli.forecasts reconcile --run-id RUN_ID
python -m rawcandle.cli.forecasts report --run-id RUN_ID
```

Every command accepts `--db`; commands reading Fundamentals also accept
`--fundamentals-db`. There is no scheduler or implicit universe expansion.

## 2. Production migration result

The explicit operator migration created `/home/kalle/projects/rawcandle/data/forecasts.db`.
The target did not exist before migration. The guard rejects known non-forecast
database names and existing SQLite databases without the forecast schema marker.
Migration is idempotent and verifies writability with a rolled-back temporary
write probe.

## 3. Schema and quick-check result

The schema version is `forecasts_v2_fiscal_links`. `PRAGMA quick_check`
returned `ok`; all 10 required tables and 9 required indexes were present.
Before acquisition the run, fetch, and snapshot counts were all zero.

After the pilot the principal counts were:

```text
forecast_run                         1
forecast_fetch                      18
forecast_snapshot                   18
forecast_estimate                  552
forecast_price_target               30
forecast_earnings_history_reference 23
forecast_identity_resolution         6
forecast_fiscal_link                48
```

## 4. Pilot symbols

Exactly `AAPL ADBE AMZN BB NVDA NUE` were requested. The production run ID was
`54122e8b1c3245cf8ec3fca5cac2184d`. No second live acquisition was run.

## 5. Acquisition summary

All 18 selected symbol/family attempts completed as `SUCCESS_CHANGED`:

| Family | Attempts | SUCCESS_CHANGED |
|---|---:|---:|
| FISCAL_ESTIMATE | 6 | 6 |
| PRICE_TARGET | 6 | 6 |
| EARNINGS_HISTORY_REFERENCE | 6 | 6 |

There were no valid-no-data, unavailable-symbol, rate-limit, transient,
malformed, or schema-mismatch terminal outcomes.

## 6. Identity route distribution

All six fiscal fetches resolved uniquely through `TICKER_ALIAS_AS_OF`.
Provider-security identity, current-security ticker, ambiguous, and unresolved
counts were zero. The resolver opened Fundamentals V4 in SQLite read-only and
query-only mode. No Yahoo provider identity was created.

## 7. Fiscal-link distribution

The six fiscal payloads contained 24 provider horizon rows. All 24 produced
`LINKED` AS_KNOWN decisions under `fundamentals_v4_fiscal_link_v1`; ambiguous
and unresolved counts were zero. ADBE's duplicate `2026-11-30` end date did not
collapse the targets: `0q` linked to FY2026 Q4 and `+1q` to FY2027 Q1.

## 8. Reconciliation summary

CURRENT_RECONCILED produced 24 separate history rows while preserving all
AS_KNOWN rows. Twelve were annual targets and twelve were future fiscal
quarters whose canonical quarter was not yet available. No canonical quarter
could yet be attached, and there were no ambiguous or changed attachments.

## 9. Annual mappings

| Symbol | 0y | +1y |
|---|---|---|
| AAPL | FY2026, 2026-09-30 | FY2027, 2027-09-30 |
| ADBE | FY2026, 2026-11-30 | FY2027, 2027-11-30 |
| AMZN | FY2026, 2026-12-31 | FY2027, 2027-12-31 |
| BB | FY2027, 2027-02-28 | FY2028, 2028-02-29 |
| NVDA | FY2027, 2027-01-31 | FY2028, 2028-01-31 |
| NUE | FY2026, 2026-12-31 | FY2027, 2027-12-31 |

All annual links had `END_DATE_SUPPORT`. Every `+1y` mapping also recorded
`FISCAL_YEAR_ROLLOVER`. No target conflict was observed.

## 10. EndDate tolerance statistics

Across all 24 linked fiscal horizons:

```text
within_45d       23
outside_45d       1
median_abs_diff   3 days
p90_abs_diff      7 days
max_abs_diff     88 days
```

The sole outside observation was ADBE `+1q`. Yahoo repeated `2026-11-30` for
both quarterly horizons; sequence correctly linked `+1q` to FY2027 Q1 and
retained `END_DATE_OUTSIDE_TOLERANCE`. This is expected provider drift, not a
reason to retune the 45-day supporting tolerance.

## 11. Provider failures, retries, and rate limits

There were zero retries, zero rate limits, and zero provider failures. The
transport retained the existing serial 0.5-second minimum request spacing,
30-second timeout, and bounded retry policy.

## 12. Schema drift

There were 138 drift-path occurrences and 23 distinct paths. All were extra
`financialData` fields outside the accepted price-target semantic contract,
including ratios, margins, cash/debt fields, growth fields, analyst-opinion
count, and recommendation fields. They were recorded but excluded from the
price-target hash and normalized contract. No earningsTrend or earningsHistory
drift was observed.

## 13. Raw evidence volume

The pilot retained 18 raw rows with 18 distinct SHA-256 hashes and 43,551 body
bytes. Retention deadlines were 30 days after fetch. Searches found no
`set-cookie`, `authorization`, `crumb`, `cookie`, or `session` keys. Raw rows
therefore contain module/error bodies, not request-session secrets.

## 14. Point-in-time sanity checks

For AAPL at the run's final fetch time, `as_known_at` returned 92 normalized
fiscal estimate rows and five price-target rows. `linked_as_known_at` returned
one FY2026 Q4 match in each explicit mode. AS_KNOWN retained a null canonical
quarter ID; CURRENT_RECONCILED also remained null because the future canonical
quarter does not yet exist. One microsecond before the first pilot fetch,
`as_known_at` returned no result. The AAPL price-target fetch had zero fiscal
links.

## 15. Observed issues

The live data exposed the known ADBE duplicate-endDate inconsistency and a
large number of intentionally ignored `financialData` fields. Neither changed
accepted semantics. This single run cannot exercise live `SUCCESS_UNCHANGED`,
failure, no-data, rate-limit, or later canonical attachment behavior; those
paths are covered by deterministic tests. Raw cleanup is still manual.

## 16. Recommendation before universe expansion

Run this exact six-symbol workflow manually once per trading day for a short
observation window. Review status, identity-route, drift, retry/rate-limit, and
endDate distributions after each run. Add a dry-run/reporting raw-evidence
cleanup command and prove later-quarter reconciliation on naturally arriving
Fundamentals rows. Only after that evidence should RawCandle define a bounded
production universe and scheduler contract.
