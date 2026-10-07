# P/B.8 — Controlled production rollout of parent equity and reviewed P/B

**Production rollout completed on 2026-10-07.** Current P/B is **1722 / 2468 (69.77309562%)**; Provider P/B is available for **2133**, with four valid accepted history slots for **2081** companies. The reviewed releases are exactly **31: 16 ordinary/common, six exact ADS factors and nine direct-common identity overrides**. No ownership mass release or source change was made.

Old active generation: **publication_drain_20261007T093516Z_fd654a20**. New active generation: **pb_reporting_20261007T193505Z**. Implementation commit **454a32e669ea4a19cffd6758bfdb44fd5b675324** remained unchanged through preflight, candidate preparation, activation and postflight. Only this report and its two compact CSVs are committed in the rollout phase.

## Mandatory Date and Review Gate

The registry is exactly the committed `PB_OWNERSHIP_BASIS_V1` artifact, SHA-256 **`0baaf493afa2faa52c2179a2353fb9089d834ef2bcb91f6e088e58f1bae068bf`**. Before writes, under locks, before preparation and immediately before atomic activation the operator verified actual UTC time and **Europe/Helsinki** calendar date. Final activation gate: **2026-10-07T22:37:18.383291+03:00** / **2026-10-07T19:37:18.383291+00:00**. Calculation as-of was **2026-10-07**.

All **63** registry records covered the date, including **31 supported releases**; stale/expired records **zero**, stale supported releases **zero**. No effective intervals were extended and no review evidence was copied forward. Reviews remain bounded to **October 7 only**. Later report as-of dates fail closed for these reviewed releases unless a separately authorized evidence refresh, **P/B.8A — Refresh Reviewed Ownership Evidence Through Current As-Of**, establishes new valid records. Parent equity and Provider P/B schema remain deployed; this rollout does not create perpetual reviewed ownership eligibility.

## Preflight

Active manifest format, directory and role paths resolved through `resolve_active_generation(require_generation=True)`. The source role SHA-256 values exactly matched active manifest verification. All three role quick_checks were **ok**, FK errors **zero**, and source immutable files had no WAL/SHM/journal sidecars. The previous Administration publication journal was **COMPLETED**, postflight **PASSED**, with no recovery pending. No automatic recovery was needed.

There were no unexpected source/test modifications. Existing runtime journal/active-generation data and the unrelated research plot files were recognized as pre-existing worktree state and excluded from the docs commit. Production and scheduler locks were available; normal `production_lock` held both throughout the operation, followed by the existing taxonomy-operation lock in the prescribed order. No Fundamentals writer or scheduler could acquire those locks while preparation/publication/postflight was running.

Free disk at preflight: **570,112,253,952 bytes**, above the conservative **10,215,669,760-byte** requirement for inactive preparation, verified rollback backups and retained generation. Source inventory captured row counts for every role table and schema fingerprints, plus 17 real snapshot fingerprints. Scheduler config and Review Queue physical guards and market/taxonomy input file stats were retained. An additional read-only logical Review Queue digest included committed WAL content across its three tables and remained identical across candidate preparation and activation; no Queue operation was performed.

Active manifest SHA-256 before: **`b2e38e8e1b286a88ad8a777cb9c9db04c66a0446af1d974fa3564119fb2a0f92`**. After: **`730b93fec46c3d4ed37b8340d7ec5ce6b2106dd42c64141c18d37ca045664eb8`**. Manifest change is the intentional generation-pointer publication, not a manual patch.

## Normal Inactive Preparation and Publication Path

A temporary operator script called the **existing** production orchestration APIs; no new source module or publisher was added. The sequence was the same immutable-generation path used by Administration publication maintenance:

1. Read-only source checks, normal production/scheduler/taxonomy locks and `guard_production_writes` on a terminal journal.
2. Complete three-role inactive candidate copies from the current source generation.
3. Existing `migrate_parent_equity` on the inactive canonical candidate, reading unchanged provider evidence.
4. Whole-universe and representative report rehearsal, content/score/provenance/schema checks.
5. Existing `_verified_backups(..., immutable_generation=True)` and `_candidate_manifest`.
6. Existing `prepare_journal(publication_mode='GENERATION_POINTER')` and `prepare_generation_from_candidates`.
7. A second final gate after candidate filesystem finalization: old source/manifest unchanged, candidate hashes stable, source/registry unchanged, guards stable and review date valid under held locks.
8. Existing `activate_prepared_generation`, which calls verified `activate_generation` and its atomic manifest switch.
9. Production postflight and normal terminal journal update to **COMPLETED / PASSED / NOT_REQUIRED**.

The canonical candidate contains `parent_equity`, `parent_equity_usd`, `v4_parent_equity_provenance` and `v4_parent_equity_source`. Migration bound **89,912 accepted quarters**, promoting **171,304 finite parent-equity values**, exactly matching P/B.7. Every bound source is **ARQ**, matches accepted shares provenance and has the original provider observation content hash. No richer MRQ/ART/MRT row, TTM aggregation, alternate quarter or common-equity relabeling was used. The preferred-capital exclusion caveat remains explicit.

Every pre-existing canonical table and every old financial column retained identical logical SHA-256. Identity/fiscal mappings, publication authority, score-bearing inputs and prior provenance were unchanged. Provider and analysis candidate files were byte-identical to source, so no score regeneration/calibration, provider acquisition or 6-K/publication-authority refresh was required. The only canonical changes are additive parent fields and their dedicated accepted provenance/source projection.

## Verification and Invariance

| Role | Source SHA-256 | Activated SHA-256 | Validation |
|---|---|---|---|
| analysis | `a8dcc37e1a0e2442dd44023b63d8c6ba91ee5fdce3ab05e2fa5407413a0355ce` | `a8dcc37e1a0e2442dd44023b63d8c6ba91ee5fdce3ab05e2fa5407413a0355ce` | quick_check ok; FK errors 0 |
| canonical | `9656dc5523c282b7243390c79913264f7614a99ba951f0b172059d8c16f3e16b` | `f1bfcfcb9c03c23dcce0c1186243c14a2f7a375fb48271cc9d14bd857cfa37d8` | quick_check ok; FK errors 0 |
| provider | `2b3a57add8b51413d98f220d4cdd313994d1a4079f987a94796bf6a2b6db5fbb` | `2b3a57add8b51413d98f220d4cdd313994d1a4079f987a94796bf6a2b6db5fbb` | quick_check ok; FK errors 0 |


Source canonical schema fingerprint: **`6bad24b24c16b7079913cb2590d9c9e2f3e8fbf170960fe4e33e992da6b8cba2`**. Activated candidate schema fingerprint: **`d0cdb27f40dbe7e34cd0cbb30172011dbc044a814a032b9f90c77189a3582456`**. Complete row-count/schema inventories and original canonical logical digests are retained in the runtime result; no DBs or raw runtime files are committed.

All **2,468 candidate P/B objects** matched the validated P/B.7 objects exactly, including current value/reason/warnings/ownership metadata, original Provider reference and 4Q history. The newly valid company/observation set matches the prior 31 evidence-backed releases; remaining original ownership population is **378**. All **2,468 postflight P/B objects** then matched the candidate again.

Provider-reference arithmetic was independently checked for all **2,133 available latest references**, each from original ARQ source. Maximum absolute residual **0.0004999145035178**, below **0.0005001**. History retains at most four accepted fiscal-quarter slots, observed dates and explicit unavailable slots; no interpolation, richer-dimension substitution or PIT claim. Valid-history distribution: **4: 2,081; 3: 50; 2: 36; 1: 25; 0: 276**.

Seventeen complete snapshots were compared from source to candidate; all non-P/B fields matched exactly, including Fundamental Score, Valuation Score, model versions/fingerprints, relative-position outputs, financial/valuation history, existing valuation multiples and reconciliations. Repeated candidate assembly was deterministic. After activation, the same normal active-generation reporting path produced identical candidate snapshots and successful Markdown rendering for all 17; ownership metadata and share-source dates appear only for supported reviewed ownership. Provider history remains visible when Current P/B is unavailable.

| Ticker | All non-P/B snapshot fields SHA-256 before = after |
|---|---|
| AAPL | `ff1e72496a52734ed3c7bca6d2e50abadf88fdaa9dbf9a6c5e7cc2bdf0bf5c4e` |
| NVDA | `e79cc32baeddb6d2ca6a85036fcae3aa3e582237fe10d89b9e6fbcc292dff887` |
| MSFT | `fde606668deef62ddc6aa94b74d8cfd842ed0d536f28bafd511e60833ccc9aca` |
| CAT | `b1324a314ff9ad93cd2fd2e918f84a1db51de53c2d3c380a589fb1e89244ad42` |
| XOM | `d7f6c0cfdb6e8044cc19cb127e2e5450f0dc0f061fbdfe6507265a0eb8cbb032` |
| MCD | `79a27a58768d1342a82c06a9ee61a6e82cbc52973b3bddaa2d156438962ea01a` |
| BA | `79e8b12e82ef193388c3d2107a2d40b4324edaaa9f281b916b3e0f6f94cd3355` |
| PSA | `a09b33b4c41f7647c1624c125a06e891482e8a04dc757b53122533bbbf09de5c` |
| GPCR | `126154a2d82d8a576c259c1ce7d76cc819c7e1a404ba1ba9fd66a2ffbc5d3fc2` |
| ONC | `580c266aa46af3ef8a7304e6361f599e6e03e538eab4e0755fcc65957aaec269` |
| SCNI | `545871c0624ae044138c45fabab98ec468b59e3ddc1cfe113a3ca55311f88de0` |
| ARM | `f9ae81da4231147d15e1346e684c31877107e6cee7495096256a757e00b4e33a` |
| CAMT | `d1380e90a59c91b70e92cf522693f8d5eebf417602d51fca43985e62025319f0` |
| BABA | `91924f1102cdbe0298402c73ad5d6930611847a9f0497811b5be66ad9333b3f0` |
| BIDU | `248d7368f0f11a06ba149e7b7d05ad52ab3bcb108d9c51f01caf00b367ba310d` |
| KALA | `06810ad68eca148b665694a91e9fd937599cf7013a41db92e685874a4d761298` |
| FTFT | `bba0e75b9abd730bb9698fc1abcfecc59db758357fcccce09efc4f048d41ce7f` |


Aggregate analysis SHA-256 is unchanged, providing a whole-file check of all score/model/calibration/relative/history state, beyond the representative snapshots. Scheduler configuration and auxiliary market/taxonomy inputs stayed unchanged; Review Queue physical and logical guards passed. Publication authority is included in the unchanged canonical table digests. No scheduler or reporting code was edited.

## Production Coverage

| Current P/B hard reason | Count |
|---|---:|
| MISSING_EQUITY | 120 |
| MISSING_PRICE | 10 |
| MULTI_CLASS_UNVERIFIED | 16 |
| NEGATIVE_EQUITY | 215 |
| NEWER_SHARE_COUNT_REQUIRED | 7 |
| OK | 1722 |
| OWNERSHIP_BASIS_UNVERIFIED | 355 |
| SHARE_BASIS_UNVERIFIED | 5 |
| STALE_EQUITY | 6 |
| STALE_PRICE | 12 |

All other hard reasons, including OWNERSHIP_REVIEW_STALE, are **zero** for this as-of. Ownership population partitions into **355 default ownership holds, 16 multi-class holds and seven newer-share-count holds**, total **378**; 355 is not the entire residual cohort. The Current-versus-Provider gap is **411**, comprising **378 ownership**, **28 price/freshness** and **five other hard share-basis holds**. Provider availability is not entitlement to Current P/B.

| Warning | All reports | Valid Current P/B |
|---|---:|---:|
| HISTORICAL_OHLC_INCOMPLETE | 58 | 41 |
| HISTORICAL_PRICE_CORROBORATION_UNAVAILABLE | 20 | 0 |
| HISTORICAL_PRICE_MISMATCH | 13 | 0 |
| LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE | 145 | 57 |
| NEAR_ZERO_EQUITY | 1 | 1 |
| REVIEWED_UNRESOLVED_BASIS | 2 | 0 |

Warnings remained diagnostics; no EPS-average difference, missing historical witness or incomplete historical OHLC warning became an unexpected hard gate. Demonstrated historical price/basis conflicts and bounded unresolved reviews remain hard holds. Current quote remains latest complete positive valid OHLC on/before as-of with a maximum three-calendar-day fallback.

| Ticker | Current P/B | Reason | Provider P/B | Valid history / slots | Ownership | Share source | Price date |
|---|---:|---|---:|---:|---|---|---|
| AAPL | 45.28512225 | OK | 41.93000000 | 4 / 4 | — | — | 2026-10-06 |
| NVDA | 25.17941923 | OK | 22.06600000 | 4 / 4 | — | — | 2026-10-06 |
| MSFT | 8.88439565 | OK | 6.55500000 | 4 / 4 | — | — | 2026-10-06 |
| CAT | 20.46517930 | OK | 20.64600000 | 4 / 4 | — | — | 2026-10-06 |
| XOM | 2.60747653 | OK | 2.45800000 | 4 / 4 | — | — | 2026-10-06 |
| MCD | N/A | NEGATIVE_EQUITY | N/A | 0 / 4 | — | — | 2026-10-06 |
| BA | 24.59476115 | OK | 28.70700000 | 3 / 4 | ORDINARY_COMMON | 2026-07-21 | 2026-10-06 |
| PSA | 5.46243447 | OK | 6.29500000 | 4 / 4 | ORDINARY_COMMON | 2026-07-21 | 2026-10-06 |
| GPCR | 1.44630534 | OK | 2.77000000 | 4 / 4 | ADR_FACTOR | 2026-07-31 | 2026-10-06 |
| ONC | 7.97231984 | OK | 7.19600000 | 4 / 4 | ADR_FACTOR | 2026-07-31 | 2026-10-06 |
| SCNI | 0.05927609 | OK | 0.13900000 | 4 / 4 | ADR_FACTOR | 2026-06-30 | 2026-10-06 |
| ARM | 37.44311441 | OK | 27.83100000 | 4 / 4 | ADR_FACTOR | 2026-05-21 | 2026-10-06 |
| CAMT | 10.15621329 | OK | 10.39000000 | 4 / 4 | IDENTITY_OVERRIDE | 2026-08-10 | 2026-10-06 |
| BABA | N/A | NEWER_SHARE_COUNT_REQUIRED | 1.95000000 | 4 / 4 | HELD | 2026-08-20 | 2026-10-06 |
| BIDU | N/A | MULTI_CLASS_UNVERIFIED | 0.76400000 | 4 / 4 | HELD | 2026-08-18 | 2026-10-06 |
| KALA | N/A | SHARE_BASIS_UNVERIFIED | 1.92500000 | 3 / 4 | — | — | 2026-10-06 |
| FTFT | N/A | SHARE_BASIS_UNVERIFIED | 0.60200000 | 4 / 4 | — | — | 2026-10-06 |


The compact production section exposes Current P/B, original Provider P/B, parent equity USD, equity quarter/source availability, as-of, quote/provider dates, status/reason/warnings and, where reviewed, ownership status and source date. Full metadata includes bound evidence and exact factor. GPCR/ONC preserve declared rounded factors with exact reviewed conversion; SCNI preserves provider zero while using official **1/40,000**. BABA/BIDU/KALA/FTFT/MCD remain unavailable for their appropriate independent reasons. P/B stays reporting-only and historical provider reference stays non-PIT-safe.

## Postflight, Backups and Rollback

Postflight active generation resolves to **pb_reporting_20261007T193505Z**. Active manifest is valid. Provider/canonical/analysis quick_check **ok**, FK errors **zero**; role hashes match verified candidate fingerprints. Parent schema and report-visible P/B are present. Source generation files were never opened writable or repaired in place. Individual active role files were not replaced; all three became active through the existing single generation-pointer switch.

Verified rollback backups remain under **`backups/fundamentals_admin_production/pb_reporting_20261007T193505Z`** (provider/canonical/analysis), and the original immutable generation remains retained. Backup hashes matched the original source set with quick_check/FK verification and normal fsync policy. Existing `restore_old_generation` was available through the journal recovery contract but was not invoked. **Rollback: NOT_REQUIRED.** Temporary candidate lane was removed after success; final generation, backups and runtime evidence remain outside Git.

Runtime evidence and the 17 candidate/production Markdown reports: **`fundamental_reports/pb_rollouts/pb_reporting_20261007T193505Z`**. Production coverage CSV has **2,468 unique companies**; validation CSV has the **17 required representative companies**. `git diff --check` and compact artifact validation passed before the documentation commit.

**Source changed: NO. Full suite: NO. No test rerun was needed because implementation was unchanged. Provider financial content: unchanged. Unrelated canonical financial data: unchanged. Analysis scores: unchanged. Valuation/Fundamental Score: unchanged. Publication authority: unchanged. Review Queue: unchanged. Scheduler: unchanged. Provider/4Q semantics: unchanged. Production rollout: YES. Active generation changed: YES. Push: NO.**
