# Phase 13G.3.42: AYTU and YYAI Refresh Review Audit

## Scope and evidence

This was a read-only audit of AYTU and YYAI against Preview run
`20260926T120423Z_refresh_fundamentals_604181deee5f`. No Refresh workflow was
executed. The audit read its structured artifacts, `fundamentals_provider.db`,
and the relevant canonical rows in `fundamentals_v4.db`.

The run did not preserve a raw network response dump. Its complete-history
evidence does preserve row counts, raw/effective fingerprints, source-key
events, boundaries, and completeness status. The same evidence and fingerprints
occur in the 11:18, 11:58, and 12:04 Previews on 2026-09-26, so no network
refetch was needed.

Previously retained below means a previously accepted provider observation.
Neither ticker had an existing `RETAINED_OUTSIDE_SOURCE_WINDOW` carry-forward:
`already_retained_carry_forward = 0` for both.

## AYTU

### Exact missing rows

| Dimension | Fiscal | Report period | Source date | Observation ID | Current companion evidence |
| --- | --- | --- | --- | --- | --- |
| ARQ | 2016 Q4 | 2016-06-30 | 2016-09-01 | `e69cb40c1cf98666dc3c76c222333940bc8fc90c91e6c439cfa194293896580c` | Current ARQ contains the same fiscal identity at source date 2016-10-25 (`94ad8f71cefd450b74a6d438113d8d4f3de308f039a42ea7d5b0c4b4604d02df`). |
| MRQ | 2016 Q4 | 2016-06-30 | 2016-06-30 | `226205541149dec15fd102a4ebddeb0c708d48146954c9c5924433bedcf61b7d` | Current MRQ starts at 2017 Q1 / report period 2016-09-30; no same-fiscal key remains. |

Both old rows have provider status `SUCCESS`. Current source acquisition is
`COMPLETE`: ARQ 42 rows and MRQ 40 rows. Both events are oldest-prefix keys and
both span 41 fiscal quarters to the newest returned fiscal quarter.

Before companion reconciliation, the evidence has two deterministic meanings:

- ARQ is `SAME_FISCAL_SOURCE_KEY_REPLACEMENT`: the current response still has
  2016 Q4, but under the later 2016-10-25 source key. Canonical 2016 Q4 already
  uses `first_public_result_date = 2016-10-25`.
- MRQ is `OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW`: current MRQ begins at the next
  fiscal quarter and covers the required 41-quarter boundary.

The classifier groups missing events by fiscal identity. If companion events
have different event classes, it replaces both with
`COMPANION_DIMENSION_CONTRADICTION`. That blanket rule changes this explainable
`TRUE_SOURCE_REMOVAL + AGED_OUT_OF_SOURCE_WINDOW` pair into two ambiguous
events even though each dimension independently has complete, deterministic
evidence.

### AYTU disposition

**Classification: `REFRESH_CLASSIFIER_DEFECT_SUSPECTED`.**

The source itself is not contradictory. ARQ records a same-fiscal source-key
replacement while MRQ records ordinary rolling-window aging. A minimal
follow-up implementation should recognize this narrowly proven combination
when both histories are complete, the replacement key is explicit, the
companion row is a coherent oldest prefix, and the minimum fiscal span is met.
It should remove only the obsolete ARQ source key and retain only the aged MRQ
row. It must not generally relax companion-dimension ambiguity.

Safe operator action: keep AYTU in review and create that focused classifier
fix with a regression fixture reproducing these exact keys. There is no current
Refresh review-approval/override path that can safely record this resolution.

## YYAI

### Source-window summary

- Previous provider state: ARQ 68 rows / 37 fiscal quarters, 2017 Q3 through
  2026 Q3; MRQ 54 rows / 39 fiscal quarters, 2017 Q1 through 2026 Q3.
- Current complete response: ARQ 35 rows, oldest fiscal 2020 Q3 and newest
  fiscal 2027 Q1; MRQ 31 rows, oldest fiscal 2019 Q3 and newest fiscal 2027 Q1.
- Missing prefix: 13 ARQ observations across 12 fiscal quarters and 10 MRQ
  observations across 10 fiscal quarters, 23 observations total.
- Every missing observation is an oldest-prefix key, chronology is coherent,
  and no event has a same-fiscal current key.

### Exact missing observations

| Dim. | Fiscal | Report period | Source date | Observation ID | Span | Result |
| --- | --- | --- | --- | --- | ---: | --- |
| ARQ | 2017 Q3 | 2017-01-31 | 2017-03-30 | `5c31062b7c779549eaa55949e7b81b76c49caec24bec4ebbb2d574bb71f1c38d` | 39 | too short |
| ARQ | 2017 Q4 | 2017-04-30 | 2017-08-03 | `02618ba3dde4020d1839cce64b5ff8786f28bb144e8bfedffef07c6197795b3a` | 38 | too short |
| ARQ | 2017 Q4 | 2017-04-30 | 2017-08-04 | `02048969069f1488ba021cd537553edbaa7e1b181c5dc4416615e8424cfe3a6d` | 38 | too short |
| ARQ | 2018 Q1 | 2017-07-31 | 2017-09-20 | `d3f6568db24b661d8f56ce9105b92c3f43ea1e7f56d81c1ffefd148491f8ab6a` | 37 | too short |
| ARQ | 2018 Q2 | 2017-10-31 | 2017-12-18 | `d81f5839fea9f70096dc04cdc656c41739c6547bb418ede1c25c873a80fe6e7a` | 36 | too short |
| ARQ | 2018 Q3 | 2018-01-31 | 2018-03-20 | `2c634258e5160678f8e80183ffc2aadd1ba4b9b269e91b6c1e74d01323a83bd1` | 35 | too short |
| ARQ | 2018 Q4 | 2018-04-30 | 2018-08-14 | `ab58e48627ba72c4f43aa13f2b5d339611acb05db5621e4b3a54d4fa212e2005` | 34 | too short |
| ARQ | 2019 Q1 | 2018-07-31 | 2018-09-17 | `839959f7765c6f02b562c268c016528304440f5271b6b832f95d1e507553aef9` | 33 | too short |
| ARQ | 2019 Q2 | 2018-10-31 | 2018-12-18 | `58de6a476a8f620b7fb26e577b6cdc74beab09383b0f8863d643a198ae648255` | 32 | too short |
| ARQ | 2019 Q3 | 2019-01-31 | 2019-03-15 | `78d6fcc95b5a2f4a4acf8eb7acfd83e1ff3cc566b19e8eb5ee3ba731d202e741` | 31 | too short |
| ARQ | 2019 Q4 | 2019-04-30 | 2019-08-06 | `f4d65af577beddca5ba523c79ae9f5b7c9b047be7f119815495b20b718198f57` | 30 | too short |
| ARQ | 2020 Q1 | 2019-07-31 | 2019-09-04 | `9600226e95521ff0c8283360d74db24e94123a4b400f83fae5438ca10c26df88` | 29 | too short |
| ARQ | 2020 Q2 | 2019-10-31 | 2019-12-16 | `d6e9dcd366664feca40fab153f16f54d932e87f17b43a76ce3cdf0ed934b3d56` | 28 | too short |
| MRQ | 2017 Q1 | 2016-07-31 | 2016-07-31 | `a5ef3536e3b09a31cc3856b43ae712cc6f28cbf818b2f8ecfe077af3871877b7` | 41 | expected window |
| MRQ | 2017 Q2 | 2016-10-31 | 2016-10-31 | `398ad937e61cb1ae5aca23401b03c340dcef47d3e77704f64f812973338fc9d8` | 40 | too short |
| MRQ | 2017 Q3 | 2017-01-31 | 2017-01-31 | `f4272d651dc12551c3ccf48e7bff43dafe41d44acbe75835667ffb662f65552e` | 39 | too short |
| MRQ | 2017 Q4 | 2017-04-30 | 2017-04-30 | `6d4518e5cadb0aea1e5009481cbd54e66a445c877891706379bc3b511b57ff2c` | 38 | too short |
| MRQ | 2018 Q1 | 2017-07-31 | 2017-07-31 | `e082e9faf6c6bcb61a43f5e37161c59b4abec91b0849945c73f5c9cf67d053c7` | 37 | too short |
| MRQ | 2018 Q2 | 2017-10-31 | 2017-10-31 | `7442cfaeb2f9a0300c844489d6934857b51401971028a0a6be1ad691228ca407` | 36 | too short |
| MRQ | 2018 Q3 | 2018-01-31 | 2018-01-31 | `23007d400eae38906276f6638b8d0afc51f5c06b4efcda56e45e0610c5cdd6e1` | 35 | too short |
| MRQ | 2018 Q4 | 2018-04-30 | 2018-04-30 | `0fb26287b986b1c31d975290d659f082be28ff66b96f74e70055106d5070a6ae` | 34 | too short |
| MRQ | 2019 Q1 | 2018-07-31 | 2018-07-31 | `1fb803ee55d1f18eafd0209cdc406f74fc461054bfd0a4ed57b7d80320c3ece2` | 33 | too short |
| MRQ | 2019 Q2 | 2018-10-31 | 2018-10-31 | `ed48cb5170f59b4d639924f2f020d343fb3265c365331629658357eab762d909` | 32 | too short |

The minimum accepted inclusive boundary span is 41 quarters. The oldest MRQ
row alone reaches 41 and therefore receives
`OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW`. The remaining 22 rows have spans 28-40
and receive `BOUNDARY_FISCAL_WINDOW_TOO_SHORT`. This is why both reason codes
appear while the aggregate action reports one newly aged row and 22 ambiguous
removals.

The rows form clean prefixes within both dimensions. Companion evidence does not
contradict prefix ordering, but it does show materially different and short
returned windows: ARQ retains only 2020 Q3 onward, while MRQ retains 2019 Q3
onward. A complete transport response is not proof that this shortened provider
history authorizes deletion or retention under the locked 10-year contract.

### YYAI disposition

**Classification: `PROVIDER_ANOMALY_SUSPECTED`.**

YYAI must remain `REVIEW_REQUIRED`. The classifier is correctly fail-closed:
the current provider response is materially shorter than the expected source
window and cannot authorize automatic deletion or automatic retained-prefix
classification. Safe operator action is to obtain provider-side evidence for
why ARQ and MRQ now begin at those dates, or design a separately approved,
auditable resolution for persistently short but complete provider histories.
Do not weaken the 41-quarter boundary in the current classifier.

## Comparison with normal retention

| Ticker | Missing events | Dimensions | Boundary spans | Outcome |
| --- | ---: | --- | --- | --- |
| ADBE | 1 | MRQ | 41 | retained |
| ANAB | 2 | ARQ + MRQ | 41, 41 | retained |
| CPB | 2 | ARQ + MRQ | 41, 41 | retained |
| GIS | 3 | ARQ + MRQ | 42, 41, 41 | retained |
| WHLR | 2 | ARQ + MRQ | 41, 41 | retained |

All accepted examples have coherent oldest-prefix events, no same-fiscal
replacement conflict, and every missing row meets the 41-quarter minimum.
AYTU differs because its ARQ event is a source-key replacement while MRQ is
aging. YYAI differs because 22 of 23 rows fail the minimum span.

## Operator recommendation

- Do not rerun Preview now: three identical same-day Previews already prove
  stable evidence, so an immediate rerun will remain blocked.
- For AYTU, create a narrowly scoped classifier follow-up for the proven
  same-fiscal replacement plus companion aging combination, then rerun focused
  fixtures and a fresh Preview.
- For YYAI, obtain targeted provider evidence or approve a separately designed
  reviewed-short-window resolution. Do not classify the 22 ambiguous rows as
  retained under the current contract.
- Do not run Test or Production until both items are resolved and a fresh
  Preview has no blocking review items.

## Safety

- Runtime code changed: `NO`
- Production databases changed: `NO`
- Workflows executed by this audit: `NO`
- Scheduler state changed: `NO`
- Watermark/state advanced: `NO`
