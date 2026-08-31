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

## V4-1B-1 Post-Review Baseline

Classification: `V4_BOOTSTRAP_REVIEW_COMPLETE_WITH_TRUE_PROVIDER_GAPS`

Artifact root: `/home/kalle/projects/rawcandle/temp/fundamentals_v4_1b1_bootstrap_review/20260831T062412Z`

Canonical financial fingerprint changed: `NO`.

Provider metadata:

- Sharadar tickers metadata rows fetched: `74078`
- Target securities matched: `2465`
- Permaticker populated: `2465`
- Permaticker NULL: `5`
- Unique permatickers: `2465`
- Identity conflicts: `0`
- Delisted securities: `17`
- Ticker aliases discovered from safe ticker-change actions: `5`

Review classifications:

- Unmatched 19: `14` provider ticker different, `3` ticker renamed, `2` bootstrap universe stale.
- Gap 172: `172` true internal missing quarter classifications.
- Missing Q4 190: `182` false missing due window, `8` true Q4 provider gaps.
- Shares 255: `107` normal buyback/issuance, `19` reverse split, `14` SPAC/recapitalization, `2` ticker/security change, `113` insufficient evidence.
- Debt mismatch: `CORZ 2024-Q4 MRQ`, classification `PROVIDER_COMPONENT_INCONSISTENCY`; canonical debt changed `NO`.

Post-review Q4:

- Fully observable completed FYs: `9830`
- Explicit Q4 present: `9822`
- True Q4 missing: `8`
- Clean Q4 coverage: `99.9186%`

TTM readiness:

- TTM input ready: `2434`
- TTM input not ready: `24`
- Readiness: `99.0236%`
- Top blockers: missing free cashflow `13`, missing EBIT `12`, missing revenue `12`, latest4 sequence gap `10`, fewer than 4 quarters `8`

Next action: `PROCEED TO V4-2 WITH EXPLICIT GAP FLAGS; DO NOT DELAY TTM MIGRATION FOR NON-MATERIAL PROVIDER EDGE CASES`

## V4-2 TTM Baseline

Artifact root: `/home/kalle/projects/rawcandle/temp/fundamentals_v4_2_ttm/20260831T073656Z`

- Classification: `V4_TTM_MIGRATION_COMPLETE_WITH_NON_BLOCKING_GAPS`
- TTM rows: `50585`
- Unique companies with ready TTM: `2448`
- Current TTM ready: `2434`
- Current TTM not ready: `24`
- Canonical financial fingerprint unchanged: `True`
- Score rows: `0`
- Lifecycle rows: `0`
- Valuation rows: `0`

## V4-3A Score Calibration Baseline (Superseded)

Artifact root: `/home/kalle/projects/rawcandle/temp/fundamentals_v4_3a_score_scaling/20260831T141119Z`

Historical classification: `V4_SCORE_V1_CONTINUOUS_SCALING_LOCKED_IMPLEMENTATION_READY`

This classification is superseded by Phase 1B / V4-3B. The active `SIMPLE_FUNDAMENTAL_SCORE_V1` methodology is locked with a Dilution upstream blocker; it is not yet production implementation-ready.

Canonical fingerprint matched pre-phase baseline: `True`
TTM fingerprint matched pre-phase baseline: `True`
Production Score rows created: `0`.
