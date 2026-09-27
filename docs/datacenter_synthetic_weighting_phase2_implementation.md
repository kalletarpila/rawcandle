# Datacenter synthetic weighting Phase 2 implementation

## 1. Implementation boundary

This phase makes the existing Datacenter base and relative synthetic OHLC
calculations membership-weight aware. The implementation is production-capable,
but this phase does not rebuild or publish production data.

The reusable policy and canonicalization live in
`analysis/ecosystem_group_weighting.py`. Datacenter taxonomy rows are adapted
to that model in
`analysis/datacenter_indices/swing_group_synthetic_ohlc.py`. Persistence,
structure, reports, EC projection, scheduler configuration, taxonomy contents,
and taxonomy versions are unchanged.

## 2. Canonical membership contract

Each taxonomy row expands to one layer route and one subindustry route. Routes
are canonicalized by:

`(ticker, group_type, group_name)`

A `CanonicalGroupMembership` retains ticker, group identity, the winning
primary/status metadata, effective weight, source route count, and source
statuses. Group member count is the number of canonical memberships.

## 3. Collision resolution

Duplicate routes are not accumulated. The canonical route uses the maximum
effective weight. This makes primary CORE/EXTENDED dominate secondary
CORE/EXTENDED, an included route dominate WATCH_ONLY/TOO_SMALL, and repeated
secondary routes remain one secondary contribution. Ties are deterministic.

## 4. V1 weighting policy

| Group | Membership | CORE/EXTENDED | WATCH_ONLY | TOO_SMALL |
|---|---|---:|---:|---:|
| subindustry | primary | 1.00 | 0.00 | 0.00 |
| subindustry | secondary | 0.33 | 0.00 | 0.00 |
| layer | primary | 1.00 | 0.00 | 0.00 |
| layer | secondary | 0.25 | 0.00 | 0.00 |

Unsupported group types, statuses, and primary flags raise `ValueError`.
`role_weight` is intentionally not an input and is not multiplied into V1.

## 5. Daily normalization

Current ticker OHLC eligibility is unchanged. For each date, positive effective
weights are normalized over price-eligible canonical members:

`weighted return = sum(return * effective_weight) / sum(effective_weight)`

Missing prices redistribute influence only among remaining positive-weight
members. If eligible effective weight is zero, OHLC remains null, the chain does
not advance, and quality status is `NO_DATA`. There is no equal-weight fallback.

## 6. Shared base and relative semantics

Base synthetic open/high/low/close returns use canonical memberships and the
shared `weighted_mean` helper. Existing first-positive-weight row anchoring,
chain linking, candle clamping, MA20, EMA20, distance-to-EMA20, and volatility
behavior is retained.

Relative OHLC uses the same canonical groups, policy, collision resolution, and
`weighted_mean` helper. It still derives ticker-relative values from each
ticker's rolling close base and updates existing base rows only.

## 7. Preserved count semantics

- `member_count`: unique canonical taxonomy tickers in the group.
- `eligible_count`: canonical members satisfying current base price
  eligibility, including zero-weight WATCH_ONLY and TOO_SMALL members.
- `relative_eligible_count`: same principle under relative price eligibility.

Positive-weight counts and weight sums are diagnostics only. Therefore
`eligible_count` may be positive while OHLC is null and status is `NO_DATA`.

## 8. Preserved volume semantics

`synthetic_volume` remains the unweighted sum of non-null raw volumes over all
price-eligible canonical members. It is independent of effective weight and can
remain populated on a zero-effective-weight date whose OHLC is null.

## 9. Shadow execution

The shadow CLI reads persisted current rows through a SQLite read-only
connection, computes weighted rows in memory, and writes only beneath
`temp/datacenter_effective_weight_calculation_only/`:

```bash
python3 -m rawcandle.cli.run_datacenter_effective_weight_shadow \
  --analysis-db data/analysis.db \
  --price-db data/osakedata.db \
  --taxonomy-csv data/datacenter_taxonomy_full_v2_1.csv \
  --chain-start-date 2025-08-01 \
  --start-date 2026-09-01 \
  --end-date 2026-09-25 \
  --market usa \
  --calc-version DC_SWING_OHLC_V1 \
  --output-dir temp/datacenter_effective_weight_calculation_only/v2_1_20260901_20260925
```

`chain-start-date` must match the intended generation anchor for meaningful
level comparison. The generated CSV includes group/date composition, eligible
weight, normalized concentration, effective member count, equal and weighted
closes, close delta, and daily returns. JSON contains the run summary.

The above shadow run produced 954 diagnostics, 943 comparable closes, and a
maximum absolute close percentage delta of approximately 38.9%. Structure
shadowing was intentionally deferred because it requires a separate chain-safe
in-memory structure comparison.

## 10. Tests run

```text
pytest -q tests/test_ecosystem_group_weighting.py \
  tests/test_datacenter_effective_weighting_integration.py \
  tests/test_datacenter_effective_weight_shadow.py \
  tests/test_datacenter_group_synthetic_ohlc.py \
  tests/test_datacenter_taxonomy.py \
  tests/test_run_datacenter_group_synthetic_ohlc_cli.py
```

Result: 52 passed. The changed modules also passed `py_compile` and
`git diff --check`.

## 11. Production actions intentionally not run

- No production `dc_*` rebuild, overwrite, or publication.
- No EC refresh, backfill, or schema change.
- No scheduler or report change.
- No taxonomy edit, version bump, or activation.
- No production workflow invocation.
- No structure persistence or report generation.

The live production data remains unchanged. Only the calculation-capable code,
tests, documentation, and ignored temp shadow outputs changed.

## 12. Known next steps

1. Run chain-safe historical weighted structure validation, including
   trend/structure/BOS/RESET differences.
2. Decide the production calculation-version transition and plan a chain-safe
   DC historical rebuild.
3. Explicitly refresh/backfill the matching EC date range after DC publication.
4. Run DC/EC parity validation over all projected synthetic and lineage fields.
5. Research size-based weighting separately; do not fold it into V1.
