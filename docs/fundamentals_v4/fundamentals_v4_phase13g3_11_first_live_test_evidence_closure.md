# Phase 13G.3.11 First Live Test Evidence Closure

## 1. Purpose

Close the retention, deletion, publication-date, and Test-report evidence gaps before any first live Refresh Production decision. This phase did not run Production.

## 2. Accepted Preview/Test Basis

The original accepted basis was Preview `20260920T114505Z_refresh_fundamentals_81d416e6f45b` and Test `20260920T115023Z_refresh_fundamentals_eaf4b9d9de09_test`, fingerprint `7e3e0a06ce995203549ac93379a4273ce942f9576911d67d013f99a9353754c0`.

Because the first Test had already deleted its candidates and its structured artifacts did not expose every required payload/provenance counter or the BNC winner chain, final evidence uses fresh MANUAL Preview `20260920T122311Z_refresh_fundamentals_81d416e6f45b` and copy-only Test `20260920T122417Z_refresh_fundamentals_eaf4b9d9de09_test`. The fingerprint and all source-window counts remained unchanged.

## 3. Existing Test Artifact Audit

The original artifacts proved 98 retained keys, split 48 ARQ and 50 MRQ, through per-history counts and exact merged-generation fingerprints. They also proved five true-removal keys absent and recorded canonical/publication aggregates. They did not provide named payload mismatch, provenance validity, current-source marking, or duplicate counters, and the deleted candidate prevented a defensible reconstruction of those row-level facts. One fresh Test was therefore necessary.

## 4. Retention Candidate Validation

The new candidate proves retained expected/actual `98/98`, ARQ `48/48`, and MRQ `50/50`. All 98 rows exist with durable `RETAINED_OUTSIDE_SOURCE_WINDOW` provenance, unchanged true source identity, and payload equal to the previously accepted provider row. Payload mismatches, retained duplicates, and current-source rows incorrectly marked retained are all zero. Current source wins on overlap by the existing merge/validation contract.

BNED retained its 2017 Q1 pair: ARQ `2016-09-08 / 2016-07-30` and MRQ `2016-07-30 / 2016-07-30`. FLWS retained its 2016 Q4 52/53-week pair: ARQ `2016-09-16 / 2016-07-03` and MRQ `2016-07-03 / 2016-07-03`. ABM retained its 2016 Q3 pair. Their historical canonical quarters survive. BNED and ABM have canonical `+0/0/-0`; FLWS has only the normal new 2026 Q4 quarter, `+1/0/-0`. No retention-only financial or availability-date change was generated.

## 5. True Source Removal Validation

True-removal expected/absent is `5/5`:

| Ticker | Dimension | Date | Reportperiod | Fiscal identity | Reason |
| --- | --- | --- | --- | --- | --- |
| BNC | MRQ | 2024-06-30 | 2024-06-30 | 2024 Q2 | `INTERIOR_SOURCE_KEY_REMOVAL` |
| BNC | MRQ | 2024-09-30 | 2024-09-30 | 2024 Q3 | `INTERIOR_SOURCE_KEY_REMOVAL` |
| BNC | MRQ | 2024-12-31 | 2024-12-31 | 2024 Q4 | `INTERIOR_SOURCE_KEY_REMOVAL` |
| LOVE | MRQ | 2017-01-29 | 2017-01-29 | 2017 Q4 | `SAME_FISCAL_SOURCE_KEY_REPLACEMENT` |
| NAMS | ARQ | 2022-11-28 | 2022-06-30 | 2022 Q2 | `INTERIOR_SOURCE_KEY_REMOVAL` |

LOVE's candidate contains replacement MRQ key `2017-02-04 / 2017-02-04` for 2017 Q4 and loses no canonical quarter. NAMS retains alternate ARQ winner `2022-10-13 / 2022-06-30`; canonical 2022 Q2 survives with `first_public_result_date = 2022-10-13`.

## 6. BNC Deep Dive

BNC source deltas are added/changed/removed `5/6/3`; canonical deltas are `1/2/1`. The three removed keys are the 2024 MRQ rows listed above. Accepted ARQ winners still exist for 2024 Q2, Q3, and Q4, so those canonical quarters survive. Candidate MRQ replacements exist for 2024 Q2 (`2024-07-31`) and Q3 (`2024-10-31`); no 2024 Q4 MRQ replacement is needed because canonical authority is ARQ.

The disappearing stable quarter is 2026 Q1. Its prior `source_availability_date` and `first_public_result_date` are both `2026-06-23`. Production provider assigned ARQ key `date=2026-06-23, reportperiod=2026-04-30` to fiscalperiod `2026-Q1`. Current authoritative Sharadar assigns that same true source key to `2026-Q4`. Candidate MRQ also assigns reportperiod `2026-04-30` to `2026-Q4`. Consequently no ARQ or MRQ row remains for stable fiscal identity 2026 Q1; the canonical rebuild removes it. A new ARQ/MRQ fiscal 2027 Q1 pair for reportperiod `2026-07-31` creates the added quarter.

This proves a source fiscalperiod revision to the existing ARQ key, not the requested causal chain from one of the three true source-key removals. The prompt explicitly requires a stop if that chain is not defensible. Production is therefore not authorized by this closure.

## 7. Canonical Removal Reconciliation

Production baseline quarters are 88,835. Exactly BNC 2026 Q1 is absent from the candidate, leaving 88,834 surviving existing quarters. Canonical impact is 56 added, 192 changed, one removed, and 88,642 unchanged. Company/security identity mapping before candidate rebuild equals after candidate rebuild.

## 8. first_public_result_date Reconciliation

Preservation applicable/applied is `88,834/88,834`; repair required is zero. The removed BNC quarter is evidence-only and is not a preservation failure. Preview expected 56 new-quarter initializations; the candidate added 56 quarters and initialized 56 new `first_public_result_date` values under the existing policy. Historical bootstrap count remains zero.

## 9. Ticker Summary Reporting Fix

The summary renderer incorrectly read source `added_count`, `changed_count`, and `removed_count` while labelling the column `Canonical impact`. It now resolves the ticker's company identity into canonical `company_impact` and prints exact `quarters_added / quarters_changed / quarters_removed`, without the undefined `~` marker. Live evidence now shows BNC `+1 / 2 / -1`, NAMS `+0 / 1 / -0`, BNED `+0 / 0 / -0`, AI `+1 / 0 / -0`, GOSS `+0 / 32 / -0`, and LOVE `+1 / 2 / -0`.

## 10. Machine-Readable Evidence

`refresh_test_evidence.json` records all required deterministic summary counters, 98 lightweight retained-row records, five true-removal records, and event-driven representative source/canonical evidence. Production code selects evidence from generic source-history events; ticker-specific expected values remain tests and audit documentation only.

## 11. Test Rerun Decision

One rerun was required because the first candidate was correctly cleaned and its retained-row payload/provenance facts could not be reconstructed fully from aggregates. A fresh Preview was run first. Test source revalidation matched the bound fingerprint exactly; no stale authorization was reused.

## 12. Production Safety

Before and after Preview/Test, production file state was identical:

| Role | SHA-256 | Size | mtime_ns |
| --- | --- | ---: | ---: |
| provider | `b71dfbb0128a4e5404a18c608e31e16ec08c07b75bbe416e1a48a62112469468` | 958828544 | 1789831083995864659 |
| canonical | `bee62a677777be63ce67737d9e77d375f22dd044b6a7c9c834ccbe7b9f1684cf` | 655724544 | 1789893262044507282 |
| analysis | `969eb38504893b260206f07033a292b0587c16164720556f11d1b77e69b834f2` | 902062080 | 1789831394579542627 |

Production writes were zero. Refresh state remains `BOOTSTRAP_BASELINE`, published watermark remains null, and scheduler service/timer remained inactive.

## 13. Cleanup

The phase-owned Test lane `temp/20260920T122417Z_refresh_fundamentals_eaf4b9d9de09_test` is absent. No provider, canonical, or analysis candidate from this run remains. No production backup or publication journal was created. Lightweight JSON/Markdown run evidence remains under the Test artifact directory.

## 14. Tests

- Focused Refresh copy/retention/Preview set: 54 passed, 0 skipped, 0 failed.
- Remaining Fundamentals Admin, Refresh production fixtures, full workflow, scheduler/UI, and RV set: 484 passed, 0 skipped, 0 failed.
- Combined final-version regression: 538 passed, 0 skipped, 0 failed.
- `python3 -m py_compile` passed for touched Python modules.
- `git diff --check` is required before commit.

## 15. Production Readiness Recommendation

`NOT_READY_FOR_PRODUCTION`

All retention, true-removal absence, publication-date, identity, cleanup, and reporting checks pass. The blocker is narrow but material: BNC's canonical 2026 Q1 removal is caused by an ARQ fiscalperiod revision, not by the three observed MRQ true-removal keys. The requested causal chain is false, so an explicit domain decision on accepting that fiscal reclassification is required before Production review.

Refresh Production was NOT executed.

## 16. Git

Baseline: `6ef0f37 fix: classify refresh retention by fiscal boundary`. This phase changes only Refresh Test evidence/reporting code, focused tests, and this closure document. Live run artifacts and databases are not committed. Nothing is pushed.
