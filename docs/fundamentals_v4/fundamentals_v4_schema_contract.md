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

V4-1A inspects SwingMaster V3 read-only for CIK values and imports only deterministic mappings with source `MIGRATED_FROM_V3`. The inspected V3 database at `/home/kalle/projects/swingmaster/rc_fundamentals_v3.db` does not contain a CIK column, so the prototype imports zero CIKs and records missing mappings. Future SEC ingestion can populate the same `company_cik` contract without changing the canonical financial schema.

## Production Safety

V4-1A must not create:

```text
data/fundamentals_provider.db
data/fundamentals_v4.db
data/fundamentals_analysis.db
```

The accepted proof artifacts live under `temp/fundamentals_v4_1a_schema_design/<timestamp>/` and are disposable.
