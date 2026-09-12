# Fundamentals V4 Active And Retired Test Boundary

The active test suite is the default pytest suite. It excludes only tests marked `retired_v3`.

The `retired_v3` marker is reserved for historical Fundamentals V3 fixture-contract tests that depend on removed temporary research artifacts, especially `temp/v3_active_tickers_99_27.csv`. That CSV must not be restored merely to satisfy old tests.

The Phase 13D.3 retired manifest contains exactly 14 real-CSV tests in `tests/test_fundamentals_v4_identity_calendar_bootstrap.py`. The synthetic V4 bootstrap tests in the same file remain active and continue to cover CIK parsing, fiscal anchor behavior, idempotency, schema preservation, and no-network/no-production guarantees.

To inspect retired tests explicitly:

```bash
pytest -m retired_v3 tests/test_fundamentals_v4_identity_calendar_bootstrap.py
```

To run the supported active suite, use the normal pytest command. The repository default expression is `not retired_v3`.
