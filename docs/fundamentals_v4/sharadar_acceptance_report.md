# Sharadar Paid 5-Year Difficult-Ticker Acceptance

V4-0D runs from RawCandle with the migrated Sharadar Direct API client. The test uses targeted ticker-level ARQ/MRQ requests plus metadata/actions probes. It does not use Nasdaq Data Link, does not bulk-download the 5-year table, and does not create V4 production databases.

ARQ/MRQ acceptance fetches full ticker-scoped fundamentals rows because field projection omitted `fiscalperiod` during acceptance. This is treated as an API behavior guard, not a schema blocker.

## Acceptance Set

Difficult tickers:

```text
AAPL WDAY ASTH CECO BBY DELL GCO HAE MRVL RL SAIC TJX TRNS
```

Control tickers:

```text
GOOGL META AMZN XOM KO
```

## Hard Known-Truth Cases

- AAPL: `2025-12-27 -> 2026-Q1`
- WDAY: `2026-04-30 -> 2027-Q1`
- ASTH: `2026-03-31 -> 2026-Q1`
- CECO: `2026-03-31 -> 2026-Q1`

## Decision Use

If V4-0D classifies Sharadar as accepted or accepted with guards, RawCandle may proceed to V4-1 provider-store and canonical-schema design using Sharadar ARQ as the primary quarterly source.

The detailed raw acceptance outputs are written under:

```text
temp/fundamentals_v4_0d_sharadar_paid_acceptance/<timestamp>/
```

Those artifacts are not committed.

## V4-0D Result

Latest accepted artifact root:

```text
temp/fundamentals_v4_0d_sharadar_paid_acceptance/20260830T161746Z/
```

Classification:

```text
SHARADAR_ACCEPTED_AS_V4_PRIMARY_PROVIDER_WITH_GUARDS
```

Summary:

- WDAY paid entitlement confirmed; old free-tier 403 is gone.
- 18 tickers tested with 72 network requests.
- AAPL, WDAY, ASTH, and CECO hard fiscal truth cases matched.
- 18/18 tickers had continuous ARQ fiscal-quarter sequences.
- 54/54 completed fiscal years had explicit Q4 coverage.
- Latest8Q coverage was 100% for Revenue, EBIT, EBITDA, OCF, Capex, FCF, Cash, Debt, and Sharesbas.
- FCF reconciled exactly or within rounding for 360/360 comparable ARQ rows.
- Debt reconciled exactly or within rounding for 360/360 comparable ARQ rows.
- Sharesbas latest8Q coverage was 100%; no unexplained share discontinuities were detected.
- ARQ and MRQ were distinct across matched periods, supporting ARQ as the V4 point-in-time quarterly source.
- Permaticker metadata coverage was 100%; CIK was not returned by the tested ticker metadata endpoint.

Guards for V4-1:

- Store Sharadar `permaticker` as provider identity metadata, not RawCandle's global key.
- Keep SEC CIK as a separate identity/provenance field once SEC provider work starts.
- Preserve the field-projection guard: ticker-scoped full ARQ/MRQ rows are required when fiscalperiod is needed.
- Treat `date` as filing/source availability fallback, not guaranteed earnings-release date.
- Keep Yahoo/SEC complementary for result timing, external fiscal-calendar evidence, and exception verification.
