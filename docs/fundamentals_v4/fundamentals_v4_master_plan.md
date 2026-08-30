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
