# Forecast Revision Overlap After Publication Refresh

Date: 2026-10-04

Decision: `FORECAST_REVISION_RESEARCH_V1_READY`

## Production Provenance

Active generation: `refresh_20261004T173815Z_refresh_fundamentals_1c0cfaa31765_production_0452fc80`.
Previous generation: `refresh_20261003T110448Z_refresh_fundamentals_33afa113e7cf_production_8278e7a6`.
The actual Production operation_report.md and result.json under the active run
(admin run identifier omits the generation prefix refresh_) confirm core COMPLETED,
publication PARTIAL, 348 eligible / 50 selected / 298 backlog, processed 50,
16 new VERIFIED, 31 UNRESOLVED, 0 AMBIGUOUS, 3 NOT_FOUND, 97 SEC requests,
and publication runtime 26.692 seconds. Systemd status was not consulted.

Compared authority by stable (company_id, fiscal_year, fiscal_quarter), not quarter_id
or recent fiscal year. Exactly 16 were non-VERIFIED or missing before and VERIFIED
after; all verified_at values fall in this Production publication execution.
Three were UNRESOLVED; thirteen lacked an authority row. Missing authority is not
the same as a newly created canonical quarter: this refresh reported zero new quarters.

All selected authority below is SEC_8K_ITEM_2_02 with HIGH canonical confidence.
The existing research projection classifies those VERIFIED exact timestamps as EXACT.

## All Sixteen New Authorities

| Company | Ticker | FY/FQ | Period end | Exact UTC publication | Previous status | Overlap | Accession / selected reference |
|---:|---|---|---|---|---|---|---|
| 87 | AIR | 2027/Q1 | 2026-08-31 | 2026-09-28T20:58:22Z | MISSING | INSIDE_FORECAST_HISTORY | [0001104659-26-111403](https://www.sec.gov/Archives/edgar/data/1750/000110465926111403/tm2626100d2_8k.htm) |
| 398 | CALM | 2027/Q1 | 2026-08-29 | 2026-09-30T10:07:27Z | MISSING | INSIDE_FORECAST_HISTORY | [0001562762-26-000111](https://www.sec.gov/Archives/edgar/data/16160/000156276226000111/8k20260930.htm) |
| 549 | CPRT | 2026/Q4 | 2026-07-31 | 2026-09-10T20:16:04Z | MISSING | BEFORE_FORECAST_HISTORY | [0001193125-26-387902](https://www.sec.gov/Archives/edgar/data/900075/000119312526387902/cprt-20260910.htm) |
| 1098 | IDT | 2026/Q4 | 2026-07-31 | 2026-09-28T20:31:47Z | MISSING | INSIDE_FORECAST_HISTORY | [0001437749-26-031364](https://www.sec.gov/Archives/edgar/data/1005731/000143774926031364/idt20260424_8k.htm) |
| 1280 | LEN | 2026/Q3 | 2026-08-31 | 2026-09-16T20:42:59Z | MISSING | BEFORE_FORECAST_HISTORY | [0001628280-26-062287](https://www.sec.gov/Archives/edgar/data/920760/000162828026062287/len-20260916.htm) |
| 1302 | LITS | 2026/Q4 | 2026-06-30 | 2026-07-30T12:30:14Z | MISSING | BEFORE_FORECAST_HISTORY | [0001193125-26-325026](https://www.sec.gov/Archives/edgar/data/1262104/000119312526325026/lits-20260730.htm) |
| 1430 | MKC | 2026/Q3 | 2026-08-31 | 2026-10-01T11:31:11Z | MISSING | INSIDE_FORECAST_HISTORY | [0000063754-26-000326](https://www.sec.gov/Archives/edgar/data/63754/000006375426000326/mkc-20261001.htm) |
| 1434 | MLKN | 2027/Q1 | 2026-08-29 | 2026-09-22T11:05:11Z | MISSING | BEFORE_FORECAST_HISTORY | [0000066382-26-000150](https://www.sec.gov/Archives/edgar/data/66382/000006638226000150/mlkn-20260922.htm) |
| 1485 | MTN | 2026/Q4 | 2026-07-31 | 2026-09-28T20:06:47Z | MISSING | INSIDE_FORECAST_HISTORY | [0000812011-26-000048](https://www.sec.gov/Archives/edgar/data/812011/000081201126000048/mtn-20260928.htm) |
| 1545 | NKE | 2027/Q1 | 2026-08-31 | 2026-10-01T20:15:15Z | MISSING | INSIDE_FORECAST_HISTORY | [0000320187-26-000184](https://www.sec.gov/Archives/edgar/data/320187/000032018726000184/nke-20261001.htm) |
| 1784 | PRGS | 2026/Q3 | 2026-08-31 | 2026-09-30T20:07:19Z | MISSING | INSIDE_FORECAST_HISTORY | [0000876167-26-000110](https://www.sec.gov/Archives/edgar/data/876167/000087616726000110/prgs-20260930.htm) |
| 1961 | SCHL | 2027/Q1 | 2026-08-31 | 2026-09-24T20:01:36Z | MISSING | BEFORE_FORECAST_HISTORY | [0000866729-26-000022](https://www.sec.gov/Archives/edgar/data/866729/000086672926000022/schl-20260924.htm) |
| 2045 | SNTI | 2026/Q2 | 2026-06-30 | 2026-07-15T11:32:12Z | UNRESOLVED | BEFORE_FORECAST_HISTORY | [0001628280-26-048248](https://www.sec.gov/Archives/edgar/data/1854270/000162828026048248/snti-20260714.htm) |
| 2046 | SNX | 2026/Q3 | 2026-08-31 | 2026-09-24T11:03:05Z | MISSING | BEFORE_FORECAST_HISTORY | [0001628280-26-063314](https://www.sec.gov/Archives/edgar/data/1177394/000162828026063314/snx-20260924.htm) |
| 2146 | TEAM | 2026/Q4 | 2026-06-30 | 2026-08-06T20:10:05Z | UNRESOLVED | BEFORE_FORECAST_HISTORY | [0001650372-26-000031](https://www.sec.gov/Archives/edgar/data/1650372/000165037226000031/team-20260806.htm) |
| 2451 | ZS | 2026/Q4 | 2026-07-31 | 2026-09-03T20:08:39Z | UNRESOLVED | BEFORE_FORECAST_HISTORY | [0001713683-26-000156](https://www.sec.gov/Archives/edgar/data/1713683/000171368326000156/zs-20260901.htm) |

## Forecast Window and Cohort

First FISCAL_ESTIMATE fetch: 2026-09-27T16:27:26.679445Z.
Latest FISCAL_ESTIMATE fetch: 2026-10-04T12:01:31.200459Z.
Current counts: 12 runs, 66525 total fetches, 21784 snapshots, 4958 fiscal snapshots; 22175 fiscal fetches.
Seven exact events fall inside the window: AIR, CALM, IDT, MKC, MTN, NKE, PRGS.
The other nine are BEFORE_FORECAST_HISTORY; none is after the latest forecast fetch.
Publication timestamps, not first-full-day or verification dates, define overlap.

Recent application run statuses:
- 2026-10-04T11:00:24.595549Z: SUCCESS (a10dc8c15a414c668392f473debf0530).
- 2026-10-03T11:00:23.402660Z: SUCCESS (d0a1b8b64259490489a1a3fe5fa7a803).
- 2026-10-02T11:01:04.629491Z: PARTIAL (dd218df16d7246bdbb5eac9521365ade).
- 2026-10-01T11:01:03.214992Z: SUCCESS (b4535537c9ef498cb83913dde8970ec2).
- 2026-09-30T11:00:17.884122Z: SUCCESS (ba0634de92544b20b778a49f970451cc).

PRE / POST / both: 7 / 7 / 7. Failed fetches do not provide values.
OBSERVED transitions: 7; NOT_YET_OBSERVED: 0; insufficient-pre: 0;
insufficient-post: 0; NO_USABLE_0Q: 0. Comparable +1q -> 0q pairs: 7.

## Concrete Engine Bugs Found and Narrow Fixes

First unmodified engine output classified all seven NOT_YET_OBSERVED and none
comparable because the next canonical quarter row is not yet present for any company.
Independent fetch-specific QA proved all seven have LINKED AS_KNOWN expected future
identities, latest PRE +1q for the immediate successor, and later POST 0q for that
same identity. ForecastFiscalLinker explicitly accepts LINKED with nullable
canonical_quarter_id for expected future quarters (sequential fiscal matching).
The research engine incorrectly required an already-created actual-result quarter row.

The fix retains existing canonical succession where present and still rejects gaps.
Only at the end of canonical history, it accepts the immediate natural successor
when supported by already reconstructed quarterly AS_KNOWN observations. No later
quarter can be skipped, no missing result quarter is fabricated, and there is no
CURRENT_RECONCILED fallback or Fundamentals write. Same-target equality remains exact.

A second exposed bug mixed None and string keys in transition-class summary, causing
sorted JSON metadata serialization to fail. Unknown trading-calendar class now uses
UNAVAILABLE; timing and revision formulas are unchanged. Regression tests cover both.

The initial CSV/metadata remain retained as diagnostic artifacts. An intermediate
target-fix CSV without metadata is incomplete because of the serialization failure;
it is not the final retained research output. The validated CSV below is final.

## Fetch-Specific QA for Every Event

Every accepted observation uses its own acquisition time, snapshot dereference,
RESOLVED fetch identity, accepted rule versions and AS_KNOWN fiscal link with
fundamentals knowledge not after acquisition. SUCCESS_UNCHANGED retains its referenced
snapshot. No simple snapshot/current-link join substitutes for reconstruction.

Latest PRE +1q and earliest POST 0q below both target exactly the listed identity.
Latest PRE usable fetch equals the PRE +1q fetch timestamp for each event.
Fetch/snapshot/link/resolution IDs and full value states are in the CSV/metadata.

| Ticker | Result | Same next target | Latest PRE +1q UTC | Earliest POST next-target 0q UTC | Last old 0q UTC |
|---|---|---|---|---|---|
| AIR | 2027/Q1 | 87/2027/Q2 | 2026-09-28T11:02:21.626036Z | 2026-10-02T11:03:13.828041Z | 2026-10-01T11:03:12.935188Z |
| CALM | 2027/Q1 | 398/2027/Q2 | 2026-09-29T11:10:06.935120Z | 2026-10-02T11:10:53.290317Z | 2026-10-01T11:10:52.669038Z |
| IDT | 2026/Q4 | 1098/2027/Q1 | 2026-09-28T11:27:26.107634Z | 2026-10-02T11:28:17.207014Z | 2026-10-01T11:28:18.473790Z |
| MKC | 2026/Q3 | 1430/2026/Q4 | 2026-09-30T11:35:40.498543Z | 2026-10-02T11:36:26.803159Z | 2026-10-01T11:36:27.076382Z |
| MTN | 2026/Q4 | 1485/2027/Q1 | 2026-09-28T11:36:53.895624Z | 2026-10-02T11:37:48.223122Z | 2026-10-01T11:37:48.184462Z |
| NKE | 2027/Q1 | 1545/2027/Q2 | 2026-10-01T11:39:18.334506Z | 2026-10-03T11:38:37.395900Z | 2026-10-02T11:39:18.606339Z |
| PRGS | 2026/Q3 | 1784/2026/Q4 | 2026-09-30T11:44:29.003994Z | 2026-10-02T11:45:14.497540Z | 2026-10-01T11:45:14.476264Z |

All transition statuses are OBSERVED. The first new 0q time is the POST time above.
This is an interval (last old 0q, first new 0q], NOT an exact Yahoo switch time.

| Ticker | Interval hours | Publication -> first new hours | Calendar days | Observed trading days | Quality flags |
|---|---:|---:|---:|---:|---|
| AIR | 24.00024801472222 | 86.08106334472222 | 4 | 4 | none |
| CALM | 24.0001725775 | 49.057302865833336 | 2 | 2 | EPS_PERCENT_DENOMINATOR_UNSUITABLE |
| IDT | 23.999648117777777 | 86.94172417055555 | 4 | 4 | none |
| MKC | 23.999924104722222 | 24.087723099722222 | 1 | 1 | none |
| MTN | 24.00001073888889 | 87.51700642277778 | 4 | 4 | EPS_PERCENT_DENOMINATOR_UNSUITABLE |
| NKE | 23.98855265583333 | 39.38955441666667 | 2 | None | none |
| PRGS | 24.00000591 | 39.63208265 | 2 | 2 | none |

NKE has no observed trading-calendar coverage on its first new 0q fetch date;
trading delay remains NULL rather than a fabricated weekday estimate.

## Same-Target Values and Revisions

| Ticker | EPS pre -> post | EPS abs / pct | Revenue pre -> post | Revenue abs / pct | EPS analysts pre -> post | Revenue analysts pre -> post | EPS / Revenue range-width change |
|---|---|---|---|---|---|---|---|
| AIR | 1.3625 -> 1.37667 | 0.014170000000000016 / 1.0400000000000011 | 892080250.0 -> 893431710.0 | 1351460.0 / 0.151495339124479 | 8.0 -> 6.0 | 8.0 -> 7.0 | -0.030000000000000027 / -21302000.0 |
| CALM | -0.385 -> -1.005 | -0.6199999999999999 / None | 618536500.0 -> 575526250.0 | -43010250.0 / -6.953550841381229 | 2.0 -> 2.0 | 4.0 -> 4.0 | 2.220446049250313e-16 / -10241000.0 |
| IDT | 0.98 -> 1.03 | 0.050000000000000044 / 5.102040816326536 | 317000000.0 -> 331000000.0 | 14000000.0 / 4.416403785488959 | 1.0 -> 1.0 | 1.0 -> 1.0 | 0.0 / 0.0 |
| MKC | 0.88169 -> 0.83969 | -0.041999999999999926 / -4.763579035715493 | 2120304810.0 -> 2118707880.0 | -1596930.0 / -0.075316057977532 | 10.0 -> 10.0 | 9.0 -> 9.0 | 0.08201000000000003 / 15300000.0 |
| MTN | -5.40543 -> -5.62455 | -0.2191200000000002 / None | 271289400.0 -> 272997190.0 | 1707790.0 / 0.6295085617056914 | 9.0 -> 10.0 | 9.0 -> 10.0 | 0.2645900000000001 / -4697340.0 |
| NKE | 0.50502 -> 0.43689 | -0.06813000000000002 / -13.490554829511705 | 11796665600.0 -> 11319061760.0 | -477603840.0 / -4.048634217452091 | 23.0 -> 24.0 | 28.0 -> 28.0 | -0.10999999999999999 / -461389550.0 |
| PRGS | 1.44677 -> 1.27331 | -0.17345999999999995 / -11.989466190203 | 258346050.0 -> 289973840.0 | 31627790.0 / 12.242412841225944 | 4.0 -> 4.0 | 5.0 -> 5.0 | -0.023830000000000018 / 383730.0 |

Null/absent/zero states and near-zero EPS guard are unchanged. Negative EPS baselines
for CALM and MTN suppress percent revision while retaining absolute changes and flags.
No old result-quarter 0q is used as a revision baseline.

## Descriptive Summary

N = 7. EPS positive / negative: 2 / 5. Revenue positive / negative: 4 / 3.
Median EPS absolute revision: -0.06813000000000002.
Median Revenue absolute revision: 1351460.0.
Median EPS / Revenue analyst-count change: 0.0 / 0.0.
Median transition interval hours: 24.00000591.
Median observed trading-day delay: 3.0 (six covered events).
Calendar-day distribution, same-day / next-day / later: 0 / 1 / 6.
Observed trading-day classes: next trading day 1, 2-3 days 2, 4+ days 3, unavailable 1.
Optional D5/D20 join skipped: first cohort of seven is too small for a nontrivial
descriptive relation, and these very recent events do not have complete D20 followup.
No trading inference or predictive model was built.

## Frozen Artifacts

Publication CSV: `/home/kalle/projects/rawcandle/exports/result_publication/result_publication_daily_research_forecast_overlap_2026-10-04.csv`.
SHA-256: `6b7f76ac8bacf6875502cd20f9bdeb867bd23a4502111e5a2f6d02ce9da47a5a`.
Adjacent .metadata.json and .yahoo-observations.json are retained. Frozen Yahoo input
is a byte-identical copy of the reviewed September 29/October 3 artifact, not new
provider evidence; no live Yahoo collection ran. The reviewed V2 artifact is unchanged.
Publication export is restricted to the seven overlapping company identities and
exact-timestamp lower bound at the first fiscal fetch; it contains seven EXACT rows.
Older retained September 29 and October 3 publication exports were not overwritten.

Final revision CSV: `/home/kalle/projects/rawcandle/exports/forecasts/forecast_revision_research_v1_2026-10-04_validated.csv`.
SHA-256: `226b881b8be03e155854132074b67268fec557d9486d9e2b48adc0dd41406da8`.
Adjacent metadata retains current source hashes, chronology/identity QA, summaries
and output hash. The _validated name avoids overwriting earlier diagnostic outputs.

## Safety, Tests and Recommendation

All source DB access used mode=ro with query_only. Current task-start, engine before/
after and final safety hashes agree; no concurrent drift was detected. Source integrity
quick_check results are ok. Active generation remained bound throughout. No snapshot
was needed, no source DB writes occurred, and scheduler/systemd are unchanged.

| Database | Current pre = post SHA-256 |
|---|---|
| forecasts | `5cc1b771ecfab2e1e31e5d2d55f6947b8c26a54b7d381e8d90f230df16f32aec` |
| canonical | `f727d5f19ceb388cc4d01110cab54712817d4e79b5ab84c6214f4bbe0402e3b2` |
| ohlc | `1d3669b8d218f0d1efc0f946fb8e1eaf01ab7bf3e2cfcd16d6e811d219257ebc` |

Only rawcandle/research/forecast_revision_research.py and its focused test module
changed. Fundamentals, publication authority, forecast acquisition and scheduler did
not change. Forecast-revision tests: 20 passed in 5.15 seconds; no unrelated suite.

This is the first real cohort, not a large-sample result. Newly fetched official
evidence removes the previous publication-window gate, and the contract-alignment fix
allows already persisted future-quarter links to supply target continuity.
Recommendation: review the seven final QA rows, retain these frozen artifacts, and
rerun the same bounded research after additional scheduled observations. Do not change
acquisition or manufacture canonical future result rows to enlarge the cohort.
