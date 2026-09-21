# Phase 13G.3.20B: Reviewed new-company analysis linkage

## Scope and safety

This phase fixes the generic Add Tickers candidate path for approved reviewed identities. It does not reinterpret the KRSA, PSQL, or QVCG approvals, does not touch DRK, and does not run a live Preview, Test, Production, Full Workflow, or scheduler operation.

Reviewed identity authority must survive the full candidate pipeline from identity creation through canonical fundamentals and downstream analysis without being re-resolved from ticker text or unavailable current provider metadata.

A valid analytical NOT_READY/LIMITED state is not a reporting-integrity error, but missing output caused by lost company identity is.

## Proven root cause

The historical Preview payload for the Test `20260921T173442Z_add_tickers_0cd741c1e14a_apply` contains 77 ARQ rows: KRSA 34, PSQL 3, and QVCG 40. Every one of those rows has `fiscalperiod = null`.

Add Tickers requested authoritative complete ticker history through a `fields=` projection. The provider returned a successful projected response without the fiscal identity required by canonicalization. Preview considered ARQ row count sufficient and marked all three tickers eligible. Provider staging then stored the incomplete rows. Canonical reconciliation reported exactly `invalid_fiscal_rows = 77` and accepted none of them.

The first broken lineage boundary was therefore:

`network complete-history acquisition -> provider row fiscal identity`

KRSA appeared healthy only because its approved plan reused company 627, whose prior canonical history already had analysis output. PSQL and QVCG created new companies and exposed the defect because they had no prior company history to mask the rejected source rows. This was not a candidate-ID instability, CIK join, model eligibility, or ticker-report lookup defect.

## Source contract correction

Authoritative complete-history acquisition now requests the complete provider response without `fields=`. This follows the established Refresh Fundamentals replacement-authority contract: discovery may be projected, but a response used to replace or add complete history must be contract-complete.

A regression fixture models the exact provider behavior: a projected response silently omits `fiscalperiod`, while the complete response includes it. The test proves Add Tickers sends no `fields` argument.

Existing live read-only Refresh evidence independently records the provider's full schema as 112 fields with `fiscalperiod` required, and its unprojected complete-history path produced fiscal-quarter classifications. In contrast, the retained Add Tickers payload proves its projected rows omitted `fiscalperiod` despite a successful response. Retaining a projection would therefore preserve the already observed silent schema-loss risk; the shared authoritative-history contract requires the full response.

Preview now validates every ARQ and MRQ row before eligibility. Each quarterly row must carry a parseable `YYYY-Q[1-4]` fiscal identity. Missing or malformed fiscal identity produces `INCOMPLETE_FISCAL_IDENTITY` and `REVIEW_REQUIRED`. Provider staging repeats the check as a safety boundary.

## Candidate lineage evidence

The real downstream path now records per ticker:

- source and parseable ARQ row counts;
- distinct source fiscal-quarter count;
- source quarters materialized in canonical;
- source observations selected in canonical provenance;
- TTM analysis-input count;
- Score, Lifecycle, and Valuation output-row counts.

The operation report renders:

`source ARQ rows accepted for canonicalization = N/N`

and:

`network ARQ -> staging -> canonical quarters -> analysis input`

The apply fails closed if fiscal rows are incomplete, source fiscal quarters are absent from canonical, or a source-backed company has no Score, Lifecycle, or Valuation rows.

## Production-shaped fixture

The fixture uses the real approved identity resolver and actual KRSA, PSQL, and QVCG approval records. It then runs `GenericBatchItemPlan -> identity application -> provider staging -> canonical reconciliation -> TTM -> structural contract -> full V2/RP/RV candidate -> ticker reporting`.

Results:

| Ticker | Identity | ARQ accepted | Canonical quarters | Score | Lifecycle | Valuation |
| --- | --- | ---: | ---: | --- | --- | --- |
| KRSA | Reuse company 627; distinct successor security | 34/34 | 34/34 | `SCORE_FULL` | `LIFECYCLE_READY` | `VALUATION_NOT_READY` in the fixture because no eligible historical price is supplied |
| PSQL | New company and new security | 3/3 | 3/3 | `SCORE_NOT_READY` | `LIFECYCLE_NOT_READY` | `VALUATION_NOT_READY` |
| QVCG | New company and new security | 40/40 | 40/40 | `SCORE_FULL` | `LIFECYCLE_READY` | `VALUATION_NOT_READY` in the fixture because no eligible historical price is supplied |

The PSQL statuses prove that short history is represented through model contracts rather than an identity/reporting failure. Score, Lifecycle, and Valuation each persist one row per TTM endpoint, including their documented not-ready states. QVCG and KRSA prove that substantial new history reaches the same company-level model path.

The fixture also removes QVCG's Score rows deliberately and proves the lineage gate raises `ADD_TICKERS_LINEAGE_ANALYSIS_OUTPUT_MISSING:QVCG`. Reporting remains fail closed for genuine attribution loss.

## Identity invariants

- KRSA keeps company 627 and preserves CYCN security 628 unchanged.
- PSQL and QVCG each create one intended company and one distinct security.
- No predecessor aliases are copied to the new PSQL or QVCG security.
- CIK remains company-level.
- No permaticker or provider metadata is fabricated for reviewed identities.
- Candidate company and security IDs remain stable through canonical and analysis processing.
- RP/RV and taxonomy eligibility semantics are unchanged.
- Approval records and fingerprints are unchanged.

## Contract and next operation

The Add Tickers contract is bumped from `PHASE13G2_BATCH_ADD_TICKERS_COPY_ONLY_V5_REVIEWED_IDENTITY_REPORTING` to `PHASE13G2_BATCH_ADD_TICKERS_COPY_ONLY_V6_COMPLETE_FISCAL_IDENTITY`.

The historical Preview and Test remain audit evidence but cannot authorize Production. The required next live sequence is:

`Run a fresh Add Tickers Preview for exactly KRSA, PSQL, and QVCG, then run a fresh Test on copies before any Production update.`
