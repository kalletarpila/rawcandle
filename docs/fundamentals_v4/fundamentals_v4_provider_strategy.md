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
