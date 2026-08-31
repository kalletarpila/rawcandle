# Fundamentals V4 Score V1 Implementation

## Scope

V4-4 implements the locked `SIMPLE_FUNDAMENTAL_SCORE_V1` methodology in RawCandle. The phase adds the production calculator, command-line entry point, focused tests, durable methodology corrections, and reproducibility artifacts.

The implementation does not add components, change component weights or anchors, calculate Lifecycle or Valuation, call external services, alter a database schema, or depend on SwingMaster at runtime.

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
| Consistency | locked normalized instability over four, otherwise three, contiguous snapshots | 10 |

YoY calculations require the exact four-quarter predecessor and every fiscal ordinal in the intervening chain. Consistency uses the same contiguous snapshot set for Revenue Growth YoY, EBIT Margin, and FCF Margin.

## Dilution policy

Stored `shares_outstanding <- sharesbas` values are compared directly. A positive YoY change above 50% is labeled `ASSUMED_GENUINE_DILUTION_BY_POLICY`, scores 0 points, and does not block readiness. This policy is explicit and limited to this private-use application.

The engine also calculates QoQ share change and finds local split rows between the YoY comparison endpoints. Both are evidence only. QoQ is not a second scored component, and the engine does not alter the YoY value based on a split row. Dilution is never imputed.

## Readiness

- `SCORE_FULL`: all seven components are observed.
- `SCORE_READY_ESTIMATED`: five core components and Dilution are observed; only Consistency is missing and receives the locked `6.988540590181791` points.
- `SCORE_LIMITED`: the current TTM row is usable, but the result does not satisfy either canonical complete status.
- `SCORE_NOT_READY`: the current TTM row is not core-ready or has no valid availability date. Its total is `NULL`.

For every result, `missing_input_reason` contains deterministic JSON with missing, observed, and imputed component lists, observed component count, observed points, imputed points, TTM readiness, and source availability. Each of the seven `score_component` rows contains the raw inputs, derived metric, observed/imputed state, and component-specific evidence.

## Persistence

No schema migration is performed. The engine writes only these existing tables in `data/fundamentals_analysis.db`:

- one `analysis_model_run` row for the Score run;
- one `score_result` row per V4 TTM endpoint;
- exactly seven `score_component` rows per Score result.

A run atomically replaces only rows whose model version is `SIMPLE_FUNDAMENTAL_SCORE_V1`. Other Score model versions and all Lifecycle and Valuation rows are preserved. A deterministic SHA-256 model fingerprint covers anchors, tolerances, imputation, status rules, and the Dilution policy.

## Execution and verification

Production command:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_score
```

Read-only production rehearsal:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_score --no-production-write
```

Each execution first writes to a copied rehearsal analysis database. A production execution writes the result twice with identical input and verifies identical value fingerprints. It also verifies that canonical financials, TTM values, Lifecycle rows, and Valuation rows are unchanged, `PRAGMA quick_check` is `ok`, and foreign-key validation has no errors.

Artifacts are written under `temp/fundamentals_v4_4_score/<UTC timestamp>/`:

- `score_v1_summary.json`;
- `score_v1_model_contract.json`;
- `score_v1_sample.csv`;
- `rehearsal_fundamentals_analysis.db`.

## Production result

The production run completed on 2026-08-31 with classification `V4_SCORE_V1_IMPLEMENTATION_COMPLETE` and model fingerprint `96aed46b1ffc86212220a5aa983a24fb9999cd0b7099626a20b794e72712bafc`.

| Status | Results |
|---|---:|
| `SCORE_FULL` | 25,271 |
| `SCORE_READY_ESTIMATED` | 4,626 |
| `SCORE_LIMITED` | 12,609 |
| `SCORE_NOT_READY` | 8,079 |
| Total | 50,585 |

The analysis database contains 354,095 component rows, exactly seven per result. Duplicate `(company_id, quarter_id, model_version)` results: 0. Results with an incorrect component count: 0. `SCORE_NOT_READY` is the only status with a `NULL` total, as required.

The first and second production writes produced the same value fingerprint: `abfc862d93bcd23e9cdafd7daf59315bda1d4ded6769082fa96bca165e1200e2`. `PRAGMA quick_check` returned `ok`, `PRAGMA foreign_key_check` returned no rows, and canonical financial, TTM, Lifecycle, and Valuation fingerprints/counts were unchanged.

The final run artifacts are in `temp/fundamentals_v4_4_score/20260831T173307Z/`. Database files and temporary artifacts are runtime outputs and are not part of the source commit.
