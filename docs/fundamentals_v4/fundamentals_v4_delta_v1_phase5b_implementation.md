# Fundamental Delta V1 Phase 5B Implementation

## Scope

Phase 5B implements:

- `rawcandle/fundamentals/delta/engine.py`: immutable fiscal resolver and Fundamental Delta engine;
- `rawcandle/fundamentals/delta/context.py`: categorical Lifecycle context and filing-date Valuation diagnostic;
- `rawcandle/fundamentals/delta/source.py`: explicit-path SQLite `mode=ro` adapters;
- `rawcandle/fundamentals/delta/rehearsal.py`: two-pass full-history analysis, artifacts, benchmarks and integrity checks;
- `rawcandle/cli/run_fundamentals_v4_delta_rehearsal.py`: read-only CLI with no apply option;
- focused engine, context, source and boundary tests.

The public pure entry points are `resolve_horizon`, `calculate_fundamental_delta`, `calculate_lifecycle_context` and `calculate_valuation_diagnostic`. `load_delta_source` is the separate database adapter.

The adapter requires exact Score, Lifecycle and Valuation fingerprints and rejects duplicates. It joins persisted Score rows to canonical fiscal and TTM readiness, reads component observation status from existing evidence JSON, and takes component maxima from the locked Score model contract. Missing source values remain missing.

## Rehearsal

The production-shaped read-only run uses as-of date `2026-09-01`, freshness limit 180 days and writes only to:

```text
temp/fundamentals_v4_delta_phase5b/20260902T040000Z/
```

It calculates all 50,585 revised-history endpoints twice. Total endpoint JSON, component JSON, Lifecycle CSV and Valuation CSV must each be byte-identical between runs. The final directory contains the first canonical serialization, readiness and distribution CSVs, current-fresh output, reconciliation, incremental 2Q analysis, representative cases, an extreme audit, persistence benchmark, fingerprints, metrics and five-database before/after integrity evidence.

Phase 5A historical strict readiness is an acceptance invariant: QoQ `27,490` and YoY `20,717`. Phase 5B adds 2Q. Current-fresh population must remain `2,441`, with Phase 5A QoQ `2,187` and YoY `2,149` unchanged.

### Results

- Delta model fingerprint: `7cd5ff99c623f047940f296e4b2f7c504dd1f9b868b3079f6ef7d3a3f9b0d49d`.
- Source fingerprint: `c9402322dc4ecc731a8c084e16471be03d0183fd55618a7faf696a61b02ce9ba`.
- Result fingerprint: `6c811ee39d0fd6cc88873c6aec8b30743449e2ffda0348ed22b019bf8d338f2d`.
- Lifecycle context source/result: `3be63bb8403e43bc383914bb3c7bd9ffff115691c2aef0fb7b83d6ddd303c689` / `24cd7ead3ba0e5e945355e0a203d2cb4dd31eb94f5bceca2180ed2cc70b4a7c0`.
- Valuation diagnostic source/result: `9b09434e1baa094b62b11e9792f7b6e781cd79fa2a3d7bbbe8af31d451273d9f` / `cfb056f0f27e98c90fa11d908eb7af0bce6f749b11ecb4a0f7ff4573f2ba31f1`.
- Historical strict-ready QoQ / 2Q / YoY: `27,490 / 25,210 / 20,717`.
- Current-fresh strict-ready QoQ / 2Q / YoY: `2,187 / 2,179 / 2,149`.
- Current-fresh Lifecycle context 2Q ready: `2,385`.
- Current-fresh Valuation diagnostic 2Q ready: `2,221`.
- Current-fresh 2Q component readiness ranges from `2,179` for Trajectory to `2,420` for Dilution.

The historical 2Q distribution is minimum `-79.0468`, P01 `-38.3333`, P10 `-15.2333`, P25 `-5.8883`, median `0.0142`, P75 `6.0929`, P90 `15.6219`, P99 `38.3430`, and maximum `79.8481`. It contains 12,628 positive, 12,551 negative and 31 exact-zero changes.

QoQ and 2Q correlation is `0.7334`. Current Trajectory correlations with total Delta are QoQ `0.2283`, 2Q `0.3741`, and YoY `0.5753`. The intermediate correlation, distinct sign combinations and 4,493 endpoints where QoQ plus 2Q are ready but YoY is unavailable support retaining 2Q as a faster intermediate horizon. This is descriptive evidence, not metric optimization.

CRMD is ready at `-2.4822 / -3.1156 / -2.8941` for QoQ / 2Q / YoY. APD is ready at `-26.7024 / 5.3761 / -4.3303`. Exact component contributions are in `representative_cases.md`.

All strict-ready totals reconciled to seven component changes within `1e-9`, with zero violations. The four canonical replay files were independently byte-identical. All five production database size, mtime, SHA-256, schema hash, page/freelist count, table counts and `quick_check` values matched before and after.

## Persistence Benchmark

The rehearsal compares horizon-normalized, wide endpoint and compact hybrid representations using actual serialized output sizes. The Phase 5C recommendation is the hybrid: one endpoint row containing three total horizons and one endpoint row per component containing three component horizons, with Lifecycle and Valuation stored separately. It minimizes repeated endpoint identities while retaining component-level auditability and company-specific rebuilds.

Measured estimates are 1,214,040 logical rows and about 247 MB table plus 82 MB index for horizon-normalized storage, versus 404,680 rows and about 82 MB table plus 21 MB index for the wide/hybrid contract. These are rehearsal-derived planning estimates, not observed production SQLite sizes.

The benchmark is an estimate, not a schema prototype. Phase 5B deliberately contains no SQL DDL for Delta and does not authorize production persistence.

## Boundaries And Risks

Results are currently revised history, not exact historical PIT values. Availability chronology prevents future endpoint display but does not recover superseded filings. Current ticker metadata is descriptive only. Extreme Score changes can reflect real discontinuities, accounting events, score floors/ceilings or source anomalies and therefore remain review candidates rather than automatic economic conclusions.

The Valuation diagnostic is especially non-causal: a score change can combine market price and multiple balance-sheet and TTM numerator changes. The representative price-movement cases are heuristics, not decompositions.

Phase 5C may design a compact versioned persistence contract only after separate authorization. Production activation, readers, rebuild operations and pipeline integration are outside Phase 5B.
