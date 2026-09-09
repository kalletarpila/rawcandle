# Phase 11F Company Snapshot V2 Presentation Freeze

## Outcome

Status: `PRESENTATION_V10_FROZEN_NO_ECONOMIC_CHANGE`.

Phase 11F corrects four final presentation defects and establishes a frozen,
versioned Company Snapshot V2 Markdown baseline. Report generation remains
read-only and never refreshes Relative Valuation.

## Corrections

1. Relative Valuation now separates the report date, persisted snapshot date,
   persisted company price date, and indicative report-price date. The peer
   heading is `Persisted peer comparison — snapshot YYYY-MM-DD`, the value
   column is `Snapshot-hintainen`, and the score label is
   `Snapshot-price Absolute Valuation Score`.
2. The old unconditional sentence
   `Nykyhintapersentiiliä ei lasketa eikä esitetä.` is removed. The indicative
   section now states that it does not rerank peers at the report price and
   points to the persisted comparison with its own snapshot and price dates.
3. Capex Intensity Shift's ratio difference and threshold are rendered as
   percentage points (`pp`). Its component intensity ratios remain percentages.
4. Own-History now shows the 40% / 40% / 20% formula, historical endpoint-price
   semantics, independent component eligibility, readiness rules, and limits
   the interpretation to relative cheapness. `Minimum positive observations`
   is replaced by `Smallest component history count`, alongside the applicable
   readiness requirement.

The explanatory text also states why changing only one company's price cannot
produce a coherent new peer percentile without rebuilding the peer snapshot.
No age or stale warning was introduced.

## Date Semantics

The four contexts are independent:

- report date: requested report context;
- Relative Valuation snapshot date: persisted calculation/as-of date;
- persisted company price date: selected company market observation inside
  that snapshot;
- indicative current-price date: report-selected market observation used only
  by the separate indicative valuation.

Peer companies use their own coherently selected prices in the same persisted
snapshot. Phase 11E latest-eligible, non-future selection remains unchanged.

## Diagnostic Units

The renderer has an explicit, tested flag-to-display-unit mapping covering all
eight active flags. Ordinary scaled ratios and yields use `%`; Capex Intensity
Shift and Recent Margin Deceleration differences use `pp`; monetary evidence
uses amount units; score changes use `p`; raw scores remain unitless points.

For Capex Intensity Shift, stored binary64 evidence, threshold `0.10`, inclusive
`>=` operator, status, reason and decision are unchanged. Only the rendered
semantic unit changed from `%` to `pp`, with the same multiplication by 100.

## Own-History Contract

```text
Own-History Valuation Percentile =
    40% * Operating Income / EV history percentile
  + 40% * FCF / Market Cap history percentile
  + 20% * Reported Common Earnings / Market Cap history percentile
```

The authoritative revised valuation history supplies each endpoint's market
cap and EV calculated from the market close selected on or before that
endpoint's availability date, with the locked three-calendar-day fallback.
The latest 20 eligible endpoints in the trailing five-year window are retained.
Each component independently accepts only observed, finite, strictly positive
yields. Missing, zero, negative, invalid and ineligible values are excluded,
not imputed as zero.

`READY` requires at least 12 accepted positive observations for every
component. `LIMITED_HISTORY` requires at least 8 for every component and 8–11
for at least one. No aggregate is emitted if any component has fewer than 8 or
its current yield is missing, nonfinite or nonpositive. A high percentile means
cheap relative to accepted positive history; it is not a discount percentage,
price-appreciation probability or forecast.

## Frozen Identity

| Identity | Phase 11E | Phase 11F frozen |
| --- | --- | --- |
| Presentation contract | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V9_RELATIVE_VALUATION` | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V10_RELATIVE_VALUATION_FROZEN` |
| Presentation fingerprint | `83f0a959a0b6dd3f03a4497955d3d0e94b687a870efcfa61672b8e5b4d20f6bf` | `d4e90e7ac75a5cfc76e87fa8855b9191485b3305193871396ca0776402fce9c0` |
| Snapshot economic fingerprint | `7b40558063684256474afa885e60e73d97f01fc01989ae9ffbcae34e74f4dd36` | unchanged |

The frozen contract material records the four date contexts, persisted
snapshot-price labels, flag semantic-unit mapping, visible Own-History method,
and frozen-baseline marker. Future behavior changes require a new explicit
presentation version. Structural and semantic tests protect headings, labels,
units and critical explanations without a brittle whole-file golden fixture.

Preserved production identities:

- Relative Valuation model:
  `76c2974108b2c5085b7dfa102acd4bb04eea36a5267bbdb1930a2bc7dc8cb35e`
- persistence/layout:
  `RELATIVE_VALUATION_CURRENT_SNAPSHOT_V1` /
  `9ffbfa6dd1ed86be3c5858607eb3284070d7a20285f0d46799cc198ba2a6d523`
- active snapshot:
  `b7f786edfa7632a320df5281182761471a15281ca1c518d2d729bbfab36dc5df`
- source/result/physical content:
  `ed787b5261a3e82f9737be6ec6920c3ee0d6a1737cfed4f643e43fb45b878ca6` /
  `3ab99303e4e9696aab0ad8fc5f40ea6f3879fb90e298ac6d3b6aab3928817f97` /
  `1431b72cd1bf744fd77dc7e0f976d4b001c95527451a3ff7c402511fe2acff61`
- active Operating-Income V2 package:
  `0e269e52a63500342df8a08ee2f91552fdc8fb216fa68cfe469bafb6aa8e3c30`

All economic model fingerprints, production rows, schemas, active pointers,
scores, percentiles, decisions and refresh behavior are unchanged.

## Examples

Temporary evidence is under:

```text
temp/fundamentals_v4_company_snapshot_phase11f/20260909T_phase11f_examples/
```

| Case | Purpose | Report-content fingerprint |
| --- | --- | --- |
| NVDA 2026-09-09 | real report/snapshot/price contexts; READY | `78e31ddedcb1e193d0ea261efa7945cae35f901cb3771685a0fb384cdb13c48a` |
| AA 2026-09-09 | LIMITED_HISTORY | `71f37fa1eafeda7055ccb4c5d464893fabef1e1b88c07ea2d018ce1844eb1db6` |
| ABG 2026-09-09 | unequal component counts 18 / 17 / 18 | `d5fcafd1d6fe2af0893d32a79257e8732ef9a8f796fa81050cb9e3f0ef937501` |
| AAOI 2026-09-09 | active Capex Intensity Shift | `81dac893ae28cf118d34ddce26a3d776556cabf53a51a433af4af1f2f1e5cba4` |
| NVDA 2026-09-07 | no eligible non-future snapshot | `127403b4e86d38e328d2fe3c54047bf435799f132510d62653663622429867d0` |

Repeated NVDA generation returned `NO_CHANGE` with the same content
fingerprint.

## Verification And Immutability

Verification results:

- focused Snapshot, Relative Valuation, Diagnostic, renderer, UI and isolation:
  302 passed;
- complete Fundamentals V4: 804 passed;
- Snapshot UI, Scheduler, security, download and production isolation:
  249 passed;
- `compileall` and `git diff --check`: passed.

The complete repository suite was not run because shared infrastructure did
not change and all required complete V4 and integration groups passed.

Preflight evidence is under
`temp/fundamentals_v4_company_snapshot_phase11f/20260909T_phase11f_preflight/`.
Matching final postflight evidence is under
`temp/fundamentals_v4_company_snapshot_phase11f/20260909T_phase11f_final_postflight/`.
Both returned `LOGICALLY_VERIFIED_CURRENT_BASELINE`. Every protected main
database SHA, schema hash, row count, logical fingerprint, active pointer and
package remained identical. The 16-file `fundamental_reports` aggregate stayed
`9ced540fc1aa5488daf5f635e5756cbcf2afd58119a244693d7af3fd09f13017`.
Read-only connections changed only the mtimes of two existing SHM sidecars;
their content and size remained unchanged. No production database or existing
production report was written.

## Deferred Upstream Contracts

Currency remains `N/A` without a validated source field and is never inferred.
Provider/canonical debt, lease treatment, shares source, and split semantics
remain deferred upstream contract work. Normalized earnings and new valuation
metrics are out of scope. Relative Valuation refresh remains a protected manual
full-universe operation with no Scheduler control.
