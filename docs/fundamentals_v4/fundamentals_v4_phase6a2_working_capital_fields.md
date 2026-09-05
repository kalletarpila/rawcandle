# Fundamentals V4 Phase 6A.2 Working-Capital Fields

Phase 6A.2 adds only the upstream data contract required by the later `WORKING_CAPITAL_SHIFT_CANDIDATE`. It does not implement, calculate, or persist diagnostic flags and does not change Score, Trajectory, Lifecycle, Valuation, Relative Position, or Delta.

## Contract

| Canonical endpoint | Sharadar SF1 |
|---|---|
| `accounts_receivable` | `receivables` |
| `inventory` | `inventory` |
| `accounts_payable` | `payables` |
| `deferred_revenue` | `deferredrev` |
| `total_assets` | `assets` |

ARQ remains canonical. MRQ remains provider-side comparison and revision evidence. Provider `date` remains the availability date. Duplicate and restated ARQ rows use the existing deterministic winner order. Missing direct values are not derived from other fields.

These are balance-sheet endpoint observations. There are no TTM, rolling, averaged, quarterized, interpolated, or forward-filled forms. Phase 6B reads the current and prior fiscal-quarter endpoints directly from canonical history.

## Persistence

Fresh provider and canonical schemas expose all five columns. Upgrade uses additive `ALTER TABLE` operations and one restricted provenance table, `v4_operating_working_capital_provenance`, for all five mappings. Existing `v4_field_provenance` storage is neither copied nor rebuilt. Normal provenance read/write APIs route fields to the correct physical store.

Backfill parses authoritative `provider_observation.payload_json`, applies the normal ARQ winner, and writes canonical values and provenance in one transaction spanning explicit database copies. Repeating identical input causes zero logical writes. Company-scoped rebuilds synchronize changed values and provenance. The CLI defaults to dry-run and rejects resolved production paths and symlinks.

Blank, null, non-numeric, and non-finite values remain missing. Numeric zero is observed data and receives provenance. No unrelated canonical field or fiscal identity is updated.

## Phase 6B readiness

Provider `workingcapital` is not an ONWC input because it is the broader current-assets-minus-current-liabilities measure. The later ONWC input is receivables plus inventory less payables and deferred revenue.

The later diagnostic is ready only when both endpoint asset values are observed, finite, and strictly positive. Its denominator is `max((assets_t + assets_t_minus_1) / 2, 10_000_000)`. Zero or negative assets produce a not-ready/data-quality result and are never rescued with an absolute value. The provisional threshold remains 10%.

Rehearsal evidence is generated under `temp/fundamentals_v4_diagnostic_flags_phase6a2/<timestamp>/`. Production deployment is outside this phase.
