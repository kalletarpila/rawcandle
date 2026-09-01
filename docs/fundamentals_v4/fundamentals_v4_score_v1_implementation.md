# Fundamentals V4 Score V1 Implementation

## Scope

V4-4 implements the locked `SIMPLE_FUNDAMENTAL_SCORE_V1` methodology in RawCandle. The phase adds the production calculator, command-line entry point, focused tests, durable methodology corrections, and reproducibility artifacts.

The owner-approved final revision replaces the historical Consistency component with Fundamental Trajectory at the same 10-point weight. The implementation does not calculate Lifecycle or Valuation, call external services, alter a database schema, or depend on SwingMaster at runtime.

## Files

- `rawcandle/fundamentals/score/engine.py`: deterministic calculation, evidence generation, persistence, rehearsal, replay, and integrity checks.
- `rawcandle/cli/run_fundamentals_v4_score.py`: production and no-write command-line execution.
- `tests/test_fundamentals_v4_score_engine.py`: component, readiness, Dilution-policy, persistence, and dependency tests.
- `docs/fundamentals_v4/fundamentals_v4_score_v1_specification.md`: active methodology and production contract.
- `docs/fundamentals_v4/fundamentals_v4_score_v1_phase_1b_report.md`: marked as historical where its former Dilution blocker differs from the active contract.
- `docs/fundamentals_v4/fundamentals_v4_master_plan.md`: V4-4 status and owner-approved Dilution policy.

## Inputs

The calculator reads `V4_TTM_EBIT_FIRST_V1` rows from `data/fundamentals_v4.db`. It uses `ttm_source_available_date` as the information-availability field and never substitutes `period_end` for availability. `period_end` and fiscal year/quarter identify the economic period and exact comparison chain.

The broad canonical universe is used without an active-security filter. Historical and delisted securities remain included. Banks, insurers, REITs, and other true financial companies are already absent upstream; the Score engine adds no outcome-driven exchange, security-type, or sector exclusions.

The only additional read is `data/osakedata.db.splits_data`. Split events are copied into Dilution evidence and are not applied as a second adjustment to stored V4 shares.

## Calculation

All interpolation is bounded, continuous, and piecewise linear. Missing input remains missing and never becomes zero. The total is the direct sum of component points; available weights are never rescaled to 100.

| Component | Formula | Maximum |
|---|---|---:|
| Revenue Growth | `revenue_ttm / revenue_ttm_4q_ago - 1` | 20 |
| EBIT Profitability | `ebit_ttm / revenue_ttm` | 15 |
| EBIT Margin Direction | current EBIT margin minus EBIT margin 4Q ago | 15 |
| FCF Margin | `free_cash_flow_ttm / revenue_ttm` | 15 |
| Balance Sheet Resilience | locked net-debt/EBIT branches | 15 |
| Dilution | `shares_outstanding / shares_outstanding_4q_ago - 1` | 10 |
| Fundamental Trajectory | four QoQ transitions across five contiguous TTM snapshots | 10 |

YoY calculations require the exact four-quarter predecessor and every fiscal ordinal in the intervening chain. Fundamental Trajectory requires five core-ready contiguous TTM snapshots and averages Revenue, EBIT-margin, and FCF trajectory points across four QoQ transitions. A flat transition gives 5 points; positive development gives 5–10; negative development gives 0–5. The tolerances are + or -5% for TTM Revenue, + or -5 percentage points for EBIT Margin, and + or -10% of prior TTM Revenue for the FCF change.

## Dilution policy

Stored `shares_outstanding <- sharesbas` values are compared directly. A positive YoY change above 50% is labeled `ASSUMED_GENUINE_DILUTION_BY_POLICY`, scores 0 points, and does not block readiness. This policy is explicit and limited to this private-use application.

The engine also calculates QoQ share change and finds local split rows between the YoY comparison endpoints. Both are evidence only. QoQ is not a second scored component, and the engine does not alter the YoY value based on a split row. Dilution is never imputed.

## Readiness

- `SCORE_FULL`: all seven components are observed.
- `SCORE_LIMITED`: the current TTM row is usable, but at least one of the seven components is missing.
- `SCORE_NOT_READY`: the current TTM row is not core-ready or has no valid availability date. Its total is `NULL`.

No active component is imputed, so the revised engine does not emit `SCORE_READY_ESTIMATED`.

For every result, `missing_input_reason` contains deterministic JSON with missing, observed, and imputed component lists, observed component count, observed points, imputed points, TTM readiness, and source availability. Each of the seven `score_component` rows contains the raw inputs, derived metric, observed/imputed state, and component-specific evidence.

## Persistence

No schema migration is performed. The engine writes only these existing tables in `data/fundamentals_analysis.db`:

- one `analysis_model_run` row for the Score run;
- one `score_result` row per V4 TTM endpoint;
- exactly seven `score_component` rows per Score result.

A run atomically replaces only rows whose model version is `SIMPLE_FUNDAMENTAL_SCORE_V1`. Other Score model versions and all Lifecycle and Valuation rows are preserved. A deterministic SHA-256 model fingerprint covers anchors, Trajectory tolerances and window, status rules, and the Dilution policy.

## Execution and verification

Production command:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_score \
  --repo-root /home/kalle/projects/rawcandle \
  --valuation-model-fingerprint 17a9c388647f9e810b9a88b5de1de764a1cb9f406c0f9e4f602da87b285ef62f \
  --full-universe --apply --confirm-production
```

Read-only production rehearsal:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_score \
  --repo-root /home/kalle/projects/rawcandle \
  --valuation-model-fingerprint 17a9c388647f9e810b9a88b5de1de764a1cb9f406c0f9e4f602da87b285ef62f \
  --full-universe
```

Each execution first writes to a copied rehearsal analysis database. A production execution writes the result twice with identical input and verifies identical value fingerprints. It also verifies that canonical financials, TTM values, Lifecycle rows, and Valuation rows are unchanged, `PRAGMA quick_check` is `ok`, and foreign-key validation has no errors.

Artifacts are written under `temp/fundamentals_v4_4_score/<UTC timestamp>/`:

- `score_v1_summary.json`;
- `score_v1_model_contract.json`;
- `score_v1_sample.csv`;
- `rehearsal_fundamentals_analysis.db`.

## Final Fundamental Trajectory revision

The owner approved Fundamental Trajectory after a read-only comparison against observed historical Consistency values in the current broad universe. The paired sample contained 2,179 companies. Old Consistency had a 7.40 median and the new Trajectory had a 5.64 median; their Pearson correlation was 0.067. This confirmed that Trajectory is a replacement with different semantics rather than a parameter adjustment. NVIDIA changed from 5.69 to 8.65 component points and DAVE from 5.84 to 8.75.

The active Score identifier remains `SIMPLE_FUNDAMENTAL_SCORE_V1` by explicit owner decision to make this part of the final Score V1. The model fingerprint changed, and the earlier `96aed46b...` production result is superseded. Git history and the historical Phase 1B report retain the earlier methodology for auditability.

## Production result

The revised production run completed on 2026-08-31 with classification `V4_SCORE_V1_IMPLEMENTATION_COMPLETE` and model fingerprint `6d12268b9b3c1b7da3d3b04b5b097afa1e6781a5c7cbc6dece3344a04e54be80`.

| Status | Results |
|---|---:|
| `SCORE_FULL` | 29,791 |
| `SCORE_LIMITED` | 12,715 |
| `SCORE_NOT_READY` | 8,079 |
| Total | 50,585 |

The analysis database contains 354,095 component rows, exactly seven per result. Active `CONSISTENCY` component rows: 0. Duplicate `(company_id, quarter_id, model_version)` results: 0. Results with an incorrect component count: 0. `SCORE_NOT_READY` is the only status with a `NULL` total, as required.

The first and second production writes produced the same value fingerprint: `47add84845743b33bc9e43d35296871890c1e850d0c9ca23b10e3b10c861f7bc`. `PRAGMA quick_check` returned `ok`, `PRAGMA foreign_key_check` returned no rows, and canonical financial, TTM, Lifecycle, and Valuation fingerprints/counts were unchanged. All 2,054 repository tests passed; pytest reported 8 warnings and no failures.

## Current-universe distribution

At the 2026-08-31 as-of date, using the latest result per company, the 180-day freshness rule, and `SCORE_FULL`, 2,199 companies were eligible.

| Fundamental Trajectory statistic | Points |
|---|---:|
| P10 | 3.9232 |
| P25 | 4.8684 |
| Median | 5.6413 |
| P75 | 6.3831 |
| P90 | 7.2459 |
| Zero-point share | 0.05% |
| Full-point share | 0.23% |

The distribution is centered close to the defined neutral score of 5 without material floor or ceiling saturation.

The revised current Top 15 scores are DAVE 97.9552, APP 97.3081, NVDA 97.2705, CDNA 96.6277, TER 96.3556, MU 95.9613, HL 95.8716, PLTR 95.6557, NEM 95.5945, EXE 94.6463, RDDT 93.5978, LPG 93.4103, INSW 93.1528, LQDA 93.0305, and ADI 93.0196.

The final run artifacts are in `temp/fundamentals_v4_4_score/20260831T203359Z/`. Database files and temporary artifacts are runtime outputs and are not part of the source commit.
