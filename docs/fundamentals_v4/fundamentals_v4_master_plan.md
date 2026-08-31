# Fundamentals V4 Master Plan

## 1. V4-0 Provider And Architecture Validation

A. Establish RawCandle as V4 owner.

1. Migrate Sharadar Direct API client.

a. Run free-tier smoke and document provider behavior.

## 2. V4-1 Provider Store

Implement `fundamentals_provider.db` migrations, provider run tracking, raw observation tables, retry metadata, content hashes, and provenance references.

## 3. V4-2 Canonical Quarterly Fundamentals

Implement canonical company/security mapping, fiscal quarter identity, accepted field values, provenance pointers, and readiness metadata in `fundamentals_v4.db`.

## 4. V4-3 Historical Sharadar Backfill

After paid access is activated and accepted, run controlled historical Sharadar acquisition through the same RawCandle client.

## 5. V4-4 TTM

Port EBIT-first TTM behavior into `rawcandle/fundamentals/ttm/`, preserving current formulas and PIT readiness rules.

## 6. V4-5 Score

Port the locked score model without recalibration.

## 7. V4-6 Lifecycle

Port lifecycle state logic without changing thresholds or fingerprints.

## 8. V4-7 Valuation

Implement valuation using RawCandle-owned OHLCV and canonical publish/availability dates.

## 9. V4-8 Yahoo Operational Refresh

Use Yahoo for result discovery, current availability, event timing, and selective enrichment.

## 10. V4-9 SEC Verification / Exception Layer

Use SEC for filing evidence, CIK/accession provenance, and targeted exception handling.

## 11. V4-10 Parallel V3/V4 Validation

Compare RawCandle V4 outputs against SwingMaster V3 for known cohorts without making V4 runtime depend on V3.

## 12. V4-11 Production Cutover

Switch downstream consumers to RawCandle V4 outputs after parity, acceptance, and rebuild procedures are proven.

## Next Phase

`V4-0D — SHARADAR PAID DIFFICULT-TICKER ACCEPTANCE`

Run from RawCandle after activating one month of Sharadar Fundamentals full history. Do not implement the canonical V4 schema before provider acceptance unless a later architecture review changes that decision.

## V4-0D Acceptance Update

V4-0D runs the paid 5-year difficult-ticker acceptance from RawCandle, using the existing Sharadar Direct API client and `SHARADAR_API_KEY`. It does not create V4 production databases and does not bulk-download the fundamentals table.

If accepted, the next implementation phase is:

`V4-1 — PROVIDER STORE + CANONICAL SCHEMA DESIGN`

Initial V4-1 schema design may use Sharadar ARQ as the primary quarterly source, while keeping Yahoo and SEC as complementary providers for operational freshness, event timing, identity/provenance, and exception verification.

V4-0D result: `SHARADAR_ACCEPTED_AS_V4_PRIMARY_PROVIDER_WITH_GUARDS`. Proceed to V4-1 with the documented identity, field-projection, date-semantics, and complementary-provider guards.

## V4-1A Schema Design Update

V4-1A result: `V4_SCHEMA_DESIGN_COMPLETE_WITH_OPEN_ARCHITECTURE_ITEMS`.

Implemented RawCandle-owned schema foundations for provider, canonical, and analysis databases, plus a disposable prototype runner and regression tests. The prototype proves ARQ/MRQ coexistence in provider storage, ARQ-only canonicalization, fiscalperiod/reportperiod preservation, explicit Q4 handling, field-level provenance, replay idempotency, and output-only contracts for Score, Lifecycle, and Valuation.

The only open architecture item found by the prototype is CIK source availability. SwingMaster V3 was inspected read-only and does not expose deterministic CIK values. V4-1B must either accept NULL CIK bootstrap until SEC provider ingest exists or provide another deterministic local CIK source. CIKs must not be invented.

Next action:

`DECIDE V4-1B CIK SOURCE: ACCEPT NULL CIK BOOTSTRAP UNTIL SEC PROVIDER INGEST OR SUPPLY A DETERMINISTIC LOCAL CIK SOURCE; DO NOT INVENT CIKS`

## V4-1A-1 Identity Calendar Bootstrap Update

V4-1A-1 corrects the CIK source to RawCandle's local `temp/v3_active_tickers_99_27.csv`. This file is the initial deterministic V4 bootstrap source for SEC CIK, verified fiscal-year-start anchors, typical fiscal-year start, `chain_status`, and `break_reason`.

The new bootstrap path parses CIK from the SEC Companyfacts URL in `Lähde`, preserves zero-padded 10-digit CIK values, imports company-level CIK provenance, and normalizes wide FY-start CSV columns into annual `company_id + fiscal_year` anchor rows. Missing CIKs remain NULL/review rows; no SEC network calls are made and CIKs are not inferred.

Sharadar ARQ remains the primary quarterly source for `fiscalperiod`, `reportperiod`, and financial fields. Fiscal calendar anchors are validation/reference metadata only.

V4-1A-1 result: `V4_IDENTITY_CALENDAR_BOOTSTRAP_COMPLETE_WITH_REVIEW_ITEMS`.

The prototype found no blocking identity or fiscal-anchor conflicts. It imported 2,436 company-level CIK mappings and 35,245 normalized company/year fiscal anchors. The only review item is 22 local CSV rows whose `Lähde` value does not contain a strict SEC Companyfacts CIK URL.

Next action:

`REVIEW 22 BOOTSTRAP CSV ROWS WITHOUT PARSABLE SEC COMPANYFACTS CIK; OTHERWISE PROCEED TO V4-1B WITH IMPORTED CIKS, VERIFIED FISCAL-CALENDAR METADATA, AND NULL CIKS ONLY WHERE THE LOCAL SOURCE LACKS A STRICT COMPANYFACTS CIK`

## V4-1B Production Bootstrap Update

V4-1B created the first RawCandle production Fundamentals V4 databases:

```text
data/fundamentals_provider.db
data/fundamentals_v4.db
data/fundamentals_analysis.db
```

The production bootstrap used Sharadar Direct `GET /data/fundamentals?years=5` only. Raw downloaded and extracted provider files, replay snapshots, and detailed audit CSV/JSON outputs are under:

```text
temp/fundamentals_v4_1b_production_bootstrap/20260830T205438Z/
```

Result: `V4_PRODUCTION_BOOTSTRAP_COMPLETE_WITH_REVIEW_ITEMS`.

The provider store ingested 102,204 matched target-universe observations: 51,476 ARQ and 50,728 MRQ. Non-quarterly dimensions were not ingested into production provider tables. Canonicalization accepted ARQ only and created 50,585 canonical quarterly financial rows plus 602,940 field-level provenance rows.

The 2,470 local bootstrap tickers remain the authoritative initial V4 universe. The production identity bootstrap created 2,458 companies, 2,470 securities, imported 2,436 company CIK rows, and preserved 22 NULL CIK review rows. Sharadar's 5Y bulk fundamentals CSV did not include a `permaticker` column in this entitlement response, so no production `provider_security_identity` permaticker rows could be imported from this bulk file; ticker-security collisions and permaticker conflicts were both 0.

Integrity and replay checks passed: all three SQLite quick checks returned `ok`, foreign-key errors were 0, canonical duplicate FY/Q rows were 0, non-null canonical fields without provenance were 0, replay created 0 duplicate rows, and baseline fingerprints were identical.

Review items before TTM migration:

- 22 local bootstrap rows without parsable CIK.
- 19 target tickers without matched ARQ/MRQ rows in the Sharadar 5Y bulk file.
- 1,044 fiscal anchor mismatches and 238 anchor-not-available cases for audit review; canonical identity was not rewritten.
- 190 completed fiscal years with Q4 missing and 172 company-level sequence gaps.
- 1 debt reconciliation `DIFFERENT` row, 255 sharesbas discontinuity flags, and missing provider components where reported.
- Sharadar 5Y bulk fundamentals endpoint did not provide permaticker values.

Next action:

`KEEP THE PRODUCTION V4 BASELINE FROZEN; RESOLVE ONLY THE SPECIFIC IDENTITY / COVERAGE / PROVIDER QUALITY REVIEW ITEMS BEFORE TTM MIGRATION`

## V4-1B-1 Bootstrap Review Update

V4-1B-1 resolved the production bootstrap review population without changing canonical financial values and without running TTM, Score, Lifecycle, or Valuation.

Result: `V4_BOOTSTRAP_REVIEW_COMPLETE_WITH_TRUE_PROVIDER_GAPS`.

The review ingested one Sharadar `tickers` metadata snapshot and one Sharadar `actions` snapshot. It populated 2,465 / 2,470 Sharadar provider security identities with permaticker, left 5 permaticker NULL, and found 0 duplicate permaticker mappings. The original 19 unmatched target tickers were classified as 14 `PROVIDER_TICKER_DIFFERENT`, 3 `TICKER_RENAMED`, and 2 `BOOTSTRAP_UNIVERSE_STALE`.

Window-aware Q4 review corrected the denominator: 9,830 fully observable completed fiscal years, 9,822 explicit Q4 present, and 8 true Q4 provider gaps, for 99.9186% clean Q4 coverage. Continuity is now 128 fully observable continuous companies, 2,151 continuous with left-window truncation, 172 true gaps, and 7 identity-review/no-quarter cases.

TTM input readiness is 2,434 / 2,458 companies, or 99.0236%. The 24 not-ready companies are explained by missing critical fields, latest4 sequence gaps, or fewer than four quarters. These are explicit flags, not a blocker to starting V4-2.

Next action:

`PROCEED TO V4-2 WITH EXPLICIT GAP FLAGS; DO NOT DELAY TTM MIGRATION FOR NON-MATERIAL PROVIDER EDGE CASES`

## Phase V4-2

Classification: `V4_TTM_MIGRATION_COMPLETE_WITH_NON_BLOCKING_GAPS`

Status: `DONE`

TTM model/version: `V4_TTM_EBIT_FIRST_V1`

Production TTM rows: `50585`

Current TTM ready / not ready: `2434` / `24`

Next: `PROCEED TO V4-3: MIGRATE AND VALIDATE THE LOCKED FUNDAMENTAL SCORE ARCHITECTURE AGAINST V4 CANONICAL + TTM DATA; KEEP THE KNOWN-GAPS REGISTER AS AN EXPLICIT DOWNSTREAM QUALITY INPUT`

## V4-3 Score Calibration

V4-3 produced the historical candidate `V4_FUNDAMENTAL_SCORE_V1` specification and calibration artifacts. It is superseded by V4-3B. Production Score writes remain frozen.

## V4-3A Score Scaling

V4-3A redesigned the now-superseded `V4_FUNDAMENTAL_SCORE_V1` as independent continuous absolute 0..N component scales. Its artifacts remain historical evidence, not the active Score V1 contract.

## V4-3B Simple Score Methodology

V4-3B locked `SIMPLE_FUNDAMENTAL_SCORE_V1`, corrected calibration to true quarter-end as-of cross-sections, and locked Consistency and the 4x Balance Sheet floor. Dilution remains blocked pending split-normalized period-end basic-share history. Reliable point-in-time financial-company and REIT classification is also an upstream calibration limitation. Production Score writes remain frozen until these contracts are resolved and a later phase explicitly authorizes implementation.
