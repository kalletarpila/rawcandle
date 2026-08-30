# Fundamentals V4 Provider Strategy

## Sharadar

Sharadar is the primary normalized fundamentals provider. The RawCandle client uses Sharadar Direct REST API only:

```text
https://api.sharadar.com/v1.0
```

Authentication uses:

```text
SHARADAR_API_KEY
x-api-key: <key>
```

No Nasdaq Data Link SDK, `quandl`, or `nasdaqdatalink` library is used.

Preserved V4-0B behavior:

- `/data/fundamentals`
- `/data/SF1` legacy alias for compatibility smoke checks
- ARQ and MRQ filtering
- explicit Q4 rows
- `reportperiod` and `fiscalperiod` preservation
- `permaticker` schema availability
- actions schema inspection
- FREE_TIER_LIMIT classification
- retry policy that does not retry 403 free-tier denials
- secret redaction

## Yahoo

Yahoo is an operational/freshness/complementary provider. Do not migrate V3 Yahoo canonicalization rules as-is.

Later migration phases should split Yahoo into:

1. market/result discovery
A. earnings/result event discovery
1. latest-quarter availability
a. provider observations and cache

## SEC

SEC is an authoritative verification/exception provider, not the default V4 normalized quarterly engine while Sharadar remains accepted.

Later migration phases should split SEC into:

1. filing discovery
A. accession and filing metadata
1. companyfacts retrieval
a. DEI/source-context evidence

V3 repair/reconciliation semantics remain reference-only or retired unless a concrete V4 requirement proves otherwise.

## Sharadar Paid 5-Year Difficult-Ticker Acceptance

V4-0D validates the user's paid `Sharadar Fundamentals 5 Years` entitlement without bulk-downloading the table. The hard gate is a single WDAY ARQ request. If WDAY still returns the former free-tier 403, the acceptance run stops and the implementation is not changed to work around entitlement.

Acceptance scope:

- difficult tickers: AAPL, WDAY, ASTH, CECO, BBY, DELL, GCO, HAE, MRVL, RL, SAIC, TJX, TRNS
- controls: GOOGL, META, AMZN, XOM, KO
- targeted ARQ/MRQ by ticker
- ticker metadata and actions metadata where available
- no `years=5`, `years=10`, or `years=full` bulk table request

Implementation note: V4-0D uses full ticker-scoped fundamentals rows for ARQ/MRQ because the Direct API field projection omitted `fiscalperiod` during acceptance. The request scope remains small and ticker-targeted.

Decision rule: Sharadar may become the V4 primary normalized fundamentals provider only if the hard known-truth fiscal cases pass, explicit Q4 coverage is broad, quarter continuity is coherent, critical fields are materially covered, and ARQ remains distinguishable from MRQ for point-in-time use. Yahoo and SEC remain complementary providers for freshness, events, provenance, and exceptions.

V4-0D result: `SHARADAR_ACCEPTED_AS_V4_PRIMARY_PROVIDER_WITH_GUARDS`. The acceptance run confirmed paid WDAY entitlement, hard fiscal truth matches, 100% explicit Q4 coverage across evaluated completed fiscal years, 100% latest8Q critical field coverage, coherent FCF/debt reconciliation, and 100% permaticker coverage. Guards remain for CIK identity enrichment, source date semantics, and full-row ARQ/MRQ fetches when `fiscalperiod` is required.
