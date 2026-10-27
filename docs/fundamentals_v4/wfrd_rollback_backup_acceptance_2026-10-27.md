# WFRD rollback backup acceptance — 2026-10-27

Task: WFRD-ROLLBACK-BACKUP-ACCEPTANCE-1. Stage 1 audit HEAD: `a9bac025c21ac986d822d09a0a6a4e837a6941ed`. Governing [Production report](wfrd_production_update_2026-10-27.md), documentation commit `a9bac025c21ac986d822d09a0a6a4e837a6941ed`.

**Stage 1 PASS. Exactly three backups are ACCEPTANCE_READY_DELETE_CANDIDATES, totaling 2,628,214,784 bytes. No deletion or acceptance operation has run. A new explicit cleanup YES/NO is required; the prior Production YES is not cleanup consent.** No source change or repository/full-suite pytest was performed.

## Successful Production and live health

| Gate | Fresh audit result |
| --- | --- |
| Production run | `20261027T184515Z_refresh_fundamentals_f3c7e2a627f5_production_72bba2f3` |
| Result | COMPLETED / SUCCESS_WITH_PUBLICATION_PARTIAL |
| Active NEW generation | `refresh_20261027T184515Z_refresh_fundamentals_f3c7e2a627f5_production_72bba2f3` |
| OLD generation | `refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`; retained separately |
| Canonical recovery journal | Exact selected Production run; COMPLETED / COMPLETED |
| Activation / postflight / recovery | ACTIVATED_AND_VERIFIED / PASSED / NOT_REQUIRED |
| Watermark | 2026-10-26 |
| Operations | Scheduler idle; normal Fundamentals/scheduler/Production exclusion locks acquired without contention; no preparing generation or active taxonomy operation |
| Active role files | All expected NEW paths exist; quick_check ok and zero FK errors for provider/canonical/analysis |
| Manifest consistency | Active and NEW generation manifests equal the journal's published manifest; all three live role SHA-256 values match recorded verification and journal candidate fingerprints |
| Current authority | Active generation, exact journal, role/manifest/queue hashes and WFRD bindings still match successful Production closeout; no superseding publication/recovery state |

The audit held normal operation/Production/scheduler guards, and the normal taxonomy read guard while validating V2/RP/RV. `validate_rebuild()` ran read-only against the active analysis, current NEW provider/canonical, current read-only market/taxonomy sources, and the published as-of date. Package physical integrity, active readers, RP date/taxonomy dependency, RV source/result fingerprints, and snapshot readers passed. RP `c9152b1f63cd2efb4bddee0de67149df7d635283f0ae69e968045fc45d0d41ba` and RV `99e8d0da082ad9bc6d5b614aaa8d149d99091232c606d2ce79906cbc9916f69d` match the successfully published snapshots. This was validation only, with no rebuild or new Production operation.

## WFRD, review, and publication-authority verification

The exact approved decision is installed in NEW and matches the unchanged live APPROVED queue item, with no stale/rejection reason. Existing expected-store verification and independent published checks pass:

| Invariant | Live result |
| --- | --- |
| ARQ `(WFRD, ARQ, 2020-03-16, 2019-12-31)` | Native raw 2020-Q4; reviewed effective 2019-Q4; exact approved resolution linkage |
| Genuine 2020 Q4 | Separate `(WFRD, ARQ, 2021-02-19, 2020-12-31)`; effective 2020-Q4; independent source/winner |
| Historical MRQ Dec 31 | Exact accepted evidence archived in NEW, HISTORICAL_ONLY / SUCCESSOR_YEAR_END_STOCKS / calculation=false; absent from current/native history |
| Current MRQ Dec 13 | PREDECESSOR / PARTIAL_PERIOD_FLOW; calculation/full-quarter/canonical/TTM/P/B/share/stock-fallback=false; no hybrid/null filling |
| Canonical 2019 Q4 | End 2019-12-31; first-public/availability 2020-03-16 |
| Canonical 2020 Q4 | End 2020-12-31; first-public/availability 2021-02-19 |
| Parent-equity/P/B/share | ARQ authority, raw/effective 2019 reviewed binding and genuine 2020 independence; 327 ARQ financial provenance rows; zero MRQ authority |
| Existing WFRD financial projections | All 27 pre-existing quarters preserved against OLD; current quarter/date/share/P/B projection matches saved Test evidence |
| WFRD Review Queue | APPROVED, exact decision unchanged, no stale/rejection reason |
| DHR P/B Review Queue | OPEN; approval=null; no operator approval |

All **131 exact processed publication-authority keys** were checked against their current rows in active NEW canonical: **81 VERIFIED, 16 UNRESOLVED, 4 AMBIGUOUS, 30 NOT_FOUND**. The stored PARTIAL result remains separate from successful core Production. No resolution, retry, enrichment, or drain was invoked. Normal follow-up reads current canonical quarter/authority data and normal external source evidence; it does not consume OLD rollback copies. The current records and Production report remain in NEW/run artifacts, and the reviewed historical MRQ evidence remains in NEW provider. Deleting the three backup copies would remove none of those records or the retained OLD generation.

## Exact eligible backup inventory and provenance

Selection uses the exact Production `result.json` backup manifest, embedded and canonical terminal journal, recorded verified backup hashes/sizes, terminal retained-backup report, and OLD-generation role paths. Filename/age similarity is not selection authority. All three are regular nonsymlink files in the exact run-owned directory, with role-specific filenames; device/inode/link count/mtime/ctime and filesystem creation timestamps were captured for later revalidation.

| Role | Exact selected path | Fresh bytes | Filesystem creation timestamp |
| --- | --- | --- | --- |
| analysis | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/20261027T184515Z_refresh_fundamentals_f3c7e2a627f5_production_72bba2f3/analysis.db` | 910,512,128 | 2026-10-27 21:05:55.618163616 +0200 |
| canonical | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/20261027T184515Z_refresh_fundamentals_f3c7e2a627f5_production_72bba2f3/canonical.db` | 749,371,392 | 2026-10-27 21:05:53.170170946 +0200 |
| provider | `/home/kalle/projects/rawcandle/backups/fundamentals_admin_production/20261027T184515Z_refresh_fundamentals_f3c7e2a627f5_production_72bba2f3/provider.db` | 968,331,264 | 2026-10-27 21:05:50.643120393 +0200 |

| Role | Verified backup SHA-256 | Separately verified OLD source SHA-256 |
| --- | --- | --- |
| analysis | `492d437dcbd979039f8cdd863187ac36e1f1c0ddd543b3564b156e901e998708` | `e984fe99df5a3683e76ad9fe9a3dd5c6f55f87d530ef7ca0a30ac5cbb9436adf` |
| canonical | `e922eac780ec91fb2edc29e64879a17dd0cb5c81649b737f0dfcbe3235529c51` | `02a13632b45008734ff6078e4e8ba717778bc261471febae504908f951c66b6b` |
| provider | `dbe53b90af540322babb3196c104b2e125c966aa9c4a28517d261293e1df88d5` | `cadd3a90f40e0320558b7a6e4de14deb06c77373b9cf3ed81fbb22d26d69dac8` |

Each backup's bytes match the Production result and journal's **verified backup** SHA-256, and each source path/hash matches its retained OLD authority. Backup quick_check and FK checks pass. The recorded snapshot method is `SQLITE_ONLINE_BACKUP`: source and backup physical hashes differ, as allowed by that method; physical equality is not required by the cleanup contract. An initial temporary diagnostic incorrectly imposed that equality and stopped before any cleanup. The audit was corrected to use recorded backup hashes and separate OLD-source lineage; repository source was not changed, and all authoritative gates were rerun successfully.

The existing public inspector and UI inspection both recognize this exact set as **ELIGIBLE / ADMIN_PRODUCTION_APPLY**, count **3**, bytes **2,628,214,784**. These measured values matched the expected aggregate, not an age-based target. No prior completed cleanup evidence exists.

`acceptance_scope.json` binds all three accepted file identities/hashes, the successful result's file hash, live authority hashes, scheduler config, and cleanup mechanism source fingerprints. Its scope fingerprint is `5c4e302235b7e369e39b5530265c71f6a18bbb790fd17a05a7ed6457b18acf2b`; each selected record is classified ACCEPTANCE_READY_DELETE_CANDIDATES. Stage 2 must compare against that exact scope before deletion.

## Recovery independence and existing cleanup mechanism

The canonical recovery journal is exact, terminal and clean, with no pending recovery step. The verified active authorities are NEW; selected backup paths are distinct from both NEW and retained OLD generation paths. Normal operation/scheduler/Production guards exclude an in-use normal publication, recovery, or cleanup operation. There is no nonterminal canonical recovery reference requiring the selected files. Historical result/journal snapshots are audit evidence rather than an independent pending recovery authority. All other retained backup sets remain outside selection.

Source reviewed: `rawcandle/fundamentals/admin/run_acceptance_cleanup.py` and the UI entry in `ui_service.py`, with normal lock/journal behavior in `production_transaction.py` and `publication_journal.py`. Stage 1 called only `inspect_cleanup_eligibility()`/UI eligibility and read-only validators; it did not call either acceptance/deletion function.

The existing public `accept_run_and_cleanup_backups()` owns deletion under the normal Production/scheduler lock; the UI entry also takes the Fundamentals operation lock. It reconstructs only the selected run's canonical manifest, rejects invalid/symlinked/unowned paths, binds OLD sources for generation publication, refuses nonterminal/recovery-required state, verifies every selected backup hash and integrity plus live role integrity **before the first unlink**, and rereads run/journal evidence immediately before deletion. It processes the three-role selection in one acceptance invocation; individual filesystem unlinks are sequential. It removes only those files, removes their directory only if empty, and writes surviving audit evidence at `fundamental_reports/admin_runs/20261027T184515Z_refresh_fundamentals_f3c7e2a627f5_production_72bba2f3/backup_cleanup.json`. It does not delete OLD/NEW generation files, other backup directories, Review Queue records, or publication-authority evidence.

Stage 2 must additionally revalidate this exact accepted run/generation and captured file identities under the normal exclusion guards immediately before invoking the existing mechanism. Any material active-generation/journal/recovery/provenance/eligibility change invalidates consent. On a cleanup exception or partial result, stop under the existing failure behavior, record actual remaining files, and do not manually finish with `rm` or broaden the selection. No cleanup source/contract defect requiring an implementation phase was found in this exact-run audit.

## Collateral inventory — KEEP

The bounded inventory covered only `backups/fundamentals_admin_production`: **32 files** total, comprising **3 DELETE_CANDIDATE**, **11 KEEP_OLDER_RETAINED_BACKUP**, and **18 KEEP_AMBIGUOUS_OR_LEGACY_UNRELATED**. There are no selected active/recovery-required files; unselected older/ambiguous files were not granted deletion eligibility. No full disk-usage backlog was scanned.

| Other directory under the Fundamentals backup root | Files | Count / bytes | Classification |
| --- | --- | --- | --- |
| `20260918T182639Z_check_update_taxonomy_293c901ce1dd_production_12a72eb2` | analysis.db | 1 / 1,582,403,584 | KEEP_OLDER_RETAINED_BACKUP |
| `20260919T113359Z_add_tickers_8bbcda32e218_production_38f7bfac` | analysis.db, canonical.db, provider.db | 3 / 2,492,153,856 | KEEP_OLDER_RETAINED_BACKUP |
| `20260919T151515Z_add_tickers_b99c78e6879b_production_53c729c1` | analysis.db, canonical.db, provider.db | 3 / 2,503,581,696 | KEEP_OLDER_RETAINED_BACKUP |
| `20260919T_phase13g25f_final_v2_publication` | analysis.db | 1 / 892,256,256 | KEEP_OLDER_RETAINED_BACKUP |
| `20260926T163001Z_first_public_result_date_bootstrap_production` | analysis.db, canonical.db, provider.db | 3 / 2,545,537,024 | KEEP_OLDER_RETAINED_BACKUP |
| `pb_quarterly_ownership_v2_20261008T080025Z` | analysis.db, canonical.db, provider.db | 3 / 2,628,182,016 | KEEP_AMBIGUOUS_OR_LEGACY_UNRELATED |
| `pb_reporting_20261007T193505Z` | analysis.db, canonical.db, provider.db | 3 / 2,553,917,440 | KEEP_AMBIGUOUS_OR_LEGACY_UNRELATED |
| `publication_drain_20261005T064921Z_43a1e040` | analysis.db, canonical.db, provider.db | 3 / 2,553,729,024 | KEEP_AMBIGUOUS_OR_LEGACY_UNRELATED |
| `publication_drain_20261006T110330Z_2d836e37` | analysis.db, canonical.db, provider.db | 3 / 2,553,741,312 | KEEP_AMBIGUOUS_OR_LEGACY_UNRELATED |
| `publication_drain_20261006T150551Z_9cfd3ca0` | analysis.db, canonical.db, provider.db | 3 / 2,553,880,576 | KEEP_AMBIGUOUS_OR_LEGACY_UNRELATED |
| `publication_drain_20261007T093516Z_fd654a20` | analysis.db, canonical.db, provider.db | 3 / 2,553,917,440 | KEEP_AMBIGUOUS_OR_LEGACY_UNRELATED |

Twenty-five unrelated existing temp lanes under `temp/fundamentals_admin_phase13g1` were separately inventoried as KEEP_UNRELATED_TEMP_LANE; they are outside the cleanup mechanism's backup-root/run manifest. The selected directory contains exactly the three accepted role files and no extra file. Full path/file identity inventory is retained in the evidence JSON. Before/after collateral inventory is identical; nothing was deleted or moved.

## Invariance, evidence, and pending gate

Before/after checks show active provider/canonical/analysis hashes, active/generation manifests, journal, watermark, WFRD Q4/date/P/B/share provenance, all live queue schemas/tables/decisions, and scheduler configuration unchanged. The queue remains byte-identical to Production closeout; DHR is still OPEN and WFRD remains APPROVED. Publication-authority rows and scope remain unchanged. No backup deletion, new Production, Preview/Test, review approval, taxonomy edit, scheduler change, or publication drain occurred. All guards were released before presenting the question.

Runtime evidence directory: `/tmp/wfrd_backup_acceptance_stage1_verified`. Records include fresh baseline/health, WFRD and V2/RP/RV validation, exact backup identities/hashes/creation times, eligibility, recovery/mechanism source fingerprints, collateral/temp inventory, 131-case publication-authority audit, final invariance, readiness summary, and phase record. The initial diagnostic-only stop is preserved separately under `/tmp/wfrd_backup_acceptance_stage1`. Runtime files and DBs are excluded from Git; only this report is committed, with no push.

**Cleanup readiness: ACCEPTANCE_READY_DELETE_CANDIDATES. Deletion performed: NO.** Sections K–L of the request require stopping here for a new explicit cleanup answer.

Do you approve deletion of the exact three rollback backups retained from successful Production run 20261027T184515Z_refresh_fundamentals_f3c7e2a627f5_production_72bba2f3, corresponding only to the OLD provider/canonical/analysis authorities and totaling the freshly revalidated 2,628,214,784 bytes, using the existing locked rollback-backup cleanup mechanism? YES/NO

YES authorizes only these exact three backup copies. It authorizes no other backup/temp deletion, OLD/NEW generation deletion, publication-authority cleanup/drain, review approval, or new Production run. If active generation, journal, recovery state, exact backup identity/provenance, or eligibility changes before deletion, consent is stale and cleanup must STOP. Post-YES revalidation, cleanup execution, deleted count/bytes and final invariance remain pending.

Branch closeout recommendation: finish this exact acceptance gate first; preserve all unrelated worktree/runtime changes and keep the branch unpushed. No broader storage cleanup or branch merge is authorized by this audit.
