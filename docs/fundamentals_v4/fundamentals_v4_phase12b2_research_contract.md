# Phase 12B.2 - Versioned twelve-month research contract

This contract is a separately versioned retrospective exploratory study. It does not replace the original Phase 12B contract, fingerprint, artifacts, or `OUTCOME_B`.

Contract fingerprint: `152d2b8c9956888755c1d9a620f29b7a929e7cad00b501882816705a701e59e0`

## Windows

- Development starts `2021-01-01` and retains only entries whose exact 63-session exit is strictly before `2023-07-03`.
- Validation entry window is `2023-07-01` through `2024-06-30`; observed SPY entry sessions are `2023-07-03` through `2024-06-28`, and the latest exit is `2024-09-27`.
- Confirmation entry window is `2024-10-01` through `2025-09-30`; the latest exit is `2025-12-30`.
- The first reserved 2026 SPY session is `2026-01-02`.

The earlier period is purged when its exact exit session is greater than or equal to the first permitted entry session of the next protected period. No following-period embargo is applied. Fiscal and ordinary calendar-year transitions are not boundaries.

## Hypotheses

H1, H2, H3, H4, H7 retain their original economic meanings. H5 compares positive versus non-positive Delta 2Q strictly inside H4. H6 is an exploratory OLS lifecycle-interaction omnibus test using a two-sided 63-session-block Freedman-Lane permutation. H8 compares B4 directly with B3 and requires material gains in both ranking and classification.

H3-H5 apply the same gates separately to both arms: at least 100 observations, 50 companies, 9 calendar months, 30 entry sessions, and a median of 3 observations per present month. Failure is `NOT_TESTABLE_SAMPLE_GATE_FAILED`, not evidence of no effect.

## Inference and multiplicity

Primary confidence intervals and null-centered p-values use 1,000 deterministic 63-SPY-session moving-block replicates with seed `120122`. H6 uses 999 deterministic Freedman-Lane permutations.

H1-H5 and H7 form a six-test, one-sided Benjamini-Hochberg family with `q <= 0.10`. H6 and H8 are separately declared tests. The seven component analyses form a two-sided BH family with `q <= 0.10`. Sample-gate failures have null p/q values and are excluded from the family test count.

H8 requires in both Validation and Confirmation:

- `Spearman(B4) - Spearman(B3) >= 0.02`;
- `Brier(B3) - Brier(B4) >= 0.002`;
- paired moving-block 95% lower bounds above zero for both metrics.

## Components

The descriptive component family is exactly:

- `BALANCE_SHEET_RESILIENCE`
- `DILUTION`
- `FCF_MARGIN`
- `FUNDAMENTAL_TRAJECTORY`
- `OPERATING_MARGIN_DIRECTION`
- `OPERATING_PROFITABILITY`
- `REVENUE_GROWTH`

Component raw evidence and bounded points are analyzed separately. This analysis cannot change Score weights, anchors, H1, the Phase 12B.2 outcome, or create a B5 model.

## Decision rules

- Outcome A requires H8 and at least one repeated H1-H5/H7 association.
- Outcome B requires at least one repeated association without the complete A gate. H6 alone can support only an exploratory Outcome B.
- Outcome C means the core study is testable but no repeated evidence exists.
- Outcome D is reserved for a non-testable core study or an implementation, identity, determinism, or label failure. An isolated H4/H5 arm-gate failure does not force Outcome D.

The complete machine-readable contract is `rawcandle/research/fundamental_profile_baseline_v2/contract.py`. The contract fingerprint is generated deterministically from that structure and must be recorded in the contract-only commit before corrected outcomes are calculated.
