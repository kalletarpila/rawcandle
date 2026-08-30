# Fundamentals V4 Architecture

RawCandle is the owner of Fundamentals V4. SwingMaster remains a reference and legacy production system, but RawCandle V4 runtime code must not import SwingMaster modules or require SwingMaster databases.

## Target Flow

```text
Sharadar / Yahoo / SEC
        |
        v
fundamentals_provider.db
        |
        v
normalization / canonicalization
        |
        v
fundamentals_v4.db
        |
        +--> TTM
        |
        v
fundamentals_analysis.db
        |
        +--> Score
        +--> Lifecycle
        +--> Valuation
        +--> readiness / quality
```

## RawCandle Module Root

Initial implementation root:

```text
rawcandle/fundamentals/
  providers/
    base.py
    sharadar.py
  provider_store/
  canonical/
  ttm/
  score/
  lifecycle/
  valuation/
  quality/
  models/
```

Only `providers/base.py`, `providers/sharadar.py`, and the Sharadar smoke CLI are implemented in V4-0C. The remaining packages are planned ownership boundaries, not implemented schemas.

## Provider Boundary

Provider ingestion stores native observations without destructive renaming. Sharadar fields such as `reportperiod`, `fiscalperiod`, `sharesbas`, `shareswa`, and `shareswadil` remain provider-native at the boundary.

The common provider contract captures operation-level metadata: provider name, provider record id, native table, provider security id, observed period end, provider fiscal label, source timestamp/reference, observation timestamp, content hash, provider status, and native fields.

## Fiscal Identity Lessons

V4 must not repeat these V3 failure modes:

- `period_end.year` is not issuer fiscal year truth.
- Fiscal year start calendar year is not necessarily the fiscal label.
- SEC frame is not issuer FY/Q truth.
- Provider/security mappings can be wrong.
- Official fiscal-year metadata is valuable and should be preserved.
- Provider period end can differ slightly from official period end.
- Q4 annual filing semantics differ from Q1-Q3.
- Filing date is not necessarily the first earnings-release date.

Sharadar ARQ currently provides explicit Q4 rows and provider fiscal labels. V4 should prefer accepted Sharadar quarterly identity, then use SEC and Yahoo for verification or operational freshness.

## Company Identity

Sharadar `permaticker` is provider-stable identity metadata, not the sole global RawCandle identity. V4 should maintain:

- internal RawCandle security/company id
- current ticker and historical ticker aliases
- provider ids such as Sharadar `permaticker`
- SEC CIK
- corporate action and ticker-change evidence

## V4-1A Schema Decision

V4-1A makes the three-database boundary explicit while still using only disposable prototype databases:

- `fundamentals_provider.db`: provider-owned acquisition truth, including run metadata, native Sharadar observations, raw JSON payloads, content hashes, and provider timestamps.
- `fundamentals_v4.db`: RawCandle canonical quarterly financial truth, including company/security identity, ticker aliases, provider identity links, CIK slots, fiscal-quarter identity, accepted wide quarterly values, field provenance, and the TTM contract placeholder.
- `fundamentals_analysis.db`: rebuildable analysis output contracts for Score, Lifecycle, and Valuation. V4-1A defines contracts only; it does not migrate or run those engines.

Sharadar ARQ is the primary quarterly canonicalization source for the prototype. MRQ remains stored provider-side and can coexist for audit, comparison, and future policy decisions, but it does not overwrite ARQ canonical rows in V4-1A.

The canonical quarterly field contract is intentionally narrow:

```text
revenue, gross_profit, operating_income, ebit, ebitda, net_income,
operating_cashflow, capex, free_cashflow, cash, total_debt,
shares_outstanding
```

Sharadar ARQ mapping:

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

Provider-side support fields such as `reportperiod`, `fiscalperiod`, `calendardate`, `date`, `lastupdated`, `debtc`, `debtnc`, `shareswa`, and `shareswadil` are preserved without forcing them into the canonical wide field contract.

V4-1A audited `/home/kalle/projects/swingmaster/rc_fundamentals_v3.db` read-only for deterministic CIK mappings. The inspected V3 schema does not contain a CIK column, so the prototype imported zero CIKs and recorded the missing mappings instead of inventing identifiers. V4 remains prepared for SEC or another deterministic CIK source in a later phase.
