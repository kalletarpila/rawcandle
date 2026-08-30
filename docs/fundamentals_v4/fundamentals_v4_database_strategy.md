# Fundamentals V4 Database Strategy

V4 uses three separate databases. No V4 production database is created in V4-0C.

## `data/fundamentals_provider.db`

Owner: fundamentals ingestion/provider layer.

Purpose: provider-side truth and acquisition metadata.

Likely contents:

- provider runs
- provider observations
- Sharadar native rows
- Yahoo event/current observations
- SEC filing/fact observations
- source timestamps and identifiers
- fetch status, retry metadata, and content hashes

Provider disagreements are not canonicalized here.

## `data/fundamentals_v4.db`

Owner: canonical/TTM layer.

Purpose: accepted canonical financial data.

Likely contents:

- company/security mapping
- canonical fiscal quarters
- canonical quarterly financials
- fiscal identity and availability metadata
- field provenance pointers
- quality/readiness metadata
- TTM

TTM belongs here initially because it is a deterministic financial-data derivation from accepted quarterly values, not a model output.

## `data/fundamentals_analysis.db`

Owner: Score/Lifecycle/Valuation layer.

Purpose: derived analytical outputs.

Likely contents:

- Score and score components
- Lifecycle state
- Valuation outputs
- readiness/quality flags used by analysis
- model versions and fingerprints
- later fundamental signals

Analysis must be rebuildable from `fundamentals_v4.db`.

## `analysis.db`

Do not reuse RawCandle's existing `analysis.db` for Fundamentals V4 analytical output. Repo inspection shows it is an existing broad analysis database, and V4 benefits from a dedicated, rebuildable `fundamentals_analysis.db` boundary.

## V4-1A Disposable Prototype

V4-1A proves the target schema on disposable databases only:

```text
temp/fundamentals_v4_1a_schema_design/20260830T183900Z/prototype_provider.db
temp/fundamentals_v4_1a_schema_design/20260830T183900Z/prototype_v4.db
temp/fundamentals_v4_1a_schema_design/20260830T183900Z/prototype_analysis.db
```

No production V4 database is created by this phase.

Prototype input came from the accepted local V4-0D Sharadar Direct API acceptance cache, not a new bulk download. The disposable provider database loaded 160 observations: 80 ARQ and 80 MRQ rows across AAPL, WDAY, ASTH, and CECO. Canonicalization accepted 80 ARQ quarterly rows and created 960 field-level provenance rows for the 12-field contract.

Integrity checks passed for all three SQLite databases: foreign-key checks returned zero errors, provider replay was idempotent, canonical replay was idempotent, there were no duplicate canonical fiscal-year/quarter rows, no orphan canonical financial rows, no orphan provenance rows, and no non-null canonical field lacked provenance.

CIK bootstrap was attempted from SwingMaster V3 using read-only SQLite inspection. The source contained 2,538 companies but no deterministic CIK column, so V4-1A imported zero CIK rows and recorded the open item for V4-1B rather than manufacturing identifiers.

## V4-1A-1 Identity / Calendar Prototype

V4-1A-1 uses the local RawCandle CSV:

```text
temp/v3_active_tickers_99_27.csv
```

as the deterministic bootstrap source for SEC CIK and verified fiscal-year-start metadata. The prototype writes only disposable databases under:

```text
temp/fundamentals_v4_1a1_identity_calendar_bootstrap/<timestamp>/
```

Schema additions are limited to canonical identity/calendar support:

- `provider_company_identity`
- extra provenance columns on `company_cik`
- `company_fiscal_calendar_profile`
- `company_fiscal_year_anchor`

The provider schema, 12-field canonical financial contract, Sharadar ARQ primary policy, and MRQ provider-side retention remain unchanged.

Accepted V4-1A-1 prototype run:

```text
temp/fundamentals_v4_1a1_identity_calendar_bootstrap/20260830T201005Z/
```

Result: `V4_IDENTITY_CALENDAR_BOOTSTRAP_COMPLETE_WITH_REVIEW_ITEMS`.

The prototype imported 2,436 company-level CIK mappings, 2,470 securities, 2,458 companies, and 35,245 normalized company/year fiscal anchors from 35,399 populated CSV FY-start cells. There were zero ticker multiple-CIK conflicts, zero identity conflicts, zero anchor conflicts, and zero duplicate replay rows. The review item is limited to 22 rows whose `Lähde` value does not contain a strict SEC Companyfacts CIK URL.
