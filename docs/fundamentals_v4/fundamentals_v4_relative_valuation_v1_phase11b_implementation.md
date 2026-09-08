# Phase 11B Relative Valuation V1 Implementation

## Outcome

`OUTCOME: IMPLEMENTED AND REHEARSED, NOT DEPLOYED`

The exact rehearsal as-of date is **2026-09-08**. Phase 11B added a pure engine,
read-only adapters, deterministic full-universe rehearsal, and an explicit
candidate Company Snapshot path. It did not alter production schemas,
databases, active package pointers, published reports, or default UI behavior.

## Delivered code

- `rawcandle/fundamentals/relative_valuation/engine.py`: current valuation,
  peer ranking, independent component histories, readiness, and serialization.
- `rawcandle/fundamentals/relative_valuation/source.py`: guarded read-only V2,
  canonical TTM, market, classification, taxonomy, filing valuation, and filing
  peer adapters.
- `rawcandle/fundamentals/relative_valuation/rehearsal.py`: dual replay and
  independent reconciliations.
- `rawcandle/fundamentals/relative_valuation/candidate_snapshot.py`: explicit
  candidate assembly over the unchanged active Snapshot V2 assembler.
- `rawcandle/fundamentals/snapshot/renderer.py`: renders Relative Valuation only
  when the candidate contract and candidate payload are supplied.

Public calculation entry points are `calculate_current_price_valuation`,
`select_history`, `historical_percentile`, `calculate_own_history`, and
`calculate_relative_valuation`. Database rows do not enter these pure APIs.

## Identities

| Artifact | Version | Fingerprint |
| --- | --- | --- |
| Relative Valuation | `CURRENTLY_REVISED_RELATIVE_VALUATION_V1` | `76c2974108b2c5085b7dfa102acd4bb04eea36a5267bbdb1930a2bc7dc8cb35e` |
| Candidate Snapshot | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_RELATIVE_VALUATION_V1_CANDIDATE` | `ddb41f5b99e5acdb39b80cf2c999692d566ea3486849e6d9732df28ba00b4c82` |
| Candidate presentation | `CURRENT_REVISED_COMPANY_SNAPSHOT_V2_PRESENTATION_V8_RELATIVE_VALUATION_CANDIDATE` | `089ba37fd2870f601ef417fa9c3d6afeda5aca1e143e6755aa9a3457b6d377e3` |

The active package remained
`0e269e52a63500342df8a08ee2f91552fdc8fb216fa68cfe469bafb6aa8e3c30`.

## Rehearsal evidence

Artifacts are under:

`temp/fundamentals_v4_phase11b/20260908T131104Z/`

Dual full-universe runs were byte-identical:

| Fingerprint | Value |
| --- | --- |
| Source | `ed787b5261a3e82f9737be6ec6920c3ee0d6a1737cfed4f643e43fb45b878ca6` |
| Result | `3ab99303e4e9696aab0ad8fc5f40ea6f3879fb90e298ac6d3b6aab3928817f97` |
| Serialized bytes SHA-256 | `0ab524e2b705606babb79dad363aed0a9e7d42ebafbb0e927a961ab6de0022da` |

The authoritative current-price adapter matched all eight Phase 11A parity
companies. All 6,939 active Absolute Valuation filing-peer rows reconciled with
the V2 engine at their active snapshot date, 2026-09-06. Every one of 4,699
independently recomputed component or aggregate values matched within `1e-12`.

## Coverage

| Cohort | Companies |
| --- | ---: |
| `COMPLETE_CURRENT` | 2,448 |
| `CURRENT_FRESH` | 2,431 |
| Current peer eligible | 2,245 |
| Same-anchor filing/current full pairs | 2,234 |
| `OWN_HISTORY_READY`, current fresh | 874 |
| `OWN_HISTORY_LIMITED`, current fresh | 124 |
| `OWN_HISTORY_READY`, economically calculable broader cohort | 875 |

Current ready peer coverage was 2,245 universe, 2,235 sector, 1,945 industry,
and 201 ecosystem results. No cohort fallback was used. The ecosystem count is
one above the Phase 11A ad hoc research table: the production taxonomy identity
contract maps `GOOGL` memberships to the same company as current ticker `GOOG`,
then deduplicates its two `DATACENTER` memberships. Phase 11A's exact-ticker
research join omitted that company. V1 intentionally follows the established
identity and taxonomy contract required by the specification.

Current-fresh own-history statuses were: 874 `READY`, 124 `LIMITED_HISTORY`,
131 `INSUFFICIENT_HISTORY`, 1,116 `CURRENT_YIELD_NOT_COMPARABLE`, 48
`CURRENT_VALUATION_NOT_READY`, and 138 `NOT_APPLICABLE`.

Component history statuses, excluding current-not-ready and not-applicable
rows, were:

| Component | Ready | Limited | Insufficient | Current nonpositive |
| --- | ---: | ---: | ---: | ---: |
| Operating yield | 1,145 | 109 | 112 | 879 |
| FCF yield | 1,164 | 137 | 127 | 817 |
| Reported Common Earnings yield | 1,035 | 111 | 159 | 940 |

## The 874/875 reconciliation

The broader count contains exactly one company not present in the current-fresh
count: `HUBG`, endpoint 2025 Q3, available 2025-11-05. At 2026-09-08 its
fundamental endpoint was 307 days old, so it failed the 180-day `CURRENT_FRESH`
condition. Its current price was nevertheless valid on 2026-09-04 (age four
days), all current yields were economically calculable, and its minimum positive
component-history count was 15. Therefore it is `OWN_HISTORY_READY` only in the
broader economically calculable research cohort. The model was not changed to
force the counts to agree.

## Candidate reports

Fourteen Markdown reports are in
`temp/fundamentals_v4_phase11b/20260908T131104Z/rehearsal/candidate_reports/`:
NVDA, AMZN, GOOG, CRMD, APD, PLTR, CLS, VRT, AAOI, BBWI, O, AVB, ALAB, and AA.
Together they cover required score extremes, applicability/readiness cases,
limited and insufficient histories, component-only evidence, and ecosystem
membership/non-membership. Existing report sections and terminology remain.
No file under `fundamental_reports` was regenerated.

## Design decisions and limitations

The three dimensions remain separate: Absolute Valuation, current peer
percentile, and own-history percentile. The combined-score approach was
rejected because it would conceal distinct evidence, introduce unsupported
cross-dimension weighting, and obscure unavailable components.

The history is revised economic history. It does not preserve what was known at
each historical date, and current sector, industry, and taxonomy memberships
are not PIT-versioned. Results must not be described as a PIT backtest.

The active 2026-09-06 filing-peer snapshot and the 2026-09-08 latest-filing
research context differ for `LFCR`: the latter has a later fiscal row with no
availability date and `VALUATION_NOT_READY`. Reconciliation correctly uses the
active snapshot's dated source set; candidate reporting retains the explicit
latest-filing not-ready state.

## Recommended Phase 11C scope

Phase 11C should add only versioned current-snapshot persistence for:

1. one package/snapshot identity and source/result fingerprints;
2. one company-level current valuation and aggregate own-history result;
3. four peer result/coverage rows per company;
4. three component evidence rows per company, including independent counts,
   spans, median, percentile, status, and reason;
5. atomic full-universe write, validation, reader API, and explicit activation;
6. protected-path rehearsal on a copy before any separately authorized
   production deployment.

It should not persist daily cross-sections, change any economic rule, merge the
three valuation dimensions, or activate the candidate report by implication.

## Production immutability

Preflight and postflight both returned `LOGICALLY_VERIFIED_CURRENT_BASELINE`.
All protected main-file hashes, sizes, mtimes, schema hashes, row counts,
`quick_check` results, foreign-key results, the active package, and the 15-file
production report aggregate remained equal. SQLite read locking changed only
the mtimes of byte-identical sidecars: the empty `analysis.db-wal`, the 32 KiB
`analysis.db-shm`, and the byte-identical `ecosystem_dashboard.db-shm`. Their
sizes and SHA-256 values were unchanged. No provider, market, canonical, or
production report update was run.
