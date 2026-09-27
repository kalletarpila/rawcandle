# Forecast Fiscal Linker V1 Implementation

Date: 2026-09-27

## 1. Identity resolver

`ForecastIdentityResolver` reads `data/fundamentals_v4.db` through SQLite
`mode=ro` and `query_only`. It resolves `(YAHOO_FINANCE, provider_symbol,
acquisition_timestamp)` in this order:

1. provider-security identity created by the acquisition time, matching the
   provider ID or provider ticker;
2. ticker alias whose validity interval contains the acquisition date;
3. security current ticker whose security validity interval contains the date;
4. unresolved.

Each level resolves only when all matching evidence identifies one
`(company_id, security_id)`. Multiple identities return `AMBIGUOUS`; the
resolver never writes aliases or identity rows. Its rule version is
`fundamentals_v4_identity_v1`.

## 2. Fiscal linker algorithm

`ForecastFiscalLinker` receives resolved company identity, acquisition time,
provider horizon, and provider end date. It finds the latest realized fiscal
quarter known at the acquisition boundary and advances the canonical fiscal
sequence. The sequence, rather than date proximity, defines the candidate.

`0q` advances one quarter and `+1q` advances two. `0y` selects the fiscal year
containing the next unreported annual result; after known Q4 this rolls to the
next fiscal year. `+1y` advances one additional fiscal year.

## 3. Acquisition-time knowledge boundary

A `v4_quarter` participates in the known state only when:

```text
COALESCE(first_public_result_date, source_availability_date)
    <= acquisition UTC date
```

`first_public_result_date` is therefore authoritative when established.
`source_availability_date` is the documented fallback for rows whose immutable
first-public baseline has not been established. `period_end` alone never makes
a result known. Fiscal anchors and profiles are included only when their
`created_at_utc` is no later than the acquisition timestamp.

## 4. Quarterly sequence rules

Fiscal quarters use explicit `Q1` through `Q4` ordinal arithmetic. The rollover
from `FY2027 Q4` to `FY2028 Q1` is deterministic. A future target is `LINKED`
by expected fiscal identity even when no canonical quarter exists. An as-known
`canonical_quarter_id` is attached only if that target quarter was itself known
by the acquisition boundary.

## 5. Annual rules

If the latest known quarter is Q1-Q3, `0y` targets that fiscal year. If it is
Q4, `0y` targets the following fiscal year. `+1y` targets the year after `0y`.
These rules use Fundamentals fiscal labels and do not assume calendar years.

## 6. EndDate evidence and tolerance

Yahoo `providerEndDate` is supporting evidence only. The linker estimates a
candidate end from an already-known target period, an acquisition-time fiscal
year anchor, or the issuer's known quarter cadence. The V1 absolute tolerance
is 45 days. Evidence receives `END_DATE_SUPPORT` or
`END_DATE_OUTSIDE_TOLERANCE`; the date never changes the sequence-derived
fiscal identity by itself.

## 7. Non-calendar and 52/53-week handling

Fiscal year and quarter labels come from Fundamentals, so non-calendar issuers
need no calendar-year conversion. Quarter cadence uses 91-day steps and annual
cadence uses 364-day steps only to assess provider date plausibility. The wide
support tolerance accommodates nominal month-end Yahoo dates versus canonical
week-ending dates. Fiscal anchors and the compact calendar profile are retained
as evidence when available.

## 8. Statuses and reason codes

Link statuses are `LINKED`, `AMBIGUOUS`, and `UNRESOLVED`. Identity statuses are
`RESOLVED`, `AMBIGUOUS`, and `UNRESOLVED`.

V1 reason codes are:

```text
IDENTITY_RESOLVED
IDENTITY_AMBIGUOUS
IDENTITY_UNRESOLVED
SEQUENTIAL_FISCAL_MATCH
FISCAL_YEAR_ROLLOVER
FISCAL_ANCHOR_SUPPORT
END_DATE_SUPPORT
END_DATE_OUTSIDE_TOLERANCE
INSUFFICIENT_FISCAL_CONTEXT
MULTIPLE_VALID_TARGETS
PROVIDER_HORIZON_UNSUPPORTED
TARGET_CONFLICT
CANONICAL_QUARTER_RECONCILED
CANONICAL_QUARTER_NOT_YET_AVAILABLE
```

## 9. Link-rule version

Fiscal decisions persist `fundamentals_v4_fiscal_link_v1`. Identity decisions
persist `fundamentals_v4_identity_v1`. Re-running the same rule and evidence is
idempotent through deterministic content hashes. A changed rule version can
coexist with prior derived output without changing provider snapshots.

## 10. Persistence and history model

Migration version `forecasts_v2_fiscal_links` adds two tables:

- `forecast_identity_resolution` stores read-only Fundamentals resolution per
  fetch and rule output.
- `forecast_fiscal_link` stores append-only, content-addressed link events.

Links belong to `fetch_id`, not only `snapshot_id`. This is required because an
unchanged payload reused by a later fetch can give moving horizons a different
fiscal meaning. Existing raw evidence, snapshots, normalized estimate rows,
provider horizons, dates, and fetch timestamps remain immutable. Reserved V1
estimate link columns remain `UNLINKED`; the derived tables are authoritative.

## 11. Future-quarter handling

A quarter can persist as:

```text
company_id + FISCAL_QUARTER + expected FY/FQ
+ canonical_quarter_id NULL + LINKED
```

No placeholder Fundamentals quarter is created. Every normalized metric for
the provider row reaches the target through its snapshot and occurrence index.

## 12. Reconciliation

`reconcile_fetch` reads the latest as-known expected target and performs an
exact current lookup by `(company_id, fiscal_year, fiscal_quarter)`. It appends
a `CURRENT_RECONCILED` event with the canonical ID, ambiguity, or still-missing
state. It never rewrites prior links or provider observations. A corrected
canonical fiscal identity can remove a stale attachment on the next
reconciliation; a full rule change is handled by rerunning the linker under a
new version.

## 13. Point-in-time linked query semantics

`linked_as_known_at` first selects the latest valid forecast fetch at or before
T under the existing changed/unchanged/no-data contract. It then requires the
requested company, fiscal target, rule version, and link mode. Estimate values
always come from that selected fetch's snapshot. AS_KNOWN links are accepted
only when their Fundamentals cutoff is no later than the fetch timestamp.

## 14. Retrospective canonical reconciliation distinction

`AS_KNOWN` answers retain the canonical ID state available at acquisition.
`CURRENT_RECONCILED` is an explicit caller choice and may attach a quarter that
Fundamentals learned later. Current reconciliation never silently replaces the
historical research view.

## 15. Edge cases tested

Tests cover provider identity precedence, alias validity and ambiguity,
quarterly and annual sequence, Q4 rollover, non-calendar and 52/53-week dates,
ADBE-style duplicate end dates, unsupported and insufficient context,
ambiguous context, future null canonical IDs, later reconciliation, idempotent
versioned output, linked quarterly and annual as-of queries, look-ahead
prevention, canonical fiscal correction, and price-target exclusion.

## 16. Remaining operational work before daily pilot

Add an explicit operator CLI that runs identity and fiscal linking for selected
already-persisted fetch IDs, reports unresolved/ambiguous distributions, and
performs reviewed reconciliation. Then validate the rule against a bounded
AAPL/ADBE/AMZN/BB pilot before any scheduler integration. Production
`data/forecasts.db` migration and scheduling remain intentionally outside this
phase.
