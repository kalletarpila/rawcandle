# Fundamentals V4 - Known Gaps and Data Quality Backlog

## 1. Purpose and policy
V4 may proceed with explicitly known non-material gaps. Gaps are never silently filled, historical completeness and current TTM readiness are separate contracts, Sharadar ARQ remains the primary canonical provider, and unresolved cases remain traceable through artifacts.

## 2. Executive status
- Companies: `2458`
- Securities: `2470`
- TTM ready: `2434`
- TTM not ready: `24`
- True internal historical gaps: `172`
- True Q4 provider gaps: `8`
- CIK NULL: `22`
- Permaticker NULL: `5`
- Shares insufficient evidence: `113`
- Other unresolved financial/provider issues: `0`

## 3. Current known gaps
| ID | Category | Count | Scope | Current impact | Blocks TTM? | Planned treatment | Status | Source artifact |
| --- | --- | ---: | --- | --- | --- | --- | --- | --- |
| V4-GAP-001 | Fiscal / quarter continuity | 172 | Historical provider/canonical gaps | Window-dependent | Only affected windows | DO_NOT_FIX_NOW / FUTURE_PROVIDER_RECHECK | OPEN | gap_172_reclassification.csv |
| V4-GAP-002 | Q4 | 8 | Explicit annual Q4 provider gaps | Window-dependent | Only affected windows | FUTURE_PROVIDER_RECHECK | OPEN | missing_q4_190_reclassification.csv |
| V4-GAP-003 | TTM readiness | 24 | Latest current TTM windows | Blocks current TTM for listed companies | YES | FUTURE_PROVIDER_RECHECK | OPEN | ttm_input_readiness.csv |
| V4-GAP-004 | Identity | 22 | Company CIK missing | No TTM impact | NO | FUTURE_SEC_VERIFICATION | OPEN | canonical company_cik |
| V4-GAP-005 | Identity | 5 | Sharadar permaticker missing | No TTM impact | NO | IDENTITY_REFRESH | OPEN | permaticker_mapping_audit.csv |
| V4-GAP-006 | Shares | 113 | Share discontinuity review debt | No automatic TTM block | NO | FUTURE_PROVIDER_RECHECK | OPEN | shares_255_reclassification.csv |

## 4. Detailed categories
### Identity
CIK remains NULL for `22` companies and Sharadar permaticker remains NULL for `5` securities. These are not TTM blockers. Permaticker-null securities: AIHS, BBBY, EQR, ISSC, LIXT.

### Fiscal / quarter continuity
`172` historical continuity gaps remain open. They block only TTM windows that require the missing quarter; an older gap does not block a complete latest four-quarter window.

### Q4
`8` true Q4 provider gaps remain. Cases: BNC 2025-Q4; HOVR 2023-Q4; ILLR 2024-Q4; LFCR 2026-Q4; MAPS 2023-Q4; OBIO 2022-Q4; OPTX 2024-Q4; SMCI 2024-Q4.

### Shares
`113` sharesbas discontinuities remain review debt. They do not automatically block TTM because the TTM contract uses endpoint canonical shares and does not repair share history here.

### Debt / financial provider inconsistencies
The `CORZ 2024-Q4 MRQ` debt component mismatch is retained as a resolved / accepted provider inconsistency. Canonical ARQ total debt was not changed.

### TTM readiness
Current latest-window TTM blockers: `24` companies. Blocker counts: `{"TTM_DATA_INSUFFICIENT": 18, "TTM_IDENTITY_BLOCKED": 7, "TTM_MISSING_EBIT": 5, "TTM_MISSING_FCF": 6, "TTM_MISSING_QUARTER": 11, "TTM_MISSING_REVENUE": 5}`.

### Other canonical field coverage
No additional unresolved canonical financial-provider issue was introduced by V4-2 math validation.

## 5. Resolved review items
17 of 19 previously unmatched target tickers were resolved by alternate/current Sharadar ticker mapping. Two stale bootstrap-universe entries remain documented as identity backlog context, not TTM blockers. The single CORZ MRQ component mismatch is accepted without changing canonical debt.

## 6. Repair / enrichment backlog
Open treatments use `DO_NOT_FIX_NOW`, `FUTURE_SEC_VERIFICATION`, `FUTURE_PROVIDER_RECHECK`, and `IDENTITY_REFRESH`. Yahoo enrichment and SEC verification remain future phases only and were not used in V4-2.

## 7. Phase gate status
TTM is blocked only for companies whose current latest four-quarter window is incomplete or has missing core inputs. Score should consume readiness and known-gap metadata. Lifecycle and Valuation should preserve the same explicit blockers and must not assume unknown first-public result dates.

## 8. Update history
- V4-2, delivery commit `Migrate Fundamentals V4 TTM engine`: migrated EBIT-first TTM, wrote production TTM rows, and reconciled current TTM blockers. Artifact root: `/home/kalle/projects/rawcandle/temp/fundamentals_v4_2_ttm/20260831T073656Z`.

## V4-3 Score Calibration Review

Score calibration consumed this register as an explicit readiness input. High-level OPEN categories remain internally consistent at `5`: Fiscal / quarter continuity, Q4, TTM readiness, Identity, and Shares. Detailed issue groups roll up under those categories; for example CIK NULL and permaticker NULL both belong to Identity.

New material data-quality gaps discovered by V4-3: `0`.

Artifact root: `/home/kalle/projects/rawcandle/temp/fundamentals_v4_3_score_calibration/20260831T133335Z`.
