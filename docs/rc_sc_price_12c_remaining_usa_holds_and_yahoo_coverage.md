# PRICE-12C — Remaining USA holds and Yahoo fallback coverage

2026-11-05: investigation and narrowly scoped revision-proof hardening completed. **No production prices, identities, statuses or derived outputs were changed.** No hold qualified for release under the existing contract. All 290 retained fallback cases have an evidence-based category; last eligible sessions remain explicitly unresolved for 273. This is not universal price coverage or end-to-end derived acceptance.

## Boundary, baseline and ownership

Starting RawCandle HEAD: `e7bc91d5db2be654c7cb79fb8aa702ee12afa47d`. StockCore HEAD: `537b1bc77ec6e656917859ffdb210eca133ef9db`, unchanged. Each checkout has one worktree. The local final RC commit is the commit containing this report, code and tests; its exact hash is recorded in the operator response and ignored final manifest. No push. Unrelated financial-journal changes and pre-existing untracked files were preserved. StockCore was read-only.

The initial trusted UTC clock was November 5 at 17:16:48 UTC: 19:16:48 Helsinki / 12:16:48 America/New_York. The accepted native US cash calendar ends completed sessions at **2026-11-04**; November 5 closes at 21:00 UTC / 23:00 Helsinki and was still open throughout the investigation. The six-session window is October 28, 29, 30 and November 2, 3, 4. Every price request used exclusive end November 5. No future or intraday daily bar was requested or accepted. The [NYSE calendar](https://www.nyse.com/trade/hours-calendars) corroborates the exchange hours.

Read the RC [PRICE-11 USA report](rc_sc_price_11_usa_coverage.md), [OMXH finality report](rc_sc_price_11_omxh_finality.md), PRICE-01/02/03 provider, append and fallback contracts, the StockCore PRICE-10 live-chain report, PRICE-11 reconciliation, PRICE-12A INM review, current P02 quality/receipt/retention contracts, native bridge/revision/insertion owners and applicable repository instructions. The current Source retention model supersedes older archival descriptions: `source_received` and accepted observations are keyed by security/session, not immutable historical vintages. A retained receipt/change scope does not recreate an old payload.

Fresh runtime inspection found Source owner IDLE, no Source/P03/P04/RC worker, all seven inspected native locks free, RC independent timer disabled/inactive, service MainPID 0 and its existing invocation `a5c2ed81babb480ba3984cebd9a9c0c6` unchanged. The service still displays its previous failed Fundamentals run; this task did not reset it. The enabled native Source task is Ready, next November 6 at 04:45 Helsinki; measured Windows commit headroom was about 83 GiB and Linux disk free about 557 GiB. Host schedule/memory evidence is retained separately. No service, timer, scheduler, handoff or background operation was started. No admission to a production write was needed because no candidate qualified.

## The 27 original anchor holds

**Resolved 0; confirmed safety hold 1; insufficient evidence 26. All 27 native bridge holds remain.** These are the exact original PRICE-11 identities, all anchored on October 30; INM is excluded and untouched. Current Source heads, accepted observations/quality, routes, action payloads, full retained receipt/change chains, original immutable RC rows and both immediately preceding peers were re-read. Earlier receipts were checked individually, not assumed missing because they were absent from the current head.

No qualifying alternate overlap witness was recovered for the 13 ordinary-overlap failures. Twelve Volume cases have an actual revision receipt but neither of the two independent peer bars meets the existing price/Volume unit contract. Additional adjacent rows were inspected diagnostically; older compatible rows were not substituted into the three-row bridge context, and the six-session revision window was not extended. Missing archival evidence is not proof that RC or Source is economically wrong.

FPF has a genuine recorded November 2 dividend of $0.138. It explains the common adjustment factor, but Source raw October 30 Low is approximately 15.11 versus RC 15.14, beyond the existing 0.1% price threshold. The relevant old action receipts also fail current native action-version qualification. The ordinary-revision Close-continuity rule and the separate dividend exception therefore cannot release this case. A current Yahoo match to Source does not supply the missing old-vintage/unit proof.

SUPN has a material multi-session economic conflict: October 30 RC Close 41.919998 versus accepted Source raw Close 35.369999 and adjusted Close 27.443922; Volume 2,818,900 versus 4,607,200. The fresh nine-session Yahoo sample agrees with the current adjusted vintage, not with the immutable RC history. Source records an $8.13 November 3 dividend. Independently, the [Nasdaq merger notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-742) and [issuer SEC filing](https://www.sec.gov/Archives/edgar/data/1356576/000110465926121103/tm2628719d2_8k.htm) establish the legacy Supernus merger and trading suspension; the issuer also describes the combined company using SUPN. This is an action/identity and economic-unit safety boundary, not an ordinary Volume revision. Which historical vintage is economically correct is not asserted.

Table keys: **I** = `INSUFFICIENT_REVISION_EVIDENCE`; **H** = `CONFIRMED_SAFETY_HOLD`. O = no qualifying ordinary overlap witness; U = compatible historical unit context unproven; A = action/receipt and price-factor conflict; E = material economic/identity conflict. Native materiality thresholds remain unchanged. RC owner ID “—” means no exact current/alias match in the pinned active canonical identity generation; RC price identity remains its existing ticker/market key, and no ID was allocated or inferred.

| Ticker | SC / RC owner ID | Source head / accepted through | RC → Source anchor Volume | Decision / reason |
| --- | --- | --- | ---: | --- |
| ACP | 3903 / — | 10 / 2026-11-04 | 1,052,714 → 1,052,700 | I / O |
| AWF | 3932 / — | 9 / 2026-11-04 | 307,268 → 307,400 | I / O |
| BEAG | 2704 / — | 11 / 2026-11-04 | 11,421 → 768,500 | I / O |
| BRKRP | 4370 / — | 10 / 2026-11-04 | 14,018 → 14,000 | I / O |
| CDT | 432 / 432 | 12 / 2026-11-04 | 5,012,800 → 5,394,900 | I / U |
| CHI | 3982 / — | 9 / 2026-11-04 | 132,179 → 132,200 | I / O |
| CHW | 3983 / — | 9 / 2026-11-04 | 47,544 → 47,500 | I / O |
| DHF | 4005 / — | 9 / 2026-11-04 | 330,716 → 330,700 | I / O |
| ECC | 4015 / — | 9 / 2026-11-04 | 1,434,120 → 1,439,300 | I / O |
| EOD | 4025 / — | 9 / 2026-11-04 | 174,833 → 174,800 | I / O |
| ETY | 4036 / — | 9 / 2026-11-04 | 382,054 → 392,700 | I / O |
| FFAI | 854 / 854 | 12 / 2026-11-04 | 1,326,600 → 1,340,500 | I / U |
| FIGXU | 3010 / — | 11 / 2026-11-04 | 673 → 700 | I / O |
| FPF | 4053 / — | 9 / 2026-11-04 | 972,768 → 972,800 | I / A |
| GGLL | 4067 / — | 10 / 2026-11-04 | 3,875,100 → 3,926,500 | I / U |
| HIO | 4080 / — | 9 / 2026-11-04 | 845,821 → 845,800 | I / O |
| KKRT | 4373 / — | 9 / 2026-11-03 | 78,314 → 78,300 | I / O |
| MEGL | 3321 / — | 11 / 2026-11-04 | 1,009,300 → 1,090,100 | I / U |
| MKDW | 2537 / 2537 | 12 / 2026-11-04 | 1,108,100 → 1,123,400 | I / U |
| RBNE | 3534 / — | 11 / 2026-11-04 | 25,268,400 → 26,072,400 | I / U |
| RKLX | 4245 / — | 10 / 2026-11-04 | 3,025,000 → 3,059,100 | I / U |
| SHFS | 3615 / — | 11 / 2026-11-04 | 62,412,400 → 68,698,100 | I / U |
| SUPN | 2114 / 2114 | 11 / 2026-11-04 | 2,818,900 → 4,607,200 | H / E |
| TGL | 2167 / 2167 | 12 / 2026-11-04 | 750,200 → 793,000 | I / U |
| UTHR | 2293 / 2293 | 11 / 2026-11-04 | 502,800 → 518,200 | I / U |
| XXII | 2442 / 2442 | 11 / 2026-11-04 | 13,659,100 → 14,178,500 | I / U |
| YMAT | 3878 / — | 10 / 2026-11-04 | 617,400 → 634,700 | I / U |

The large ignored hold inventory contains exact original/current OHLCV, accepted raw/adjusted context, receipt IDs and versions, complete original/subsequent retained change scopes, per-receipt witness outcomes under the starting and final code, actions, current identity dependencies and unit comparisons. Every original anchor still matches its retained PRICE-11 values. No `QUALIFIED_NON_BLOCKING_REVISION` or additional confirmed scaling diagnosis was forced. All 27 original ticker strings remain held; no substitute Yahoo route was attempted.

## Narrow implementation and validation

`services/price_revision_policy.py` now rejects a session first inserted in a mixed daily receipt as revision proof. Previously, aggregate `changed_sessions > missing_inserted` could qualify the inserted session merely because another session was revised. The comparison now also requires a prior same-security, same-session native change, joined to a COMPLETE receipt with accepted observations and the native deterministic change key. Absent or unsupported proof fails closed with `REVISION_SESSION_PREVIOUS_ACCEPTANCE_REQUIRED`. This tightens provenance; it neither relaxes economic safeguards nor republishes Source. Genuine revisions with prior acceptance still append through the existing owner.

Final focused run: **85 passed, 0 failed** across `test_price11_revisions.py`, `test_stockcore_price_provider.py`, and `test_price12c_fallback_boundaries.py`. One adjacent native insertion group: **16 passed, 0 failed**. Total **101 distinct tests**; full suite **NO**. The 11 new cases cover mixed insertion/revision receipts, invalid prior acceptance evidence, closed delisted/OTC/renamed routes retaining their original requested symbol, unit holds overriding closed-route fallback, true empty Yahoo responses and repeat preservation, intraday Source exclusion, and missing completed Source tails remaining unfilled without fallback. Existing tests cover actual native overlap revisions, price/split/unit conflicts, stale identity, Source dependency changes before commit, rollback, idempotence and historical row preservation.

An initial pytest command lacked its parent Temp directory; after fixing the test environment, two new assertions needed correction (empty tuple versus list, and the documented no-new-Source-tail result versus an assumed hold). The final complete focused run and adjacent run passed. No full-suite expansion or production database copy occurred.

## Yahoo investigation and classifications

Input is exactly the **290 `PROVIDER_NO_DATA` rows** from retained PRICE-11 `fallback_inventory.json`; SSKN is excluded. The original inventory date is a historical reference, not a current listing assertion. All 290 current bridge decisions still permit the existing Yahoo route: 124 `MISSING_SOURCE_TICKER`, 166 `NO_ELIGIBLE_SOURCE_ROUTE`. None is a Source safety-hold fallback. Current Source collection intervals are not listing or terminal-trading dates.

Grouped metadata was acquired once from the [Nasdaq listed directory](https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt), [other exchange directory](https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt) and [SEC ticker/exchange directory](https://www.sec.gov/files/company_tickers_exchange.json). Both exchange files were timestamped November 5, 12:11 Eastern. None of the 290 old symbols appeared as a non-test current listing. This is useful route evidence, **not proof of delisting, inactivity or absence of OTC trading**. Of the original tickers, SEC directory OP now belongs to OpenPayd, illustrating symbol reuse; it was not assigned to the old RC history.

Existing SC identity evidence maps 166 cases. Read-only inspection of the pinned active RC identity generation found 21 exact current-ticker matches and 25 matches including historical aliases. Current SEC CIK metadata was then read for 42 recent or successor-candidate issuers, and 58 specifically identified class-delisting/transition filings were examined. All 23 instruments with October last-RC dates received grouped metadata review; the recent mapped cases received issuer filing checks. Unmapped recent CLSD and GTI remain provider-limited without an authoritative transition established; their missing metadata is explicit. No 290-symbol price retry or independent broad search loop was run.

Native RC yfinance 0.2.66 made **29 logical bounded history reads**: SUPN (October 23–November 4), FPF (October 28–November 4), and 27 candidate successor symbols (October 28–November 4). Twenty-eight reads returned observations; WSKEF returned a no-data error and was not retried. Twenty-six successor symbols have valid completed November 4 bars; OHLCV/event context is retained as returned by RC auto-adjusted history. These are investigation observations, not accepted RC or StockCore rows. Exact underlying Yahoo HTTP requests are unknown. The 103 successful direct public metadata reads are separate from Yahoo price calls and public web-reference searches. One initial sandbox DNS failure made no successful metadata HTTP request; the bounded metadata script then ran with network access.

| Final category | Count | Interpretation |
| --- | ---: | --- |
| ACTIVE_AND_CURRENT | 6 | Six verified continuing securities already current under their successor symbols; exact RC/Yahoo November 4 match and usable native Source routes. |
| ACTIVE_MISSING_SESSIONS | 0 | No same-symbol append-qualified case; active successor gaps are counted separately. |
| VERIFIED_DELISTED | 20 | Exchange/class removal proven; global cessation and terminal session are not assumed. |
| VERIFIED_INACTIVE | 0 | No cases assigned. |
| VERIFIED_RENAMED_OR_MIGRATED | 10 | Primary issuer/exchange transition established; original history not redirected. |
| VERIFIED_OTC_CONTINUATION | 7 | Issuer/security OTC continuation corroborated; unit/class review remains separate. |
| PROVIDER_UNAVAILABLE | 241 | Retained original-symbol no-usable-new-data evidence; listing/terminal status unresolved. |
| SOURCE_ROUTE_UNAVAILABLE | 0 | No cases assigned. |
| SAFETY_HELD | 0 | No cases assigned. |
| UNRESOLVED | 6 | Material issuer, class or successor continuity question remains. |

**20 verified exchange delistings; 0 globally verified inactive securities; 7 verified OTC continuations.** The 20 delistings include four unit classes (APADU, CCCXU, CGCTU, SVACU); subsequent common shares or warrants are different instruments. A Form 25 filing date is recorded separately and never relabelled a last trading date or calculated delisting effective date. AHL and DBRG preferred shares and TWO senior note TWOD do not continue the old common-stock price series. HWH’s historical warrant/right/unit removal does not delist its continuing common shares.

**Six verified continuing securities are already current**: AIHS→VAI, AMRK→GOLD, EQR→VMRK, ISSC→IA, LIXT→NMAD and PSTG→P. Each successor has an existing RC November 4 bar matching all five sampled Yahoo fields exactly, and its current native Source bridge route is usable with no hold. These are assigned ACTIVE_AND_CURRENT; their superseded symbols remain recorded. **11 active continuing securities have a verified November 4 successor/OTC observation missing from RC.** This is an orthogonal missing-coverage flag across migration categories, not 11 append-qualified old-symbol routes. Their exact pending latest-date scope is November 4 after owner-qualified identity/action/unit/anchor review. Sixteen issuer transitions are established in total: six current cases and ten remaining migration cases. KRSA also has current RC observations, but CYCN’s old identity/action continuity remains separately unqualified. Other sampled successor observations are kept separate where reverse merger, reincorporation, class or ADS/ordinary-share continuity remains unqualified. **273 original securities still have unresolved actual last eligible sessions.** An RC database date, a rejected Yahoo stub, a current successor quote, a security terminal date and an exchange removal date are different fields.

Only explicit old-symbol terminal dates are recorded: LIXT July 2, 2026 from its [exchange/issuer transition notice](https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2026-469), and LNW November 12, 2025 from its [issuer timetable](https://explore.investors.lnw.com/static-files/6711c991-6b74-4f42-aaaf-81740ef0f40e). Both continued under other symbols/venues; neither date means all trading stopped. Several old-symbol RC observations extend beyond published transitions. Those identity/vintage inconsistencies are retained as review obligations, not repaired by overwriting old rows.

## All 290 instrument decisions

Compact keys: **K** `ACTIVE_AND_CURRENT`; **P** `PROVIDER_UNAVAILABLE`; **D** `VERIFIED_DELISTED`; **R** `VERIFIED_RENAMED_OR_MIGRATED`; **O** `VERIFIED_OTC_CONTINUATION`; **U** `UNRESOLVED`. Route **M→M** means originally/currently missing Source ticker; **C→C** means originally/currently closed Source route. Type/exchange/currency come from the current pinned Source identity; `?` is unknown, not inferred from ticker spelling. USD is not assumed for unknown currencies. Detailed RC owner IDs, action/merger/ticker/class evidence, all provider outcomes, original/last Yahoo dates, distinct terminal/effective/required-session fields and exact limitations are in the ignored inventory.

Yahoo column gives **last valid original-symbol observation / sampled successor observation**; `?` means not independently established. Merely finding the same date in RC does not populate Yahoo. “Eligible” refers to the independently verified continuing security where established; `?` retains uncertainty about the original security. Classification source links identify the direct supporting primary record, with full payloads outside Git.

| RC ticker | SC ID / route | Type / exchange / currency | Last RC | Yahoo original / successor | Class | Eligible | Evidence / next scope |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ABL | — / M→M | ? / ? / ? | 2026-02-27 | ? / ? | P | ? | Listing/terminal unresolved |
| ABVE | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| ACLX | 2574 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-05-15 | ? / ? | P | ? | Listing/terminal unresolved |
| AGH | — / M→M | ? / ? / ? | 2026-07-02 | ? / ? | P | ? | Listing/terminal unresolved |
| AHL | 2593 / C→C | ADR / NYSE / ? | 2026-02-23 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/1267395/000087666126000166/xslF25X02/primary_doc.xml); continuing other class excluded |
| AIHS | 82 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-09-02 | ? / VAI 2026-11-04 | K | 2026-11-04 | [primary](https://www.sec.gov/Archives/edgar/data/1711012/000121390026093717/ea0303367-8k_senmiao.htm) VAI; RC current, exact match; old-symbol date conflict |
| AL | 2601 / C→C | COMMON_STOCK / NYSE / USD | 2026-04-07 | ? / ? | P | ? | Listing/terminal unresolved |
| ALBT | — / M→M | ? / ? / ? | 2026-08-31 | ? / ? | P | ? | Listing/terminal unresolved |
| ALEX | 2604 / C→C | COMMON_STOCK / NYSE / USD | 2026-03-12 | ? / ? | P | ? | Listing/terminal unresolved |
| ALTS | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| AMBC | — / M→M | ? / ? / ? | 2026-01-16 | ? / ? | P | ? | Listing/terminal unresolved |
| AMRK | — / M→M | ? / ? / ? | 2026-01-30 | ? / GOLD 2026-11-04 | K | 2026-11-04 | [primary](https://www.sec.gov/Archives/edgar/data/1591588/000119312525307852/gold-20251202.htm) GOLD; RC current, exact match; old-symbol date conflict |
| AMWD | 2622 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-05-28 | ? / ? | P | ? | Listing/terminal unresolved |
| APADU | 2629 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-05-15 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/1956439/000162828026031825/enhanced-form25.htm); unit class only |
| APGE | 172 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-09-03 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/1974640/000135445726000853/xslF25X02/primary_doc.xml) |
| APLS | 2632 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-05-15 | ? / ? | P | ? | Listing/terminal unresolved |
| APM | — / M→M | ? / ? / ? | 2026-07-27 | ? / ? | P | ? | Listing/terminal unresolved |
| ASGN | — / M→M | ? / ? / ? | 2026-06-18 | ? / ? | P | ? | Listing/terminal unresolved |
| ATAI | 2655 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-09-11 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/2081043/000135445726000870/xslF25X02/primary_doc.xml) |
| ATGE | — / M→M | ? / ? / ? | 2026-04-10 | ? / ? | P | ? | Listing/terminal unresolved |
| ATON | — / M→M | ? / ? / ? | 2026-06-18 | ? / ? | P | ? | Listing/terminal unresolved |
| ATUS | — / M→M | ? / ? / ? | 2026-01-16 | ? / ? | P | ? | Listing/terminal unresolved |
| ATXS | 2660 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-01-23 | ? / ? | P | ? | Listing/terminal unresolved |
| AVDL | 2666 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-02-13 | ? / ? | P | ? | Listing/terminal unresolved |
| AVNS | 2667 / C→C | COMMON_STOCK / NYSE / USD | 2026-07-24 | ? / ? | P | ? | Listing/terminal unresolved |
| AXL | — / M→M | ? / ? / ? | 2026-03-19 | ? / ? | P | ? | Listing/terminal unresolved |
| BCARU | 2695 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-08-27 | ? / ? | P | ? | Listing/terminal unresolved |
| BFK | 3942 / C→C | FUND / NYSE / ? | 2026-02-09 | ? / ? | P | ? | Listing/terminal unresolved |
| BHAT | — / M→M | ? / ? / ? | 2026-05-14 | ? / ? | P | ? | Listing/terminal unresolved |
| BITF | — / M→M | ? / ? / ? | 2026-06-04 | ? / ? | P | ? | Listing/terminal unresolved |
| BK | — / M→M | ? / ? / ? | 2026-07-17 | ? / BNY 2026-11-04 | R | 2026-11-04 | [primary](https://www.bny.com/corporate/global/en/about-us/newsroom/press-release/bny-announces-planned-change-of-stock-ticker-symbol-to-bny-130465.html) BNY; owner transition pending; old-symbol date conflict |
| BLBX | — / M→M | ? / ? / ? | 2026-04-10 | ? / ? | P | ? | Listing/terminal unresolved |
| BLD | 2723 / C→C | COMMON_STOCK / NYSE / USD | 2026-07-02 | ? / ? | P | ? | Listing/terminal unresolved |
| BLE | 3948 / C→C | FUND / NYSE / ? | 2026-02-09 | ? / ? | P | ? | Listing/terminal unresolved |
| BLFS | 334 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-10-07 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/834365/000135445726000952/xslF25X02/primary_doc.xml) |
| BNRG | — / M→M | ? / ? / ? | 2026-08-20 | ? / ? | P | ? | Listing/terminal unresolved |
| BNZI | — / M→M | ? / ? / ? | 2026-10-28 | ? / PARA 2026-11-04 | R | 2026-11-04 | [primary](https://www.sec.gov/Archives/edgar/data/1826011/000119312526352362/para-20260630.htm) PARA; owner transition pending; old-symbol date conflict |
| BRR | 2751 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-10-28 | 2026-10-28 / SVIA 2026-11-04 | R | 2026-11-04 | [primary](https://www.sec.gov/Archives/edgar/data/2076163/000149315226043753/form8-k.htm) SVIA; owner transition pending; old-symbol date conflict |
| BTAI | 370 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-10-08 | ? / BTAIQ 2026-11-04 | O | 2026-11-04 | [primary](https://www.sec.gov/Archives/edgar/data/1720893/000110465926120737/tm2624733d2_8k.htm) BTAIQ; owner transition pending; old-symbol date conflict |
| BTM | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| BXMX | 3978 / C→C | FUND / NYSE / ? | 2026-03-27 | ? / ? | P | ? | Listing/terminal unresolved |
| CADE | 2778 / C→C | COMMON_STOCK / NYSE / USD | 2026-01-30 | ? / ? | P | ? | Listing/terminal unresolved |
| CAEP | — / M→M | ? / ? / ? | 2026-05-15 | ? / ? | P | ? | Listing/terminal unresolved |
| CAPT | — / M→M | ? / ? / ? | 2026-10-28 | ? / CAPTF 2026-11-04 | O | 2026-11-04 | [primary](https://www.nasdaq.com/press-release/captivision-announces-nasdaq-global-markets-delisting-otc-2026-04-08) CAPTF; owner transition pending; old-symbol date conflict |
| CASI | 2785 / C→C | ADR / NASDAQ / ? | 2026-04-27 | ? / CASIF 2026-11-04 | O | ? | [primary](https://www.sec.gov/Archives/edgar/data/1962738/000110465926043516/tm2611790d1_6k.htm) CASIF; owner transition pending; old-symbol date conflict |
| CCCX | — / M→M | ? / ? / ? | 2026-03-02 | ? / ? | P | ? | Listing/terminal unresolved |
| CCCXU | 2793 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-03-02 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/2007825/000119312526050159/d186927d25.htm); unit class only |
| CCO | 422 / C→C | COMMON_STOCK / NYSE / USD | 2026-10-15 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/1334978/000087666126000839/xslF25X02/primary_doc.xml) |
| CCRN | 2799 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-07-28 | ? / ? | P | ? | Listing/terminal unresolved |
| CDTX | 2802 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-01-08 | ? / ? | P | ? | Listing/terminal unresolved |
| CEPT | — / M→M | ? / ? / ? | 2026-07-01 | ? / ? | P | ? | Listing/terminal unresolved |
| CFLT | 2808 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-03-17 | ? / ? | P | ? | Listing/terminal unresolved |
| CGCTU | 2813 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-06-08 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/2049662/000135445726000536/xslF25X02/primary_doc.xml); unit class only |
| CHACU | 2816 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-03-26 | ? / ? | U | ? | [primary](https://www.sec.gov/files/company_tickers_exchange.json); identity/class unresolved |
| CHEK | — / M→M | ? / ? / ? | 2026-01-16 | ? / ? | P | ? | Listing/terminal unresolved |
| CIO | 2830 / C→C | COMMON_STOCK / NYSE / USD | 2026-01-08 | ? / ? | P | ? | Listing/terminal unresolved |
| CIVI | 2833 / C→C | COMMON_STOCK / NYSE / USD | 2026-01-29 | ? / ? | P | ? | Listing/terminal unresolved |
| CLCO | 2836 / C→C | ADR / NYSE / ? | 2026-01-08 | ? / ? | P | ? | Listing/terminal unresolved |
| CLSD | — / M→M | ? / ? / ? | 2026-10-28 | ? / ? | P | ? | Listing/terminal unresolved |
| CMA | 2840 / C→C | COMMON_STOCK / NYSE / USD | 2026-01-30 | ? / ? | P | ? | Listing/terminal unresolved |
| CMPO | — / M→M | ? / ? / ? | 2026-03-19 | ? / ? | P | ? | Listing/terminal unresolved |
| CNTA | 2852 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-06-29 | ? / ? | P | ? | Listing/terminal unresolved |
| COMM | — / M→M | ? / ? / ? | 2026-03-13 | ? / ? | P | ? | Listing/terminal unresolved |
| CPRX | 2859 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-07-21 | ? / ? | P | ? | Listing/terminal unresolved |
| CREV | — / M→M | ? / ? / ? | 2026-04-10 | ? / ? | P | ? | Listing/terminal unresolved |
| CRNX | 570 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-09-02 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/1658247/000135445726000839/xslF25X02/primary_doc.xml) |
| CSAN | 2869 / C→C | ADR / NYSE / ? | 2026-10-02 | ? / CSANY 2026-11-04 | O | 2026-11-04 | [primary](https://www.cosan.com.br/en/investor-relations/other-informations-for-investors/our-stocks/) CSANY; owner transition pending |
| CSGS | 2870 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-05-15 | ? / ? | P | ? | Listing/terminal unresolved |
| CTLP | 2874 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-05-15 | ? / ? | P | ? | Listing/terminal unresolved |
| CTRA | 2875 / C→C | COMMON_STOCK / NYSE / USD | 2026-05-07 | ? / ? | P | ? | Listing/terminal unresolved |
| CUK | 2878 / C→C | COMMON_STOCK / NYSE / USD | 2026-05-07 | ? / ? | P | ? | Listing/terminal unresolved |
| CVAC | 2884 / C→C | ADR / NASDAQ / ? | 2026-01-06 | ? / ? | P | ? | Listing/terminal unresolved |
| CVGW | 2887 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-06-08 | ? / ? | P | ? | Listing/terminal unresolved |
| CWAN | 2888 / C→C | COMMON_STOCK / NYSE / USD | 2026-07-02 | ? / ? | P | ? | Listing/terminal unresolved |
| CYBR | 2891 / C→C | ADR / NASDAQ / ? | 2026-02-13 | ? / ? | P | ? | Listing/terminal unresolved |
| CYCN | 628 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-10-14 | ? / KRSA 2026-11-04 | R | ? | [primary](https://www.sec.gov/Archives/edgar/data/1755237/000119312526389318/d178159d8k.htm) KRSA; owner transition pending |
| DAWN | 2896 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-04-24 | ? / ? | P | ? | Listing/terminal unresolved |
| DAY | 2897 / C→C | COMMON_STOCK / NYSE / USD | 2026-02-03 | ? / ? | P | ? | Listing/terminal unresolved |
| DBRG | 2899 / C→C | COMMON_STOCK / NYSE / USD | 2026-09-29 | 2026-09-29 / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/1679688/000087666126000800/xslF25X02/primary_doc.xml); continuing other class excluded |
| DENN | 2903 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-01-21 | ? / ? | P | ? | Listing/terminal unresolved |
| DEVS | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| DGLY | — / M→M | ? / ? / ? | 2026-03-06 | ? / ? | P | ? | Listing/terminal unresolved |
| DOMO | 701 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-10-01 | ? / HUCK 2026-11-04 | R | 2026-11-04 | [primary](https://www.sec.gov/Archives/edgar/data/1505952/000110465926109635/tm2625825d1_8k.htm) HUCK; owner transition pending; old-symbol date conflict |
| DOOO | — / M→M | ? / ? / ? | 2026-02-04 | ? / DOO 2026-11-04 | R | 2026-11-04 | [primary](https://www.sec.gov/Archives/edgar/data/1748797/000119312525307451/d847897dex991.htm) DOO; owner transition pending |
| DVAX | 2928 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-02-10 | ? / ? | P | ? | Listing/terminal unresolved |
| EA | 2932 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-08-10 | ? / ? | P | ? | Listing/terminal unresolved |
| EB | 2934 / C→C | COMMON_STOCK / NYSE / USD | 2026-03-09 | ? / ? | P | ? | Listing/terminal unresolved |
| ECDA | 2937 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-03-17 | ? / ? | P | ? | Listing/terminal unresolved |
| EEX | 2943 / C→C | COMMON_STOCK / NYSE / USD | 2026-07-14 | ? / ? | P | ? | Listing/terminal unresolved |
| EHAB | 2952 / C→C | COMMON_STOCK / NYSE / USD | 2026-05-14 | ? / ? | P | ? | Listing/terminal unresolved |
| EKSO | — / M→M | ? / ? / ? | 2026-05-15 | ? / ? | P | ? | Listing/terminal unresolved |
| ELWS | — / M→M | ? / ? / ? | 2026-03-13 | ? / ? | P | ? | Listing/terminal unresolved |
| EM | 2961 / C→C | ADR / NASDAQ / ? | 2026-05-15 | ? / ? | P | ? | Listing/terminal unresolved |
| EMPG | 2962 / C→C | ADR / NASDAQ / ? | 2026-08-03 | ? / ? | P | ? | Listing/terminal unresolved |
| ENTO | — / M→M | ? / ? / ? | 2026-01-16 | ? / ? | P | ? | Listing/terminal unresolved |
| EQR | 788 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-08-21 | ? / VMRK 2026-11-04 | K | 2026-11-04 | [primary](https://investors.vivmarkresidential.com/news-events/press-releases/detail/113/vivmark-residential-launches-as-one-of-the-countrys-leading-real-estate-companies) VMRK; RC current, exact match; old-symbol date conflict |
| ESPR | 2974 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-07-13 | ? / ? | P | ? | Listing/terminal unresolved |
| ETHM | — / M→M | ? / ? / ? | 2026-07-02 | ? / ? | P | ? | Listing/terminal unresolved |
| ETHZ | — / M→M | ? / ? / ? | 2026-04-27 | ? / ? | P | ? | Listing/terminal unresolved |
| EVTV | — / M→M | ? / ? / ? | 2026-07-20 | ? / ? | P | ? | Listing/terminal unresolved |
| EWCZ | 2982 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-05-15 | ? / ? | P | ? | Listing/terminal unresolved |
| EXAS | 2983 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-03-23 | ? / ? | P | ? | Listing/terminal unresolved |
| EXPI | — / M→M | ? / ? / ? | 2026-07-10 | ? / ? | P | ? | Listing/terminal unresolved |
| FCT | 4045 / C→C | FUND / NYSE / ? | 2026-08-11 | ? / ? | P | ? | Listing/terminal unresolved |
| FDP | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| FFIC | 2998 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-06-08 | ? / ? | P | ? | Listing/terminal unresolved |
| FFWM | 3000 / C→C | COMMON_STOCK / NYSE / USD | 2026-03-31 | ? / ? | P | ? | Listing/terminal unresolved |
| FIHL | — / M→M | ? / ? / ? | 2026-07-02 | ? / ? | P | ? | Listing/terminal unresolved |
| FOLD | 3028 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-04-27 | ? / ? | P | ? | Listing/terminal unresolved |
| FRGE | 3029 / C→C | COMMON_STOCK / NYSE / USD | 2026-03-03 | ? / ? | P | ? | Listing/terminal unresolved |
| FYBR | 3042 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-01-21 | ? / ? | P | ? | Listing/terminal unresolved |
| GAMB | — / M→M | ? / ? / ? | 2026-07-29 | ? / ? | P | ? | Listing/terminal unresolved |
| GBIO | 3049 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-02-10 | ? / ? | P | ? | Listing/terminal unresolved |
| GBTG | 923 / C→C | COMMON_STOCK / NYSE / USD | 2026-09-29 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/1820872/000087666126000798/xslF25X02/primary_doc.xml) |
| GCI | — / M→M | ? / ? / ? | 2026-01-16 | ? / ? | P | ? | Listing/terminal unresolved |
| GDEN | 3052 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-05-15 | ? / ? | P | ? | Listing/terminal unresolved |
| GES | 3057 / C→C | COMMON_STOCK / NYSE / USD | 2026-01-22 | ? / ? | P | ? | Listing/terminal unresolved |
| GLDD | 3071 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-04-01 | ? / ? | P | ? | Listing/terminal unresolved |
| GLMD | 3073 / C→C | ADR / NASDAQ / ? | 2026-10-08 | ? / ? | U | ? | [primary](https://www.sec.gov/files/company_tickers_exchange.json); identity/class unresolved |
| GLPG | — / M→M | ? / ? / ? | 2026-07-02 | ? / ? | P | ? | Listing/terminal unresolved |
| GLTO | — / M→M | ? / ? / ? | 2026-05-08 | ? / ? | P | ? | Listing/terminal unresolved |
| GMRE | — / M→M | ? / ? / ? | 2026-04-10 | ? / ? | P | ? | Listing/terminal unresolved |
| GREE | — / M→M | ? / ? / ? | 2026-07-30 | ? / ? | P | ? | Listing/terminal unresolved |
| GTI | — / M→M | ? / ? / ? | 2026-10-28 | ? / ? | P | ? | Listing/terminal unresolved |
| GTLS | 3103 / C→C | COMMON_STOCK / NYSE / USD | 2026-07-16 | ? / ? | P | ? | Listing/terminal unresolved |
| GV | — / M→M | ? / ? / ? | 2026-10-01 | ? / ? | P | ? | Listing/terminal unresolved |
| HI | 3120 / C→C | COMMON_STOCK / NYSE / USD | 2026-02-10 | ? / ? | P | ? | Listing/terminal unresolved |
| HLX | 1042 / C→C | COMMON_STOCK / NYSE / USD | 2026-09-02 | ? / HOS 2026-11-04 | R | ? | [primary](https://www.sec.gov/Archives/edgar/data/866829/000119312526378529/d102206d8k.htm) HOS; owner transition pending; old-symbol date conflict |
| HOLX | 3137 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-04-07 | ? / ? | P | ? | Listing/terminal unresolved |
| HOTH | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| HOUS | 3141 / C→C | COMMON_STOCK / NYSE / USD | 2026-01-08 | ? / ? | P | ? | Listing/terminal unresolved |
| HTBK | 3148 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-04-21 | ? / ? | P | ? | Listing/terminal unresolved |
| HWH | 1081 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-09-28 | ? / ESYN 2026-11-04 | R | 2026-11-04 | [primary](https://www.sec.gov/Archives/edgar/data/1897245/000149315226043411/form8-k.htm) ESYN; owner transition pending; old-symbol date conflict |
| IAC | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| IINN | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| INDU | — / M→M | ? / ? / ? | 2018-12-06 | ? / ? | P | ? | Listing/terminal unresolved |
| IOBT | — / M→M | ? / ? / ? | 2026-06-05 | ? / ? | P | ? | Listing/terminal unresolved |
| IPCX | 3194 / C→C | ADR / NASDAQ / ? | 2026-08-14 | ? / ? | P | ? | Listing/terminal unresolved |
| IPCXU | 3195 / C→C | ADR / NASDAQ / ? | 2026-08-14 | ? / ? | P | ? | Listing/terminal unresolved |
| IPODU | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| IRBT | — / M→M | ? / ? / ? | 2026-02-18 | ? / ? | P | ? | Listing/terminal unresolved |
| ISSC | 1170 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-10-28 | 2026-10-28 / IA 2026-11-04 | K | 2026-11-04 | [primary](https://www.nasdaq.com/press-release/innovative-aerosystems-change-nasdaq-ticker-symbol-ia-following-corporate-rebranding) IA; RC current, exact match; old-symbol date conflict |
| JAMF | 3204 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-02-04 | ? / ? | P | ? | Listing/terminal unresolved |
| JFB | 3212 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-09-03 | 2026-09-03 / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/2024306/000135445726000855/xslF25X02/primary_doc.xml) |
| JFBR | — / M→M | ? / ? / ? | 2026-06-01 | ? / ? | P | ? | Listing/terminal unresolved |
| JHG | 3215 / C→C | COMMON_STOCK / NYSE / USD | 2026-07-02 | ? / ? | P | ? | Listing/terminal unresolved |
| KALV | 3227 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-06-12 | ? / ? | P | ? | Listing/terminal unresolved |
| KAR | — / M→M | ? / ? / ? | 2026-02-18 | ? / ? | P | ? | Listing/terminal unresolved |
| KW | 3256 / C→C | COMMON_STOCK / NYSE / USD | 2026-06-15 | ? / ? | P | ? | Listing/terminal unresolved |
| KWM | 3257 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-10-08 | ? / ? | U | ? | [primary](https://www.sec.gov/files/company_tickers_exchange.json); identity/class unresolved |
| LBRDA | 1274 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-08-21 | ? / ? | P | ? | Listing/terminal unresolved |
| LBRDK | 1275 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-08-21 | ? / ? | P | ? | Listing/terminal unresolved |
| LC | — / M→M | ? / ? / ? | 2026-08-20 | ? / ? | P | ? | Listing/terminal unresolved |
| LEG | 1285 / C→C | COMMON_STOCK / NYSE / USD | 2026-08-27 | ? / ? | P | ? | Listing/terminal unresolved |
| LGCB | — / M→M | ? / ? / ? | 2026-07-02 | ? / ? | P | ? | Listing/terminal unresolved |
| LITM | — / M→M | ? / ? / ? | 2026-05-14 | ? / ? | P | ? | Listing/terminal unresolved |
| LIXT | 1311 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-09-03 | ? / NMAD 2026-11-04 | K | 2026-11-04 | [primary](https://www.nasdaqtrader.com/TraderNews.aspx?id=eca2026-469) NMAD; RC current, exact match; old-symbol date conflict |
| LMFA | — / M→M | ? / ? / ? | 2026-07-29 | ? / ? | P | ? | Listing/terminal unresolved |
| LNW | — / M→M | ? / ? / ? | 2026-10-28 | ? / LNWO 2026-11-04 | O | 2026-11-04 | [primary](https://infomemo.theocc.com/infomemos?number=57628) LNWO; owner transition pending; old-symbol date conflict |
| LPRO | 3289 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-08-07 | ? / ? | P | ? | Listing/terminal unresolved |
| LPSN | 1330 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-09-04 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/1102993/000135445726000857/xslF25X02/primary_doc.xml) |
| LSH | — / M→M | ? / ? / ? | 2026-08-11 | ? / ? | P | ? | Listing/terminal unresolved |
| MASI | 3307 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-06-12 | ? / ? | P | ? | Listing/terminal unresolved |
| MAXN | — / M→M | ? / ? / ? | 2026-07-10 | ? / ? | P | ? | Listing/terminal unresolved |
| MBAV | — / M→M | ? / ? / ? | 2026-07-29 | ? / ? | P | ? | Listing/terminal unresolved |
| MCTR | — / M→M | ? / ? / ? | 2026-02-04 | ? / ? | P | ? | Listing/terminal unresolved |
| MCW | 3318 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-06-08 | ? / ? | P | ? | Listing/terminal unresolved |
| MEG | — / M→M | ? / ? / ? | 2026-06-26 | ? / ? | P | ? | Listing/terminal unresolved |
| MESA | — / M→M | ? / ? / ? | 2026-01-06 | ? / ? | P | ? | Listing/terminal unresolved |
| MFH | — / M→M | ? / ? / ? | 2026-01-09 | ? / ? | P | ? | Listing/terminal unresolved |
| MMC | — / M→M | ? / ? / ? | 2026-03-13 | ? / MRSH 2026-11-04 | R | 2026-11-04 | [primary](https://www.marsh.com/en/corp/about/news/marsh-mclennan-to-change-nyse-symbol-to-mrsh.html) MRSH; owner transition pending; old-symbol date conflict |
| MNMD | — / M→M | ? / ? / ? | 2026-03-13 | ? / ? | P | ? | Listing/terminal unresolved |
| MODG | — / M→M | ? / ? / ? | 2026-03-13 | ? / ? | P | ? | Listing/terminal unresolved |
| MOFG | 3346 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-02-25 | ? / ? | P | ? | Listing/terminal unresolved |
| MOGO | — / M→M | ? / ? / ? | 2026-02-27 | ? / ? | P | ? | Listing/terminal unresolved |
| MPW | — / M→M | ? / ? / ? | 2026-03-19 | ? / ? | P | ? | Listing/terminal unresolved |
| MRSN | 3352 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-01-06 | ? / ? | P | ? | Listing/terminal unresolved |
| MRUS | 3353 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-01-02 | ? / ? | P | ? | Listing/terminal unresolved |
| MSW | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| MVF | 4165 / C→C | FUND / NYSE / ? | 2026-02-25 | ? / ? | P | ? | Listing/terminal unresolved |
| MYD | 4167 / C→C | FUND / NYSE / ? | 2026-02-23 | ? / ? | P | ? | Listing/terminal unresolved |
| MYNZ | — / M→M | ? / ? / ? | 2026-05-11 | ? / ? | P | ? | Listing/terminal unresolved |
| NAOV | — / M→M | ? / ? / ? | 2026-02-04 | ? / ? | P | ? | Listing/terminal unresolved |
| NCC | 3374 / C→C | COMMON_STOCK / NYSE / USD | 2022-03-02 | ? / ? | P | ? | Listing/terminal unresolved |
| NFBK | 3382 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-07-28 | ? / ? | P | ? | Listing/terminal unresolved |
| NIL | — / M→M | ? / ? / ? | 2022-03-02 | ? / ? | P | ? | Listing/terminal unresolved |
| NITO | — / M→M | ? / ? / ? | 2026-04-27 | ? / ? | P | ? | Listing/terminal unresolved |
| NOTV | — / M→M | ? / ? / ? | 2026-07-27 | ? / ? | P | ? | Listing/terminal unresolved |
| NSA | 3405 / C→C | COMMON_STOCK / NYSE / USD | 2026-07-21 | ? / ? | P | ? | Listing/terminal unresolved |
| NUKK | — / M→M | ? / ? / ? | 2026-03-19 | ? / ? | P | ? | Listing/terminal unresolved |
| NUTR | 3414 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-10-15 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/2006468/000135445726000961/xslF25X02/primary_doc.xml) |
| NUVL | 3415 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-07-21 | ? / ? | P | ? | Listing/terminal unresolved |
| NXJ | 4193 / C→C | FUND / NYSE / ? | 2026-04-24 | ? / ? | P | ? | Listing/terminal unresolved |
| OBLG | — / M→M | ? / ? / ? | 2026-02-04 | ? / ? | P | ? | Listing/terminal unresolved |
| ODV | — / M→M | ? / ? / ? | 2026-07-27 | ? / ? | P | ? | Listing/terminal unresolved |
| OLPX | 3433 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-07-13 | ? / ? | P | ? | Listing/terminal unresolved |
| OMI | — / M→M | ? / ? / ? | 2026-02-27 | ? / ? | P | ? | Listing/terminal unresolved |
| ONTF | 3442 / C→C | COMMON_STOCK / NYSE / USD | 2026-03-31 | ? / ? | P | ? | Listing/terminal unresolved |
| OP | — / M→M | ? / ? / ? | 2026-01-09 | ? / ? | U | ? | [primary](https://www.sec.gov/files/company_tickers_exchange.json); identity/class unresolved |
| OS | 3452 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-04-01 | ? / ? | P | ? | Listing/terminal unresolved |
| PCH | 3477 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-02-04 | ? / ? | P | ? | Listing/terminal unresolved |
| PKST | 3491 / C→C | COMMON_STOCK / NYSE / USD | 2026-05-05 | ? / ? | P | ? | Listing/terminal unresolved |
| PLTS | 3494 / C→C | ADR / NASDAQ / ? | 2026-09-29 | ? / ? | P | ? | Listing/terminal unresolved |
| PLYM | 3495 / C→C | COMMON_STOCK / NYSE / USD | 2026-01-27 | ? / ? | P | ? | Listing/terminal unresolved |
| POAI | — / M→M | ? / ? / ? | 2026-02-04 | ? / ? | P | ? | Listing/terminal unresolved |
| PRA | 3504 / C→C | COMMON_STOCK / NYSE / USD | 2026-07-02 | ? / ? | P | ? | Listing/terminal unresolved |
| PSKY | 1813 / C→C | COMMON_STOCK / NYSE / USD | 2026-10-22 | ? / SKYD 2026-11-04 | R | ? | [primary](https://www.sec.gov/Archives/edgar/data/2041610/000110465926113913/tm2626659d7_8k.htm) SKYD; owner transition pending |
| PSTG | — / M→M | ? / ? / ? | 2026-06-12 | ? / P 2026-11-04 | K | 2026-11-04 | [primary](https://www.nasdaq.com/press-release/everpure-change-ticker-symbol-p-2026-04-07) P; RC current, exact match; old-symbol date conflict |
| PTNM | 3516 / C→C | ADR / NASDAQ / ? | 2026-07-29 | ? / ? | P | ? | Listing/terminal unresolved |
| PX | — / M→M | ? / ? / ? | 2026-04-10 | ? / ? | P | ? | Listing/terminal unresolved |
| QD | — / M→M | ? / ? / ? | 2026-02-18 | ? / ? | P | ? | Listing/terminal unresolved |
| QIPT | 3523 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-03-23 | ? / ? | P | ? | Listing/terminal unresolved |
| QLGN | — / M→M | ? / ? / ? | 2026-01-16 | ? / ? | P | ? | Listing/terminal unresolved |
| QMMM | 3524 / C→C | ADR / NASDAQ / ? | 2026-08-27 | ? / ? | P | ? | Listing/terminal unresolved |
| QRVO | 1843 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-10-05 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/1604778/000135445726000942/xslF25X02/primary_doc.xml) |
| QVCGA | — / M→M | ? / ? / ? | 2026-06-18 | ? / ? | P | ? | Listing/terminal unresolved |
| RAPT | 3531 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-03-06 | ? / ? | P | ? | Listing/terminal unresolved |
| RAY | 3532 / C→C | ADR / NASDAQ / ? | 2026-10-08 | ? / ? | U | ? | [primary](https://www.sec.gov/files/company_tickers_exchange.json); identity/class unresolved |
| REVG | 3547 / C→C | COMMON_STOCK / NYSE / USD | 2026-01-30 | ? / ? | P | ? | Listing/terminal unresolved |
| RITR | 3553 / C→C | ADR / NASDAQ / ? | 2026-09-24 | ? / RITRF 2026-11-04 | O | ? | [primary](https://data.sec.gov/submissions/CIK0001951229.json) RITRF; owner transition pending |
| RMAX | 1906 / C→C | COMMON_STOCK / NYSE / USD | 2026-08-24 | ? / ? | P | ? | Listing/terminal unresolved |
| RPTX | 3565 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-01-28 | ? / ? | P | ? | Listing/terminal unresolved |
| RYI | — / M→M | ? / ? / ? | 2026-04-10 | ? / ? | P | ? | Listing/terminal unresolved |
| SAVA | — / M→M | ? / ? / ? | 2026-05-11 | ? / ? | P | ? | Listing/terminal unresolved |
| SCVL | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| SDM | 3596 / C→C | ADR / NASDAQ / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| SEE | 3598 / C→C | COMMON_STOCK / NYSE / USD | 2026-04-09 | ? / ? | P | ? | Listing/terminal unresolved |
| SEM | 3601 / C→C | COMMON_STOCK / NYSE / USD | 2026-06-30 | ? / ? | P | ? | Listing/terminal unresolved |
| SEMR | 3602 / C→C | COMMON_STOCK / NYSE / USD | 2026-04-27 | ? / ? | P | ? | Listing/terminal unresolved |
| SGBX | — / M→M | ? / ? / ? | 2026-03-19 | ? / ? | P | ? | Listing/terminal unresolved |
| SGD | — / M→M | ? / ? / ? | 2026-02-04 | ? / ? | P | ? | Listing/terminal unresolved |
| SHCO | 3613 / C→C | COMMON_STOCK / NYSE / USD | 2026-01-28 | ? / ? | P | ? | Listing/terminal unresolved |
| SILA | 3622 / C→C | COMMON_STOCK / NYSE / USD | 2026-06-30 | ? / ? | P | ? | Listing/terminal unresolved |
| SKA | — / M→M | ? / ? / ? | 2021-07-16 | ? / ? | P | ? | Listing/terminal unresolved |
| SKBL | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| SKYT | 3628 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-08-07 | ? / ? | P | ? | Listing/terminal unresolved |
| SLNO | 3634 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-05-18 | ? / ? | P | ? | Listing/terminal unresolved |
| SLP | 2032 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-10-07 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/1023459/000135445726000953/xslF25X02/primary_doc.xml) |
| SLRX | — / M→M | ? / ? / ? | 2026-03-06 | ? / ? | P | ? | Listing/terminal unresolved |
| SMLR | 3639 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-01-21 | ? / ? | P | ? | Listing/terminal unresolved |
| SNBR | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| SNCY | 3643 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-05-15 | ? / ? | P | ? | Listing/terminal unresolved |
| SNV | 3648 / C→C | COMMON_STOCK / NYSE / USD | 2026-01-02 | ? / ? | P | ? | Listing/terminal unresolved |
| SOF | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| SOPA | — / M→M | ? / ? / ? | 2026-08-07 | ? / ? | P | ? | Listing/terminal unresolved |
| SSSS | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| STEL | 3673 / C→C | COMMON_STOCK / NYSE / USD | 2026-06-30 | ? / ? | P | ? | Listing/terminal unresolved |
| STKL | 3678 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-05-15 | ? / ? | P | ? | Listing/terminal unresolved |
| STSS | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| SUUN | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| SVACU | 3695 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-07-10 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/2074850/000135445726000666/xslF25X02/primary_doc.xml); unit class only |
| TALK | 2134 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-08-18 | ? / ? | P | ? | Listing/terminal unresolved |
| TBH | — / M→M | ? / ? / ? | 2026-06-30 | ? / ? | P | ? | Listing/terminal unresolved |
| TBPH | 2144 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-09-25 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/1583107/000135445726000901/xslF25X02/primary_doc.xml) |
| TBRG | 3713 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-07-13 | ? / ? | P | ? | Listing/terminal unresolved |
| TEF | — / M→M | ? / ? / ? | 2026-03-13 | ? / ? | P | ? | Listing/terminal unresolved |
| TERN | 3721 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-05-15 | ? / ? | P | ? | Listing/terminal unresolved |
| TGNA | 3729 / C→C | COMMON_STOCK / NYSE / USD | 2026-03-20 | ? / ? | P | ? | Listing/terminal unresolved |
| THAR | — / M→M | ? / ? / ? | 2026-04-10 | ? / ? | P | ? | Listing/terminal unresolved |
| THR | 3733 / C→C | COMMON_STOCK / NYSE / USD | 2026-05-29 | ? / ? | P | ? | Listing/terminal unresolved |
| THS | 3734 / C→C | COMMON_STOCK / NYSE / USD | 2026-02-10 | ? / ? | P | ? | Listing/terminal unresolved |
| TIVC | — / M→M | ? / ? / ? | 2026-06-29 | ? / ? | P | ? | Listing/terminal unresolved |
| TMHC | 3747 / C→C | COMMON_STOCK / NYSE / USD | 2026-07-23 | ? / ? | P | ? | Listing/terminal unresolved |
| TOI | — / M→M | ? / ? / ? | 2026-08-11 | ? / ? | P | ? | Listing/terminal unresolved |
| TPH | 3752 / C→C | COMMON_STOCK / NYSE / USD | 2026-05-13 | ? / ? | P | ? | Listing/terminal unresolved |
| TRUE | 3763 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-01-28 | ? / ? | P | ? | Listing/terminal unresolved |
| TSE | — / M→M | ? / ? / ? | 2026-04-27 | ? / ? | P | ? | Listing/terminal unresolved |
| TWO | 3780 / C→C | COMMON_STOCK / NYSE / USD | 2026-08-24 | 2026-08-24 / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/1465740/000087666126000795/xslF25X02/primary_doc.xml); continuing other class excluded |
| UBXG | — / M→M | ? / ? / ? | 2026-07-27 | ? / ? | P | ? | Listing/terminal unresolved |
| UDMY | 3785 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-05-11 | ? / ? | P | ? | Listing/terminal unresolved |
| ULY | — / M→M | ? / ? / ? | 2026-04-29 | ? / ? | P | ? | Listing/terminal unresolved |
| UOKA | — / M→M | ? / ? / ? | 2026-05-21 | ? / ? | P | ? | Listing/terminal unresolved |
| USEG | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| VERO | 3803 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-04-06 | ? / ? | P | ? | Listing/terminal unresolved |
| VIT | 3812 / C→C | ADR / NYSE / ? | 2018-02-22 | ? / ? | P | ? | Listing/terminal unresolved |
| VRAR | — / M→M | ? / ? / ? | 2026-04-10 | ? / ? | P | ? | Listing/terminal unresolved |
| VRE | 3824 / C→C | COMMON_STOCK / NYSE / USD | 2026-05-26 | ? / ? | P | ? | Listing/terminal unresolved |
| VSCO | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| VTYX | 3827 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-03-04 | ? / ? | P | ? | Listing/terminal unresolved |
| VVPR | — / M→M | ? / ? / ? | 2026-05-14 | ? / ? | P | ? | Listing/terminal unresolved |
| WAI | — / M→M | ? / ? / ? | 2026-07-23 | ? / ? | P | ? | Listing/terminal unresolved |
| WBD | 2365 / C→C | COMMON_STOCK / NASDAQ / USD | 2026-10-06 | ? / ? | D | ? | [primary](https://www.sec.gov/Archives/edgar/data/1437107/000119312526415091/d155700d25.htm) |
| WBS | 3837 / C→C | COMMON_STOCK / NYSE / USD | 2026-08-20 | ? / ? | P | ? | Listing/terminal unresolved |
| WGRX | — / M→M | ? / ? / ? | 2026-07-29 | ? / ? | P | ? | Listing/terminal unresolved |
| WKEY | 3849 / C→C | ADR / NASDAQ / ? | 2026-10-14 | 2026-10-14 / ? | U | ? | [primary](https://www.sec.gov/files/company_tickers_exchange.json); identity/class unresolved |
| WLAC | — / M→M | ? / ? / ? | 2026-05-18 | ? / ? | P | ? | Listing/terminal unresolved |
| WSR | 3858 / C→C | COMMON_STOCK / NYSE / USD | 2026-07-13 | ? / ? | P | ? | Listing/terminal unresolved |
| WTO | — / M→M | ? / ? / ? | 2026-07-17 | ? / ? | P | ? | Listing/terminal unresolved |
| XTKG | 3871 / C→C | ADR / NASDAQ / ? | 2026-04-15 | ? / XTKGF 2026-11-04 | O | ? | [primary](https://data.sec.gov/submissions/CIK0001754323.json) XTKGF; owner transition pending |
| ZYXI | — / M→M | ? / ? / ? | 2026-03-26 | ? / ? | P | ? | Listing/terminal unresolved |

## Publication, downstream debt and next actions

Exact additional Source rows: **none**. Exact additional Yahoo rows: **none**. Total inserted: **0**. Existing USA rows modified/deleted: **0**. No production price insertion owner or derived publisher was invoked. Investigation caches/evidence were written only under `/tmp/stockcore-price12c/Temp/`; the persistent operational price/analysis/Source databases, identities, universes and statuses were not opened writable. No production mutation needs a publication receipt or recovery retry. Independent postflight verified all 1,161 pinned original/context/current-successor price rows exactly, all 27 Source heads and all 290 original route sets, unchanged price/analysis database size/inode/mtime, and unchanged protected configuration, financial pointer/journal and PRICE-11 debt-ledger hashes. The final runtime check again found no workers or held native locks and the same service invocation/timer state.

Newly affected technical outputs: **none**. No Dow recalculation was needed or performed. PRICE-11’s outstanding divergence/candlestick reconciliation, subsequent relevance refresh, and affected DC/EC membership/group/report recovery remain exactly as recorded in `data/price_history_reconciliation/price11/derived_obligations.json`; its baseline hash is pinned and unchanged. No stale output was marked current, and end-to-end derived acceptance is not claimed. INM, OMXH, Source/P03/P04 execution and Fundamentals remediation remain outside this task.

Next actions are owner-specific: qualify explicit identity/action/unit transitions for the 11 verified missing continuing securities before testing their true RC anchors and inserting missing sessions; reconcile the copied ADR/ordinary categories and avoid preferred/note/unit substitutions; obtain authoritative listing/trading evidence for the remaining provider-limited and class-conflict cases; and obtain compatible native historical revision/unit evidence for the 26 unproven anchor cases. SUPN requires explicit merger/security/economic review. If an anchor ages outside the six completed sessions, this task grants no window extension. No different OHLCV provider, automatic retry, universe policy or broad identity migration was introduced.

Large retained evidence is in `/tmp/stockcore-price12c/Temp/output/{holds_final,fallback_final,summary,baseline,clock,preservation_postflight}.json`, with public/native provider payloads in `provider/`, fresh runtime/host observations and focused test logs in `output/`. `evidence_manifest.json` pins task inputs, outputs, code and retained payload hashes. These generated artifacts are outside Git. The local commit contains only this report, the revision-policy change and the two task-owned test files. The native price bridge resolves the exact requested ticker, and its insertion owner keys prices by ticker/date; neither accepts a qualified successor-transition token. Existing canonical aliases therefore do not authorize redirecting old price history. No owner-qualified price identity transition was established for the 11 missing continuing securities.
