# Fundamentals V4 Production Baseline

Classification: `V4_PRODUCTION_BOOTSTRAP_COMPLETE_WITH_REVIEW_ITEMS`

Artifact root: `/home/kalle/projects/rawcandle/temp/fundamentals_v4_1b_production_bootstrap/20260830T205438Z`

Production databases:

- `/home/kalle/projects/rawcandle/data/fundamentals_provider.db`
- `/home/kalle/projects/rawcandle/data/fundamentals_v4.db`
- `/home/kalle/projects/rawcandle/data/fundamentals_analysis.db`

Sharadar history scope: `years=5`.

Universe: `2470` local bootstrap tickers from `temp/v3_active_tickers_99_27.csv`.

Provider observations: `102204`. Canonical quarters: `50585`. Provenance rows: `602940`.

CIK populated: `2436`. CIK NULL: `22`.

Q4 completed FY coverage: `98.1023` percent.

Latest8Q all-12 complete: `2429`. Latest4Q all-12 complete: `2437`. Latest quarter all-12 complete: `2445`.

Field coverage:

- revenue: `50171 / 50585` (`99.1816%`)
- gross_profit: `50171 / 50585` (`99.1816%`)
- operating_income: `50171 / 50585` (`99.1816%`)
- ebit: `50171 / 50585` (`99.1816%`)
- ebitda: `50078 / 50585` (`98.9977%`)
- net_income: `50171 / 50585` (`99.1816%`)
- operating_cashflow: `50085 / 50585` (`99.0116%`)
- capex: `50087 / 50585` (`99.0155%`)
- free_cashflow: `50085 / 50585` (`99.0116%`)
- cash: `50583 / 50585` (`99.996%`)
- total_debt: `50583 / 50585` (`99.996%`)
- shares_outstanding: `50584 / 50585` (`99.998%`)

TTM readiness windows:

- Latest8Q companies: `2447`; all-12 complete: `2429`; critical-6 complete: `2429`
- Latest4Q companies: `2450`; all-12 complete: `2437`; critical-6 complete: `2437`
- Latest quarter companies: `2451`; all-12 complete: `2445`; critical-6 complete: `2445`

Provider identity match:

- Bulk `permaticker` field present: `false`
- Bulk rows with permaticker: `0`
- Matched rows with permaticker: `0`
- Permaticker conflicts: `0`
- Ticker-security collisions: `0`

Replay:

- Provider observations before/after: `102204 / 102204`
- Canonical quarters before/after: `50585 / 50585`
- Canonical financial rows before/after: `50585 / 50585`
- Provenance rows before/after: `602940 / 602940`
- Changed canonical values: `0`
- Duplicate rows created: `0`
- Fingerprints identical: `true`

Baseline fingerprints are stored in `v4_production_baseline_fingerprints.json` under the artifact root. Generated Sharadar bulk files and audit artifacts remain under `temp/` and are not committed.

Next action: `KEEP THE PRODUCTION V4 BASELINE FROZEN; RESOLVE ONLY THE SPECIFIC IDENTITY / COVERAGE / PROVIDER QUALITY REVIEW ITEMS BEFORE TTM MIGRATION`
