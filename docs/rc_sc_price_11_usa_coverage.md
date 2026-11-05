# PRICE-11 — USA immutable history, revision qualification and fallback coverage

Status as of November 5, 2026: targeted USA append repair completed; genuine or unproven safety cases remain held. Historical USA OHLCV rows modified: **0**. See the coordinating [StockCore report](../../stockcore/docs/rc_sc_price_11_revision_and_history_reconciliation.md) and [OMXH report](rc_sc_price_11_omxh_finality.md).

## Original November 5 accounting

These are the original PRICE-10 run's counters, not PRICE-11's later corrections:

| Source-route ticker outcome | Tickers | Source rows |
| --- | ---: | ---: |
| No new accepted Source session | 36 | 0 |
| One new session | 3,613 | 3,613 |
| Two new sessions | 10 | 20 |
| Three new sessions | 1 | 3 |
| Total Source routes | **3,660** | **3,636** |

The ten two-session tickers were EDD, EXG, HQL, JPC, KTF, MEGI, NKX, OIA, PTA and WIW (November 3–4). VMO received November 2–4. The 36 no-new cases are included in 3,660; they are not another route category. No-new means no newer qualified accepted Source observation, not proof that the ticker traded through November 4 or had a complete current calendar.

There were also **303 Yahoo bridge routes**, of which **12 actually inserted one November 4 row each**. Thus total USA insertion was **3,636 + 12 = 3,648**. A zero `rows_inserted_from_fallback` service counter refers to the separate optional missing-OHLCV recovery mechanism; it does not count ordinary Yahoo history reached through the bridge's Yahoo routing. The premise that 303 Yahoo routes produced zero actual rows is incorrect.

The remaining 291 Yahoo routes were older than November 4: 276 had attributable native no-usable-data journal messages; 15 had nonempty history without a new usable date. Their routes comprised 124 missing Source tickers and 167 no-longer-eligible dated Source routes. Yahoo's generic “possibly delisted” text is not authoritative delisting evidence.

## Immutable-history revision contract

The user's addendum governs: retain existing USA RC observations, diagnose later accepted Source revisions, and append eligible newer sessions when identity, session and economic units are qualified. No volume tolerance was widened.

`services/price_revision_policy.py` binds a mismatch to an actual native Source daily revision receipt and `source_changes` witness, including the revised session and fields. Initial imports are not revision proof. The session must belong to the latest six completed sessions of its accepted calendar. An earlier retained revision receipt can qualify if identity/calendar dependencies still match; the window is never extended into arbitrary old history.

Price continuity, compatible historical peer units, native Source availability, adjusted-factor/action checks and the existing persistent-scaling guard remain required. A common material price multiplier or unproven unit context remains held. Native hard holds take precedence over Yahoo fallback. `stockcore_price_provider.py` pins the exact Source dependency, receipt and action fingerprint and holds Source's acceptance lock through native RC insertion, rechecking Source references and RC anchor/splits immediately before commit.

Detailed diagnostics separately classify `NON_BLOCKING_HISTORICAL_REVISION` and `SAFETY_HOLD`. They include old/current OHLCV, raw Source/adjustment context, changed fields, absolute/relative differences, security/session, receipt/revision, and eligible/actually appended dates. Normal summaries contain aggregate counts and bounded examples. Ignored `data/price_bridge_revisions/` retains at most six session records per security; deterministic old/new-value deduplication avoids fresh warnings for unchanged differences even when an unrelated Source head advances.

## Individual reassessment of the 436 original holds

| Original group | Non-blocking / resolved | Retained | Reason changed |
| --- | ---: | ---: | --- |
| 408 volume holds | **394** | **14** | No group reassignment |
| 28 price/factor holds | **14** | **14** | INM now has explicit `SOURCE_UNIT_HOLD` |
| Total | **408** | **28** | INM remains protected |

All 346 newly volume-held November 3 anchors qualified; 48 of 62 older October 30 volume anchors qualified. Fourteen of fifteen newly price-held tickers qualified; INM did not. All thirteen older price/factor holds remain held.

The 436 original same-session comparisons contain 436 Volume differences, 7 Open, 21 High, 21 Low and 6 Close differences (fields overlap). Of the 408 non-blocking comparisons, all have Volume differences; Open/High/Low/Close counts are 2/10/12/2. Retained comparisons have corresponding counts 5/11/9/4 plus 28 Volume differences. There are 407 volume-only comparisons and 29 also involving OHLC. The live bridge emitted 435 detailed anchor diagnostics; INM was rejected earlier by the new native Source quality hold. The durable historical inventory explicitly retains INM's original comparison too.

Retained ordinary-revision qualification reasons are: 13 without a qualifying ordinary-overlap witness, 12 without independently compatible historical unit context, 2 unqualified native revision receipts, plus INM's confirmed unit/action defect. These are not assertions that all 27 other held prices are economically wrong.

The fourteen retained volume tickers are BEAG, CDT, ETY, FFAI, GGLL, MEGL, MKDW, RBNE, RKLX, SHFS, TGL, UTHR, XXII and YMAT. The thirteen retained price/factor tickers other than INM are ACP, AWF, BRKRP, CHI, CHW, DHF, ECC, EOD, FIGXU, FPF, HIO, KKRT and SUPN. Their exact qualification failures and native witness evidence remain in the inventory. BEAG's current provider volume agrees with Source, but this alone cannot prove the old RC quantity's economic compatibility or replace a qualifying native revision witness.

## Actual PRICE-11 USA publication

**503 Source rows for 408 tickers** were appended using the existing native `execute_ticker_ohlcv_update_plan` / `insert_missing_ohlcv_rows` path, with the new Source publication guard. Distribution:

- 360 tickers: November 4 only.
- 47 tickers: November 2, 3 and 4.
- ONCO: November 2 and 3 only; no qualified accepted November 4 Source observation was available. No bar was invented.

Source row totals by date: November 2 **48**, November 3 **48**, November 4 **407**. AAPL's November 3 Volume remains exactly **62,093,400**, despite Source's accepted **63,160,000**. Its qualified November 4 observation was appended, including accepted Volume **89,523,300**.

SSKN received **one** additional November 4 Yahoo row: adjusted OHLC approximately 0.0001, Volume 2,700. Its retained November 3 anchor (OHLC approximately 0.0002, Volume 10,309) matched the fresh provider anchor exactly; no split appeared in the bounded returned observations. The [issuer's Nasdaq delisting notice](https://investors.strataskinsciences.com/news-releases/news-release-details/strata-skin-sciences-confirms-nasdaq-delisting/) and [issuer filing](https://strataskinsciencesinc.gcs-web.com/static-files/ea3f777d-479a-4bd9-a002-6e2d589faa47) distinguish Nasdaq delisting from subsequent same-symbol OTC trading. The route remained an explicitly permitted closed Source route with no overriding safety hold. No split/backfill or historical replacement ran.

Total USA additions: **504 rows, 409 tickers**. Exact new IDs: **15,604,528–15,605,031**. Date totals including SSKN: 48 / 48 / 408 for November 2 / 3 / 4. Existing USA rows modified/deleted: **0**. All 1,308 retained original anchor/context row identities and values independently matched after publication. Every new row matched its pinned accepted Source row or SSKN's retained provider observation. No other new market/date scope appeared.

Fresh requalification yielded zero eligible new Source rows for all 408 repaired Source tickers. SSKN repeat insertion yielded zero. New-date duplicates were checked independently. No provider request was made during publication or replay verification.

## The 291 originally stale Yahoo cases

| Outcome class after PRICE-11 | Tickers |
| --- | ---: |
| CURRENT_FOR_ELIGIBLE_SESSION | **1** (SSKN) |
| PROVIDER_NO_DATA | **290** |
| INACTIVE_OR_DELISTED_VERIFIED | 0 |
| SOURCE_ROUTE_UNAVAILABLE | 0 |
| MISSING_OBSERVATION_REQUIRES_REPAIR | 0 conclusively demonstrated remaining |
| SAFETY_HELD | 0 within this Yahoo-only cohort |
| UNRESOLVED | 0 as the primary provider-result class |

**Last eligible trading session remains UNRESOLVED for all 290 provider-limited cases.** This is deliberately a second dimension of the inventory: a provider no-data result does not establish terminal trading, current coverage, or absence of a valid newer observation elsewhere. Fourteen of the fifteen nonempty/no-new cases were checked once more in a bounded native request and still had no usable newer session. DBRG's extra NaN observation was rejected by the normal converter. The other 276 were classified from retained native evidence without another universe retry. No ticker was declared inactive from Yahoo's generic error alone.

Exact per-ticker latest observations, route reasons, provider evidence and eligibility uncertainty are in ignored `data/price_history_reconciliation/price11/fallback_inventory.json`. Resolving actual terminal dates or alternate-provider coverage for these 290 requires additional instrument-specific evidence; no repeated requests or unattended retries were scheduled.

## Recovery, derived state and operational limits

Durable `price_attempt.json` precedes the first insertion and contains exact scope, Source pins, originals, code hashes and pending derived obligations. `usa_progress.json`, `usa_result.json`, `sskn_result.json`, `historical_difference_inventory.json` and `price_postflight.json` retain actual outcomes. A partial/ambiguous attempt is not automatically retried.

Native Dow was explicitly recalculated from each ticker's earliest added session for all 409 repaired USA tickers, preserving earlier events. The combined OMXH/USA recovery is described in the OMXH report. Divergence/candlestick/relevance and affected DC/EC refresh obligations remain explicit; end-to-end derived consistency is **not certified**.

The six-session/receipt/compatible-peer rule intentionally leaves unproven cases held. The bridge diagnoses the compared historical anchor; it does not scan or reconcile all legacy history. Ordinary USA Yahoo fallback outside the scheduled morning context retains its legacy date cap; this change does not introduce a universal USA/crypto finality calendar. No unsafe Source hold can be bypassed by this fallback.

Validation: 399 distinct focused RC test cases passed across overlapping groups, plus 5 native StockCore quality-hold tests. Full suite: NO. No scheduler/service starts, schedule changes, Fundamentals changes or push.
