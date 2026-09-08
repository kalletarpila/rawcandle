# Phase 11C Relative Valuation Persistence Rehearsal

## Outcome

`REHEARSED_NOT_DEPLOYED`. The final rehearsal used as-of `2026-09-08` under
`temp/fundamentals_v4_phase11c/20260908T163000Z/`. Production schemas,
databases, active package pointers, reports, and UI behavior were not changed.

The source fingerprint is
`ed787b5261a3e82f9737be6ec6920c3ee0d6a1737cfed4f643e43fb45b878ca6`
and result fingerprint is
`3ab99303e4e9696aab0ad8fc5f40ea6f3879fb90e298ac6d3b6aab3928817f97`.
Both exactly equal Phase 11B.

## Coverage And Rows

The source contains 2,448 complete-current companies, 2,431 current-fresh
companies, 2,245 current peer-eligible companies, and 2,234 same-anchor
filing/current pairs. Current-fresh own history contains 874 `READY` and 124
`LIMITED_HISTORY` companies. The broader calculable count is 875; the sole
additional company is HUBG, endpoint 2025 Q3, availability date 2025-11-05,
and age 307 days. HUBG is persisted with `current_fresh=0` and cannot enter the
current-fresh or peer-eligible counts.

One active snapshot contains 2,448 company rows, 9,792 peer rows, 2,448
own-history rows, and 7,344 component rows. Thus every company has exactly four
peer statuses and three component evidence rows, including unavailable cases.

## Rehearsal Results

Fresh and upgraded production-shaped schemas have the same 11-object logical
signature. The first apply activated snapshot
`b7f786edfa7632a320df5281182761471a15281ca1c518d2d729bbfab36dc5df`
with physical fingerprint
`1431b72cd1bf744fd77dc7e0f976d4b001c95527451a3ff7c402511fe2acff61`.
Calculation took 6.98 seconds and write/reconciliation took 1.37 seconds.

The independent second apply was `NO_CHANGE`: zero inserts, updates, deletes,
pointer changes, audit rows, database growth, journal growth, and WAL growth.
Nine failure points all raised and preserved the reopened active snapshot.
Date-only cases produced `NO_CHANGE`, bounded `DATE_ONLY_NO_CHANGE`, and a new
activated snapshot when staleness changed results, respectively.

Six genuinely different full snapshots retained only active plus previous.
The retention database grew from 6.02 MB to 11.73 MB for two snapshots, reached
17.33 MB while replacing the third, and then stayed exactly 17.33 MB through
snapshots four to six while freelist pages were reused. No `VACUUM` was used.
The first production-copy apply increased the main file by 5,738,496 bytes.
Observed rollback-journal peak was 63,032 bytes; WAL remained zero.

Measured one-snapshot object allocation was about 5.75 MB including indexes:
company 651,264 bytes, peer 1,798,144 bytes, peer index 1,040,384 bytes,
own history 438,272 bytes, components 1,830,912 bytes, and small metadata,
pointer, audit, and snapshot objects of one page each.

Reader timings were 0.50 ms for one company, 1.86 ms for 20 companies, 9.85 ms
for the 2,448-row universe, and 5.71 ms for the 2,245-row universe peer group.
All 15 persisted candidate reports were byte-identical to pure-engine reports,
including NVDA, AMZN, GOOG, CRMD, APD, PLTR, CLS, VRT, and HUBG.

Deep validation returned SQLite `quick_check=ok`, zero foreign-key violations,
one active snapshot, no orphans or duplicate logical rows, exact cardinalities,
and exact peer, component, aggregate, physical, source, and result
reconciliation.

## Verification And Production Immutability

The focused Phase 11C persistence suite passed 16/16 tests. The complete
Fundamentals V4 collection passed 794/794 tests, and Python bytecode compilation
completed without errors. The full-suite command was
`PYTHONPATH=. pytest -qq tests/test_fundamentals_v4_*.py`.

Independent preflight and postflight production audits both returned
`LOGICALLY_VERIFIED_CURRENT_BASELINE`. Their normalized protected-database
inventories have the same SHA-256,
`a44cd5cd89851af3535f0d4717ba39abe8892692d6fb4b9f87d86202f4aaacca`,
covering main/WAL hashes and sizes, schema hashes, row counts, and logical
fingerprints. Their production-invariant manifests also have the same SHA-256,
`2631eeeabe299d940c9048516dbe4f0ecda55693117fb9a85a52dd6a5c4c1ee0`.
The active package remained
`0e269e52a63500342df8a08ee2f91552fdc8fb216fa68cfe469bafb6aa8e3c30`,
and the aggregate production-report fingerprint remained
`d95ff084174fc3b60ca533f75f6a55325d48479e242a55fd5a5b0d25a7886ad1`.
The production analysis schema contains zero Phase 11C objects. No production
report was generated, overwritten, or published.

## Evidence

The machine-readable summary is
`temp/fundamentals_v4_phase11c/20260908T163000Z/rehearsal/phase11c_rehearsal_summary.json`.
Storage, reader latency, failure injection, fresh/upgraded databases, and 15
candidate Markdown reports are in the same rehearsal directory. These are
temporary, untracked evidence artifacts.

Postflight production-audit evidence is under
`temp/fundamentals_v4_phase11c/20260908T163000Z/postflight/`. The matching
preflight evidence is under
`temp/fundamentals_v4_phase11c/20260908T160217Z/preflight/`.
