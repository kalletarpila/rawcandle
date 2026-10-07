# Reporting-only Parent Equity and P/B V1 — corrected in P/B.5

Date: 2026-10-07, Europe/Helsinki. P/B.3 implementation and P/B.5 gate correction/copy validation complete; **live production rollout not executed**. Coverage below describes the candidate migrated from active generation `publication_drain_20261007T093516Z_fd654a20`, not the unchanged live generation.

## Result

Implemented canonical accepted parent equity, current restricted P/B, exact provider P/B reference, and a maximum four-quarter provider history in the existing company Fundamentals Markdown report. P/B is reporting-only. Valuation Score formula, weights, model version/fingerprints, relative-position logic and calibration are unchanged.

Candidate operational universe: **2,468 companies**. Current P/B valid after P/B.5: **1,691 (68.52%)**, up **96** from the P/B.3 count of 1,595. Latest provider reference valid: **2,133**. Four valid provider history slots: **2,081**. The valid-count distribution is four: 2,081; three: 50; two: 36; one: 25; zero: 276.

Compared with P/B.1, the arithmetic ceiling was 2,123 and conservative factor/class/date cohort 1,696. P/B.4 found the share-average proximity and mandatory historical full-OHLC gates too conservative. P/B.5 replaces those with diagnostics while preserving demonstrated contradictions and bounded reviewed unresolved-basis holds. Counts are measured, not forced to match research estimates. See [the detailed correction report](fundamentals_v4_pb_reporting_v1_gate_correction.md). Latest provider P/B can remain available when current ownership/basis validation rejects the company; provider history never uses current prices.

## Canonical Storage and Acceptance

`rawcandle/fundamentals/schema/parent_equity.py` is the dedicated additive field contract:

- `v4_quarter_financials.parent_equity`: finite native Sharadar `equity`, reporting-currency parent equity.
- `v4_quarter_financials.parent_equity_usd`: finite native `equityusd`, already USD-converted; no recalculation using rounded FX.
- `v4_parent_equity_provenance`: field/native mapping, provider, observation ID, acceptance time/rule, DIRECT transformation and confidence. Numeric zero and negative balances are accepted and preserved.
- `v4_parent_equity_source`: one accepted source-evidence projection per quarter. It retains observation ID/content hash, ARQ dimension, fiscalperiod, reportperiod, provider date/source availability, lastupdated/fetched time, metadata category and original same-row `pb`, `marketcap`, `price`, `sharesbas`, `shareswa`, `shareswadil`, `sharefactor` evidence.

The native provider P/B in this source projection is copied evidence, **not a derived canonical valuation**. Derived current P/B and provider validation/reason output are computed in the reporting/query layer, through `book_value_report`; no extra analysis history/version table is introduced. Reporting reads canonical accepted values/evidence plus market bars, and **does not read provider JSON**. The canonical evidence projection is rebuildable from accepted provider observation links.

Parent-equity fields are an additive extension of the existing financial row and use dedicated provenance routing. The existing score-input field tuple is kept unchanged so P/B cannot enter score calculations accidentally. No currency label is guessed for local equity; output uses explicitly USD parent equity. Provider definitions established in P/B.1 remain applicable.

Acceptance uses the unique current accepted `shares_outstanding` provenance observation for each accepted quarter. It asserts same ARQ dimension, exact fiscalperiod, canonical source_reportperiod and sharesbas equality. It never picks a richer alternate observation or another dimension. Missing equity remains NULL; NaN/infinity and nonnumeric values become NULL. The accepted source projection is rebuilt with canonical reconciliation so old bindings cannot persist after a source change. Reporting additionally checks source observation equality against current shares provenance, making an obsolete projection unavailable.

Rule: `PARENT_EQUITY_ACCEPTED_ARQ_V1`. Existing quarter/report metadata supplies the balance-sheet association. Equity availability uses the bound provider observation source availability, not an earlier result-publication timestamp or TTM aggregation. No four-flow-quarter readiness requirement, no annual-minus-quarter equity, no common-equity or tangible-common-equity claim.

Mandatory visible caveat: **Parent equity attributable to parent shareholders as supplied by Sharadar; preferred-capital exclusion is not proven.**

## Current P/B Contract

`PB_CURRENT_PARENT_EQUITY_V1`, semantic mode `CURRENT_REVISED_REPORTING`, role `REPORTING_ONLY`.

Formula for the supported restricted cohort: **latest valid market close × canonical accepted shares_outstanding / parent_equity_usd**. This is a current reported-share whole-company market-cap proxy, using filing-cover shares rather than asserting a more recent authoritative outstanding count. The balance is the latest accepted eligible fiscal endpoint; source availability must be on/before as-of and no more than 180 calendar days old. Market price is latest complete valid positive OHLC for ticker/market on/before as-of, with at most three-calendar-day fallback.

Output explicitly includes as-of date, actual price date, equity fiscal year/quarter, report period and own source availability. Price/quarter/provider dates are distinct. No P/B cap, negative cheapness signal or score contribution exists.

### Ownership and Share-Basis Gates

Initial allowed provider categories are Domestic Common Stock and Canadian Common Stock, with **factor exactly one**, one active security and target ticker among active securities. Other categories, primary/multiple-class flags, ADR/ADS, absent/nonunit/zero factor and inactive/ambiguous security ownership return `OWNERSHIP_BASIS_UNVERIFIED`. Provider metadata is drawn from fundamentals/SF1 security metadata, not an arbitrary ETF/stock metadata row. Selected canonical 6-K official evidence with provider-type conflict or ADR/ADS identification also blocks current P/B; no new ownership factor is inferred from it.

Corrected `SHARE_BASIS_UNVERIFIED` checks:

1. Canonical outstanding shares must equal same-observation sharesbas. Missing/nonpositive accepted shares return MISSING_SHARES.
2. Same-row provider price × shares must reproduce same-row marketcap within **1%** for the allowed factor-one cohort. The native price/cap inputs remain required.
3. A demonstrated exact-date historical **positive finite close** mismatch greater than **1%** remains an unresolved basis hold. Missing historical data or invalid historical full-OHLC geometry alone cannot block Current P/B.
4. An explicit bounded unresolved-basis review may hold the exact accepted company/observation/content-hash combination on/after its review date. The two P/B.4 NEEDS_MORE_EVIDENCE records are retained in `book_value_reviews.py`. No ticker comparison or universal percentage cutoff creates a hold. Reviews do not transfer to another company, source revision or date preceding review.

Weighted-average EPS shares are optional diagnostic evidence, **not the denominator** and never a proximity eligibility condition. Absolute sharesbas/shareswa deviation >25% attaches `LARGE_ENDPOINT_VS_AVERAGE_SHARE_DIFFERENCE`. Missing/nonpositive averages do not block. Diluted EPS shares remain evidence only. Missing finite positive provider-date close attaches `HISTORICAL_PRICE_CORROBORATION_UNAVAILABLE`; a usable close with incomplete full OHLC attaches `HISTORICAL_OHLC_INCOMPLETE`. Actual price contradiction attaches `HISTORICAL_PRICE_MISMATCH` and remains blocked. A matched reviewed hold attaches `REVIEWED_UNRESOLVED_BASIS` with reference metadata in the report object. Existing compact Warnings rendering is reused.

BRTX/IESC/MNST remain held by the generic price contradiction. KALA/FTFT remain held by the bounded reviewed-evidence mechanism, not their EPS-share deviation alone. SCNI fails ownership/factor validation. BABA/BIDU/ASML remain unavailable under the unchanged ownership contract. Missing old price history for newly listed or discontinuous securities is not an ownership failure when current/as-of inputs are valid.

Near-zero positive equity at most USD 1m attaches `NEAR_ZERO_EQUITY`; it remains numeric if other gates pass. This transparent diagnostic follows P/B.1 research, not a new score policy.

### Reasons and Precedence

Priority: missing/zero/negative equity, missing/future own availability, stale equity, missing price, stale price, unsupported ownership, missing shares, inconsistent share/price basis, nonfinite derived value, then OK. A company can fail several gates; coverage counts use its first explicit reason.

| Reason | Candidate count |
|---|---:|
| OK | 1,691 |
| NEGATIVE_EQUITY | 215 |
| ZERO_EQUITY | 0 |
| MISSING_EQUITY | 120 |
| OWNERSHIP_BASIS_UNVERIFIED | 409 |
| SHARE_BASIS_UNVERIFIED | 5 |
| MISSING_PRICE | 10 |
| STALE_PRICE | 12 |
| STALE_EQUITY | 6 |
| MISSING_SHARES | 0 |
| EQUITY_AVAILABILITY_UNVERIFIED | 0 |
| PB_NONFINITE | 0 |

Multiple-class exclusions use `OWNERSHIP_BASIS_UNVERIFIED`, as requested in the ownership contract; there is no separate `MULTIPLE_CLASS_UNVERIFIED` reason. Counts include all 2,468 operational members, including retained inactive identities; no universe change.

## Provider Reference and Four-Quarter History

Field `PB_PROVIDER_OBSERVATION`, semantic mode `PROVIDER_OBSERVATION_REFERENCE`. Reference is **original same-observation Sharadar ARQ pb**, never current-price reconstruction. Requirements: finite positive parent equity USD, marketcap and P/B; ARQ and observation date present; **absolute** residual `abs(marketcap / equityusd - pb) <= 0.0005001`. This P/B.2 tolerance allows low-ratio three-decimal rounding. Invalid values return NULL with `PROVIDER_INPUTS_INVALID`, `PROVIDER_PB_ARITHMETIC_MISMATCH`, `PROVIDER_OBSERVATION_INVALID`, or equity reason. An unmigrated generation reports `PARENT_EQUITY_NOT_MIGRATED` for provider reference.

Newest fiscal quarter first, maximum four **accepted quarter keys**, with no interpolation. The query limits accepted quarter slots before P/B validity checks. A missing/invalid latest slot is shown explicitly as N/A and reason; it is **not replaced with an older fifth slot or MRQ/ART/MRT row**. Missing fiscal quarters are not invented. If fewer accepted eligible quarters exist, fewer rows are returned. Current reference is always the latest accepted slot, not the latest older valid P/B. Each row exposes observation date, year/quarter, report period and diagnostic observation ID/hash/rule.

Provider P/B history may remain visible when current P/B is unavailable. It is labelled **Provider P/B history**, not result-publication, quarter-end, PIT or historical RawCandle valuation. Neither metric is PIT-certified. Current-vs-provider change percentage is deliberately omitted in V1 because it could imply a pure price move when bases differ.

## Company Report Placement and Representative Output

The existing V2 company snapshot assembler attaches `book_value`; the existing renderer adds a compact `Book Value / P/B` section and the four-row provider history table. UI report generation already uses this assembler/renderer, so no UI redesign or separate live workflow is needed. Parent equity/date/status/caveat and both reasons are visible. Full report content fingerprints naturally include the new section; score model fingerprints are unchanged.

Copy-validated AAPL output at as-of 2026-10-07:

```text
Book Value / P/B
Current P/B                45.29x
Provider P/B               41.93x
Parent equity (USD)        $107.52B
Equity quarter             2026-Q3
Price date                 2026-10-06
Provider observation date  2026-07-31
Status                     OK
```

These are actual candidate values, not fabricated Production examples. MCD displays Current P/B N/A / NEGATIVE_EQUITY; BABA displays N/A / OWNERSHIP_BASIS_UNVERIFIED with valid dated provider reference/history. Internal observation IDs are available in the snapshot structure, not shown in the compact table.

Representative sample:

| Ticker | Current P/B | Reason | Provider P/B | Provider date | Valid 4Q slots |
|---|---:|---|---:|---|---:|
| AAPL | 45.2851x | OK | 41.930x | 2026-07-31 | 4 |
| AMD | 15.7706x | OK | 11.706x | 2026-08-05 | 4 |
| CAT | 20.4652x | OK | 20.646x | 2026-08-05 | 4 |
| FTFT | N/A | SHARE_BASIS_UNVERIFIED | 0.602x | 2026-08-14 | 4 |
| KALA | N/A | SHARE_BASIS_UNVERIFIED | 1.925x | 2026-08-19 | 3 |
| MCD | N/A | NEGATIVE_EQUITY | N/A | 2026-08-07 | 0 |
| MSFT | 8.8844x | OK | 6.555x | 2026-07-29 | 4 |
| NVDA | 25.1794x | OK | 22.066x | 2026-08-26 | 4 |
| SCNI | N/A | OWNERSHIP_BASIS_UNVERIFIED | 0.139x | 2026-08-26 | 4 |
| XOM | 2.6075x | OK | 2.458x | 2026-08-03 | 4 |
| ASML | N/A | OWNERSHIP_BASIS_UNVERIFIED | 28.142x | 2026-07-15 | 4 |
| BABA | N/A | OWNERSHIP_BASIS_UNVERIFIED | 1.950x | 2026-08-20 | 4 |
| BIDU | N/A | OWNERSHIP_BASIS_UNVERIFIED | 0.764x | 2026-08-18 | 4 |

## Rebuild and Rollout Evidence

Canonical preparation: `migrate_parent_equity(provider_copy_or_readonly_source, canonical_copy, accepted_at=...)`. Writes are rejected for active role paths, legacy production filenames, symlinks and finalized immutable generation directories. Normal `phase12d.reconcile_canonical` also runs the same acceptance in its existing copy transaction after canonical winner/provenance reconciliation; active-copy guard runs before opening a writer. Failure rolls back parent plumbing together with reconciliation. Bootstrap prototypes gain fields at the normal reconciliation/migration step, not by changing score-bearing field mappings.

Copy source: current active immutable generation. SQLite online backup made `/tmp/rawcandle_pb3/fundamentals_v4.db`. **89,912 accepted quarters bound; 171,304 finite parent field values promoted**. Every original canonical table and every original financial column was compared before/after with deterministic logical SHA-256; all unchanged. Existing financial timestamps and prior provenance were unchanged. Foreign-key checks passed; new provenance observation bindings/content hashes match provider source evidence.

Coverage/query output is fully rebuildable from the copied canonical accepted inputs, existing market bars, explicit as-of and rules. No persistent current P/B history/state is required. Provider/analysis Production DBs were never opened writable; no source refresh, analysis score rebuild, scheduler change or live publication was executed. Manifest bytes and Production role file size/mtime remained unchanged.

The **existing** `prepare_generation_from_candidates` / `activate_generation` path was tested on isolated fixture projects with migrated canonical fields and unchanged analysis-score content. It supports the additive schema and preserves analysis values. The corrected candidate passed the copy validation described in the P/B.5 report; any later rollout must use the normal reviewed immutable-generation Administration copy/reconciliation/publication path. It does not introduce another Production publisher.

**Production rollout: NO.** The optional live population in this phase was left unexecuted; all coverage/rendered examples are candidate evidence. Current live canonical schema still lacks the new parent-equity fields, so reports show explicit unavailable values until a normal immutable-generation publication includes the migrated candidate. No direct active SQL mutation is required or permitted. No automatic refresh was launched just to populate P/B.

## Original P/B.3 Tests and Validation

- Focused P/B tests: **32 passed**, including mapping/provenance, parent caveat, equity/price reasons, ADR/classes/factors, share discontinuities, determinism, rounding tolerance, exact row binding/no richer fallback, four-quarter ordering/gaps/N/A, rendering, stale projection rejection, rollback and isolated immutable generation publication.
- One grouped Fundamentals/reporting regression: **130 passed** across P/B, additive provenance, immutable generations, snapshot UI and V2 company snapshot tests. Three additional P/B tests added after this group passed in the final focused run.
- Reconciliation integration checks: **19 passed** in `test_phase12d_operational_rebuild.py`, including canonical source revision, no-op replay and rollback.
- Real candidate snapshots for AAPL/NVDA/MCD compared to the original: current valuation, valuation multiples, all model fingerprints, score/valuation quarter history and average valuation results are identical. New P/B sections render successfully.
- Compact CSV uniqueness/count/finite/null checks and `git diff --check` complete before commit. Full suite: **not run**.

Only source, focused tests and these compact documentation/coverage/validation artifacts are committed. Database copies, journals, backups, caches and unrelated worktree files are excluded. Nothing pushed.

## P/B.5 Gate Correction Validation

Current corrected counts and warnings are in `fundamentals_v4_pb_reporting_v1_corrected_coverage.csv`; the original P/B.3 coverage/validation CSVs remain historical evidence. The corrected validation sample contains 30 real companies. See [the detailed correction report](fundamentals_v4_pb_reporting_v1_gate_correction.md) for review bindings, warning counts, fixture semantics, full-universe provider/4Q comparisons and six complete snapshot comparisons.

Focused corrected P/B tests: **42 passed**. One relevant Fundamentals/reporting regression group: **88 passed**. No full suite. Fresh active-generation backup rebuilt parent-equity on `/tmp/rawcandle_pb5/fundamentals_v4.db`; original canonical tables/old financial columns retained identical logical fingerprints. All 2,468 provider references/4Q histories equal the P/B.3 baseline. All non-P/B snapshot fields, including score fingerprints and financial/valuation history, compare exactly for six real companies. Production DBs, market DB and active manifest unchanged; no scheduler change, live workflow or Production rollout.

## P/B.7 Reviewed Ownership Contract V1

`PB_OWNERSHIP_BASIS_V1` adds bounded reviewed ordinary/common, exact ADS economic-unit and direct-common identity support to the existing reporting-only Current P/B contract. The 63-record immutable-evidence registry binds company/security/ticker, accepted observation/hash, source/effective dates and review provenance; 31 records support releases and 32 retain explicit holds. Review validity currently covers **2026-10-07 only**, with separately enforced share-source age <=180 days and known unresolved share-action holds. Future calculation dates require a renewed review. No provider metadata or accepted source fields are rewritten.

Copy-only corrected coverage: **1,722 / 2,468 = 69.77309562%**, **+31** over P/B.5 (16 ordinary, six exact ADS factors, nine direct-common identity overrides). The residual original ownership cohort is 378: 355 default ownership holds, 16 refined multi-class holds and seven newer-share-count holds. Provider P/B remains 2,133, so the gap is 411. Parent equity and preferred-capital caveat, three-day complete-OHLC current lookup, historical diagnostics, Provider P/B/4Q semantics and scores remain unchanged. The old SCNI unavailable example above describes the earlier P/B.3/P/B.5 contract; its audited-day candidate now uses the official 1/40,000 factor through generic reviewed evidence.

See [the ownership contract report](fundamentals_v4_pb_ownership_contract_v1.md), [full candidate coverage](fundamentals_v4_pb_ownership_contract_v1_coverage.csv) and [representative validation](fundamentals_v4_pb_ownership_contract_v1_validation.csv). Focused tests: **80 passed**; one relevant regression group: **88 passed**. Production rollout and full suite: **NO**. Active generation, production data, Provider P/B, 4Q history and Valuation Score were not changed.
