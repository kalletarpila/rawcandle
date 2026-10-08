# P/B.11 — Controlled Production rollout of quarterly ownership V2

**Production rollout completed on 2026-10-08, Europe/Helsinki.** Active ownership contract is **PB_OWNERSHIP_BASIS_V2**, effective from **2026-10-08**. Current P/B is **1,721 / 2,468 (69.73257699%)**, versus **1,690** under live V1 with identical frozen inputs. Exactly **31** reviewed approvals are active: **16 ordinary/common, six exact ADR factors, nine identity overrides**. Additional ownership releases: **zero**. Rollback: **NOT_REQUIRED**.

Old active generation: **pb_reporting_20261007T193505Z**. New active generation: **pb_quarterly_ownership_v2_20261008T080025Z**. Implementation commit **bec5f59a4452933fcb8e8cd9cbce68534c0fc809** and all source/test files remained unchanged throughout preflight, rehearsal, activation and postflight. This operator phase commits documentation and compact CSVs only.

## Contract and scope

The deployed behavior is the copy-validated [P/B.10 contract](fundamentals_v4_pb_quarterly_ownership_durability_v2.md). Current P/B keeps **PB_CURRENT_PARENT_EQUITY_V1** and uses current usable price × latest accepted quarterly validated economic units / latest accepted quarterly parent equity. Ordinary/direct-common units equal accepted sharesbas. ADS equivalents use accepted ordinary sharesbas × explicitly reviewed exact ratio. The numerator is a current-price quarterly-share proxy. No daily share updating, DAILY numerator, daily action completeness claim, provider ingestion or automatic new-Q approval was added.

V2 applies only through the additive generation-local canonical configuration. The source/global default remains V1; reporting before 2026-10-08 selects V1. New accepted observations, including same-quarter revisions, require a matching new observation/hash/quarter-bound ownership review. Old shares and exact ADR factors cannot transfer automatically. Same accepted Q requires no daily manual re-review. Existing parent-equity 180-day and price three-day freshness policies remain unchanged.

## Preflight and evidence binding

HEAD was exactly the approved implementation. There were no unexpected source/test changes or untracked source/test files. The active generation and manifest resolved through the normal generation API. All source role hashes matched the active manifest, quick_checks were **ok**, FK errors **zero**, and immutable source roles had no WAL/SHM/journal sidecars. Prior publication state was **COMPLETED**, with writes unblocked and no recovery pending.

Committed V2 registry SHA-256: **7b7d0cdd9bce7d448b70c7c46af54d3401f4fb0005b4f94f021d29c0e0e460e6**. Immutable V1 registry SHA-256: **0baaf493afa2faa52c2179a2353fb9089d834ef2bcb91f6e088e58f1bae068bf**. Both were checked before preparation, under locks, at the final gate and after activation. V2 configuration is:

```json
{
  "effective_from": "2026-10-08",
  "ownership_contract": "PB_OWNERSHIP_BASIS_V2",
  "review_artifact_sha256": "7b7d0cdd9bce7d448b70c7c46af54d3401f4fb0005b4f94f021d29c0e0e460e6",
  "singleton": 1
}
```

Free disk before preparation: **576,463,585,280 bytes**; required conservative allowance: **14,512,930,816 bytes** for candidates, immutable preparation, verified rollback backups and frozen market input. The existing production lock acquired the Administration and scheduler kernel locks; the taxonomy lock followed in the prescribed order. No conflicting writer held those locks. They remained held through preparation, activation and postflight.

Source evidence includes complete role inventories with table counts/schema fingerprints, ordered-row digests for all 30 original canonical tables, and 18 complete snapshot fingerprints. Scheduler config, Review Queue main/WAL and logical table digests, market main/WAL, and taxonomy main/WAL were bound and rechecked. Transient SHM reader-lock bytes are not financial state; queue committed content was independently checked. Market input was copied exactly for rehearsal; no market or taxonomy data was modified.

## Existing immutable publication path

1. Read-only source preflight, then normal production/scheduler and taxonomy locks with terminal-journal guards.
2. Fresh inactive copies of the three active roles, plus a frozen market copy. Provider/analysis copies remained byte-identical to source.
3. Existing `activate_quarterly_ownership` on inactive canonical only, effective 2026-10-08 and bound to the exact committed V2 artifact.
4. Full-universe/date rehearsals, representative snapshots/rendering, score and financial invariance, synthetic new-Q rollback scenarios and targeted normal-refresh smoke.
5. Existing `_verified_backups(..., immutable_generation=True)`, `_candidate_manifest`, and `prepare_journal(publication_mode="GENERATION_POINTER")`.
6. Existing `prepare_generation_from_candidates`, followed by the final source/input/code/registry/candidate hash and lock/journal gate.
7. Existing `activate_prepared_generation`, which performs verified atomic manifest activation of the complete three-role generation.
8. Production postflight, then normal journal completion **COMPLETED / PASSED / NOT_REQUIRED**.

No active DB was modified in place, no role was separately activated, no manifest was manually patched, and no post-activation SQL repair was performed. The old immutable generation and normal verified rollback backups are retained.

Activation clock gate: **2026-10-08T11:03:45.432769+03:00** / **2026-10-08T08:03:45.432769+00:00**. Final production gate: **PASSED**. Active manifest SHA before: **730b93fec46c3d4ed37b8340d7ec5ce6b2106dd42c64141c18d37ca045664eb8**; after: **7c103baedea1f7f0808388bec8138dea238951cf9c9ab476e727cf7d07ba0fa8**. This is the authorized atomic generation-pointer change.

| Role | Source SHA-256 | Activated SHA-256 | Postflight |
|---|---|---|---|
| provider | `2b3a57add8b51413d98f220d4cdd313994d1a4079f987a94796bf6a2b6db5fbb` | `2b3a57add8b51413d98f220d4cdd313994d1a4079f987a94796bf6a2b6db5fbb` | quick_check ok; FK 0 |
| canonical | `f1bfcfcb9c03c23dcce0c1186243c14a2f7a375fb48271cc9d14bd857cfa37d8` | `185597dc364c8cd1642d53054af485c5d4f690b49df18d38dbe911b3220fd924` | quick_check ok; FK 0 |
| analysis | `a8dcc37e1a0e2442dd44023b63d8c6ba91ee5fdce3ab05e2fa5407413a0355ce` | `a8dcc37e1a0e2442dd44023b63d8c6ba91ee5fdce3ab05e2fa5407413a0355ce` | quick_check ok; FK 0 |

Canonical schema fingerprint before: **d3a56b07260c1149a7b93b878bf59dfbb722d0eb3874e4fb295277e8b208112a**; after: **234949b3a1cd870e109eab9e940e202f375ac71f63086677d07b64de6479e365**. These fingerprints use compact canonical JSON of sorted schema rows. Every pre-existing schema object and all 30 original tables/financial columns, accepted provenance, parent equity, identity/fiscal mappings and publication authority retained identical content. The only addition is `v4_pb_reporting_contract` with one row.

## Candidate and live validation

| Report date | Selected ownership contract | V1 valid | Candidate/live valid | Restored |
|---|---|---:|---:|---:|
| 2026-10-07 | V1 | 1,721 | 1,721 | 0 |
| 2026-10-08 | V2 | 1,690 | 1,721 | 31 |
| 2026-10-09 | V2 | 1,689 | 1,720 | 31 |

All **2,468 October 7 P/B objects** match V1 exactly under identical frozen candidate inputs; no retroactive activation occurred. October 8/9 restore precisely the same reviewed 31, with no date-only OWNERSHIP_REVIEW_STALE and no additional ownership releases. The 32 explicit hold records retain their original underlying reasons. The full universe was computed twice on the candidate for all three dates and matched deterministically. Production then matched all **7,404 candidate P/B objects** across those dates.

Coverage is measured rather than forced. Relative to original P/B.8 coverage of 1,722, **CTVA** now fails the existing historical price-corroboration gate with SHARE_BASIS_UNVERIFIED under identical inputs in both V1 and V2. On October 9, **QRVO** has latest usable quote **2026-10-05**, exceeding the three-calendar-day price policy and returning STALE_PRICE. These explain the measured 1,721 / 1,721 / 1,720 sequence. The semantic change causes only the exact +31 restoration.

**New-Q rehearsal: nine PASS** — AMT, APTV, CAMT, GPCR, MREO, ONC, ZLAB, ARM and SCNI. Synthetic accepted next-Q records superseded previously valid reviews. Without a matching review, Current P/B returned OWNERSHIP_NEW_QUARTER_REVIEW_REQUIRED and no value/numerator; new parent equity and Provider P/B/history still updated. A matching explicit synthetic operator-confirmed review restored the calculation with **110% of old accepted shares** and **120% of old parent equity**, keeping the quote fixed. Each new ADR review explicitly carried its exact reviewed factor; SCNI retained raw provider factor zero. Every transaction rolled back, and canonical/frozen-market complete byte hashes matched before/after rehearsal. No real new-Q approval was added.

**Normal-refresh compatibility: PASS.** The single targeted smoke drove `phase12d.reconcile_canonical` through new-Q acceptance, parent-equity/share/factor refresh and Provider P/B/history rollover, preserved V2 configuration, required explicit new-Q review, and checked repeated reconciliation/report determinism. Inspection of `fresh_rebuild_canonical` confirms its existing explicit deletion list excludes the V2 reporting table. No scheduler or separate P/B refresh process was added.

**Score/financial invariance: PASS.** Eighteen complete candidate snapshots matched source for every non-`book_value` JSON field, including Fundamental Score, Valuation Score, relative position, score/model fingerprints and history, valuation-core outputs, existing multiples and unrelated financial outputs. Repeated candidate assembly matched exactly; each live postflight snapshot then matched its candidate. Whole-file analysis SHA equality additionally verifies all stored scoring/calibration state, beyond representative reports. Provider and all original canonical table digests remained identical.

**Reporting: PASS.** All 18 candidate/live reports rendered Current P/B, price date, equity quarter, share-basis quarter/date, ownership status and this disclosure:

> Current P/B uses the latest market price with the latest accepted quarterly share basis and parent equity. Share changes after that quarterly basis may not yet be reflected.

Reviewed source dates retain their reviewed basis; generic ordinary/common dates are clearly labeled PROVIDER_FILING_DATE_PROXY. The compact validation CSV records all 18 requested companies for all three dates, including prices, equity, Current/Provider P/B, reasons/warnings, ownership metadata and share-basis quarter/date. V1 rows intentionally retain V1 output structure rather than backfilling V2 fields.

| Company | Current P/B | Reason | Share quarter/date | Price date |
|---|---:|---|---|---|
| AAPL | 45.69775648 | OK | 2026-Q3 / 2026-07-31 | 2026-10-07 |
| APTV | 1.04895992 | OK | 2026-Q2 / 2026-07-31 | 2026-10-07 |
| BA | 24.40040786 | OK | 2026-Q2 / 2026-07-21 | 2026-10-07 |
| CTVA | N/A | SHARE_BASIS_UNVERIFIED | 2026-Q2 / 2026-07-31 | 2026-10-07 |
| FTFT | N/A | SHARE_BASIS_UNVERIFIED | 2026-Q2 / 2026-08-14 | 2026-10-07 |
| GPCR | 1.40471160 | OK | 2026-Q2 / 2026-07-31 | 2026-10-07 |
| KALA | N/A | SHARE_BASIS_UNVERIFIED | 2026-Q2 / 2026-08-19 | 2026-10-07 |
| MREO | 1.96743372 | OK | 2026-Q2 / 2026-08-10 | 2026-10-07 |
| NVDA | 24.99313065 | OK | 2027-Q2 / 2026-08-26 | 2026-10-07 |
| ONC | 7.99956941 | OK | 2026-Q2 / 2026-07-31 | 2026-10-07 |
| PSA | 5.38867171 | OK | 2026-Q2 / 2026-07-21 | 2026-10-07 |
| QRVO | 2.90106027 | OK | 2027-Q1 / 2026-07-28 | 2026-10-05 |
| SCNI | 0.05490326 | OK | 2026-Q2 / 2026-06-30 | 2026-10-07 |
| ZLAB | 4.68086487 | OK | 2026-Q2 / 2026-07-31 | 2026-10-07 |
| ARM | 36.42956602 | OK | 2027-Q1 / 2026-05-21 | 2026-10-07 |
| BABA | N/A | NEWER_SHARE_COUNT_REQUIRED | 2027-Q1 / 2026-08-20 | 2026-10-07 |
| BIDU | N/A | MULTI_CLASS_UNVERIFIED | 2026-Q2 / 2026-08-18 | 2026-10-07 |
| CAMT | 10.00178325 | OK | 2026-Q2 / 2026-08-10 | 2026-10-07 |

## Production coverage and holds

Operational universe **2,468**; Current P/B **1,721 (69.73257699%)**; Provider P/B **2,133**; four valid accepted history slots **2,081**. Provider/history availability and semantics are unchanged for every company. Accepted ARQ slot logic, provider observation dates and revised/non-PIT labeling are unchanged.

| Hard reason | Count |
|---|---:|
| MISSING_EQUITY | 120 |
| MISSING_PRICE | 10 |
| MULTI_CLASS_UNVERIFIED | 16 |
| NEGATIVE_EQUITY | 215 |
| NEWER_SHARE_COUNT_REQUIRED | 7 |
| OK | 1,721 |
| OWNERSHIP_BASIS_UNVERIFIED | 355 |
| SHARE_BASIS_UNVERIFIED | 6 |
| STALE_EQUITY | 6 |
| STALE_PRICE | 12 |

Remaining ownership population is **378**: **355** OWNERSHIP_BASIS_UNVERIFIED + **16** MULTI_CLASS_UNVERIFIED + **seven** NEWER_SHARE_COUNT_REQUIRED. The literal 355 reason count is not the entire ownership population. KALA/FTFT, BRTX/IESC/MNST and all other existing share-basis hard holds remain held; BABA remains NEWER_SHARE_COUNT_REQUIRED and BIDU MULTI_CLASS_UNVERIFIED. No unreviewed ownership case was released.

| Warning | All reports | Valid Current P/B |
|---|---:|---:|
| HISTORICAL_OHLC_INCOMPLETE | 58 | 41 |
| HISTORICAL_PRICE_CORROBORATION_UNAVAILABLE | 20 | 0 |
| HISTORICAL_PRICE_MISMATCH | 14 | 0 |
| LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE | 145 | 57 |
| NEAR_ZERO_EQUITY | 1 | 1 |
| REVIEWED_UNRESOLVED_BASIS | 2 | 0 |

## Targeted checks, postflight and artifacts

One normal-refresh rollout smoke passed:

```text
pytest -q tests/test_fundamentals_pb_quarterly_ownership.py::test_normal_reconciliation_supersedes_review_and_operator_confirmed_new_q_restores
1 passed in 6.72s
```

An independent process subsequently resolved the new active generation, confirmed historical V1/current V2 selection, and successfully calculated BA, GPCR and SCNI on October 8/9. The journal remained COMPLETED with writes unblocked.

No source changes, automatic rerun of the 142 + 49 implementation tests, or full test suite occurred. Operator checks additionally covered source/candidate/active manifest validity, three-role quick_check/FK, exact artifact/config binding, full-universe deterministic reporting, nine synthetic new-Q scenarios, representative rendering and score/financial isolation.

Postflight: **PASSED**. All three role quick_checks **ok**, FK errors **zero**; exact candidate role hashes match the new active manifest. V2 is active on/after October 8, V1 still selects October 7. Review Queue physical and committed logical state, scheduler config, source role files, market and taxonomy inputs remained unchanged through final gate and postflight. Publication authority and parent equity are included in unchanged canonical digests. The existing journal is terminal **COMPLETED / PASSED / NOT_REQUIRED**. Rollback **NOT_REQUIRED**.

Runtime evidence, rendered reports, complete inventories/hashes, backup paths and all-date P/B objects are retained under `fundamental_reports/pb_rollouts/pb_quarterly_ownership_v2_20261008T080025Z`. Normal verified backups are under `backups/fundamentals_admin_production/pb_quarterly_ownership_v2_20261008T080025Z`. The temporary candidate lane was cleaned after completion; finalized generations and rollback backups are retained. No runtime journal, DB, manifest, backup, cache or generated company report is committed.

Committed deliverables:

- [Detailed rollout report](fundamentals_v4_pb_quarterly_ownership_v2_production_rollout.md).
- [Production coverage CSV](fundamentals_v4_pb_quarterly_ownership_v2_production_coverage.csv): 2,468 current-as-of member rows.
- [Representative validation CSV](fundamentals_v4_pb_quarterly_ownership_v2_production_validation.csv): 54 company/date rows.

Production rollout **YES**; active generation changed **YES**; V2 active **YES**; V1 preserved **YES**; reviewed approvals **31**; additional approvals **0**; provider/canonical financial/parent equity/analysis scoring/publication authority/Review Queue/scheduler/market/taxonomy changes **NO**; Provider P/B/4Q semantics changes **NO**; rollback **NOT_REQUIRED**; full suite **NO**; push **NO**.
