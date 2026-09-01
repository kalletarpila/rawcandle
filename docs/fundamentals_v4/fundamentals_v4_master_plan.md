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

### Valuation Phase 3B

Status: `PURE_ENGINE_AND_TEMPORARY_MIGRATION_FOUNDATION_COMPLETE_NOT_PRODUCTION_ACTIVE`

Phase 3B adds the canonical `net_income_common <- netinccmn` and TTM `ttm_net_income_common` contracts, an explicit temporary-database migration, deterministic availability-date price selection, exact current taxonomy applicability rules, and the pure `ABSOLUTE_VALUATION_SCORE_V1` engine. Production schemas, valuation rows, normal pipelines, and backfills remain unchanged. Phase 3C may design guarded persistence and production migration after reviewing the Phase 3B rehearsal.

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

V4-3B locked `SIMPLE_FUNDAMENTAL_SCORE_V1`, corrected calibration to true quarter-end as-of cross-sections, and locked the 4x Balance Sheet floor. The canonical universe already excludes banks, insurers, REITs, and other true financial companies, so point-in-time sector classification is not a Score blocker. Later owner-approved revisions score stored period-end basic shares directly, treat positive YoY changes above 50% as genuine dilution, and replace level-stability Consistency with the 10-point five-snapshot Fundamental Trajectory component. V4-4 implements production Score writes in the existing analysis schema.

## Lifecycle Phase 2A

Status: `PURE_METHODOLOGY_IMPLEMENTED_NOT_PRODUCTION_ACTIVE`

Phase 2A implements `V4_FUNDAMENTAL_LIFECYCLE_V1` as a pure raw classifier and immutable two-observation state machine. The active specification is `fundamentals_v4_lifecycle_v1_specification.md`. SCALING precedes GROWTH, PRE_REVENUE is an exact four-zero-quarter STARTUP profile, STRUGGLING is separate from TRANSITION, DISTRESSED enters immediately and exits only after two identical recovery states, and UNCLASSIFIED clears candidates while exposing the last confirmed state only as history.

No schema, production database, Score behavior, backfill, scheduler, report or activation changed. The next implementation phase is a small deterministic revised-history persistence and production backfill.

## Lifecycle Phase 2B (Retired Project Record)

Status: `RETIRED_BEFORE_PRODUCTION_ACTIVATION`

Phase 2B implemented an append-only PIT persistence experiment in commit `f3b5520d876463aeced46ec7f55fa235206f5101`. It was never migrated, backfilled, scheduled, reported or activated in production. Phase 2B.1 removed its code, schema definitions, CLI, tests and active specification in a forward cleanup commit; Git history preserves the experiment if it is ever needed for research.

The locked direction is revised-history only. Future lifecycle production history will use currently accepted canonical and TTM data, run in canonical fiscal-quarter order, carry the explicit label `REVISED_HISTORY`, and remain subject to retrospective restatement changes. It answers what lifecycle history looks like under currently accepted fundamentals, not what an investor saw on each historical date. This is an accepted simplification for the personal research scope. Score V1 remains independent.

## Lifecycle Phase 2C

Phase 2C implements the unactivated revised-history pipeline: current canonical/TTM adapter, complete company replay through the unchanged Phase 2A engine, the `lifecycle_revised_result` schema, atomic fingerprint-scoped replacement, explicit-fingerprint readers, guarded dry-run/apply CLI, quick checks and a temporary full-universe rehearsal. The production analysis database is explicitly blocked as a destination. Production migration and backfill remain Phase 2D work requiring separate authorization.

## Lifecycle Phase 2D

Phase 2D added narrow exact-path production authorization and activated revised-history refresh after the existing Score V1 production stage. The operational refresh is full-universe because no trustworthy changed-company set is currently exposed. Lifecycle uses its own transaction, preserves the previous lifecycle dataset on failure and cannot roll back already committed canonical, TTM or Score data. The legacy empty `lifecycle_result` table remains untouched; `lifecycle_revised_result` is the active Lifecycle V1 table. The authorized deployment completed on 2026-09-01 from code commit `0a667702d190d48d8782310c873ff79d25d32191`; evidence is in `fundamentals_v4_lifecycle_v1_phase2d_deployment.md`.

Valuation Phase 3C prepares `V4_VALUATION_REVISED_HISTORY_V1` persistence without production activation. It retains the empty legacy `valuation_result`, adds a separate versioned revised-history contract, rehearses canonical common earnings and analysis persistence on SQLite backups, requires an identical zero-write second apply, proves every exact-zero FULL score has three observed nonpositive numerators, reports a 180-day current-universe cross-section, and exactly reconciles Phase 3A readiness. Production deployment remains a separately authorized Phase 3D.

Phase 3C.2 replaces the original provenance-table rebuild with schema version `v4_3c2_additive_provenance`: legacy provenance is unchanged, common-earnings provenance uses a dedicated restricted table behind one API, and production-shaped rehearsal completes with zero freelist and unchanged valuation fingerprints. This additive path supersedes the original Phase 3C migration for Phase 3D.

Phase 3D code gate adds narrow production authorization and activates Valuation after the established Score and Lifecycle stages. The operational fallback remains full-universe until a trustworthy changed-company set exists. Each analysis model commits independently, and Valuation failure preserves prior valuation rows while surfacing the overall run as failed.

Phase 3D production deployment completed on 2026-09-01 with verified retained backups, zero-write second canonical and Valuation applies, locked Valuation fingerprints, unchanged Score/Lifecycle results, read-only osakedata/provider sources, and no rollback. The deployment record is `fundamentals_v4_valuation_v1_phase3d_deployment.md`.
