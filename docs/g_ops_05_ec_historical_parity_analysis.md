# G-OPS-05 EC rebuildability and historical parity

**Decision-phase result: COMPLETE. Propose retirement of 23 images, retaining one
existing full Analysis recovery image. No deletion, production repair or retention
policy change occurred.** The final user clarification makes whole-database
recovery, rather than eliminating historical parity differences, the storage gate.

Current RawCandle EC fact tables are DC projections. All 79,670 ticker, 16,491
group-signal, 31,800 synthetic and 16,491 index rows identify the corresponding
`dc_*` source table; no independently acquired EC observations were found.
The loaders deterministically map source keys/values through existing EC entity,
taxonomy and membership metadata. All intentionally unmapped diagnostic fields
are NULL. Rebuilding projections requires that metadata and applicable versions;
it must preserve V1 separately from V2 and does not authorize a publication.
Original entity IDs, watchlists, deployment decisions, audit/run clocks, historical
source-row hashes and publication controls are **not** replaceable by DC prices alone.
Fresh projection can generate valid new provenance; it cannot recreate every old
publication hash/clock from rewritten current DC rows. The retained
image and compact control-state export preserve them.

A fresh bounded recovery drill restored the existing latest image's EC scope,
replayed six dates using its DC sources, and matched **every current EC fact
payload and source-lineage value across all four complete tables**, excluding
new replay clocks. A separate base-prefix plus recorded 2,508-row tail comparison
also matched **all columns including original clocks**. Thus the current accepted
EC state can be recovered without keeping 23 older whole databases or performing
a live rebuild. Generating fresh historical projections from *current* DC would
produce a different vintage; that remains a separate acceptance decision.

The full Analysis image contains much more than EC. The selected retained image
also protects non-EC analysis, observations, research and control state. See the
[whole-database decisions](g_ops_05_backup_recovery_decisions.md); EC rebuildability
alone was not used to release it. StockCore was neither imported nor modified:
this dependency is specific to RawCandle's transitional implementation. Future
StockCore remains a generic multi-ecosystem EC model, with Datacenter as one
ecosystem and no dedicated DC-table architecture inferred from this investigation.

## Reproduction and version hypothesis

The original 25-date strict, explicit-V2 comparison reproduces exactly:

| Family | Semantic field differences | Required-lineage differences |
|---|---:|---:|
| Ticker | 0 | 0 |
| Group signal | 0 | 0 |
| Synthetic OHLC | 10,255 | 1,007 |
| Group index | 5,014 | 1,026 |
| **Total** | **15,269** | **2,033** |

The 19 dates are September **21,22,23,24,25,28,29,30**, October
**1,2,5,6,7,8,9,12,13,14,15**, 2026. Latest six dates
**October 16,19,20,21,22,23** pass. Coverage passes all 25 dates; it does not prove
semantic parity. These counts describe field comparisons, not 17,302 securities:
2,033 group/date records differ, of which 1,150 have semantic differences.
Exact keys/values are retained in ignored `temp/g_ops_05/exact_mismatches.json`.
Only the diagnostic output cap was increased; tolerance, keys and strict policy
were unchanged.

The user's methodology-transition hypothesis is confirmed historically, but it
must not conflate different comparisons:

- Synthetic V1 equal weighting changed to explicit weighted V2 on September 27.
  Both versions were published and retained separately. The V1 DC and EC complete
  15,370-row fingerprints still exactly match their accepted migration receipts
  in the first post-transition image, the latest image and live production.
- The 15,269 reproduced semantic differences compare **V2 against V2**, under the
  same active V2.1 taxonomy hash. They are not caused by selecting V1 on one side.
  The group-index comparison is `DC_INDEX_CALC_V1` on both sides, using the same
  `BASE20200101` convention. The actual index base-date transition predates every
  reviewed image. No weighted group-index V2 publication was identified.
- The September transition did expose a real bridge integration failure:
  September 29–October 2 calls omitted explicit OHLC version selection after two
  versions coexisted. They failed visibly; the October 3 propagation fix and
  accepted catchup closed that operational failure. This does not prove permanent
  parity with later source vintages, nor require keeping each failed pre-image.

Exact formulas, commits, activation evidence and lineage interpretation are in
the [version matrix](g_ops_05_version_and_lineage_matrix.md).

## Confirmed vintage evidence and its limits

The later source changes are established by existing local receipts, not new
provider acquisition. September 22 missing-day recovery inserted **176** active
Datacenter ticker observations on October 13, then **22** more on October 14.
The June 30, 2023 recovery inserted **91** active Datacenter ticker observations
on October 14. Those changes affect eligible returns, chained levels and rolling
history under an unchanged calculation definition.

The image sequence provides concrete boundaries:

| Fact | Before input recovery | After input recovery | Current EC historical value |
|---|---|---|---|
| Backup power, Sep 22, V2 eligible count | 5 | 9 | 5 |
| Same V2 synthetic open | 249.812472628538 | 247.2843943341193 | 249.812472628538 |
| Ecosystem Sep 21 index | 792.494027974008 | 789.4268184194938 | 792.494027974008 |

The synthetic transition is visible between images 15 and 16; the earlier-date
index-level transition appears between 16 and 17, after the June 2023 insert
receipt. V1/V2 labels and taxonomy identity do not change across these boundaries.
The V1 value for the same synthetic key is 227.09717301714056, distinct from both
V2 vintages. This rules out mistaking the old V2 value for a V1 projection.
Current EC historical semantics September 21–October 5 match the earlier DC
vintage in image 15; October 6 semantics match image 16, with zero semantic
mismatches in those paired comparisons.

The propagation mechanism is confirmed in current code and executed logs:
`analysis/datacenter_indices/swing_pipeline_orchestrator.py` rebuilds index history
from 2020-01-01 and synthetic base/relative/structure from 2025-08-01, while
`rawcandle/scheduler/runner.py` selects EC replacement using the narrower Stage 2
materialized interval. October 24 logs show full DC history replacement alongside
an EC interval of October 16–23. Older EC payloads remain accepted earlier source
vintages; head equality cannot establish history-wide synchronization.

This confirms different input/publication vintages and an incomplete historical
invalidation envelope. It does **not** independently re-prove every arithmetic
result or establish that the listed inserts are the sole cause of every numeric
change; other ordinary input revisions cannot be excluded without recreating
historical raw observations. No such exhaustive reconstruction was needed for
retirement, and no calculation definition or threshold was changed.

## Current-state conclusions

- **CURRENT_ACCEPTED:** active taxonomy V2.1, configured synthetic V2, four canonical
  fact/watermark heads through October 23, latest six-date parity and original
  acceptance receipts. Ticker/group-signal parity passes the entire requested
  25-date window. No current-window arithmetic defect was demonstrated.
- **HISTORICAL_VERSION_DIFFERENCE:** preserved V1 versus V2 is intentional and
  version-selectable. Required provenance also legitimately identifies different
  source-run vintages, although strict equality still fails.
- **HISTORICAL_REPAIR_REQUIRED, if current-history mirroring is required:** older
  same-version projections are stale relative to current DC inputs. Reconciliation
  should use the accepted DC sources and existing explicit-version loaders after
  separate authorization; changing formulas or weakening parity is unnecessary.
- **CURRENT_REPAIR_REQUIRED:** the historical dirty-range propagation gap requires
  a separately scoped integration decision if automatic historical synchronization
  is the intended contract. This finding is not permission to repair production.
- **UNRESOLVED:** full historical arithmetic certification and old raw-input
  counterfactuals. An earlier broader read-only guard also found pre-window group
  universe/lineage differences; these are recorded separately, not included in
  the 19-date counts, and were not expanded after the scope clarification.

Datacenter daily/rolling report readers use `dc_*` facts directly; these EC
historical differences do not feed those inspected DC report queries. No claim
is made about every possible historical EC consumer. The independent October 25
Fundamentals blocker remains unchanged: EC skipped, no catchup needed, no new
EC image. See [acceptance](g_ops_05_acceptance_evidence.md).
