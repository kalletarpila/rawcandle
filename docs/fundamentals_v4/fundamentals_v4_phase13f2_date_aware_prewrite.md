# Fundamentals V4 Phase 13F.2 Date-Aware Listing Eligibility Pre-Write Record

Date: 2026-09-12

Outcome: **OUTCOME B — PRE-WRITE MATERIAL BLOCKER; PRODUCTION UNCHANGED**

Phase 13F.2 was stopped before production writes. The prompt authorizes production writes only after classification mapping, listing-interval, rehearsal, backup and dependency gates pass. Those gates did not pass.

## Universal Policy

Eligibility is security-specific and date-aware:

```text
eligible_on_date =
    verified_listing_start_date <= calculation_date
    and (
        verified_listing_end_date is NULL
        or calculation_date <= verified_listing_end_date
    )
```

This is not an AREB exception. Ticker reuse, company lineage and shared names must not join separate listing episodes without stable-security evidence. SNDK and SNDK1 remain distinct securities and listing intervals.

## Deterministic Evidence

Two read-only pre-write runs were executed:

- `temp/fundamentals_v4_phase13f2_date_aware/20260912T_PHASE13F2_DATE_AWARE_PREWRITE_R1`
- `temp/fundamentals_v4_phase13f2_date_aware/20260912T_PHASE13F2_DATE_AWARE_PREWRITE_R2`

Both produced:

- outcome: `OUTCOME B — PRE-WRITE MATERIAL BLOCKER; PRODUCTION UNCHANGED`
- determinism fingerprint: `7f8284355b43973519d0c980cf6bef6a09904e2927b0a07417434771c5807be7`
- production immutability: `true`

## Pre-Write Blockers

- `NORMALIZED_CLASSIFICATION_MAPPING_REVIEW_REQUIRED:196`
- `CURRENT_ACTIVE_LISTING_INTERVAL_UNRESOLVED:5`
- `AREB_CURRENT_RV_PEER_ELIGIBLE_DEFECT:1`
- `VALUATION_CLASSIFICATION_OMISSIONS_REQUIRE_PIPELINE_REBUILD:7`

Because unresolved normalized classification mappings and current-active listing intervals materially affect peer membership, Phase 13F.2 did not start production writes.

## Listing Population

- canonical securities: `2471`
- currently listed by resolved date-aware evidence: `2449`
- delisted by provider metadata: `17`
- unresolved listing intervals: `5`
- unresolved intervals on current-active securities: `5`

The five unresolved current-active securities are:

| Company | Security | Ticker | Evidence |
| ---: | ---: | --- | --- |
| 82 | 82 | AIHS | canonical active + local OHLC, no provider interval |
| 278 | 278 | BBBY | canonical active + local OHLC, no provider interval |
| 787 | 788 | EQR | canonical active + local OHLC, no provider interval |
| 1166 | 1170 | ISSC | canonical active + local OHLC, no provider interval |
| 1304 | 1311 | LIXT | canonical active + local OHLC, no provider interval |

Stale OHLC alone was not treated as delisting evidence.

## AREB Date-Aware Result

AREB stable identity:

- company_id: `192`
- security_id: `192`
- permaticker: `637535`
- listing interval: `2022-02-07` through `2026-05-12`
- status: `DELISTED`

AREB Relative Position:

- active RP rows audited: `12`
- rows classified as valid listed-period rows: `12`
- post-delisting RP rows: `0`

The active RP rows use comparison date `2026-03-31`, which is inside AREB's verified listed interval. They should not be removed merely because AREB is now delisted.

AREB Relative Valuation:

- active RV company rows audited: `1`
- current RV snapshot date: `2026-09-12`
- row classification: `CURRENT_PEER_ELIGIBLE_DEFECT`

The current RV row is after AREB's listing end and must not remain peer-eligible/current-fresh in a corrected production refresh.

## Classification Findings

Phase 13F.1 counts remain the active classification baseline:

- primary active securities: `2454`
- missing/ambiguous/unresolved ticker_meta matches: `0`
- exact raw matches: `2251`
- normalized-only matches requiring review: `196`
- valuation classification omissions: `7`

The seven omissions remain:

`AIHS`, `BATRK`, `BBBY`, `BELFB`, `EQR`, `ISSC`, `LIXT`.

## Required Continuation

Before any production correction:

1. Review all 196 normalized-only mappings and classify them as formatting-only, approved alias, semantic mismatch or unresolved.
2. Resolve listing intervals for AIHS, BBBY, EQR, ISSC and LIXT using authoritative local evidence or defer writes.
3. Add versioned classification/listing dependency identities so old RP/RV snapshots cannot be declared compatible.
4. Rehearse the full correction on protected copies, including full-universe RP and separate manual RV refresh.
5. Only after all gates pass, take durable backups and run production apply with mandatory second `NO_CHANGE`.

No production writes, backups, active pointer changes, RP/RV activation, report writes, network/API calls or taxonomy changes were performed in this phase.

## Verification

- `python3 -m compileall rawcandle/fundamentals/phase13f2_date_aware_policy.py rawcandle/cli/run_phase13f2_date_aware_prewrite.py`
- `python3 -m pytest tests/test_phase13f2_date_aware_policy.py`
- Production preflight quick_check: provider/canonical/analysis/market all `ok`
