# Fundamentals V4 Score Calibration (Superseded V4-3A Record)

This file records the historical V4-3A calibration only. It is superseded by `SIMPLE_FUNDAMENTAL_SCORE_V1` in `fundamentals_v4_score_v1_specification.md` and must not be used as an active Score V1 contract. The old 25/15/15/15/10/15/5 structure, readiness rules, fingerprint, and implementation-ready classification below are retained only for traceability.

Classification: `V4_SCORE_V1_CONTINUOUS_SCALING_LOCKED_IMPLEMENTATION_READY`

Artifact root: `/home/kalle/projects/rawcandle/temp/fundamentals_v4_3a_score_scaling/20260831T141119Z`

The V4-3A calibration used V4 canonical quarterly fundamentals and `V4_TTM_EBIT_FIRST_V1` TTM rows. It did not write production Score rows, Lifecycle rows, Valuation rows, canonical quarterly values, or TTM values.

Score semantic: `CURRENT_FUNDAMENTAL_STATE`.

Delta Score semantic: `CHANGE_IN_FUNDAMENTAL_STATE`.

Future fundamental improvement monotonicity is a non-blocking diagnostic, not a production readiness criterion.

Primary split key: `ttm_source_available_date`.

Development observations 2021-2023: `23857`

2024 validation observations: `9737`

2025 locked OOS observations: `9774`

2026 forward validation observations: `7127`

Stock-return fields used for calibration: `0`.

Future-fundamental optimization used: `NO`.

Cross-sectional percentile scoring used: `NO`.

The candidate model fingerprint is `68601dda8d4e873e58a134c286f5d0468bfefa58dfec84920d4596412371b3ff`. The locked model was created before 2025 and 2026 evaluation; those periods were diagnostics only.
