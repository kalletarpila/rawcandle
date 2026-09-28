# Fundamentals publication-boundary audit (2026-09-28)

## 1. Conclusion

Classification: **D. `PUBLICATION_BOUNDARY_NOT_RELIABLE_ENOUGH`**.

RawCandle cannot currently determine reliably when a quarterly result first
became public. Coverage is complete, but `first_public_result_date` was not built
from independent company, SEC, or earnings-release evidence. Its production
baseline was copied from the accepted Sharadar ARQ winner's `date`, the same
source used by `source_availability_date`. Routine refresh preserves the former
and may move the latter when the winning provider row changes.

This is adequate as a provider-date convention, but not as authority for the
question “what consensus was known immediately before the public release?”

## 2. Current field semantics

| Field | Current origin and contract |
|---|---|
| `period_end` | Sharadar ARQ winner `reportperiod` |
| `source_availability_date` | Current Sharadar ARQ winner `date`; it may change when the winner changes |
| `first_public_result_date` | Initial Sharadar `date` baseline, immutable during routine refresh; explicit repair is required to change it |

The original production-bootstrap path inserted
`first_public_result_date=NULL`. The implemented baseline operation copies
`source_availability_date` into every eligible null `first_public_result_date`,
and current production reflects that provider-date baseline. New canonical
quarters initialize both fields from the accepted winner's `date`. This makes
the field a preserved provider-date baseline, not independently verified
first-public evidence. It is neither manual review nor SEC/IR evidence.

Both columns are nullable by schema. A source date can be null when no acceptable
provider date exists, although current winner selection fails closed unless
Sharadar `date >= reportperiod`. `first_public_result_date` can be null before
bootstrap or initialization. Current production has no nulls in either field.

## 3. Sharadar ingestion mapping

The current path ingests `calendardate`, `reportperiod`, `fiscalperiod`, `date`,
and `lastupdated` from Sharadar Fundamentals. Winner selection is ARQ-only and
orders duplicate fiscal identities by `reportperiod`, then
`COALESCE(lastupdated,date)`, while rejecting a candidate whose `date` is before
`reportperiod`.

Exact mappings are:

- `reportperiod` -> `v4_quarter.period_end` and `source_reportperiod`
- `fiscalperiod` -> canonical fiscal year/quarter and `source_fiscalperiod`
- `date` -> provider `source_availability_date` -> canonical
  `source_availability_date`
- initial accepted `date` -> canonical `first_public_result_date`
- `calendardate` and `lastupdated` remain in provider observations

Provider evidence also preserves exact `fetched_at_utc`, and `provider_run`
stores exact run start/completion timestamps. Refresh observations put Sharadar
`lastupdated` into `observed_at_utc`; historical bulk observations leave it null.
In production, all 192,535 Sharadar Fundamentals observations have
`fetched_at_utc`, but only 6,875 have `observed_at_utc`. These timestamps do not
become the canonical quarter publication boundary. Canonical `created_at_utc`
and `updated_at_utc` describe canonical publication/rebuild work, not when the
issuer first released results.

## 4. Production coverage

Read-only SQL covered all 89,894 canonical quarters (FY2015-FY2027).

| Coverage | Count | Percent |
|---|---:|---:|
| `first_public_result_date` | 89,894 | 100.0000% |
| `source_availability_date` | 89,894 | 100.0000% |
| both | 89,894 | 100.0000% |
| first-public only | 0 | 0.0000% |
| source-availability only | 0 | 0.0000% |
| neither | 0 | 0.0000% |

For `source_availability_date - first_public_result_date`:

| Bucket | Count | Percent |
|---|---:|---:|
| negative | 20 | 0.0222% |
| same day | 89,860 | 99.9622% |
| +1 day | 0 | 0.0000% |
| +2 days | 0 | 0.0000% |
| +3-7 days | 1 | 0.0011% |
| >7 days | 13 | 0.0145% |

Median, p90, and p95 are all 0 days. Maximum positive lag is 146 days;
minimum is -109 days. Percentiles use linear interpolation. The mass at zero is
primarily a bootstrap artifact and must not be read as independent agreement.

## 5. Recent-quarter coverage

The FY2025+ subset contains 16,224 quarters. Both dates are present on all
16,224 rows (100.0000%); first-only, source-only, and neither are all zero.

| Bucket | Count | Percent |
|---|---:|---:|
| negative | 1 | 0.0062% |
| same day | 16,218 | 99.9630% |
| +1 day | 0 | 0.0000% |
| +2 days | 0 | 0.0000% |
| +3-7 days | 0 | 0.0000% |
| >7 days | 5 | 0.0308% |

Recent median, p90, and p95 are 0 days. Maximum positive lag is 103 days;
minimum is -80 days.

## 6. Representative sample

| Ticker | FY/Q | Period end | First public | Source available | Difference |
|---|---|---|---|---|---:|
| AAPL | FY2026 Q3 | 2026-06-27 | 2026-07-31 | 2026-07-31 | 0 |
| NVDA | FY2026 Q4 | 2026-01-25 | 2026-02-25 | 2026-02-25 | 0 |
| AMZN | FY2026 Q2 | 2026-06-30 | 2026-07-31 | 2026-07-31 | 0 |
| ADBE | FY2026 Q3 | 2026-08-28 | 2026-09-22 | 2026-09-22 | 0 |
| BB | FY2027 Q2 | 2026-08-31 | 2026-09-24 | 2026-09-24 | 0 |
| NUE | FY2026 Q2 | 2026-07-04 | 2026-08-12 | 2026-08-12 | 0 |
| AVAV | FY2026 Q3 | 2026-01-31 | 2026-03-11 | 2026-06-22 | +103 |
| PPCB | FY2026 Q1 | 2025-09-30 | 2026-02-02 | 2025-11-14 | -80 |

AAPL, NVDA, BB, and NUE also demonstrate non-calendar and 52/53-week period
ends. AVAV and PPCB expose winner-revision drift in opposite directions.

## 7. Official-source verification

The comparison used issuer pages where available and SEC Item 2.02 8-K
acceptance metadata. It verifies publication date and, for SEC, filing timestamp;
it does not prove the exact instant an earlier issuer press release went live.

| Ticker/quarter | Official evidence | Official date/time | Canonical dates | Result |
|---|---|---|---|---|
| AAPL FY2026 Q3 | [Apple release](https://www.apple.com/newsroom/2026/07/apple-reports-third-quarter-results/), [SEC 8-K](https://www.sec.gov/Archives/edgar/data/320193/000032019326000018/aapl-20260730.htm) | 2026-07-30; SEC 20:30:28Z | both 2026-07-31 | `NEITHER_MATCH` |
| NVDA FY2026 Q4 | [NVIDIA release](https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-fourth-quarter-and-fiscal-2026), [SEC 8-K](https://www.sec.gov/Archives/edgar/data/1045810/000104581026000019/nvda-20260225.htm) | 2026-02-25; SEC 21:31:25Z | both 2026-02-25 | `BOTH_MATCH` |
| AMZN FY2026 Q2 | [SEC 8-K](https://www.sec.gov/Archives/edgar/data/1018724/000101872426000024/amzn-20260730.htm) | 2026-07-30 20:06:23Z | both 2026-07-31 | `NEITHER_MATCH` |
| ADBE FY2026 Q3 | [SEC 8-K](https://www.sec.gov/Archives/edgar/data/796343/000079634326000147/adbe-20260910.htm) | 2026-09-10 20:06:14Z | both 2026-09-22 | `NEITHER_MATCH` |

Thus only one of four date comparisons matches. Every row also has
`DATE_ONLY_LIMITATION` inside RawCandle because canonical storage discards
intraday precision.

## 8. Timestamp precision

`v4_quarter` stores ISO dates only. It cannot distinguish before-market-open,
intraday, and after-market-close releases. The forecast linker converts the
acquisition timestamp to its UTC date and compares that date lexically to the
canonical knowledge date. Consequently, any forecast fetched earlier on a
release date may be treated as post-release even when the release occurred after
market close. Conversely, a provider date one day late can classify genuinely
post-release forecasts as pre-release until the next date.

Date precision is therefore insufficient for same-day snapshot classification.
A conservative next-session rule can avoid some intraday ambiguity, but it
cannot repair incorrect source dates such as the verified AAPL, AMZN, and ADBE
examples.

## 9. Current consumers and linker impact

Fundamentals TTM and downstream lifecycle availability use
`ttm_source_available_date = MAX(input source_availability_date)`. The TTM engine
does not populate its own `first_public_result_date`. Refresh detects latest-Q
advancement from fiscal identities, while downstream as-of eligibility remains
source-availability-driven.

The forecast fiscal linker does implement:

```sql
COALESCE(first_public_result_date, source_availability_date) <= acquisition_utc_date
```

It prefers first-public whenever present; all current rows have it. Missing
first-public would fall back to the movable Sharadar winner date. That fallback
can delay the effective boundary. It is not guaranteed never to move it earlier:
winner selection only enforces `date >= period_end`, and 20 production rows have
a current source date earlier than their immutable baseline.

The existing `0q -> next unreported quarter` sequence is structurally sound
away from publication boundaries, but not reliably safe on or near release day.
A late boundary creates labeling lag; an early or same-day-before-release
boundary creates look-ahead risk.

No forecast-accuracy evaluation join is implemented yet. Existing design docs
propose first-public with source-availability fallback, but that proposal should
not be promoted to market-public authority without new evidence.

## 10. Research semantics

**Market-public boundary:** current fields do not support this cleanly.
`first_public_result_date` is provider-derived and date-only, and the official
sample demonstrates mismatches. It is not suitable as the default boundary for
future forecast-accuracy research in its current meaning.

**RawCandle-data-availability boundary:** `source_availability_date` means the
Sharadar source row's `date`, not the moment RawCandle ingested or published it.
Exact `fetched_at_utc` and run timestamps exist in provider storage, but are not
the canonical quarter boundary. Historical bulk rows were fetched in 2026, so
their ingestion timestamp also cannot reconstruct historical provider
availability. The current pair therefore does not cleanly answer either research
question.

## 11. Yahoo upcoming earnings-date capability

Installed yfinance 0.2.66 exposes:

- `Ticker.get_calendar()` via Yahoo `calendarEvents.earnings.earningsDate`;
  the underlying list can represent a date range, but yfinance converts it to
  date-only values. A live AAPL check returned one estimated date, 2026-10-29,
  with estimate ranges and no confirmation flag.
- `Ticker.get_earnings_dates(limit, offset)` scrapes Yahoo's earnings calendar
  and supports future plus historical rows, EPS estimate, reported EPS, surprise,
  and timezone-aware displayed event times. The installed environment lacks its
  optional `lxml` parser, so the live scrape could not complete during this audit.

These APIs could support a separate forward-looking expected-Q event calendar.
Future dates are estimates unless independently confirmed, and Yahoo historical
dates must not become actual-publication authority without separate evidence.

## 12. Data-quality cases

- Same day: 89,860 rows; AAPL FY2026 Q3 is a same-field example but is one day
  later than official publication, proving same-field is not validation.
- Source later by 1+ days: 14 rows; LOVE FY2024 Q1 is the maximum at +146 days
  (`2023-06-09` vs `2023-11-02`).
- Negative lag: 20 rows; RH FY2023 Q3 is the minimum at -109 days
  (`2023-03-27` vs `2022-12-08`).
- Missing first-public: none.
- Missing source-availability: none.
- Recent extremes: AVAV FY2026 Q3 +103 days and PPCB FY2026 Q1 -80 days.
- Apparent incorrect first-public dates: AAPL +1 day, AMZN +1 day, and ADBE
  +12 days versus official evidence. Their linked provider observations confirm
  that canonical values came from Sharadar `date`; they were not transcription
  errors introduced by the query.

Positive and negative extremes are not labeled provider errors without external
case-by-case evidence. They demonstrate that routine winner movement and an
immutable baseline have intentionally different semantics.

## 13. Exact next step

Add one additive, provenance-bearing `result_publication_timestamp` authority
from official SEC Item 2.02 acceptance and/or issuer earnings-release evidence,
starting with FY2025+ quarters needed by forecast research. Preserve both current
fields unchanged. Do not begin pre-Q/post-Q accuracy labeling until that timestamp
has coverage and QA for the research universe.
