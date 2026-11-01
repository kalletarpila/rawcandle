# RC-SC-PRICE-01: StockCore data compatibility

Study: 2026-11-01. StockCore HEAD `20d3cdcddf82fdfac29ae652219fd1725eea4b7b`.
Source was read only with SQLite URI `mode=ro`, query_only, explicit closure and
bounded snapshots. No staging payload was imported. See [current contract](rc_sc_price_01_current_provider_contract.md),
[plan](rc_sc_price_01_implementation_plan.md), [evidence](rc_sc_price_01_acceptance_evidence.md).

## Accepted Source representation

Actual Source: `/home/kalle/projects/stockcore/runtime/osakedata_ng.db`.
It is a projection-mode Store, application ID `0x53434f52`, schema/user_version 5,
currently **DELETE journal**, not WAL. RawCandle also uses DELETE journal.

| Contract | Current representation and use |
| --- | --- |
| Official identity | securities.security_id; company_id is distinct and nullable; payload contains market, eligibility, type and evidence |
| Ticker aliases/routes | dated `routes`, provider=yahoo, accepted flag, half-open valid_from/valid_to; no separate ticker_aliases table |
| Collection | memberships(scope=collection); not the RC scheduler's ticker selector |
| Accepted prices | source_observations(security_id,session,payload,quality_id,segment,receipt_id), joined source_quality through **source_accepted view** |
| Payload fields | Open, High, Low, Close, Adj Close, Volume, ticker, vintage |
| Publication head | source_heads revision/dependency/receipt_id; SourceDependency binds security, identity, calendar and source revision |
| Acceptance evidence | source_receipts status, intent, summary, created_at; source_coverage per session; source_changes pending invalidation |
| Unaccepted evidence | source_received and failed/held receipts; never price authority for the bridge |
| Actions | corporate_actions kind/status/current version/payload/reason/receipt_id; split ratio NEW_PER_OLD, dividends sourced cash/ex-date |
| Calendars | source_calendars plus settings calendar_binding:<id>; binding can preserve an earlier dependency hash after a qualified prospective extension |
| Other holds | source_quality_hold:<id>, held nondividend actions, route/eligibility changes, and daily schedule request.held operator exclusions |

Current canonical reader is **`stockcore.prices.PriceReader.read`**. It checks
calendar binding, current dependency tokens, dated resolver, action/unit holds,
ordinary/adjusted quality and required volume. Per-session statuses are AVAILABLE,
HELD or MISSING; values exist only for AVAILABLE. It retains absence positions,
UNKNOWN_PREFIX, qualified NO_PRICE_OBSERVATION/ACTION_ONLY evidence, receipt,
vintage and segment. Its envelope status can be HELD with some AVAILABLE sessions;
do not discard every ticker globally because of one absent session.

An unsuccessful later fetch does not erase healthy accepted observations. Conversely,
raw stored observations or a COMPLETE historical receipt alone do not override a
current dependency/action/route hold. A scalar maximum stored date is not a qualified
cutoff. Per-session reader results and current action/operator exclusions decide use.

PriceReader opens through Store.read, which internally opens a normal read/write
SQLite connection and then sets query_only. **That is insufficient for the explicit
runtime no-write-access requirement.** The disposable study subclass changes only
the connection open to URI mode=ro and retains canonical Store validation/reader
logic. A future RC-owned read-only facade must likewise fail closed on foreign IDs,
schema/mode drift and missing files, with no initialize/migrate/transaction methods.
Never instantiate StockCore services that initialize operation storage or acquisition.

## Ticker mapping and measured coverage

RC candidate aggregation exactly mirrors current service SQL. Counts observed at
`2026-11-01T14:06:58.418627+00:00`; reads are sequential per-ticker snapshots,
not one global cross-database snapshot. Recheck at implementation/activation.
These are all selected candidates, before the service's needs_update filter.
One USA candidate, BTC-USD, already has RC's 2026-11-01 maximum and would be
already_current; 4,621 candidates would reach the update branch on this date.

Minimal mapping: RC `usa` → StockCore `USA`, exact already-uppercase Yahoo ticker
→ dated `identity.resolve(ticker=..., as_of=...)`, one accepted security and route,
current active security/eligible interval. Recheck each returned session against the
same instrument. Use actual dated routes, never provider-association guesses,
related-symbol heuristics, punctuation substitutions or merger stitching. The resolver
normalizes case internally; the proposed bridge first requires a verified RC convention.
RC omxh has no supported Source market/calendar here; it must skip without Yahoo.
No new security master or ID allocation is needed.

| Scheduled selection | Unique accepted mapping | Missing ticker | Ineligible/closed route | Ambiguous | Unsupported market | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| usa | 4,201 | 127 | 196 | 0 | 0 | 4,524 |
| omxh | 0 | 0 | 0 | 0 | 98 | 98 |
| Total | 4,201 | 127 | 196 | 0 | 98 | 4,622 |

No unverified-case or inactive-instrument-only classifications occurred after dated
resolution. Missing examples: ABL, ABVE, AGH. Closed/ineligible examples: ACLX, ALUR,
APGE; these are not reclassified as absent aliases. Zero observed ambiguities is not
permission to choose a first match: synthetic ticker and ID resolver ambiguity checks pass.

Of 4,201 uniquely mapped tickers, canonical six-completed-session probes found
**4,169 with qualified adjusted-usable recent rows**, 24 with no recent available
rows, and 8 with some HELD sessions (AXG, ENLV, MSGS, NUWE, NXXT, OMEX, SCAG, WHLR).
The eight are withheld conservatively as whole requested scopes; they are not
automatically split into independent tradable segments.

Nine explicit Source operator holds (ACVA, ATKR, BZH, FGNX, LU, MAMK, MIMI, NVNI,
PASW) overlap the 24 unavailable tickers. They must remain holds even when an older
accepted reader window would otherwise return good prices. Current daily schedule
is configured **23:45 Helsinki, enabled=0**; this is a read-only fact, not a readiness
gate for all accepted historical rows and not proof of systemd runtime state.

Further conservative screening compares six recently qualified sessions with RC's
stored OHLCV using the installed yfinance float formula, and reconciles processed
Source split dates/ratios against RC corrected splits:

| Mutually exclusive preliminary disposition | Tickers |
| --- | ---: |
| Candidate passing recent exact OHLCV and split screen | 3,236 |
| UNSAFE_TO_IMPORT: recent overlap mismatch | 931 |
| UNSAFE_TO_IMPORT: split reconciliation conflict | 2 |
| Source operator hold | 9 |
| Other recent Source gap/unavailable | 15 |
| Source HELD | 8 |
| Missing ticker | 127 |
| Ineligible route | 196 |
| Unsupported market | 98 |
| Total | 4,622 |

Thus **1,386 are already withheld by this screen**. The 3,236 are **candidates,
not certified safe imports**: whole-history compatibility is not established for
all of them. No matched ticker has a qualified recent session newer than its RC
maximum date at this observation. Do not confuse 4,201 identity matches, 4,169 recent
Source qualifications, 3,236 preliminary candidates and zero presently newer tickers.

Across matched recent overlap, 241 tickers have OHLC differences, 857 have volume
differences (overlapping sets). All 241 price cases also differ beyond a diagnostic
one-ppm screen; no tolerance was approved as an acceptance rule. PLRZ's corrected
RC split ratio differs from Source's 1/6, and SCLX's differs from Source's 1.606.
No rounding, ratio orientation guess or history rewrite was used to reconcile them.

## Actual cutoffs and availability

Source contains accepted observations for 4,288 securities, 7,614,464 rows, overall
dates 2018-01-01 through **2026-10-30**. These aggregate counts are inventory,
not all-market or consumer eligibility. For the 4,201 matches, stored latest dates:

| Stored latest date | Tickers |
| --- | ---: |
| 2026-10-16 | 10 |
| 2026-10-21 | 14 |
| 2026-10-23 | 1 |
| 2026-10-26 | 4 |
| 2026-10-28 | 3 |
| 2026-10-29 | 3 |
| 2026-10-30 | 4,166 |

Source six completed exchange sessions at this study end on 2026-10-30. USA
calendars cover through 2028/2030 in current shared definitions, with preserved
dependency hashes to 2026 definitions. BTC-USD instead has a CRYPTO_UTC_24_7
calendar in UTC, through 2030; its latest completed day is Oct 31 and is MISSING
in the recent reader scope (five prior available days through Oct 30). Market=USA
does not make crypto an equity or override its instrument calendar. Calendars supply holidays, early closes,
DST and completed-session clocks; Calendar.requested range end is **inclusive**.
Convert RC's exclusive end by subtracting one calendar day, intersect with completed
sessions, and return empty if the intersection is empty. Do not request an
uncompleted session or synthesize a weekday calendar. Preserve exchange-local date
labels; do not normalize daily sessions by taking UTC dates after arbitrary shifts.

## Price basis: compatible formula, unequal histories

StockCore yfinance transport **1.7.0** explicitly requests period=None, interval=1d,
auto_adjust=False, actions=True, repair=False, prepost=False, back_adjust=False,
keepna=True, rounding=False and the request timeout. Six fields originate in the
same returned frame vintage. Approved Source normalization permits missing Adj Close
→ same-row Close and missing Volume → 0, safe int64 truncation; provenance is often
UNKNOWN_UPSTREAM_NORMALIZATION. Equality or zero does not prove the original field
was present. These exceptions are accepted Source policy, not evidence of exact
parity with an independently captured RC response.

Returning ordinary OHLC would silently switch RawCandle's price basis. Deterministic
same-vintage compatibility uses:

```text
factor = float(Adj Close) / float(Close)
Open,High,Low = corresponding ordinary float * factor
Close = float(Adj Close)                 # direct substitution, not Close * factor
Volume = accepted provider volume       # no dividend or split multiplier
```

Require positive finite denominator/factor/outputs, qualified adjusted_usable and
volume units. Never reconstruct from dividend cash sums, never fill an invalid
factor with 1, never multiply by a split again. Current PriceReader's adjusted
calculation uses Decimal qualification/multiplication and returns Close*factor;
that can differ in the last bit from yfinance's float/direct-Close output. Use its
qualification semantics, then the exact RC-facing float operation on the **same
snapshot's six fields**. This does not authorize changing StockCore's Ordinary
technical default or pretending a production consumer is research.

`PriceReader(basis='DIVIDEND_ADJUSTED')` without research=True currently raises
**ADJUSTED_BASIS_REQUIRES_EXPLICIT_RESEARCH**. Research=True was used only for
the offline comparisons. A future production bridge needs an explicitly reviewed
RC-local compatibility reconstruction on qualified Ordinary + accepted six fields,
or a separately authorized owner reader extension. No owner policy bypass is approved.

Retained local Yahoo fixtures: 30 ordinary frames, **63,962 rows** reproduce installed
auto_adjust bit-for-bit for OHLC; volume is unchanged. Eleven separately captured
True validation windows share **183 rows**: none differs beyond rtol=atol=1e-6,
but exact equality is not universal. No fresh provider request was made. This verifies
the transform, not equivalence of StockCore's later capture or RC stored histories.

## Representative compatibility matrix

All Source comparisons use current accepted rows and the public canonical reader
with a read-only Store facade. No sample's action ratio was applied to its prices.

| Case / window | Measured result | Import conclusion |
| --- | --- | --- |
| AMD, 2026-10-01–13, nondividend control | 9 qualified rows; 8 exact OHLC vs RC, one outside 1ppm; all 9 volumes differ | Formula compatible; stored parity UNSAFE_TO_IMPORT |
| AAPL dividend, 2024-08-01–20 | 14 qualified rows; no exact RC OHLC rows, max absolute difference 0.402047; volumes match | Same adjustment definition, different vintage/history; unsafe exact-history claim |
| NVDA 10:1, 2024-06-03–18 | 12 qualified rows, PROCESSED 2024-06-10 split; RC historical OHLC differs, volumes match | No double split; not exact RC historical parity |
| AAPL older 4:1, 2020-08-24–09-04 | 10 qualified rows; processed split; RC adjusted prices differ | No conversion to original unsplit units; withhold incompatible scope |
| WMT 3:1, 2024-02-20–03-05 | 11 qualified rows, processed split; historical OHLC differs | Same limitation as NVDA; cannot rewrite RC to agree |
| NFE reverse 1:50, 2026-09-10–18 | 6 qualified rows, one UNKNOWN prefix position; 5 common RC rows exactly match OHLCV | Use only qualified available interval; no claim about unknown prehistory |
| BTLN reverse 1:8, 2026-09-25–30 | 3 qualified bars; Sep 28 accepted NO_PRICE_OBSERVATION plus independent processed split; no common RC rows | Preserve absence; no invented action-day price or parity proof |
| QQQ/SPY ETFs, 2026-10-01–13 | Each 9 qualified rows; OHLC exact vs RC, all volumes differ | Price formula works; exact OHLCV import unsafe pending resolution |
| PLTR short prefix, 2020-09-28–10-05 | 4 qualified rows exact vs RC, 2 UNKNOWN_PREFIX positions | No prefix filling, listing-date invention or borrowed warm-up |
| VATE reverse-split diagnostic window, 2020-05-01–22 | Only 7 current accepted rows, exact vs RC; 9 UNKNOWN_PREFIX positions | Historical invalid-factor fixture is not current accepted authority |
| DEC old diagnostic, 2023-06-28–07-06 | 0 accepted bars, 6 MISSING positions | Skip; retained ordinary fixture cannot create accepted Source data |
| ALUR inactive, 2026-10-01–16 | 0 accepted bars in sample; current route closed Oct 17 | Current mapping skip; historical presence never reactivates it |
| AXG held, 2026-10-23–30 | 4 HELD + 2 MISSING, action/unit/eligibility reason | Skip scope, not raw stored-price fallback |
| ACA stale, 2026-10-23–30 | 6 MISSING, latest stored Oct 21 | No new qualified rows; no global freshness gate |
| LU operator-held, 2026-10-20–30 | 9 MISSING; explicit Source ADS/unit review hold | Skip even if an older slice might be numeric |
| PLRZ/SCLX current split inventories | Corrected RC events have different ratio values | UNSAFE_TO_IMPORT; do not insert/relabel/reprocess events |

The retained same-vintage fixtures include invalid zero/negative adjustment factors
(DEC/NFE/VATE) and the True keepna date-removal difference. Mathematical reproduction
of invalid outputs is **not** source eligibility; current accepted intervals can be
narrower after later Source qualification. Existing synthetic tests also cover zero
denominator/missing factor and invalid outputs. Do not infer all 30 retained tickers'
current production Source eligibility from those fixture checks.

## Corporate actions, revisions and bounded snapshots

Current inventory: 1,537 PROCESSED splits, 59 HELD splits; 73,232 RECORDED dividends,
386 HELD dividends. These are Source-wide action counts, not scheduled import counts.
PriceReader holds nondividend action boundaries; it does not blanket-hold Ordinary
prices for every dividend action hold. The bridge must still require adjusted_usable,
read applicable action evidence, respect operator holds and never fabricate dividends.
Identical processed split versions are no-ops for Source. Revised/new split evidence
requires full qualified Source replacement; failed replacement preserves accepted
data with holds. RawCandle's default destructive split callback is incompatible with
the requested no-history-rewrite bridge and must not be reached.

Source commits observations/actions/head/coverage/receipts atomically in its own
SQLite database. Derived analysis commits are separate and irrelevant to price
authority. A complete latest derived run is not required to read good Source prices.
Daily Source overlap catches only six sessions' revisions; older corrections require
owner repair. RawCandle insert-only writes cannot propagate either old dividend
factor changes or corrected existing bars. Whole-history equality was not tested
for all 3,236 candidates; do not certify it from six recent matching sessions.

DELETE journal means readers can delay writer commit. An isolated two-connection
probe confirmed SQLITE_BUSY on commit with an open reader and success immediately
after reader closure. No production write attempt was used. Metadata/reader probes
used 8,403 snapshots, maximum 2.033s including initial bounded identity/calendar
classification; overlap fetch snapshots max 0.000512s. These are observations,
not a latency SLA or proof of zero contention. A production facade should bound rows,
SQL time and busy timeout, fully materialize one ticker, close the Source connection,
then construct DataFrames, sleep, write RC and analyze. Do not use immutable=1 on
an active database, acquire Source writer locks or hold a job-wide snapshot. Concurrent
publication must expose either prior or next accepted snapshot, never staged rows.
