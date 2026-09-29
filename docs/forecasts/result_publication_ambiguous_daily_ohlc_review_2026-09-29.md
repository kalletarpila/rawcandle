# AMBIGUOUS result-publication review for daily OHLC research

Date: 2026-09-29  
Scope: all production `result_publication_v1` authority rows with status `AMBIGUOUS`  
Mode: read-only analysis; no authority, evidence, quarter, forecast, or scheduler writes

## Objective

The review asks whether exact SEC publication-timestamp ambiguity also changes the first full post-result trading day used by daily-OHLC research. It does not choose a canonical timestamp and does not weaken the accepted authority hierarchy.

All 651 AMBIGUOUS quarters and all 1,318 associated CONFLICT evidence rows were inspected. They represent 451 companies. Every evidence row is a distinct SEC accession, form 8-K, with `PRESENT_AND_DOCUMENT_CONFIRMED` Item 2.02 evidence. No 8-K/A evidence is present.

## Session and trading-day convention

Each SEC acceptance timestamp was converted from UTC to `America/New_York`, including daylight-saving transitions. Sessions use the reviewed simple convention:

- `PRE_MARKET`: before 09:30 ET
- `REGULAR_HOURS`: 09:30 ET through 15:59:59 ET
- `AFTER_MARKET`: 16:00 ET or later
- `UNKNOWN`: conversion or trading-day context unavailable

The repository has no narrowly discoverable market-calendar helper and neither `pandas_market_calendars` nor `exchange_calendars` is installed. The analysis therefore used read-only US daily rows in `data/osakedata.db` as the practical trading-date authority. It used each company's security ticker history; where a company had multiple security tickers, their derived day had to agree. The two companies without an active security still had their historical ticker and OHLC rows available. All 651 quarters had sufficient date coverage.

The first full post-result trading day was derived as follows:

- PRE_MARKET on an observed trading date D: D
- PRE_MARKET on a non-trading date: first observed trading date after D
- REGULAR_HOURS or AFTER_MARKET on D: first observed trading date after D
- missing or disagreeing ticker coverage: unavailable

This is a research derivation only. It is not a new publication authority.

## All-quarter classification

| Review bucket | Quarters | Percent |
|---|---:|---:|
| `SAME_EXACT_TIMESTAMP` | 0 | 0.00% |
| `SAME_DATE_SAME_SESSION` | 7 | 1.08% |
| `SAME_DATE_DIFFERENT_SESSION` | 2 | 0.31% |
| `DIFFERENT_DATE_SAME_EFFECTIVE_POST_DAY` | 4 | 0.61% |
| `DIFFERENT_EFFECTIVE_POST_DAY` | 638 | 98.00% |
| `INSUFFICIENT_CONTEXT` | 0 | 0.00% |
| Total | 651 | 100.00% |

The two `SAME_DATE_DIFFERENT_SESSION` cases also imply different effective days. Consequently, the independent research-usability result is:

| Research status | Quarters | Percent |
|---|---:|---:|
| `DAILY_RESEARCH_USABLE` | 11 | 1.69% |
| `DAILY_RESEARCH_AMBIGUOUS` | 640 | 98.31% |
| `DAILY_RESEARCH_UNAVAILABLE` | 0 | 0.00% |

Only 11 AMBIGUOUS quarters are practically harmless for daily-OHLC research. The remaining 640 materially change the first full post-result trading day and require resolution or exclusion before consumption.

Additional aggregate views:

- same local publication date: 9 (1.38%); different dates: 642 (98.62%)
- all candidates in the same session category: 377 (57.91%); multiple session categories: 274 (42.09%)
- same effective post-result trading day: 11; different effective days: 640
- session sets: AFTER+PRE 241, AFTER only 225, PRE only 152, AFTER+REGULAR 20, PRE+REGULAR 12, and all three 1

## Candidate distribution

| Candidate timestamps per quarter | Quarters |
|---:|---:|
| 2 | 636 |
| 3 | 14 |
| 4 | 1 |

The span between the earliest and latest candidate was at most one hour in 7 quarters, more than one hour but at most one day in 8, 2-7 days in 61, 8-30 days in 303, and more than 30 days in 272. There were no equal-timestamp conflicts.

Matching-method combinations were:

- exact period-end only: 546 quarters
- exact period-end plus explicit fiscal quarter: 77
- exact period-end plus reviewed Q4/full-year context: 16
- explicit fiscal quarter only: 8
- explicit fiscal quarter plus Q4/full-year context: 3
- Q4/full-year context only: 1

Thus most ambiguity is not caused by competing fiscal-text parsers. It is caused by multiple distinct Item 2.02 filings that independently match the same canonical quarter.

## Daily-usable cases

The seven same-date/same-session cases are:

- CF FY2025 Q1-Q4 and FY2026 Q1-Q2: two AFTER_MARKET filings on each result date; both imply the next trading day
- FIS FY2025 Q4: two PRE_MARKET filings on 2026-02-24; both imply 2026-02-24

The four different-date/same-effective-day cases are:

- ARKO FY2026 Q2: AFTER_MARKET 2026-08-06 and PRE_MARKET 2026-08-07; both imply 2026-08-07
- MNTK FY2025 Q2: AFTER_MARKET 2025-08-06 and PRE_MARKET 2025-08-07; both imply 2025-08-07
- MNTK FY2025 Q4: AFTER_MARKET 2026-03-11 and PRE_MARKET 2026-03-12; both imply 2026-03-12
- MNTK FY2026 Q2: AFTER_MARKET 2026-08-05 and PRE_MARKET 2026-08-06; both imply 2026-08-06

These 11 cases can later be consumed under a derived `DAILY_RESEARCH_USABLE` status while their canonical authority remains AMBIGUOUS.

The two same-date/different-session cases must not be treated as harmless:

- ABG FY2025 Q1: PRE_MARKET and AFTER_MARKET on 2025-04-29 imply 2025-04-29 versus 2025-04-30
- ORN FY2025 Q3: PRE_MARKET and AFTER_MARKET on 2025-10-29 imply 2025-10-29 versus 2025-10-30

## Recurring ambiguity patterns

All 1,318 conflict rows have distinct accession numbers and source references. Forty-one quarters reuse the same primary-document filename across separate accessions, but filenames such as `form8-k.htm` are not document identity.

A targeted official-SEC text review fetched 222 documents across 107 priority quarters: every reused-document-name case, all 11 daily-usable cases, both same-date/different-session cases, and all quarters for WOR, BKD, CF, CRGY, DMLP, DTE, FANG, IPAR, LCID, and OXY. It found:

- zero byte- or extracted-text-identical filing pairs
- 10 pairs with extracted-text similarity of at least 0.98, still with distinct accessions and timestamps
- preliminary, supplemental, amendment, and revision language in subsets, but not with semantics uniform enough for a keyword rule
- no SEC request failures during the targeted review

The recurring practical patterns are:

1. Separate filings days or weeks apart, both explicitly repeating the same period end. This dominates the population.
2. A result-date filing followed by a later Item 2.02 filing that repeats prior-quarter context. Yahoo often supports one date, but the later filing can still be valid evidence under the current matcher.
3. Same-day dual filings. CF's six recurring cases are daily-equivalent; ABG and ORN cross the PRE/AFTER boundary and are not.
4. Closely related or templated filings under different accessions. High textual similarity does not prove semantic duplication or identify the initial publication.
5. Mixed exact-period, explicit-quarter, and Q4/full-year matches. These are a minority and remain context-dependent.

Among the highest-repeat companies, WOR has eight materially different-effective-day quarters. BKD, CRGY, DMLP, DTE, FANG, IPAR, LCID, and OXY each have six, all materially ambiguous. CF has six, all daily-usable. Yahoo supports one candidate date in every reviewed quarter for WOR, BKD, CRGY, DTE, FANG, IPAR, LCID, and OXY; DMLP is mostly unavailable. This is strong prioritization evidence, not canonical authority.

## Yahoo corroboration

Yahoo/yfinance historical earnings dates were queried serially for all 451 identified tickers. No Yahoo evidence was written to production. Events were mapped inside the canonical period-end through +180-day window and compared in New York local time with the SEC candidate dates.

The review labels mean:

- `SUPPORTS_ONE_CANDIDATE`: exact Yahoo event instant equals only one SEC candidate instant
- `SUPPORTS_DATE_ONLY`: Yahoo matches the local date of only one SEC candidate, but not its exact instant
- `DOES_NOT_DISCRIMINATE`: Yahoo matches a date shared by multiple SEC candidates
- `CONFLICTS`: the nearest plausible Yahoo event date matches no SEC candidate date
- `UNAVAILABLE`: no usable historical Yahoo event in the reviewed window

| Yahoo result | Quarters |
|---|---:|
| `SUPPORTS_ONE_CANDIDATE` | 0 |
| `SUPPORTS_DATE_ONLY` | 524 |
| `DOES_NOT_DISCRIMINATE` | 44 |
| `CONFLICTS` | 51 |
| `UNAVAILABLE` | 32 |

Of the 524 date-only cases, Yahoo supports the latest SEC candidate in 466, the earliest in 51, and a middle candidate in 7. Therefore neither "always earliest" nor "always latest" is safe. Yahoo supports one date for 520 of the 640 daily-ambiguous quarters, but it remains secondary corroboration and cannot resolve those rows automatically. For the 11 daily-usable quarters, Yahoo does not discriminate in 7 and supports one date in 4.

## SwingMaster V3

No SwingMaster V3 lookup was needed. Current SEC metadata, targeted official filing text, Yahoo corroboration, and local OHLC coverage were sufficient to classify all 651 quarters and identify the priority population. The old repository was not located or scanned.

## Resolution-safety assessment

| Proposed future rule | Assessment | Evidence |
|---|---|---|
| All accepted candidates imply the same first full trading day | `SAFE_CANDIDATE` for a separate research status only | Deterministic for 11 quarters; does not select canonical timestamp |
| Multiple rows have exactly the same timestamp and source identity | `SAFE_CANDIDATE` in principle | Zero current cases; future implementation must require true identity, not filename |
| Resolve same-day/same-session conflicts to one timestamp | `NEEDS_MANUAL_REVIEW` | Daily-equivalent but exact canonical instant remains unresolved |
| Select the Yahoo-supported SEC date | `NEEDS_MANUAL_REVIEW` | Useful in 524 cases, but Yahoo is secondary and has 51 conflicts and 32 unavailable cases |
| Treat repeated primary-document filename as duplicate | `DO_NOT_AUTOMATE` | 41 cases, distinct accessions/source references; no exact text pair in targeted review |
| Treat high text similarity as duplicate | `DO_NOT_AUTOMATE` | 10 targeted pairs at similarity >=0.98, but none identical and semantics can differ |
| Choose earliest candidate | `DO_NOT_AUTOMATE` | Yahoo supports earliest only 51 times versus latest 466 and middle 7 |
| Choose latest candidate | `DO_NOT_AUTOMATE` | Same counter-evidence; later filings may be supplemental or repeated context |
| Resolve from preliminary/supplemental/amendment keywords | `DO_NOT_AUTOMATE` | Terms are context-sensitive and do not consistently identify initial publication |

No narrow rule found in this review safely reduces exact-timestamp ambiguity in production. The safe result is limited to a derived daily-research usability classification.

## Proposed research contract

Keep canonical authority unchanged and derive a separate status at query or research-build time:

```text
DAILY_RESEARCH_USABLE
  all accepted authoritative candidates imply one identical
  candidate_first_full_post_result_trading_date

DAILY_RESEARCH_AMBIGUOUS
  accepted authoritative candidates imply two or more first full
  post-result trading dates

DAILY_RESEARCH_UNAVAILABLE
  timestamp, timezone, security, or trading-date context is insufficient
```

The derived record should retain every candidate's UTC timestamp, ET timestamp, local date, session, effective trading date, source reference, and the calendar/OHLC snapshot identifier used for derivation. It must not populate `result_publication_timestamp_utc` or turn AMBIGUOUS authority into VERIFIED authority.

For the current production population this contract admits 11 quarters, blocks 640, and leaves none unavailable.

## Read-only verification

Before analysis:

- `data/fundamentals_v4.db`: SHA-256 `9c1c14be2f52165f93d4c9d30aba8bb64fc5489e37190ed9fb672ffa993caaad`
- `data/forecasts.db`: SHA-256 `8fc6785ce83f8a94a0cb80be8d1514e6a9f3ea1d42ac33b9d2081f83ffc9cd42`
- authority AMBIGUOUS rows: 651
- associated CONFLICT evidence rows: 1,318
- canonical integrity: `quick_check=ok`, zero foreign-key errors

After analysis:

- `data/fundamentals_v4.db`: SHA-256 `9c1c14be2f52165f93d4c9d30aba8bb64fc5489e37190ed9fb672ffa993caaad`, unchanged
- `data/forecasts.db`: SHA-256 `8fc6785ce83f8a94a0cb80be8d1514e6a9f3ea1d42ac33b9d2081f83ffc9cd42`, unchanged
- authority AMBIGUOUS rows: 651, unchanged
- associated CONFLICT evidence rows: 1,318, unchanged
- canonical integrity: `quick_check=ok`, zero foreign-key errors

All SQLite analysis connections used URI `mode=ro`. The SEC and Yahoo steps wrote only temporary analytical JSON under `/tmp`. No enrichment `--apply`, migration, forecast command, or scheduler command ran.

## Recommendation

First implement and test a non-production research projection for the 11 `DAILY_RESEARCH_USABLE` quarters, keeping canonical authority AMBIGUOUS. Then manually review the 640 `DAILY_RESEARCH_AMBIGUOUS` quarters in this order: ABG and ORN session-boundary cases; recurring WOR/BKD/CRGY/DTE/FANG/IPAR/LCID/OXY patterns where Yahoo supports one date; other Yahoo-supported cases; then Yahoo conflicts and unavailable cases. Any proposed canonical resolver rule must be validated against the complete 651-quarter set and the issuer/SEC hierarchy before a separate production change is considered.
