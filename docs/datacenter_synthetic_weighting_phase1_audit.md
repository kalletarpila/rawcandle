# Datacenter synthetic weighting Phase 1 audit

## 1. Git / repository state

- Audit baseline HEAD: `f72289bf28070859618fc5b6803579de2af11ea7`.
- Initial worktree state contained two unrelated untracked files:
  `data/.fundamentals_admin_publication_journal.json` and
  `docs/fundamentals_v4/fundamentals_v4_phase13g3_48_live_publication_date_bootstrap.md`.
- No relevant implementation file was modified. The dirty worktree does not make
  this audit unreliable.

## 2. Current taxonomy source and membership semantics

The active scheduler configuration names
`data/datacenter_taxonomy_full_v2_1.csv` and
`DC_TAXONOMY_FULL_V2_1` (`scheduler_config.json:13-14`). The calculation itself
does not hard-code that file: the pipeline passes its configured `taxonomy_csv`
through `--taxonomy-csv`
(`analysis/datacenter_indices/swing_pipeline_orchestrator.py:1173-1190`), the CLI
passes it to `persist_datacenter_group_synthetic_ohlc`
(`run_datacenter_group_synthetic_ohlc.py:79-93`), and
`_load_taxonomy_rows` calls `load_datacenter_taxonomy_csv`
(`analysis/datacenter_indices/swing_group_synthetic_ohlc.py:214-215`).

The loader requires and parses all eight CSV fields: `taxonomy_version`,
`ticker`, `layer`, `subindustry`, `report_group_status`, `is_primary`,
`role_weight`, and `notes`
(`analysis/datacenter_indices/taxonomy.py:8-17,45-135`). The synthetic group
builder uses only `ticker`, `layer`, and `subindustry`
(`swing_group_synthetic_ohlc.py:218-236`). Rows are processed separately by
`taxonomy_version`.

The current synthetic path builds layer and subindustry groups only. The separate
`analysis/datacenter_indices/calculator.py` also builds an ecosystem group, but
it is not the producer of `dc_group_synthetic_ohlc_daily`.

## 3. Current synthetic OHLC algorithm

`_build_group_definitions` creates both layer and subindustry definitions using
the same shape, and `build_group_synthetic_ohlc_rows` sends both through the same
loop and aggregation (`swing_group_synthetic_ohlc.py:218-236,449-566`).

For each ticker, `_build_ticker_daily_inputs` creates daily open/high/low/close
returns relative to the ticker's previous non-null close. A date is eligible only
when all four current OHLC values exist, a previous non-null close exists, and
that previous close is non-zero. Volume is not required
(`swing_group_synthetic_ohlc.py:288-320`).

For each group/date:

- `member_count` is the number of unique taxonomy tickers in the group.
- `eligible_count` is the number of members with a daily synthetic input.
- Each OHLC return is the arithmetic mean over eligible members, so the current
  calculation is genuinely equal-weight among that day's eligible tickers.
- The first eligible group row in the requested range is anchored to
  O=H=L=C=100; its constituent returns are not applied.
- Later O/H/L/C values are the previous valid synthetic close multiplied by one
  plus the corresponding mean constituent return.
- High is clamped to at least max(open, close), and low to at most
  min(open, close).
- A zero-eligible date produces null OHLC and leaves the chain anchor unchanged.
  The next valid date chains from the preceding valid synthetic close.

See `swing_group_synthetic_ohlc.py:455-498`. Missing OHLC therefore changes both
eligibility and aggregate magnitude: remaining eligible members are renormalized
to `1 / eligible_count`.

MA20 and EMA20 are calculated from valid synthetic closes. Volatility is the
population standard deviation of the last 20 valid synthetic close-to-close
returns (`swing_group_synthetic_ohlc.py:496-529`).

## 4. Current status handling

`report_group_status` is validated against CORE, EXTENDED, WATCH_ONLY, and
TOO_SMALL, but is not consulted by group construction, eligibility, or
aggregation (`taxonomy.py:19-24,79-82`;
`swing_group_synthetic_ohlc.py:218-236`). Consequently all four statuses
contribute equally when price-eligible. The active V2.1 file has 230 CORE, 106
EXTENDED, 14 WATCH_ONLY, and no TOO_SMALL rows.

A group containing only secondary members or only WATCH_ONLY/TOO_SMALL members is
still built and calculated normally. A group with no taxonomy members cannot be
created by the current builder. A created group with zero price-eligible members
gets null synthetic values and `NO_DATA`.

## 5. Multi-membership / duplicate behavior

Secondary rows are included. `is_primary` is parsed and validated but ignored,
so primary and secondary memberships are equal contributors.

The taxonomy loader rejects only an exact
`(taxonomy_version, ticker, layer, subindustry)` duplicate
(`taxonomy.py:59-60,116-122`). It permits one ticker to reach the same layer
through multiple subindustries, or the same subindustry through multiple layers.
`_build_group_definitions` canonicalizes both maps with `set[str]`, effectively
deduplicating `(ticker, group_type, group_name)` before calculation. Thus a
ticker cannot contribute twice to one calculated group, but canonicalization is
implicit and discards the membership metadata needed for weighting.

In active V2.1, a read-only CSV check found 18 duplicated canonical keys (19 rows
beyond one-per-key), all observed at layer level; for example ETN reaches
`Electrical & power systems` three times. Multiple subindustry memberships
within one layer therefore become one layer contribution, while each distinct
subindustry receives its own contribution.

## 6. `role_weight` current semantics and usage

The CSV loader converts the value with `float()`, rejects values `<= 0`, and
stores it on `DatacenterTaxonomyRow` (`taxonomy.py:95-104,124-133`). It does
not explicitly reject non-finite floats. The synthetic
calculation never reads it. The active V2.1 taxonomy has `role_weight=1.0` on all
350 rows.

Outside calculation it is persisted into taxonomy membership data and compared
as a computational taxonomy-change field. No observed code establishes a
numerical return-weighting meaning. Phase 2 V1 should therefore exclude
`role_weight`: multiplying by an unestablished field would couple the new
policy to metadata whose present values carry no differentiation.

## 7. `synthetic_volume` semantics

`synthetic_volume` is the unweighted sum of non-null raw volumes among that
date's OHLC-eligible group members. It is null when none of those eligible inputs
has volume (`swing_group_synthetic_ohlc.py:493-494`). It is neither averaged,
normalized, chain-linked, nor used as an OHLC weight. Phase 2 should leave this
calculation unchanged.

## 8. Downstream lineage

The base builder calculates the chain-linked OHLC, then MA20, EMA20,
distance-to-EMA20, and volatility from that synthetic close series.

Relative OHLC is an important exception to a simple base-series lineage.
`build_group_relative_ohlc_updates` rebuilds the same taxonomy groups, derives
each ticker's OHLC divided by its own rolling close SMA, and independently takes
equal-weight means over eligible tickers. It requires a matching base row only as
the update target; it does not derive relative values from synthetic OHLC
(`swing_group_synthetic_ohlc.py:671-827`). It must use the same future effective
membership policy to avoid internally inconsistent base and relative fields.

`build_group_structure_updates` reads the already-persisted synthetic high, low,
and close series. It detects pivots, labels successive highs HH/LH and lows
HL/LL, derives trend classification, records BOS crossings, and resets after two
same-direction BOS events (`swing_group_synthetic_ohlc.py:963-1238`). These
stages need no weighting-specific logic; rebuilding their inputs is sufficient.

## 9. `dc_* -> ec_*` projection contract

The relevant mappings are:

- `dc_group_swing_signal_daily -> ec_group_signal_daily`
- `dc_group_synthetic_ohlc_daily -> ec_group_synthetic_ohlc_daily`
- `dc_group_index_daily -> ec_group_index_daily`

For synthetic OHLC, the producer is
`load_ec_group_synthetic_ohlc_daily_from_dc` in
`rawcandle/ec_group_synthetic_ohlc_daily_loader.py:621`. It selects one exact
`ohlc_date + taxonomy_version + calc_version` scope, resolves each DC
`group_type/group_name` to an EC entity, and inserts the row under
`ecosystem_id`, `taxonomy_version_id`, `signal_date`, `entity_id`, and
`ohlc_calc_version`.

This is a transformed, near-lossless projection, not an independent
calculation. Counts, OHLCV, MA/EMA/volatility, structure, BOS/RESET, relative
fields, quality status, and source run are copied; dates and several structure
field names are renamed. `latest_structure_date`, `structure_state`, and two
relative-strength target fields are intentionally null because no DC source
column maps to them (`ec_group_synthetic_ohlc_daily_loader.py:29-86,485-618`).
Lineage adds `source_table`, canonical source-PK JSON, source-row hash, and
`source_run_id`.

A DC rebuild does not automatically update EC. The explicit EC source-layer
refresh invokes the loader with `replace_existing=True`
(`rawcandle/cli/run_ec_source_layer_refresh.py:387-401`). Backfill/build paths
invoke the same loader for their selected scopes. Therefore changing historical
DC rows requires the matching EC refresh/backfill; otherwise DC can be weighted
while EC retains an older equal-weight projection. The current scheduler is
configured for `refresh_latest` and `only_on_new_signal_date=true`, so an
in-place same-date DC rewrite especially needs an explicit EC replacement.

The loader validates source taxonomy/calc scope, null and duplicate source keys,
one-to-one entity resolution, and duplicate/null target keys. The separate
`rawcandle/ec_dc_fact_parity_audit.py:_synthetic_ohlc_parity` compares group
keys, all material synthetic/relative/structure values with numeric tolerance,
and lineage (`ec_dc_fact_parity_audit.py:850-922`).

## 10. Current rolling-report source boundary

`analysis/datacenter_indices/swing_daily_report.py:_load_synthetic_rows` reads
precomputed rows directly from `dc_group_synthetic_ohlc_daily` for the selected
date/taxonomy/calc version (`swing_daily_report.py:1137-1157`).
`analysis/datacenter_indices/swing_weekly_report.py:load_weekly_swing_report_data`
loads the same table for its selected date window
(`swing_weekly_report.py:571-660`). Neither report rebuilds group membership,
OHLC, or weights. A future weighting change requires regenerated facts, not
report-code changes.

## 11. Identified risks / ambiguities

- Relative OHLC has a separate constituent aggregation and will remain
  equal-weight unless Phase 2 routes it through the centralized policy too.
- Implicit set deduplication loses primary/secondary and status metadata before
  aggregation; weighting cannot be safely inserted after the current
  `_build_group_definitions` output.
- When only zero-weight memberships are price-eligible, preserved
  `eligible_count` can be non-zero while eligible effective weight is zero.
  Phase 2 must explicitly emit null OHLC and `NO_DATA` for that case.
- The first eligible row is always anchored at 100. Weighting does not affect
  that row's OHLC, only subsequent returns and its volume.
- The current calculation range defines the chain anchor. Reweighting a partial
  range without sufficient rebuild scope can create a series inconsistent with
  previously persisted history.
- EC synchronization is operational, not automatic or transactionally coupled
  to the DC rebuild.
- `role_weight` is marked computational in taxonomy change planning but has no
  established calculation semantics.

## 12. Recommended implementation boundary for Phase 2

1. Introduce an ecosystem-neutral membership record/helper outside the DC
   persistence/CLI layer. Expand each taxonomy row into layer and subindustry
   memberships, then canonicalize by
   `(ticker, group_type, group_name)` before aggregation.
2. Resolve collisions deterministically. A canonical key may combine multiple
   taxonomy rows; Phase 2 must define precedence rather than silently summing
   duplicate routes. For the proposed policy, take the maximum effective weight
   across routes: this makes primary CORE/EXTENDED dominate secondary
   CORE/EXTENDED, while any included route dominates a zero-weight route.
3. Centralize one pure effective-weight function parameterized by group type,
   primary flag, and report status. V1 returns the proposed 1.00/0.33
   subindustry and 1.00/0.25 layer weights, with WATCH_ONLY and TOO_SMALL at
   zero. Do not multiply by `role_weight` in V1.
4. On each date, keep current price eligibility rules, then normalize positive
   effective weights by their eligible sum. Compute each OHLC return as
   `sum(return * effective_weight) / sum(effective_weight)`. Missing members
   redistribute weight only among positive-weight eligible members.
5. Preserve `member_count` as unique canonical taxonomy tickers and
   `eligible_count` as unique canonical members satisfying current daily price
   eligibility, including zero-weight statuses. Track eligible-weight sum
   internally; if it is zero, emit null OHLC and `NO_DATA`.
6. Keep `synthetic_volume` as the current unweighted sum over price-eligible
   members, independent of effective weight.
7. Reuse the same canonical memberships and policy in base and relative OHLC.
   Leave MA/EMA/volatility, structure/BOS/RESET, report readers, and EC schema
   free of weighting-specific logic.
8. Rebuild DC base, relative, and structure over a chain-safe range, then run the
   existing EC refresh/backfill for the same dates and finish with DC/EC parity
   validation.

The smallest safe insertion point is before the per-date loops: replace the
ticker-only `_build_group_definitions` result with canonical weighted membership
objects, and call one daily weighted-mean helper from both
`build_group_synthetic_ohlc_rows` and
`build_group_relative_ohlc_updates`.

## 13. Exact files/symbols likely to change next

- New ecosystem-neutral helper module under `analysis/`: canonical membership
  model, collision resolution, effective-weight policy, and weighted mean.
- `analysis/datacenter_indices/swing_group_synthetic_ohlc.py`:
  `_build_group_definitions`, `build_group_synthetic_ohlc_rows`, and
  `build_group_relative_ohlc_updates`.
- `tests/test_datacenter_group_synthetic_ohlc.py`: primary/secondary,
  status-zeroing, canonical duplicate, daily renormalization, zero-weight,
  relative parity, count, chain, and volume contracts.
- A focused test module for the new ecosystem-neutral helper.
- `rawcandle/ec_group_synthetic_ohlc_daily_loader.py` should not need weighting
  logic; its existing tests and `rawcandle/ec_dc_fact_parity_audit.py` should be
  run to prove projection parity.
- Daily/weekly report modules should not change.
