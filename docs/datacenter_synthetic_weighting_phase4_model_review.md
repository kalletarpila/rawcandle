# Datacenter synthetic weighting Phase 4 model review

## 1. Baseline

The implementation baseline is
`31546a1cbd8dd5a1a21c7432a5e91efd305eef29`. This review uses the existing
deterministic Phase 3 artifacts for taxonomy `DC_TAXONOMY_FULL_V2_1` over
2025-08-01 through 2026-09-25. It does not rerun the Phase 3 structure chain.
The V1 weights remain `1.00 / 0.33 / 0.25`, with zero weight for WATCH_ONLY and
TOO_SMALL and no `role_weight`.

## 2. Concentration metrics

Phase 4 reuses the shared `weight_concentration` helper and the Phase 3
structural summaries. Because Phase 3 did not persist eligible breadth per
date, Phase 4 derives only the missing positive and eligible-positive member
counts from the same taxonomy and price inputs. The review covers 15,370 group
dates, 16 layer groups, and 37 subindustry groups.

## 3. Diagnostic thresholds

Breadth is HEALTHY at four eligible positive members, THIN at two or three,
SINGLE_MEMBER at one, and NO_EFFECTIVE_MEMBERS at zero. Effective member count
is HEALTHY at `>=3.0`, CONCENTRATED at `1.5..<3.0`, and HIGHLY_CONCENTRATED below
`1.5`. Largest-member bands use `0.40` and `0.60`; top-three bands use `0.80`
and `0.95`. These are review diagnostics only.

## 4. Group classification

| Class | Groups |
|---|---:|
| HEALTHY_WEIGHTED_GROUP | 52 |
| CONCENTRATED_BUT_USABLE | 0 |
| STRUCTURALLY_THIN | 1 |
| NO_EFFECTIVE_COVERAGE | 0 |

The classification follows the specified median effective-count,
median-largest-weight, single-member-share, and 90% no-coverage rules.

## 5. Structural-impact cross-analysis

All ten groups with the largest Phase 3 structural changes are
HEALTHY_WEIGHTED_GROUP. They include Specialty metals, Power generation /
utilities, Electrical & power systems, Virtualization / cloud software, Power
generation and utility exposure, and Storage. The observed structure changes
therefore do not cluster in historically thin groups. Large changes remain
expected consequences of applying membership semantics to well-covered
groups; size alone is not evidence of an invalid calculation.

## 6. Thin-group diagnostics

Broad hardware / indirect exposure is the only STRUCTURALLY_THIN group. The
current taxonomy gives it one positive-weight member. It has 289 single-member
dates and one no-effective-member date, median effective member count `1.0`,
and median largest-member and top-three shares `1.0`. Its causes are
`MISSING_MEMBER_RENORMALIZATION` and `NARROW_CURRENT_TAXONOMY`. It had no
equal-versus-weighted structure or trend change because both calculations are
effectively the same single-member series.

## 7. Candidate A

No guardrail retains all 15,370 group dates, all 517 weighted BOS events, all
237 weighted RESET events, and all 15,359 populated trend states. This is the
unchanged V1 behavior.

## 8. Candidate B

Requiring at least two eligible positive members retains 15,058 group dates
(`97.9701%`) and suppresses 312 (`2.0299%`) across 23 groups. It retains 505 BOS
events and 231 RESET events, suppressing 12 and 6 respectively. Trend coverage
is `98.0402%`.

## 9. Candidate C

Requiring effective member count `>=1.5` produces the same observed result as
Candidate B: 312 group dates, 12 BOS events, 6 RESET events, and 301 populated
trend states suppressed. The equality is empirical for this dataset; the two
rules are not generally equivalent for every possible positive-weight mix.

## 10. Candidate D

Combining the Candidate B and C requirements also produces the same observed
result. It retains `97.9701%` of group dates, 505/517 BOS events, 231/237 RESET
events, and 15,058/15,359 populated trend states.

## 11. Coverage trade-offs

Candidates B, C, and D filter 100% of dates belonging to the sole
STRUCTURALLY_THIN group. They also filter `0.1459%` of dates belonging to
HEALTHY_WEIGHTED_GROUP groups, caused by isolated price-coverage gaps. Thus a
simple guardrail cleanly identifies the persistently single-member group but
also removes a small amount of otherwise healthy-group history and associated
events. Filtering is not free, even though aggregate coverage remains high.

## 12. V1 weighting constants

No calculation anomaly, unstable boundary, or pathological concentration in a
well-covered group was found. The largest structure changes occur in healthy
groups, proving that V1 is consequential but not that `1.00 / 0.33 / 0.25` is
defective. No alternative constants were tested, and this evidence does not
support `WEIGHT POLICY REQUIRES REVISIT`.

## 13. Current taxonomy breadth

The only persistent concentration failure is directly explained by current
taxonomy breadth: Broad hardware / indirect exposure has one positive-weight
member. Twenty-two additional suppressed dates occur as isolated coverage
gaps among otherwise healthy groups. Current breadth is therefore the dominant
limitation for the thin-group finding, but it does not explain the largest
structural changes in healthy groups.

## 14. Technical conclusion

`GUARDRAIL RECOMMENDED FOR REVIEW`

V1 is internally consistent and the constants do not require revision on this
evidence. A minimum-breadth/effective-count diagnostic merits architecture
review because it removes persistently single-member behavior with limited
aggregate coverage loss. This is not a production activation decision.

## 15. Open architecture decision

The architect/user must decide whether production publication should allow a
single-member synthetic group, suppress it, or wait for taxonomy breadth. If a
guardrail is selected, Candidate B is operationally simplest in this dataset;
Candidates C and D add no observed filtering benefit. The decision must also
accept the loss of 12 BOS and 6 RESET events and define how unavailable dates
affect chain continuity before implementation.

## 16. Production actions not run

- No production `dc_*` or `ec_*` rows were rebuilt, overwritten, or published.
- No taxonomy, taxonomy version, scheduler, report, or EC architecture changed.
- No guardrail was activated in synthetic calculation.
- No size, market-cap, role, or alternative membership weighting was added.

All five review artifacts are under
`temp/datacenter_effective_weight_model_review/DC_TAXONOMY_FULL_V2_1_20250801_20260925/`.
