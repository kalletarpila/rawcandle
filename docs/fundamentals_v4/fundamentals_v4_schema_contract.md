# Fundamentals V4 Schema Contract

V4-1A defines the schema contract for RawCandle-owned Fundamentals V4. It is proven on disposable prototype databases and is not yet a production migration.

## Databases

`fundamentals_provider.db`

Provider-side acquisition truth. Stores provider runs, provider observations, native Sharadar rows, raw JSON, provider status, content hashes, observed timestamps, and provider source references. ARQ and MRQ rows coexist here.

`fundamentals_v4.db`

Canonical quarterly financial truth. Stores RawCandle company/security identity, ticker aliases, provider identity links, CIK mappings, fiscal quarters, accepted wide quarterly financials, field-level provenance, and TTM contract metadata.

`fundamentals_analysis.db`

Rebuildable analysis outputs. Stores Score, Lifecycle, and Valuation result contracts only in V4-1A. The engines are not migrated in this phase.

## Canonical Field Contract

The canonical quarterly financial row contains exactly these financial fields:

```text
revenue
gross_profit
operating_income
ebit
ebitda
net_income
operating_cashflow
capex
free_cashflow
cash
total_debt
shares_outstanding
```

Every non-null canonical field must have one provenance row pointing back to the accepted provider observation and native provider field. Null canonical values do not create provenance rows. Numeric zero remains distinct from null.

## Sharadar ARQ Mapping

```text
revenue <- revenue
gross_profit <- gp
operating_income <- opinc
ebit <- ebit
ebitda <- ebitda
net_income <- netinc
operating_cashflow <- ncfo
capex <- capex
free_cashflow <- fcf
cash <- cashneq
total_debt <- debt
shares_outstanding <- sharesbas
```

Sharadar ARQ is the V4-1A canonical source. Sharadar MRQ is retained provider-side and validated, but it does not overwrite ARQ canonical quarterly rows.

## Provider Fields Preserved Outside Canonical

The provider schema retains Sharadar fields that are important for audit, identity, and later policy decisions:

```text
reportperiod
fiscalperiod
calendardate
date
lastupdated
debtc
debtnc
shareswa
shareswadil
```

`debtc`, `debtnc`, `shareswa`, and `shareswadil` are intentionally not canonical fields in V4-1A. `sharesbas` maps to canonical `shares_outstanding`.

## Fiscal Identity

Canonical fiscal quarters use provider fiscal-year and fiscal-quarter labels derived from Sharadar `fiscalperiod`, including explicit Q4 rows. `reportperiod`, period-end date, filing date, first public result date, and provider availability dates are separate fields because they answer different questions.

## CIK Bootstrap

V4-1A-1 supersedes the earlier V3 DB CIK audit. The initial local V4 bootstrap source for CIK is:

```text
temp/v3_active_tickers_99_27.csv
```

CIK is parsed strictly from the SEC Companyfacts URL in the `Lähde` column using `CIK([0-9]{10})\.json`. The stored canonical CIK remains zero-padded 10 digits. Rows without this strict pattern remain NULL/review rows; V4 does not infer or repair CIKs from ticker symbols.

CIK is company-level metadata. V4 stores it in `company_cik` with local bootstrap provenance:

```text
source_type = LOCAL_VERIFIED_BOOTSTRAP
source_name = v3_active_tickers_99_27
source_field = Lähde
derivation = PARSED_FROM_SEC_COMPANYFACTS_URL
```

SEC CIK provider identity is stored through `provider_company_identity`, not `security.cik`, because CIK identifies the issuer/company rather than one tradable security.

## Fiscal Calendar Bootstrap

The same CSV is the initial local V4 source for verified fiscal-year-start anchors, typical fiscal-year start, `chain_status`, and `break_reason`.

The wide CSV columns `FY1999 alkoi` through `FY2027 alkoi` are normalized into `company_fiscal_year_anchor` rows keyed by `company_id + fiscal_year`. Blank cells remain blank and are not inferred. If two ticker aliases mapped to the same company disagree for the same fiscal year, the anchor is blocked for review instead of choosing a value automatically.

Company-level profile metadata lives in `company_fiscal_calendar_profile`.

Historical chain breaks do not invalidate newer exact anchors. For example, `BROKEN_AT_FY2011` does not make an explicitly populated FY2027 anchor uncertain.

Fiscal calendar anchors are reference metadata for validation, anomaly detection, future SEC exception handling, and provider fallback. Sharadar `fiscalperiod` remains primary for normal quarterly canonical identity.

## Production Safety

V4-1A must not create:

```text
data/fundamentals_provider.db
data/fundamentals_v4.db
data/fundamentals_analysis.db
```

The accepted proof artifacts live under `temp/fundamentals_v4_1a_schema_design/<timestamp>/` and are disposable.

## V4-1B Production Contract

The V4-1A schema contract is now instantiated in production by V4-1B at:

```text
data/fundamentals_provider.db
data/fundamentals_v4.db
data/fundamentals_analysis.db
```

Schema version metadata remains `v4_1a_prototype` for provider, canonical, and analysis schemas; V4-1B is a production bootstrap of that approved schema, not a schema redesign.

Production canonicalization remains ARQ-only. MRQ is retained provider-side for restatement/comparison evidence and does not overwrite ARQ canonical history. ART, MRT, ARY, and MRY were present in the bulk file but excluded from production provider ingestion for this phase.

The production bootstrap created 50,585 canonical quarter rows and 50,585 canonical financial rows. Every non-null canonical financial cell has field-level provenance; `canonical_fields_without_provenance = 0`. NULL values remain NULL and zero values remain zero.

Sharadar 5Y bulk fundamentals delivered these provider identity fields:

```text
ticker
dimension
calendardate
date
reportperiod
fiscalperiod
lastupdated
```

The same bulk file did not include `permaticker`. V4-1B therefore could not populate production `provider_security_identity` permaticker rows from this endpoint. The import records this as a review item, while preserving ticker-based mapping against the local 2,470-security bootstrap universe with 0 ticker-security collisions.

Baseline fingerprints for the production run are stored under:

```text
temp/fundamentals_v4_1b_production_bootstrap/20260830T205438Z/v4_production_baseline_fingerprints.json
```

## V4-2 TTM Contract

`v4_ttm_values` stores canonical-derived TTM values and readiness rows keyed by company, endpoint quarter, and model version. `v4_ttm_input_quarter` stores the exact four-quarter lineage when present. TTM output remains in `fundamentals_v4.db`; analysis outputs remain in `fundamentals_analysis.db` and are not populated in V4-2.
