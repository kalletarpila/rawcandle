# Fundamentals V4 Phase 13A Ticker-Onboarding Readiness

Phase 13A is a read-only audit for a future Scheduler Add Tickers workflow. It does not implement UI, add companies, fetch Sharadar data, migrate schema, refresh Relative Valuation or write production databases.

Run:

```bash
python -m rawcandle.cli.run_phase13a_ticker_onboarding_audit
```

The audit writes timestamped ignored artifacts under `temp/fundamentals_v4_phase13a_ticker_onboarding/`.

Current decision: `OUTCOME B — AUTHORITATIVE OPERATIONAL UNIVERSE WORK REQUIRED FIRST`.

Reason: operational Fundamentals membership is currently inferred from canonical active securities and historical bootstrap/alias lineage. A future Add Tickers implementation needs a durable authoritative operational-universe registry with explicit company/security identity, current ticker, market, status, effective dates, source/reason, audit fields, append-only history, alias semantics and deterministic fingerprinting.

Relative Valuation remains manual. Onboarding must not silently refresh the active Relative Valuation snapshot; newly onboarded companies may show Relative Valuation unavailable until a separate explicit full-universe refresh.
