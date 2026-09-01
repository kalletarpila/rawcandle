# Valuation V1 Phase 3C Persistence and Production Gate

## Status

Phase 3C prepares revised-history persistence and rehearses the canonical and analysis database stages on verified SQLite backups. It does not migrate or write production and does not activate a pipeline hook.

- model: `ABSOLUTE_VALUATION_SCORE_V1`
- model fingerprint: `17a9c388647f9e810b9a88b5de1de764a1cb9f406c0f9e4f602da87b285ef62f`
- persistence schema: `V4_VALUATION_REVISED_HISTORY_V1`
- history mode: `REVISED_HISTORY`
- source fingerprint: `e552cf0b01a1e649d6269a968c4ea7e96b903acccce9c8b73d21d7c6cd230e47`
- result fingerprint: `46bdde9bd6711180b9bc1b75462c42c39e2ff5498ee93ad0c711cbbf88e69a18`

The legacy empty `valuation_result` placeholder is unchanged. The active prepared contract is the new `valuation_revised_result` table. Its uniqueness key is company, fiscal year, fiscal quarter, model fingerprint and revised-history mode. Other model fingerprints are preserved.

## Persistence and readers

Every status row retains identity, fiscal endpoint, availability and price dates, price age, close, shares, market cap, balance sheet, EV, three TTM numerators, yields, points, total, applicability and taxonomy evidence, model/source/result fingerprints and calculation audit time.

An identical logical rebuild performs no delete or insert. Replacement of one model fingerprint is protected by a database-local savepoint and verified against its logical fingerprint before release.

`ValuationRepository` requires an explicit model fingerprint for:

- latest company result
- current universe at an explicit as-of date and freshness limit
- full company history
- fiscal-quarter lookup
- status and reason lookup

Latest readers return a latest `NOT_READY` or `NOT_APPLICABLE` row as such; they never substitute an older `FULL` row. Daily valuation snapshots remain out of scope.

## Rehearsal

Artifacts are in `temp/fundamentals_v4_valuation_phase3c/20260901T_phase3c`.

| Copy | Initial bytes | Final bytes | Growth |
|---|---:|---:|---:|
| canonical | 269,901,824 | 433,410,048 | 163,508,224 |
| analysis | 253,874,176 | 302,678,016 | 48,803,840 |

Canonical-copy work added one quarterly common-income column, two TTM columns, backfilled 50,171 quarterly common-income/provenance rows and changed 42,596 TTM rows. Existing `net_income` and `ttm_net_income` were not repurposed.

The first analysis apply inserted 50,585 rows. The identical second apply inserted and deleted zero rows and reported all 50,585 unchanged. Both database quick checks were `ok`, foreign-key checks had zero violations, and both applies reproduced the same result fingerprint.

The Phase 3C persistence fingerprint is intentionally not compared byte-for-byte with Phase 3B replay fingerprint `d0422935...`: Phase 3B hashed the ordered engine-result fingerprints, while Phase 3C hashes the richer persisted logical row including taxonomy, security status and source evidence. The locked model fingerprint and all status counts remain unchanged.

## Exact-zero gate

The hard invariant passed for all 11,595 exact-zero `VALUATION_FULL` observations across 1,120 companies. Every row had observed, finite EBIT, FCF and common earnings, and all three were nonpositive. The all-three-nonpositive sign pattern also contained exactly 11,595 rows.

| EBIT / FCF / common earnings sign | Rows | Share of FULL |
|---|---:|---:|
| nonpositive / nonpositive / nonpositive | 11,595 | 29.642% |
| nonpositive / nonpositive / positive | 44 | 0.112% |
| nonpositive / positive / nonpositive | 3,237 | 8.275% |
| nonpositive / positive / positive | 105 | 0.268% |
| positive / nonpositive / nonpositive | 594 | 1.519% |
| positive / nonpositive / positive | 3,251 | 8.311% |
| positive / positive / nonpositive | 1,282 | 3.277% |
| positive / positive / positive | 19,009 | 48.595% |

Zero rows were 631 current and 10,964 historical-only observations; 11,480 belonged to currently active and 115 to inactive securities. Market-cap groups were 5,737 micro, 4,046 small, 1,501 mid and 311 large. Lifecycle diagnostics were 6,174 DISTRESSED, 2,738 STARTUP, 1,075 DECLINING, 531 STRUGGLING, 160 GROWTH, 35 SCALING, 26 TRANSITION and 856 unavailable. These diagnostics do not alter valuation.

The deterministic 24-row sample uses stable market-cap groups, lifecycle groups, inactive/recent/near-zero/extreme-negative cases and stable identifiers. `zero_score_sample.csv` contains the four quarterly common-income inputs and provenance IDs for each sample. No missing-to-zero conversion was found.

## Current universe

The established as-of convention selects the latest available fiscal observation per company no later than 2026-09-01 and requires age at most 180 calendar days. It produced 2,431 companies: 2,246 FULL, 139 NOT_APPLICABLE REITs and 46 NOT_READY.

NOT_READY comprised 35 nonpositive EV, six stale-price fallbacks, four TTM-not-ready and one unrecognized classification. Score mean was 27.76; P01/P10/P25/P50/P75/P90/P99 were 0.00/0.00/0.00/24.63/46.31/65.77/93.25. Exact zero was 631 (28.09%) and exact 100 was six (0.27%).

Non-overlapping bands `[0,20)`, `[20,40)`, `[40,60)`, `[60,80)`, `[80,100]` contained 1,003 / 521 / 413 / 213 / 96 scores. Full component distributions and correlations are in `phase3c_rehearsal.json`.

Representative current rows include NVDA 29.60, AAPL 25.03, MSFT 35.33, DAVE 39.88, TSLA 2.90, T 83.45, VZ 72.41, REIT O as NOT_APPLICABLE, non-REIT developer AEI 0.00 and exchange CME 29.78. No bank or insurer exists in the current canonical valuation universe, so no such row can be fabricated.

Deterministic profile representatives are mature/profitable and leveraged A (29.14), growth AIP (1.09), loss-making AAL (27.81) and net-cash AAOI (0.00). Lifecycle is diagnostic context only and does not select weights or alter scores.

## Phase 3A bridge

The exact bridge reconstructs 42,878 dated rows and the reported 41,576 formula-ready rows. Those become 39,117 FULL, 2,455 REIT NOT_APPLICABLE and four NOT_READY: two unrecognized classifications and two stale prices.

The remaining 9,009 rows are 7,707 undated, 864 nonpositive EV, 372 TTM-not-ready/invalid chain, 44 missing prices, 18 missing/nonpositive shares and four stale prices. Three Phase 3A-ready observations are newly excluded because Phase 3B requires complete coherent OHLC, not merely a usable close. This is an eligibility-contract difference, not recalibration.

## Production gate

Production provider, canonical, analysis and market database byte sizes and mtimes remained unchanged. Production checks remained: Score 50,585 rows and 354,095 components with result fingerprint `47add848...`; Lifecycle 50,585 rows with result fingerprint `43fee8da...`; legacy valuation zero rows. Production canonical remains unmigrated with 50,585 quarterly and TTM rows. All production SQLite quick checks returned `ok`.

Phase 3D is recommended only through the separate authorization and staged runbook. Remaining risks are current/revised taxonomy rather than historical PIT taxonomy, revised economic history after restatements, date-only availability, the accepted split-compatibility policy, and the lack of banks/insurers in the canonical universe for a live exclusion example.
