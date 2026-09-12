# Fundamentals V4 Phase 13F.1 Classification And Current-Universe Reconciliation

Date: 2026-09-12

Outcome: **OUTCOME B — CORRECTABLE CLASSIFICATION OR ELIGIBILITY DRIFT IDENTIFIED**

Phase 13F.1 was a read-only production audit. It did not write production databases, activate packages, refresh Relative Position or Relative Valuation, generate production reports, call network APIs or modify taxonomy.

## Source Of Truth

The authoritative Fundamentals V4 sector/industry source is `data/osakedata.db.ticker_meta`, resolved by stable security identity plus ticker and market. Datacenter taxonomy remains an independent thematic ecosystem source and must not override sector or industry.

`ticker_meta` is current revised classification. It is authoritative for current production reconciliation, but it is not a point-in-time historical sector/industry source.

## Deterministic Runs

Two independent read-only runs were executed:

- `temp/fundamentals_v4_phase13f1_reconciliation/20260912T_PHASE13F1_RECONCILIATION_FINAL2_R1`
- `temp/fundamentals_v4_phase13f1_reconciliation/20260912T_PHASE13F1_RECONCILIATION_FINAL2_R2`

Both produced:

- outcome: `OUTCOME B — CORRECTABLE CLASSIFICATION OR ELIGIBILITY DRIFT IDENTIFIED`
- determinism fingerprint: `4d51dfafe33268849f0cce2a266fc1b9142ba56861e6d4c189156d470103e86f`
- production immutability: `true`
- artifact size: about 13 MB per run

## Current Universe

- Active Operational Universe version: `1e01484c56dec911b961d680e867a51a`
- OU as-of date: `2026-09-12`
- Total OU member rows: `2459`
- Primary active security rows after expanding multi-security companies: `2454`
- Historical-retained member rows outside the primary denominator: `16`
- Multi-active companies expanded into individual securities: `11`

## Classification Reconciliation

Primary active security denominator: `2454`

- Exact matches: `2251`
- Normalized-only matches: `196`
- Missing `ticker_meta` row: `0`
- Missing sector: `0`
- Missing industry: `0`
- Ambiguous ticker+market match: `0`
- Unresolved stable identity: `0`
- Sector mismatches in persisted valuation classification: `7`
- Industry mismatches in persisted valuation classification: `7`
- Both sector and industry mismatching: `7`
- `ticker_meta` rows without current OU match: `2580`

The seven classification drifts are valuation classification fields that are `NULL` while `ticker_meta` is populated:

| Company | Security | Ticker | ticker_meta sector | ticker_meta industry | Persisted valuation |
| ---: | ---: | --- | --- | --- | --- |
| 82 | 82 | AIHS | Industrials | Rental & Leasing Services | `NULL / NULL` |
| 274 | 274 | BATRK | Communication Services | Entertainment | `NULL / NULL` |
| 278 | 278 | BBBY | Consumer Cyclical | Specialty Retail | `NULL / NULL` |
| 303 | 303 | BELFB | Technology | Electronic Components | `NULL / NULL` |
| 787 | 788 | EQR | Real Estate | REIT - Residential | `NULL / NULL` |
| 1166 | 1170 | ISSC | Industrials | Aerospace & Defense | `NULL / NULL` |
| 1304 | 1311 | LIXT | Healthcare | Biotechnology | `NULL / NULL` |

These require valuation-derived classification rebuild and downstream RP/RV/Snapshot reconciliation. Fundamental Score remains classification-independent.

## Eligibility Audit

Two active securities have locally stale-ended OHLC evidence:

| Company | Security | Ticker | Latest local OHLC | Finding |
| ---: | ---: | --- | --- | --- |
| 787 | 788 | EQR | 2026-08-21 | `LOCAL_PRICE_HISTORY_STALE_ENDED` |
| 1166 | 1170 | ISSC | 2026-08-24 | `LOCAL_PRICE_HISTORY_STALE_ENDED` |

No current active security had a missing `ticker_meta` identity in the primary audit. Provider `lastpricedate` alone was not treated as stale-ended evidence because local OHLC is the usable price source for current production.

## AREB RP/RV Participation

AREB is not merely harmless stored evidence.

Relative Position:

- Active AREB RP rows: `12`
- AREB ready rows in active RP snapshots: `8`
- Conclusion: `PRODUCTION_DEFECT_AREB_PARTICIPATES_IN_CURRENT_RELATIVE_POSITION`
- Affected ready groups: universe and Consumer Cyclical sector for both Fundamental Score and Absolute Valuation Score across active V1/V2 snapshots
- Counterfactual affected other-company RP rows: `10120`

Relative Valuation:

- Active AREB RV company rows: `1`
- AREB ready peer-position rows: `2`
- Conclusion: `PRODUCTION_DEFECT_AREB_PARTICIPATES_IN_CURRENT_RELATIVE_VALUATION`
- Affected ready groups: universe and Consumer Cyclical sector
- Counterfactual affected other-company RV peer rows: `2549`

Therefore AREB must be removed from current peer eligibility and retained only as historical/ineligible evidence.

## Dependency Matrix

| Consumer | Current source | Required source | Status | Rebuild scope |
| --- | --- | --- | --- | --- |
| Onboarding/eligibility | identity + market evidence + ticker_meta audit | ticker_meta by security ticker+market | compliant for source; eligibility drift found | OU/dependency fingerprints |
| Fundamental Score | financial statements | not classification-dependent | unchanged | none |
| Diagnostic applicability | diagnostic endpoints/applicability ids | ticker_meta where classification-dependent | review/recalculate for changed applicability | diagnostic endpoints/evaluations |
| Lifecycle | fundamental trends | not ordinary sector/industry | unchanged by code inspection | none |
| Absolute Valuation | ticker_meta via valuation source loader | ticker_meta by ticker+market | source compliant, 7 persisted drifts | valuation rebuild for affected rows |
| Relative Position | ticker_meta resolver + active package rows | ticker_meta + current eligibility | AREB eligibility defect | full-universe RP rebuild |
| Relative Valuation | ticker_meta resolver + active snapshot | ticker_meta + current eligibility | AREB eligibility defect | separate manual full RV refresh |
| Snapshot/UI | active RP/RV readers | current eligible company only | verify after rebuild | Snapshot/UI reconciliation |

## Phase 13F.2 Protected Correction Plan

1. Preflight production with quick_check, foreign_key_check, path verification, active pointer fingerprints and backups for provider, canonical, analysis, market and taxonomy.
2. Prepare an isolated production rehearsal from current production state.
3. Correct the seven valuation classification drift rows by rebuilding from `ticker_meta`; do not manually patch formulas.
4. Investigate EQR and ISSC local price-history staleness and decide whether they remain current eligible, become not-ready, or transition out of current eligibility.
5. Transition AREB out of current RP/RV peer eligibility while retaining historical/delisted evidence.
6. Recalculate any classification-dependent diagnostic applicability impacted by the seven drifts.
7. Rebuild full-universe Relative Position because denominator and rank changes are cross-sectional.
8. Run the separately initiated manual Relative Valuation refresh after RP activation.
9. Verify Snapshot/UI cannot select AREB as a current active company and that current reports show refreshed peer groups.
10. Run mandatory first apply and second `NO_CHANGE` gates.
11. Verify production immutability boundaries, active pointers, dependency fingerprints and rollback artifacts.

Expected unaffected layers: Fundamental Score and Lifecycle economics. Absolute valuation formulas remain unchanged, but applicability/status and classification fields may change for the seven drift rows.

## Verification

- `python3 -m compileall rawcandle/fundamentals/phase13f1_reconciliation.py rawcandle/cli/run_phase13f1_reconciliation.py`
- `python3 -m pytest tests/test_phase13f1_reconciliation.py`
- `python3 -m pytest tests/test_phase13f_historical_delisted.py`
- Targeted Phase 13B-F, Diagnostic, Relative Position, Relative Valuation, Snapshot/UI and production-isolation regression: `198 passed`
- Production preflight quick_check: provider/canonical/analysis/market all `ok`
- Production postflight quick_check: provider/canonical/analysis/market all `ok`

Full repository suite was not required because this phase added a read-only audit path and did not change production apply code. Shared classification reader regressions should still be run before Phase 13F.2 apply.
