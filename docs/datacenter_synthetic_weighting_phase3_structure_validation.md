# Datacenter synthetic weighting Phase 3 structure validation

## 1. Baseline

The implementation baseline is starting HEAD
`0d0938ebaa7f506a85524a5ec0a44f69ef1b7bb8`. The validation uses taxonomy
`DC_TAXONOMY_FULL_V2_1`, price input
`data/osakedata.db`, and the current `DC_SWING_OHLC_V1` Datacenter synthetic
implementation. The active persisted generation contains 290 dates from
2025-08-01 through 2026-09-25. It covers 16 layer groups and 37 subindustry
groups.

## 2. Chain range

- `chain_start_date`: `2025-08-01`
- `comparison_start_date`: `2025-08-01`
- `comparison_end_date`: `2026-09-25`

The full usable production-generation range was selected. The price loader
reads ticker rows through the end date, including rows before the chain anchor,
so the first in-range daily return can use the previous valid ticker close.

Relative OHLC needs 20 valid ticker closes for its rolling base. MA20 and EMA20
need 20 valid synthetic closes, while 20-day return volatility effectively
needs 21 closes. Pivots require future confirmation with radius 5 for
subindustries and 10 for layers. Structure, BOS, and RESET accumulate from
confirmed pivots and have no separate fixed warm-up. Early null technical
fields are retained in both lanes, making the full range methodologically
equivalent without an arbitrary recent cut-off.

## 3. Equal construction

The equal lane is recalculated from the same taxonomy and prices as the
weighted lane. Its injected membership policy assigns `1.0` to every valid
canonical membership, including WATCH_ONLY and TOO_SMALL, reproducing the old
equal-contribution semantics while retaining current validation and collision
handling. It is not a persisted-close shortcut.

Against persisted production rows, all compared synthetic OHLC, EMA20,
distance-to-EMA20, and volatility fields reproduced with zero mismatches and a
maximum numeric delta of `0.0`.

## 4. Weighted construction

The weighted lane uses the Phase 2 V1 policy: primary CORE/EXTENDED `1.00`,
secondary subindustry `0.33`, secondary layer `0.25`, and WATCH_ONLY/TOO_SMALL
`0.00`. Canonical keys are `(ticker, group_type, group_name)`, duplicate routes
resolve to the maximum route weight, and daily normalization includes eligible
positive-weight members only. There is no `role_weight`, route accumulation,
or equal-weight fallback.

## 5. Shared engine

Both recalculated OHLC histories are written only to temporary SQLite
databases and processed with the existing
`build_group_structure_updates` engine. Pivot, HH/HL/LH/LL, trend, BOS, RESET,
age, and freshness behavior therefore remain identical between lanes. The
temporary databases are removed after use.

## 6. Event rules

Structure and trend states are compared on the same group and date. BOS events
match only within the same group and direction/type and within +/-5 valid group
trading days. RESET uses the same window and also compares reason. Candidate
selection is nearest by absolute trading-day distance, ties choose the earlier
date, and matching is one-to-one. Unmatched events are EQUAL_ONLY or
WEIGHTED_ONLY; a matched RESET with a different reason is REASON_CHANGED.

## 7. Aggregate results

The output contains 15,370 group-date comparisons across all 53 groups. Of
these groups, 31 (58.5%) have at least one structure-label change and 31 have at
least one trend-classification change. Twenty-one groups have no change above
the `LEVEL_CHANGE_ONLY` class.

## 8. Trend differences

Trend changes are broad rather than isolated: 31 groups changed trend on at
least one date. The largest counts include Specialty metals (142), Power
generation / utilities (125), Electrical & power systems (113), Virtualization
/ cloud software (108), and Power generation and utility exposure (101).

## 9. BOS

The comparison found 429 matched BOS events, 86 equal-only events, and 88
weighted-only events. Thirty-one groups have a BOS presence or timing change.
Matched timing shifts range from -5 to +4 valid trading days, with median zero
and maximum absolute shift five days. No BOS reason-change category applies.

## 10. RESET

The comparison found 194 matched RESET events, 35 equal-only events, 40
weighted-only events, and three reason changes. Thirty groups have a RESET
presence, timing, or reason change. Matched timing shifts range from -4 to +4
valid trading days, with median zero and maximum absolute shift four days.

## 11. Concentration

Weighting materially concentrates several smaller groups. Phase 2 and Phase 3 use the same shared concentration helper. Broad hardware /
indirect exposure has a median effective member count of `1.0` and largest
normalized member share `1.0`. Storage has median effective member count
`4.53`, median largest share `0.30`, and median top-three share `0.70`.
Virtualization / cloud software has corresponding values `4.55`, `0.38`, and
`0.63`. Dates without eligible positive-weight members remain zero-count dates;
they are not replaced by equal weighting.

## 12. Largest changes

Prominent structure effects occur in Specialty metals, Power generation /
utilities, Electrical & power systems, Virtualization / cloud software, Power
generation and utility exposure, and Storage. Storage has the largest observed
absolute close difference at approximately 46.1%. The reported mechanical
causes are secondary-member deemphasis, WATCH_ONLY/TOO_SMALL removal,
primary-member concentration, missing-member renormalization, and, where
present, multi-route collision resolution.

## 13. Anomalies

No implementation anomaly, equal-baseline reproduction bug, or unexpected weighted chain discontinuity was found. The discontinuity count is `0`. The
run status is `OK`, with an empty anomaly list. This conclusion concerns the
comparison's technical integrity; the substantial economic and structure
differences are expected consequences to review, not calculation failures.

## 14. Evidence summary

The deterministic artifacts are under
`temp/datacenter_effective_weight_structure_validation/DC_TAXONOMY_FULL_V2_1_20250801_20260925/`:

- `summary.json`
- `group_summary.csv`
- `group_date_structure_comparison.csv`
- `event_comparison.csv`
- `largest_changes.csv`

Equal reproduction, shared-engine execution, deterministic event matching, and
fixture reruns support `NO TECHNICAL BLOCKER FOUND`. The final focused suite passed 123 tests; changed modules also passed `py_compile` and `git diff --check`. This is not a GO decision
for production publication.

## 15. Production actions not run

- No production `dc_*` table was rebuilt, overwritten, or published.
- No production `ec_*` table was refreshed or backfilled.
- No taxonomy or taxonomy version was changed or activated.
- No scheduler or report configuration was changed.
- No workflow persisted weighted production results.

Production data remains unchanged. All validation persistence was temporary or
under `temp/`.

## 16. Architecture questions

Before production planning, decide the new calculation-version identifier and
the atomic historical rebuild/publication boundary for `dc_*`. Define rollback
and DC/EC parity checks before projecting the generation to `ec_*`. Keep the
future generic EC calculation-authority migration and report migration separate
from this weighting rollout. Product review should explicitly accept the
observed BOS/RESET churn and concentration in small groups before any GO/STOP
decision.
