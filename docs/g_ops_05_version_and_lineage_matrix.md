# G-OPS-05 version, definition and lineage matrix

These are RawCandle contracts. They do not prescribe a DC dependency for StockCore.
Definition SHA-256/Git blob identities are in ignored
`temp/g_ops_05/definition_fingerprints.json`; per-image version metadata is in
`snapshot_states.json`. Calculation labels alone do not identify input vintage.

| Definition / event | Commit / implementation date | Effective production evidence | Meaning |
|---|---|---|---|
| Group index calculation | `b31ae6a5`, May 14, 2026; persistence `4c059540`, May 15 | Existing `DC_INDEX_CALC_V1` facts | Equal mean of eligible member close returns; deduplicated ticker sets for ecosystem/layer/subindustry; chained first valid level 100 |
| Fixed index anchor | `f1a58d63`, May 15 | Every reviewed image uses `BASE20200101` run IDs | Calculate from fixed 2020-01-01 rather than an implicit earliest available range, then select the write interval; calc tag remains V1. Exact original activation clock is not retained in the reviewed receipts; implementation date is not invented as one. |
| Synthetic V1 | `1831284f`, May 17; relative `6583e211`, structure `efcfed03` | Pre-September-27 images contain V1 only | Equal eligible-member OHLC returns, first valid chain level 100; volume is an unweighted sum |
| Weighting engine | `0d0938eb`, September 27; structure validation `31546a1c` | Shadow/rehearsal evidence, not an inferred production activation | Introduced canonical memberships and effective weights; intermediate source still defaulted to a V1 label |
| Explicit version separation | `dc3a1b26`, September 27 | Accepted migration after `53f752ce` timestamp and `e2e14113` watermark fixes; run `20260927T124208Z` | V1 explicitly equal; V2 explicitly weighted; unknown versions rejected. No accepted interim weighted-as-V1 activation was identified. |
| Weighted V2 activation | September 27 accepted migration receipts | Scheduler V1→V2; full V2 rebuild/projection Aug 1, 2025–Sep 25, 2026; 290 dates / 15,370 rows | DC and EC V2 accepted together, V1 preserved exactly |
| Explicit bridge version propagation | `fb9fb3e7`, October 3 | Accepted `20261003T135234Z` catchup / image `20261003T135514Z` | Fix selection ambiguity once V1/V2 coexist; no formula change |
| October 13–14 price inserts | Existing missing-day recovery receipts | 176 + 22 taxonomy tickers on Sep 22; 91 on June 30, 2023 | Input-vintage change, not a new taxonomy or calculation label |
| October 14 EC recovery | `logs/ec_recovery_20261014T094436Z.json` and recovery report | R1/R2/R3 PASS; EC Oct 6–13 accepted | Selected-range reconciliation; not a full historical re-projection |
| Latest accepted EC bridge | October 24 scheduler receipts | Oct 16–23; explicit V2; zero selected-date mismatches | Does not certify all earlier history |

The active EC taxonomy is ID **3**, `DC_TAXONOMY_FULL_V2_1`, persisted
`active_from=2026-08-06 10:27:04`, source hash
`2e27c6e68aa22c53c04e123f79744058b39a6a22b465634fda7510971c3159ef`.
All 24 images have the same active taxonomy identity. V1/V2 taxonomy records
are inactive; this task did not change them. Taxonomy version and OHLC calculation
version are separate dimensions.

## Exact synthetic weighting distinction

For an eligible ticker and OHLC component X, the input is
`r_i,X = X_i / previous_valid_ticker_close - 1`. After the first valid group row
anchored at 100, the group component is
`previous_valid_group_close * (1 + weighted_mean(r_i,X))`, with high/low expanded
to contain open/close. Zero positive total weight produces NO_DATA. Valid-chain
MA20/EMA20/volatility and BOS/reset structure follow the group series;
layer/subindustry pivot radii are 10/5. Relative OHLC20 instead applies the same
membership weighting to per-ticker OHLC/SMA20 ratios; it is not group OHLC divided
by a group SMA.

| Membership | V1 weight | V2 effective weight |
|---|---:|---:|
| Primary CORE/EXTENDED | 1 | 1 |
| Secondary layer CORE/EXTENDED | 1 | 0.25 |
| Secondary subindustry CORE/EXTENDED | 1 | 0.33 |
| WATCH_ONLY / TOO_SMALL | 1 | 0 |

Duplicate ticker/group routes collapse to the strongest canonical route; weights
are not added across duplicate routes. V2 uses the central policy derived from
`is_primary` and `report_group_status`, not an arbitrary CSV `role_weight` multiplier.
Volume remains the unweighted sum of eligible input volumes. Eligible count is a
count, not total economic weight. These details are existing definitions, not
changes introduced by G-OPS-05.

The group-index engine remains different: it builds deduplicated ticker sets and
uses `mean(eligible close returns)`, median/breadth measures, a chained equal index,
and 20/60/120-day return/volatility/benchmark statistics. It does not apply the
synthetic V2 membership policy. No group-index V2 tag was found in the reviewed
production images; the observed index-definition transition is fixed anchoring,
not evidence of a currently weighted index engine.

## What the 2,033 lineage differences mean

Every reproduced required-lineage difference is **source_run_id equality**:
1,007 synthetic rows and 1,026 index rows, exactly 53 + 54 records on each of the
19 dates. No missing `source_table`, source-PK/hash presence or missing-record
category contributes to this count. The original identifiers remain valid
source-vintage provenance in `ec_signal_run`; they are not missing mandatory IDs.

Current DC identifies
`DC_GROUP_SYNTH_OHLC_20250801_20261023_DC_SWING_OHLC_V2` and
`DC_INDEX_DC_TAXONOMY_FULL_V2_1_BASE20200101_20200101_20261023`.
Older EC rows identify migration/catchup runs ending September 25, October 2,
and subsequent dates. Rebuilding a DC range changes that run ID even when the
semantic values of a particular older date do not change. Of the 2,033 affected
group/date records, **883 have only lineage differences**; October 7–15 has no
semantic differences in the requested window.

Strict policy deliberately requires equality. Existing RSO policy relaxes
`source_run_id` only for group-signal and synthetic facts in its specific
revalidation workflow; it does not relax index provenance and cannot remove the
15,269 semantic differences. It was not substituted for strict acceptance here.
Thus lineage drift shares the full-rebuild/narrow-projection mechanism but is
not itself proof of V1/V2 mixing or an arithmetic defect.

Mismatches concern group records: Backup power is **EC entity_id 2 / GROUP_L1 /
BACKUP_POWER**; Datacenter ecosystem is **entity_id 1 / ECOSYSTEM / DATACENTER**.
Source keys use group names and dates; no canonical `security_id` exists in this
EC/DC fact contract. Ticker identities are not fabricated from group IDs. The
Backup power input insertion receipt identifies **CAT, CMI, GEV and GNRC**, raising
its Sep 22 eligibility from 5 to 9. No cross-ecosystem StockCore identity mapping
was performed.

The preserved V1 fingerprints match the accepted migration exactly:

- DC, 15,370 rows: `c9bc7e40154ba980fb76bb6659147515b585aba2ee4a2d709e3f9bce75720bd9`.
- EC, 15,370 rows: `4659a993031a5c178ed028a4274c298e21b0de548a6d85438e3cc2b65d06b6eb`.

They match image 5, image 24 and current production. Keeping an earlier full
image solely to preserve the old equal-weight definition is therefore unnecessary.
See [rebuildability](g_ops_05_ec_historical_parity_analysis.md) and
[retirement decisions](g_ops_05_backup_recovery_decisions.md).
