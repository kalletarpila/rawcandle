# Fundamentals V4 Phase 12B Research Contract

## Locked identity

- Contract: `PHASE12B_REVISED_HISTORY_FUNDAMENTAL_PROFILE_BASELINE_V1`
- Fingerprint: `26a2826841ca024aa40682a3160df4fcff83cd2af1e3cbe9cccbb401f7201139`
- Locked at: `2026-09-10T05:57:32Z`
- Authoritative specification: `PHASE 12B - LEAKAGE-CONTROLLED FUNDAMENTAL PROFILE BASELINE`

The earlier `LEAKAGE-CONTROLLED FORWARD-RETURN BASELINE` draft is discarded.
No hypothesis, band, cohort, artifact, acceptance, or commit definition is
inherited from it.

## Mandatory status

> The feature history is currently revised and was reconstructed from a
> provider snapshot obtained in 2026. It is not original point-in-time history.
> Results describe retrospective associations and cannot establish real-time
> historical investability.

This phase is not PIT-valid, an investable backtest, a production model, a
technical entry system, a score modification, or authorization for Company
Snapshot prediction. Results from 2025 or 2026 may not be used for tuning.

## Temporal contract

| Period | Entry dates | Interpretation |
|---|---|---|
| `DEVELOPMENT` | 2021-01-01 through 2023-12-31 | Fit and development evidence |
| `TEMPORAL_VALIDATION` | 2024-01-01 through 2024-12-31 | Frozen-model validation |
| `RETROSPECTIVE_CONFIRMATION` | 2025-01-01 through 2025-12-31 | Retrospective confirmation, not OOS |
| `FORWARD_REPORT_ONLY` | 2026-01-01 through 2026-12-31 | Mature labels only; no selection |

Assignment uses the tradable entry date. Purge removes observations whose
63-session label ends after the assigned period. The first 63 SPY sessions of
each later period are embargoed. New data arriving after contract lock is
reserved for `PROSPECTIVE_FORWARD_VALIDATION`.

## Signal and labels

The information date is the stored source availability date. The tradable
entry is the first complete SPY session strictly later than that date, using
the company's valid stored adjusted open and SPY open on the same session.

Entry is session zero. Therefore a horizon `h` exits at SPY session index
`entry_index + h`, using exact synchronized company and SPY closes. No later
substitute exit and no forward filling is allowed. Company-session coverage
must be at least 90%, and all price inputs must be finite and positive.

The primary target is company simple 63-session price return minus SPY simple
63-session price return. Its binary form is one only when excess return is
strictly greater than zero. The 21- and 42-session targets are secondary.
Results are stored-adjusted price returns, not verified total returns.

## Cohort and features

The primary common cohort requires `SCORE_FULL`, `VALUATION_FULL`, 2Q
`DELTA_READY`, `LIFECYCLE_READY`, all six primary features, supported valuation
applicability, resolved identity, and a valid 63-session label. Missing values
are not imputed.

Primary features are Fundamental Score, Absolute Valuation Score, Fundamental
Delta 2Q, Fundamental Trajectory, confirmed categorical Lifecycle, and active
Diagnostic Flag count. Flag count includes only `EVALUATED_FLAGGED`; not-ready
and not-applicable statuses remain separate.

Current Relative Position, Relative Valuation, Own-History Relative Valuation,
peer percentiles, taxonomy, and current classification percentiles are excluded
as historical predictors. Current sector and industry may appear only in
explicitly non-PIT descriptive stability evidence.

## Fixed analysis

The exact bands, H1-H8 hypotheses, eight descriptive cross-tabs, five baseline
models, evaluation metrics, missing-exit stress views, sample gates, bootstrap,
and evidence classifications are encoded in
`rawcandle.research.fundamental_profile_baseline.contract.CONTRACT`.

Continuous features are centered and scaled from development data only.
Bounded scores are not winsorized. Lifecycle uses non-ordinal one-hot encoding
with `MATURE` as reference. Linear regression is unregularized. Logistic
regression uses fixed L2 regularization, `C=1`, `lbfgs`, and `max_iter=1000`.
There is no hyperparameter search or later-period refit.

Dependence-aware intervals use a deterministic 63-session calendar-time moving
block bootstrap with 1,000 repetitions and seed 12012. Benjamini-Hochberg is
applied across exactly H1-H8. Primary descriptive cells require 200 labelled
observations, 100 companies, and 12 entry months.

## Safety

All sources are opened through SQLite `mode=ro` with `query_only=ON`. The phase
has no network calls, production writes, schema, model persistence, Snapshot or
Scheduler integration, provider update, canonical rebuild, or Relative
Valuation refresh.
