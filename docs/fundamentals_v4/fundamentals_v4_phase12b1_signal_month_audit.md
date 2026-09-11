# Phase 12B.1 - Signal-month, continuity, purge, and embargo audit

## Decision

`OUTCOME B - THE LOCKED BOUNDARY POLICY IS INTERNALLY CONSISTENT BUT UNNECESSARILY REMOVES VALID OBSERVATIONS`

This phase did not rerun H1-H8, refit B0-B4, change the locked Phase 12B contract, or write production data. It reconstructed cohort membership from the accepted Phase 12D candidate A feature databases and the same Phase 12B label functions.

Contract fingerprint: `26a2826841ca024aa40682a3160df4fcff83cd2af1e3cbe9cccbb401f7201139`

Accepted source fingerprint: `402abff41586358b412f111fda297369b5a1011c5c28e4ffdb7fe308176d661a`

## Direct finding

The research partition is assigned by `entry_date`, not fiscal year, period end, availability year, or exit year. `entry_date` is the first complete SPY session strictly after `source_availability_date`. Company and SPY returns use that same entry session and the exact session at offset 63.

The annual seven-month result comes from double-sided boundary protection:

1. Purge removes an earlier-period row whenever `exit_date_63` is later than that period's calendar end.
2. Embargo removes the first 63 SPY sessions of every post-development period.

These operations remove different rows, so there is no duplicate row removal. They nevertheless protect the same adjacent-boundary dependence risk from opposite sides. Economically calculable labels are excluded by contract rather than by data invalidity.

## Accepted cohort reconciliation

| Period | Rows | Companies | Retained signal months |
| --- | ---: | ---: | --- |
| Development | 13,051 | 1,870 | 2021-01..06; 2022-02..12; 2023-01..09 |
| Validation 2024 | 3,876 | 1,945 | 2024-04..10 |
| Confirmation 2025 | 3,953 | 1,989 | 2025-04..10 |

All three row and month counts exactly reconcile to the accepted Phase 12D replay.

The missing Development months have two causes:

- `2021-07` through `2022-01`: no common-cohort row survives readiness, predominantly because absolute valuation is not `VALUATION_FULL`; incomplete TTM and Score readiness are secondary causes.
- `2023-10` through `2023-12`: otherwise ready rows are removed by the period-end purge.

For 2024 and 2025:

- January through March are emptied by the first-63-session embargo after readiness filtering.
- November and December are emptied by the period-end purge.
- A few October rows remain because exact filing and entry dates differ within the month.

## Fiscal continuity

The operational chains use integer fiscal ordinals and do not reset at calendar-year boundaries. Audit evidence contains:

- 59,035 valid ready TTM chains crossing a fiscal-year boundary;
- 3,013 rejected cross-year chains, all carrying data-readiness blockers;
- zero rejection condition based only on year inequality.

The rejected chains comprise 1,904 missing-quarter cases, 833 missing revenue/operating-income/FCF cases, 255 missing-FCF cases, and 21 missing revenue/operating-income cases. Valid Q4-to-Q1, multi-year, Delta 2Q, and CAGR ordinal transitions are covered by focused tests.

Internal `2021 -> 2022` and `2022 -> 2023` changes are not research boundaries and remove zero rows. A 63-session label may cross those years normally.

## Boundary mechanics

The 2024 embargo cutoff is `2024-04-03`, 93 calendar days after period start. The 2025 cutoff is `2025-04-04`, also 93 calendar days after period start. The comparison is strict: entries before the cutoff are embargoed and an entry on the cutoff is retained.

Purge removes 2,395 assigned Development rows before 2024, 2,429 Validation rows before 2025, and 2,432 Confirmation rows before 2026. Embargo separately removes 2,356 assigned 2024 rows and 2,394 assigned 2025 rows before feature/readiness gates.

## Counterfactual cohorts

| Policy | Development | 2024 | 2025 | Status |
| --- | ---: | ---: | ---: | --- |
| P0 implemented | 13,051 / 26 months | 3,876 / 7 | 3,953 / 7 | Locked contract |
| P1 literal contract | 13,051 / 26 | 3,876 / 7 | 3,953 / 7 | Same as P0 |
| P2 earlier-side purge only | 13,051 / 26 | 5,722 / 10 | 5,863 / 10 | Diagnostic only |
| P3 no boundary exclusion | 14,878 / 29 | 7,658 / 12 | 7,854 / 12 | Diagnostic only; overlapping labels |
| P4 non-overlapping future proposal | 13,051 / 26 | 5,722 / 10 | 5,863 / 10 | Requires a new contract |

P2/P4 retain no label whose exit crosses its assigned period end. The additional January-March observations come only from removing the later-side embargo. P3 demonstrates total boundary attrition but is not valid confirmatory evidence under the locked design.

## Bootstrap limitation

The implementation performs 1,000 deterministic one-level moving-block bootstrap replicates with seed `12012`. A sampled block starts at a SPY entry session and includes all company rows appearing during the following 63 sessions. Company observations sharing market time are therefore moved together rather than treated as independently timed observations.

Validation has 123 unique entry-session starts and Confirmation 121, but each covers only seven calendar signal months. A numerical 95% interval can be generated, but resampling cannot create more independent market regimes than the seven observed months. This is an inferential limitation separate from the boundary-policy finding.

## Source snapshot note

The Phase 12D candidate directory froze canonical, analysis, and provider databases but referenced the production market database. Its accepted market hash was `38078094058004539dcb155df8b4172cb6822dc20c465c02cd7468710a1d1cdd`. The current market database contains only later price-day additions. The audit accepts reconstructed historical evidence only because all 2021-2025 row and month counts and the feature source fingerprint reconcile exactly. It makes no accepted-result claim about the changed 2026 maturity edge.

## Consequence

The original Phase 12B results remain valid descriptions of the original locked contract. They must not be reinterpreted as P2-P4 results. A Phase 12B.2 is required to create a separately versioned, less restrictive boundary contract before recomputing hypotheses or models. It is a research-design correction, not a hidden fix to the original implementation.

Primary generated evidence:

`temp/fundamentals_v4_phase12b1/20260911T_PHASE12B1_FINAL_A/`

Deterministic replay evidence:

`temp/fundamentals_v4_phase12b1/20260911T_PHASE12B1_FINAL_B/`

Both runs produced the economic fingerprint `afd3a69e0eda032727b27020933a65e47db4c99e3363a93816ff2975d24763a7`; all 13 economic artifacts were byte-identical.
