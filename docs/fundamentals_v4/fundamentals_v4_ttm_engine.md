# Fundamentals V4 TTM Engine

Model/version: `V4_TTM_EBIT_FIRST_V1`

The RawCandle V4 TTM engine is EBIT-first and uses canonical V4 quarterly financial values from `fundamentals_v4.db`. It has no SwingMaster runtime import.

Flow fields summed over four contiguous fiscal quarters: `revenue, gross_profit, operating_income, ebit, ebitda, net_income, net_income_common, operating_cashflow, capex, free_cashflow`.

Phase 3B adds `ttm_net_income_common = SUM(net_income_common)` and `net_income_common_4q_ready`. Missing common earnings does not change the pre-existing core TTM readiness or the semantics of `net_income <- netinc` and `ttm_net_income`. The additive calculation version is `V4_TTM_EBIT_FIRST_V1_COMMON_EARNINGS_ADDENDUM`; the established TTM model identifier remains compatible with Score and Lifecycle readers.

Instant endpoint fields: `cash, total_debt, shares_outstanding`.

Core readiness requires revenue, EBIT, free cash flow, endpoint cash, endpoint total debt, and endpoint shares. NULL is never converted to zero; zero remains a valid observed value.

Availability date rule: `ttm_source_available_date = MAX(input source_availability_date)`. `first_public_result_date` is not invented.

Production rows: `50585`. Current TTM ready companies: `2434`. Current not-ready companies: `24`.
