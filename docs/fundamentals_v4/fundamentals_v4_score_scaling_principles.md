# Fundamentals V4 Score Scaling Principles

`Score = current fundamental state`.

`Delta Score = change in fundamental state`.

Each component independently maps its own current fundamental metric or metrics to a continuous absolute real-valued scale from 0 to N. Historical V4 distributions support floor, ceiling and saturation decisions, but the final score is not a percentile rank, z-score, universe decile or future-outcome model.

Missing component values are never converted to zero and available components are never reweighted back to 100. `SIMPLE_FUNDAMENTAL_SCORE_V1` permits exactly one optional-component median imputation only under `SCORE_READY_ESTIMATED`; the component-specific value must be locked in the canonical specification. Observed points, imputed points, and diagnostic-only results remain separately identifiable.
