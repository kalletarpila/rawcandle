# Phase 12B.2 Methodology-Corrected Replay Results

## Decision

`OUTCOME C - NO REPEATABLE EVIDENCE UNDER THE CORRECTED CONTRACT`

The corrected retrospective study is technically testable, but none of H1-H8 meets its precommitted repeated-evidence rule. This does not authorize a production model, score change, or investment use. The data remains revised-history, non-PIT, and survivorship-limited.

## Identities

- Contract fingerprint: `152d2b8c9956888755c1d9a620f29b7a929e7cad00b501882816705a701e59e0`
- Source fingerprint: `402abff41586358b412f111fda297369b5a1011c5c28e4ffdb7fe308176d661a`
- Sample fingerprint: `1fe60ac6bc272244e872b32d5ce1537dc2bc250b39f526e51095c9bccb19f01d`
- Result fingerprint: `2faf5a504779e5f793c5cf3f156062da2c5674974ea15014757c160dd4376e31`
- Original Phase 12B contract fingerprint: `26a2826841ca024aa40682a3160df4fcff83cd2af1e3cbe9cccbb401f7201139`

## Cohorts

| Period | Entry dates | Last exit | Rows | Companies | Months | Entry sessions | Effective 63-session blocks |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| Development | 2021-01-05 to 2023-03-30 | 2023-06-30 | 9,455 | 1,711 | 20 | 369 | 6 |
| Validation | 2023-07-03 to 2024-06-28 | 2024-09-27 | 7,427 | 1,932 | 12 | 236 | 4 |
| Confirmation | 2024-10-01 to 2025-09-30 | 2025-12-30 | 7,801 | 2,013 | 12 | 240 | 4 |
| 2026 report-only | 2026-01-06 to 2026-06-10 | 2026-09-10 | 3,767 | 1,989 | 6 | 106 | 2 |

All exact labels use an entry-to-exit offset of 63 SPY sessions. There are zero duplicate endpoints, and Development labels end before Validation, Validation labels end before Confirmation, and Confirmation labels end before the reserved 2026 interval. The later period receives no blanket embargo.

## H1-H8 Result

- H1 Fundamental Score: weak or uncertain. Spearman is `0.0706`, `0.1232`, and `0.0438`; the Confirmation CI is `[-0.0302, 0.1202]` with `q=0.5554`.
- H2 Valuation Score: weak or uncertain. Spearman is `0.0899`, `0.1522`, and `0.0049`; the Confirmation CI is `[-0.0176, 0.0486]` with `q=0.7732`.
- H3 positive Delta 2Q: no repeated evidence. Mean-excess differences are `0.00338`, `0.01093`, and `-0.00182`.
- H4 high Fundamental and Valuation: not testable under the arm gate. Treatment counts are `413`, `97`, and `49`; Validation and Confirmation fail the 100-observation minimum.
- H5 positive Delta within H4: not testable under the arm gate. Treatment/comparator counts are `290/123`, `68/29`, and `43/6`.
- H6 Lifecycle interaction: no repeated evidence. Partial R-squared values are `0.00359`, `0.00216`, and `0.00178`; permutation p-values are `0.057`, `0.281`, and `0.335`.
- H7 active Diagnostic Flag count: no repeated evidence. Spearman changes from `-0.0803` and `-0.1156` to `+0.0221` in Confirmation.
- H8 B4 versus B3: failed. In Validation, Spearman change is `-0.02873` and Brier improvement `0.000255`; in Confirmation they are `-0.00897` and `-0.001555`. Neither period meets the locked materiality and positive-lower-CI gate.

The machine-readable files contain all point estimates, 95% block intervals, raw p-values, adjusted q-values, arm gates, missing-exit stress, and concentration checks.

## Models And Components

In Validation, B3/B4 Spearman is `0.1286/0.0999`, AUC `0.5405/0.5386`, and Brier `0.23981/0.23955`. In Confirmation, B3/B4 Spearman is `-0.0072/-0.0161`, AUC `0.4848/0.4863`, and Brier `0.24413/0.24568`. B4 therefore has no stable incremental value over B3.

No component has a repeated stable association across all three periods. Dilution points are positively associated in Development and Validation but not Confirmation. Balance Sheet Resilience is positive in Validation and Confirmation but weak in Development. FCF Margin and Operating Profitability are strongest in Validation but do not confirm. These are descriptive exploratory observations only.

## Original Reconciliation

The corrected study retains 24,683 unique common-cohort endpoints versus 20,880 in the original study. Across any period, 17,164 endpoints occur in both, 7,519 are newly included, and 3,716 original endpoints are excluded by the corrected calendar and non-overlap construction. Common labels have fingerprint `805bc11e7359f35aa18ede9681467e6485452caca5c51c5b13861a8f1f920d98`.

The original contract, artifacts, fingerprints, and `OUTCOME_B` remain unchanged. Phase 12B.2 supersedes none of that historical record; it is a separate corrected retrospective replay.

## Determinism And Isolation

Runs `20260911T_PHASE12B2_FINAL_A2` and `20260911T_PHASE12B2_FINAL_B` produced byte-identical 30-file economic manifests and the same contract, source, sample, and result fingerprints. JSON artifacts parse successfully.

Production preflight and postflight normalized fingerprints are both `e20f798866ec25f4bf39ee8c165375603acf2453a84926c30d8e49375610903f`. Database content is identical. SQLite changed only the taxonomy SHM sidecar mtime while servicing read-only access; its content hash remained unchanged.

## Artifacts

- `temp/fundamentals_v4_phase12b2/20260911T_PHASE12B2_FINAL_A2/`
- `temp/fundamentals_v4_phase12b2/20260911T_PHASE12B2_FINAL_B/`
- Contract: `docs/fundamentals_v4/fundamentals_v4_phase12b2_research_contract.md`

The next justified action is not a production or ML phase. Any further research should be separately predeclared and should address original point-in-time fundamentals, historical-universe survivorship, and terminal/delisting returns before treating later windows as stronger evidence.
