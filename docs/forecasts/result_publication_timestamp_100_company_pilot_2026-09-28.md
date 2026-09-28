# Result publication timestamp 100-company pilot

Date: 2026-09-28

## Decision

`GO_FULL_FY2025_ENRICHMENT`

The corrected copy-only pilot resolved 571 of 675 quarters (84.59%) without accepting a timestamp outside the matching contract. The 104 non-VERIFIED quarters remained explicitly unresolved, ambiguous, or not found. Production authority and evidence tables remain empty.

## KO and XOM exceptions

- KO FY2025 Q4 was a narrow parser defect. SEC accession `0001628280-26-006642` is an Item 2.02 8-K accepted `2026-02-10T11:59:38Z`; its context says "fourth quarter and full year 2025". V1 previously required the year immediately after "quarter". The corrected Q4-only full-year rule resolves it as VERIFIED.
- XOM FY2025 Q4 was the same class of narrow defect. SEC accession `0000034088-26-000033`, accepted `2026-01-30T11:31:24Z`, says "full-year 2025" and references `4Q25`. The corrected Q4 full-year and `4QYY` forms resolve it as VERIFIED.
- XOM FY2026 Q2 is a legitimate `NO_ITEM_2_02_FOUND`. SEC submissions contain no relevant Item 2.02 8-K after the quarter end. XOM filed its 10-Q on `2026-08-03T18:55:38Z`; V1 does not treat that as an automatic publication fallback. Yahoo has a `2026-07-31 06:00:00-04:00` earnings event, but Yahoo cannot establish canonical authority.

The changes do not alter CIK matching, the 180-day window, Item 2.02 requirements, or source precedence.

## Yahoo and lxml

`lxml>=5.3.0` was already a normal dependency in `requirements.txt`; the development environment had not installed it. Installing `lxml 6.1.3` made yfinance 0.2.66 `Ticker.get_earnings_dates()` work. No packaging file changed.

Yahoo remained secondary evidence only. The six controls all had timezone-aware `America/New_York` events. Each available SEC/Yahoo pair matched on calendar date but not exact timestamp:

| Quarter | SEC authority UTC | Yahoo event | Yahoo minus SEC | Status |
|---|---|---|---:|---|
| AAPL FY2026 Q3 | 2026-07-30T20:30:28Z | 2026-07-30 16:00 EDT | -30m28s | MATCH_DATE_ONLY |
| NVDA FY2026 Q4 | 2026-02-25T21:31:25Z | 2026-02-25 16:00 EST | -31m25s | MATCH_DATE_ONLY |
| AMZN FY2026 Q2 | 2026-07-30T20:06:23Z | 2026-07-30 16:00 EDT | -6m23s | MATCH_DATE_ONLY |
| ADBE FY2026 Q3 | 2026-09-10T20:06:14Z | 2026-09-10 16:00 EDT | -6m14s | MATCH_DATE_ONLY |
| KO FY2025 Q4 | 2026-02-10T11:59:38Z | 2026-02-10 06:00 EST | -59m38s | MATCH_DATE_ONLY |
| XOM FY2025 Q4 | 2026-01-30T11:31:24Z | 2026-01-30 06:00 EST | -31m24s | MATCH_DATE_ONLY |

Yahoo evidence was not written to production.

## Deterministic sample

Selection rule: `result_publication_pilot_100_stratified_v1`.

Eligible companies came from the active Fundamentals operational universe, required `ACTIVE_SINGLE_SECURITY`, one active CIK, and at least one FY2025+ canonical quarter. Selection used permanent `company_id`; ticker was display/control metadata. AAPL, NVDA, AMZN, ADBE, KO, and XOM were required controls. The remaining 94 were selected by SHA-256 order in round-robin strata of market-cap tertile, sector, and fiscal pattern.

Distribution:

- size: 46 large, 27 mid, 25 small, 2 unavailable
- fiscal pattern: 46 calendar-year, 32 non-calendar-year, 22 52/53-week
- sectors: 11 named sectors plus 2 unavailable classifications
- exact scope: 100 companies and 675 FY2025+ quarters

Exact selected identities (`company_id/security_id/ticker`):

```text
7/7/AAPL, 1592/1601/NVDA, 152/152/AMZN, 44/44/ADBE, 1231/1235/KO, 2420/2431/XOM,
2382/2393/WLK, 1536/1545/NFLX, 181/181/APTV, 1758/1768/PM, 1628/1638/OKE, 2057/2067/SPGI,
108/108/ALKS, 498/499/CMI, 411/411/CBRE, 1145/1149/IONQ, 819/820/EXC, 824/825/EXP,
2227/2237/TTWO, 2465/2477/BABA, 1348/1356/LW, 1535/1544/NFG, 846/847/FDS, 1898/1908/RMD,
271/271/BAH, 2046/2056/SNX, 226/226/ATO, 676/677/DIS, 1010/1014/HAS, 1058/1062/HRL,
564/565/CRL, 1175/1179/J, 2014/2024/SLAB, 1789/1799/PRM, 2434/2445/YELP, 1389/1397/MCRI,
1298/1305/LINC, 934/937/GEL, 1100/1104/IDYA, 2192/2202/TPC, 424/424/CCS, 142/142/AMPL,
2234/2244/TXNM, 2396/2407/WS, 1832/1842/QNST, 1485/1494/MTN, 2054/2064/SPB, 1049/1053/HP,
1570/1579/NRIX, 778/779/EPAC, 882/883/FOR, 624/625/CXM, 1544/1553/NJR, 2249/2260/UFPI,
353/353/BOOT, 458/459/CHEF, 2087/2097/STAA, 827/828/EXPO, 1235/1239/KOPN, 2058/2068/SPH,
941/944/GEVO, 391/391/CABO, 1681/1691/PACK, 183/183/AQB, 144/144/AMPY, 484/485/CLPT,
1802/1812/PSIX, 61/61/AEI, 2035/2045/SMXT, 666/667/DGXX, 1131/1135/INHD, 516/517/CNVS,
643/644/DBI, 1539/1548/NGVC, 937/940/GEOS, 765/766/ENGN, 1920/1930/RR, 1900/1910/RMR,
1086/1090/IBEX, 1745/1755/PLAY, 1276/1282/LE, 694/695/DNUT, 2324/2335/VREX, 1207/1211/KELYA,
248/248/AVNW, 952/955/GLPI, 1300/1307/LION, 1453/1462/MOS, 2002/2012/SIRI, 2439/2450/YUMC,
1790/1800/PRMB, 1697/1707/PBF, 2211/2221/TRU, 19/19/ABT, 1761/1771/PNR, 531/532/COMP,
1356/1364/LYFT, 1715/1725/PEG, 1917/1927/RPM, 1476/1485/MSGS
```

## Copy safety and integrity

The pilot used an SQLite online backup at `/tmp/rawcandle_result_publication_100_company_pilot_v2.db`. Preflight and postflight both returned `quick_check=ok` and zero foreign-key errors.

Postflight contained 675 authority rows and 591 evidence rows for exactly the 100 selected company IDs; rows outside scope were zero. Existing-state hashes were unchanged:

- `v4_quarter`: `65308a16e9e6385c87887fb3689c6f40850e4116d1a8266254f06d28a46702fd`
- existing quarter date fields: `86a1a17acdf0c69eba150e0395f00af419efbb9e78ca70a6e11889cf77386796`
- `v4_quarter_financials`: `b218cacc5f76a5ef49fac59f6e6f00d7c09974d31cbcbc7368a08eda3f0472a7`

Production remained `quick_check=ok`, with zero foreign-key errors and zero authority/evidence rows. `forecasts.db` remained at SHA-256 `8fc6785ce83f8a94a0cb80be8d1514e6a9f3ea1d42ac33b9d2081f83ffc9cd42`.

## Status, sources, and confidence

| Status | Quarters | Percent |
|---|---:|---:|
| VERIFIED | 571 | 84.59% |
| UNRESOLVED | 33 | 4.89% |
| AMBIGUOUS | 10 | 1.48% |
| NOT_FOUND | 61 | 9.04% |

73 companies had 100% VERIFIED quarters. 27 had at least one non-VERIFIED quarter.

All 571 authorities were `SEC_8K_ITEM_2_02` with HIGH confidence. No source diversity was manufactured.

Non-VERIFIED reasons:

- `NO_ITEM_2_02_FOUND`: 58
- `QUARTER_MATCH_FAILED`: 34
- `MULTIPLE_VALID_CANDIDATES`: 10
- `UNRESOLVED_CONTEXT`: 2

Examples include foreign filer BABA and several small issuers with no 8-K Item 2.02, PLAY/RPM/WLK documents without sufficient canonical period context, and ten quarters with two distinct valid Item 2.02 filings. The latter remained AMBIGUOUS; none was silently resolved to the earlier timestamp.

## Timestamp and matching QA

- exact timestamp precision: 571/571, 100%
- normalized UTC: 571/571, 100%
- accepted before period end: 0
- accepted more than 180 days after period end: 0
- same-quarter multiple valid filing conflicts: 10
- exact period-end document match: 514
- explicit fiscal quarter/year match: 54
- reviewed Q4 full-year context match: 3

The conflicts were separate non-amended 8-K filings with different SEC acceptance timestamps, not duplicate database rows. No accepted authority violated company/CIK, period context, Item 2.02, or acceptance-window requirements.

## Lag against provider dates

The two existing fields had the same values in this pilot, so their distributions are equal. This is a comparison of different semantics, not a correction of Sharadar data.

For each of `first_public_result_date` and `source_availability_date`:

- same day: 316
- +/-1 day: 120
- 2-7 days: 65
- 8-30 days: 62
- more than 30 days: 8
- direction: 243 negative, 12 positive, 316 zero
- median absolute difference: 0 days
- p90 absolute difference: 9 days
- p95 absolute difference: 15 days
- maximum absolute difference: 105 days

## Requests and runtime

The first diagnostic run exposed an implementation defect: all historical Item 2.02 documents in the SEC recent list were fetched, including documents older than the FY2025+ scope. That run made 4,134 requests and took 2,180.1 seconds. It was discarded for the gate.

The corrected run filtered document fetches by the earliest canonical period year:

- runtime: 193.283 seconds
- SEC metadata requests: 100
- SEC document requests: 818
- total requests: 918
- candidate filings/documents inspected: 818
- old candidate documents skipped before fetch: 3,234
- requests/company: 9.18
- requests/quarter: 1.36
- cache hits: 0
- retries: 0
- 429 responses: 0
- transient failures: 0
- company failures: 0

The client now retries `TimeoutError` alongside HTTP transient errors. No concurrency was added.

## Cache and checkpoint assessment

Submissions metadata and each candidate document are fetched once per company per process, then reused across all of that company's quarters. An in-memory URL cache protects accidental duplicate requests but had zero hits in the corrected pilot because URLs were already unique.

Company-level commits are an adequate V1 checkpoint. A restart skips VERIFIED quarters but can refetch evidence for prior non-VERIFIED quarters; at the observed 15.41% non-VERIFIED rate this is bounded and preferable to storing filing HTML. A persistent SEC document cache is not required before the first full run. The operator should retain the compact JSON report and use explicit company scopes for any interrupted-run continuation.

## Full-run estimate and operator gate

Current canonical scope has 16,224 FY2025+ quarters. Of these, 16,210 quarters across approximately 2,535 companies have an active CIK and are directly eligible for the current resolver; the active operational universe subset is 15,668 quarters across 2,439 companies.

Linear projection from the corrected pilot:

- requests: approximately 23,000; planning range 20,000-30,000
- runtime: approximately 82 minutes; operational range 1.4-3 hours
- expected VERIFIED coverage: 80-88%
- expected new SQLite allocation: approximately 14-20 MB
- required backup: one verified online backup of the approximately 664 MB canonical database

The full enrichment was not executed. Recommended approved command after a fresh source/worktree and journal preflight:

```bash
python3 -m rawcandle.cli.run_result_publication_enrichment \
  --from-fiscal-year 2025 \
  --apply --confirm-production \
  --report temp/result_publication_full_fy2025.json
```

Exact next step: schedule a supervised 1.4-3 hour operator window, confirm at least 1.5 GB free space for backup and working margin, run the command above, and review all AMBIGUOUS rows before enabling any forecast research consumption.
