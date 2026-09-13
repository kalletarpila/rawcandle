# Phase 13F.3.2 Successor Fundamentals Recovery

Outcome: **OUTCOME A - SUCCESSOR FUNDAMENTALS RECOVERED AND DATE-AWARE COPY-ONLY CHAIN VERIFIED; STRUCTURAL-BREAK PRODUCTION POLICY STILL DEFERRED**

Final artifact root:

`temp/fundamentals_v4_phase13f3_2_successor_recovery/20260913T_PHASE13F3_2_FINAL3/`

## Source Recovery

The production provider database had no local `provider_observation` rows for the five accepted successor identities by stable provider id or old/current ticker text. The verified Phase 12C ten-year Sharadar archive was used instead.

Archive:

`data/source_archives/sharadar/fundamentals/phase12c_20260910/sharadar_fundamentals_10y.zip`

SHA-256 verified:

`dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36`

Recovered rows:

| Ticker | Permaticker | CIK | ARQ | MRQ | Source status |
| --- | ---: | --- | ---: | ---: | --- |
| VMRK | 197624 | 0000906107 | 41 | 41 | FOUND_IN_VERIFIED_ARCHIVE |
| IA | 198182 | 0000836690 | 41 | 41 | FOUND_IN_VERIFIED_ARCHIVE |
| VAI | 120343 | 0001711012 | 36 | 38 | FOUND_IN_VERIFIED_ARCHIVE |
| NXH | 195902 | 0001130713 | 41 | 41 | FOUND_IN_VERIFIED_ARCHIVE |
| NMAD | 108994 | 0001335105 | 40 | 41 | FOUND_IN_VERIFIED_ARCHIVE |

BBBY/NXH contamination gate passed. Accepted NXH rows were only current NXH rows tied to permaticker `195902` and CIK `0001130713`; bankrupt BBBYQ remains separate as permaticker `197799` and CIK `0000886158`.

## Copy-Only Chain

Provider staging on isolated copies inserted 401 rows on first apply: 199 ARQ and 202 MRQ. Identical replay inserted zero rows. Rollback injection restored provider-copy state.

Canonical and TTM reconstruction completed for all five successor identities. Package refresh, Relative Position, manual Relative Valuation refresh, dependency attachment and Snapshot smoke completed on two independent copy lanes.

Relative Valuation date-aware eligibility was corrected generally at source selection:

- active operational-universe membership is required;
- security listing eligibility is checked as of the RV snapshot date;
- provider metadata delisting dates are used when available;
- ticker-specific exceptions were not introduced.

FINAL3 Relative Valuation evidence:

- pre-refresh compatibility: `OPERATIONAL_UNIVERSE_MISMATCH`
- post-refresh compatibility: `COMPATIBLE`
- RV company count: `2438`
- RV excluded input counts: `{"NOT_ACTIVE_OPERATIONAL_UNIVERSE_MEMBER": 16}`
- AREB post-delisting current RV rows: `0`
- second RV refresh: logical no-change `true`, physical no-change `true`

Structural Snapshot endpoint policy remains explicit and does not change Own-History formulas:

| Ticker | Status |
| --- | --- |
| VMRK | STRUCTURALLY_LIMITED_NO_POST_TRANSITION_OBSERVED_ENDPOINT |
| IA | FULL_CONTINUITY_ALLOWED |
| VAI | BUSINESS_COMPARABILITY_REVIEW_REQUIRED |
| NXH | CURRENT_ISSUER_LINEAGE_CONTINUITY_ALLOWED |
| NMAD | STRUCTURALLY_LIMITED_NO_POST_TRANSITION_OBSERVED_ENDPOINT |

Deterministic replay matched. Production immutability was true. No production database writes, production pointer changes, production report regeneration, Scheduler changes or UI changes were made.

The Own-History structural-break production policy remains deferred under the separate versioned contract blocker:

`OWN_HISTORY_STRUCTURAL_BREAK_POLICY_REQUIRES_SEPARATE_VERSIONED_CONTRACT`
