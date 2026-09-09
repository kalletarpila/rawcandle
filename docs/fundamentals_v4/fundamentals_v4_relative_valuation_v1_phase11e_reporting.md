# Phase 11E Latest Eligible Relative Valuation Reporting

## Outcome

Status: `REPORT_SELECTION_CORRECTED_NO_PRODUCTION_DATA_CHANGE`.

Company Snapshot V2 now uses the latest eligible persisted Relative Valuation
snapshot. A report dated after the active snapshot no longer hides valid
Relative Valuation merely because the dates differ. The report displays the
persisted snapshot's actual date and keeps it separate from the report date and
the report's descriptive current-price valuation.

Relative Valuation refresh remains a separate protected manual full-universe
operation. Report generation, UI opening, listing and download remain read-only
with respect to databases and never invoke the Relative Valuation engine or
writer.

## Root Cause And Selection

Phase 11D's `generate_active_company_snapshot()` required
`active_snapshot.as_of_date == report_date`. This correctly prevented mixed
dates but unnecessarily made every later report unavailable.

Phase 11E replaces that gate with these deterministic rules:

1. Validate the active pointer, complete status, model, persistence, and layout.
2. If active `as_of_date <= report_date`, use the active complete snapshot.
3. If the active snapshot is newer than the report date, use the newest retained
   complete snapshot with `as_of_date <= report_date` and the same exact model,
   persistence, and layout.
4. If none exists, render
   `RELATIVE_VALUATION_NO_ELIGIBLE_NON_FUTURE_SNAPSHOT`.
5. If the company is absent, render
   `RELATIVE_VALUATION_COMPANY_NOT_IN_SNAPSHOT`.
6. Invalid pointer/metadata/contract renders
   `RELATIVE_VALUATION_SNAPSHOT_INVALID`.

Selection passes the chosen `snapshot_id` explicitly through company, all four
peer, own-history, and all three component reads. Rows from different snapshots
cannot be mixed. No age threshold is applied. Existing readiness, peer
eligibility, peer-group-too-small, missing/nonpositive yield, limited history,
and `current_fresh` states are preserved as persisted.

## Context Separation

The report labels `Report date` and `Relative Valuation snapshot date`
separately. The Relative Valuation table retains its own persisted price date,
score, peer population, and own-history window. It does not claim that ranks
were recalculated using a newer report price. The existing descriptive current
valuation, filing valuation, exact-Q-1 valuation, and filing-date Relative
Position keep their own established dates and semantics.

## Identity Changes

Only Company Snapshot selection and presentation identities changed:

| Identity | Before Phase 11E | Phase 11E |
|---|---|---|
| Snapshot contract | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_RELATIVE_VALUATION_V1` | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_RELATIVE_VALUATION_V2` |
| Snapshot fingerprint | `a688cb7f1637126bb354d179cd12610d891073a10f0692a9a83830c3f6b12391` | `7b40558063684256474afa885e60e73d97f01fc01989ae9ffbcae34e74f4dd36` |
| Presentation contract | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V8_RELATIVE_VALUATION` | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V9_RELATIVE_VALUATION` |
| Presentation fingerprint | `e1eecc4d12942470236ecc3ae7a885eb8f562de8b401a774f27efc7f439d6738` | `83f0a959a0b6dd3f03a4497955d3d0e94b687a870efcfa61672b8e5b4d20f6bf` |

Preserved identities:

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
- active Operating-Income package:
  `0e269e52a63500342df8a08ee2f91552fdc8fb216fa68cfe469bafb6aa8e3c30`

Score, Lifecycle, Absolute Valuation, Delta, Relative Position, Diagnostic
Flags, retention, schema, persisted rows, and active pointer are unchanged.

## Examples

Examples and structured summary are under:

```text
temp/fundamentals_v4_relative_valuation_phase11e/20260908T_examples/
```

| Case | Report date | Selected RV date | Result |
|---|---|---|---|
| NVDA | 2026-09-12 | 2026-09-08 | `READY`; repeated generation `NO_CHANGE` |
| AA | 2026-09-12 | 2026-09-08 | `LIMITED_HISTORY`; industry peer group remains too small |
| HUBG | 2026-09-12 | 2026-09-08 | `current_fresh=false`; current valuation remains not ready |
| NVDA historical | 2026-09-07 | none | explicit no-eligible-non-future status |

The NVDA report shows the unchanged persisted score `24.1504198443976` and
price date `2026-09-04` even though the report date is `2026-09-12`. This proves
the later report context does not recalculate or relabel persisted peer ranks.
Synthetic tests additionally prove that a newer descriptive report price is
preserved separately while Relative Valuation continues to use its selected
snapshot's score and price.

## Verification And Immutability

- focused reader/Snapshot/UI/isolation group: 115 passed in 41.78 seconds
- complete Fundamentals V4 group: 802 passed in 104.21 seconds
- Scheduler, Snapshot UI, secure download, and production isolation: 249 passed
  in 16.98 seconds
- `compileall` and `git diff --check`: passed

The complete repository suite was not run because no shared infrastructure was
changed and all required targeted, complete V4, UI, Scheduler, download, and
isolation groups passed.

Preflight and postflight evidence is under
`temp/fundamentals_v4_relative_valuation_phase11e/`. Every protected main
database SHA, schema hash, row count, logical fingerprint, active package, and
the 15-file production-report aggregate remained identical. The report
aggregate remains
`d95ff084174fc3b60ca533f75f6a55325d48479e242a55fd5a5b0d25a7886ad1`.
Read-only connections changed only the mtimes of two existing SHM sidecars;
their sizes and SHA-256 content remained unchanged. No production database,
schema, pointer, row, package, or existing report was written.

## Remaining Limitation

Relative Valuation changes only after the separately authorized protected
manual full-universe refresh documented in the Phase 11D runbook. Active plus
previous retention means sufficiently old historical report dates may
legitimately have no eligible non-future snapshot. No Scheduler refresh control
was added.

## Phase 11F Supersession

Phase 11F supersedes only the Phase 11E presentation identity and wording with
the frozen V10 report contract. Phase 11E snapshot-selection behavior and all
economic and persisted identities remain unchanged. See
`fundamentals_v4_company_snapshot_v2_phase11f_presentation_freeze.md`.
