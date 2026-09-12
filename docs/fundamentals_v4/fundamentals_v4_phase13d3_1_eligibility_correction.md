# Fundamentals V4 Phase 13D.3.1 Eligibility Correction

Phase 13D.3.1 supersedes one Phase 13D.3 interpretation without rewriting Phase 13D.3 history. Commit `71ea7f8` remains historical evidence; this follow-up corrects the decision model.

## Outcome

Selected outcome: `OUTCOME B — SNDK READY, BUT LOCAL-PROVIDER REPLACEMENT CANDIDATE NOT ESTABLISHED`.

SNDK is independently ready for a separately authorized protected Phase 13E production onboarding. The local-provider replacement candidate audit found no eligible replacement among the 16 Phase 13A candidates because every candidate is delisted in local Sharadar metadata.

## AREB Correction

AREB must be rejected from active onboarding before classification review:

- identity status: `RESOLVED`
- listing status: `DELISTED`
- operational-universe status: `NOT_ELIGIBLE`
- operational-universe reason: `DELISTED_SECURITY`
- classification status: `SOURCE_CLASSIFICATION_MISMATCH`
- Datacenter taxonomy status: `NOT_MEMBER_BY_DESIGN`

The local classification remains `Consumer Cyclical / Footwear & Accessories`, while the external expected classification is `Industrials / Commercial Services & Supplies`. That mismatch is preserved as secondary evidence. It is not the primary onboarding blocker, and AREB's lack of Datacenter taxonomy membership is not an error.

## Candidate Gate

Active onboarding candidates are filtered before ranking. A candidate must have stable provider identity, supported security type, active/non-delisted listing evidence, compatible exchange and market evidence, current local OHLC evidence, applicable provider fundamentals, and no unresolved ticker-reuse collision.

Delisted candidates remain visible in audit output with deterministic rejection reasons but cannot be selected solely by provider-row count.

## SNDK Decision

SNDK remains distinct from SNDK1:

- current SNDK: permaticker `643888`, CIK `0002023554`;
- predecessor SNDK1: permaticker `197210`;
- identity status: `RESOLVED_DISTINCT_SECURITY_WITH_CORPORATE_LINEAGE`.

Do not merge price, share-count, market-cap, valuation, or listing histories across the 2016-2025 gap. Existing Phase 13D.2 and 13D.3 evidence remains valid for SNDK-only production planning: archive SHA-256 `dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36`, no network dependency, explicit manual Relative Valuation refresh, deterministic Snapshot output after the audit/presentation split, and production immutability.

## Artifacts

Run:

```bash
python3 -m rawcandle.cli.run_phase13d3_1_eligibility_correction \
  --output temp/fundamentals_v4_phase13d3_1_eligibility_correction/20260912T_PHASE13D3_1_ELIGIBILITY_CORRECTION
```

The run writes only small read-only artifacts: AREB corrected decision, candidate eligibility audit, SNDK readiness decision, retired V3 runtime audit, production pre/postflight inventories, storage manifest, and artifact fingerprints. It performs no production writes, no Relative Valuation refresh, no Snapshot publication, no API/network request, and no heavy copy rehearsal.
