# P/B.2 — Sharadar pb / Filing-Date Timing Validation Against Result Publication

Audit date: 2026-10-07, Europe/Helsinki. Read-only research; reporting and production behavior unchanged.

## Executive Summary

**Sharadar `pb ≈ marketcap/equityusd`: YES.** All 1,848 eligible same-row observations are within 1%; median absolute percentage difference **0.006898%**, P95 **0.046464%**, maximum **0.749964%**. Every absolute ratio residual is under 0.0005, consistent with three-decimal rounding; no material arithmetic outlier (>1%).

Sharadar ARQ `date` behaves like a **provider filing/availability index with a predominantly same-date trading close**. It is distinct from report period, lastupdated and RawCandle selected result authority. Median gap is **0 days**, but only **1,178 / 63.74%** are same calendar day; 214 are more than two days later, 20 precede authority. Range **−38 to +36 days**.

Authority comparison is primarily SEC Item 2.02 8-K acceptance: 1,840 observations. No issuer-release authority or issuer-release evidence exists in this active generation, so issuer-vs-8-K gap is **not measurable**. These authority timestamps must not be described as independently proven first issuer-release times.

All nine Phase 13G.3.80 keys were examined: eight usable provider P/B rows, six same-day and two +1 day; BTDR lacks P/B inputs. Provider price matches date-day close within 0.1% in **1,834 / 99.24%** (114 also match neighboring dates). Some adjustment-base discrepancies remain.

Recommended label: **`PROVIDER_OBSERVATION_PB`**, field **`PB_PROVIDER_OBSERVATION`**. Suitable as a reporting-only historical provider reference: **YES**, with its own date, accepted observation binding and explicit caveats. PIT-safe historical metric: **NO**. Keep current validated market-cap/latest-parent-equity P/B separate.

## Cohort and Exact Observation Binding

Active generation: `publication_drain_20261007T093516Z_fd654a20`. Provider/canonical/analysis resolve under `data/fundamentals_generations/publication_drain_20261007T093516Z_fd654a20/`; market closes from `data/osakedata.db`. The P/B.1 report is the accounting baseline. The active manifest bytes and all four database size/mtime values were unchanged before/after research queries. Connections explicitly used `mode=ro` and `query_only=on`; no workflow/import that could create schemas was run.

There are 2,468 operational company members; 2,466 have an eligible latest accepted canonical financial quarter as of 2026-10-07. Selection uses the latest fiscal endpoint with canonical source availability on/before as-of, **not the latest quarter that happens to have a usable P/B or VERIFIED authority**. Thus it does not backfill easier timing cases.

Exactly six required Phase 80 quarter keys are additional to that latest-operational endpoint set. The combined target set is 2,472 unique quarters. 364 lack VERIFIED authority; 2,108 have authority and exact accepted shares provenance. Of these, 260 fail positive finite P/B/marketcap/equity inputs: 88 missing and 172 nonpositive. The complete eligible cohort is **1,848**: 1,842 latest-operational rows plus six supplemental required Phase 80 keys. The nine-key 6-K subset is therefore separately reported, not presented as a random latest-universe stratum.

CSV has **1,849 rows**: all 1,848 eligible observations plus the required BTDR exclusion. `eligible=0` is excluded from the main percentages and arithmetic. No large raw JSON extracts are committed.

Each row binds `v4_quarter` to the unique `v4_field_provenance` shares_outstanding record, then `provider_observation.observation_id`. There are no ambiguous multi-observation shares provenance keys. We assert ARQ, exact fiscalperiod/source_reportperiod and sharesbas equality with canonical shares. Provider P/B, price, marketcap, equity/USD, factor and all dates come from **that one payload**. No MRQ, alternate same-quarter provider snapshot or current price is substituted.

Observation ID, stored content hash, provenance ID/rule/acceptance, quarter ID, provider fetched time and authority evidence ID/hash/accession are retained in CSV. Equity is not yet a canonical field: this is an **accepted shares-source-row research binding**, not a newly authorized canonical equity provenance contract.

The cohort contains 335 technology, 300 industrials, nine financial services and 18 ADR-category observations. All eligible sector counts:

| Sector | n |
| --- | --- |
| Healthcare | 456 |
| Technology | 335 |
| Industrials | 300 |
| Consumer Cyclical | 205 |
| Real Estate | 139 |
| Energy | 96 |
| Consumer Defensive | 89 |
| Basic Materials | 86 |
| Communication Services | 79 |
| Utilities | 54 |
| Financial Services | 9 |

No market-cap size threshold was applied, so small/large firms and difficult timing cases are retained. This is a full eligible cohort, not a hand-picked 100–200 sample.

## Arithmetic Validation

Calculation: `pb_reconstructed = marketcap_provider / equityusd`, positive finite numerator/denominator. Percentage difference: `100 × abs(pb_reconstructed / pb_provider − 1)`. Provider P/B must be finite and positive. Negative book ratios are excluded from comparability; values are not converted into positive cheapness signals.

| Measure | Result |
|---|---:|
| n | 1,848 |
| Median absolute percentage difference | 0.006898% |
| P95, linearly interpolated order statistic | 0.046464% |
| Maximum | 0.749964% |
| Within 0.1% | 1,833 (99.19%) |
| Within 1% | 1,848 (100%) |
| Within 5% | 1,848 (100%) |
| Material outliers >1% | 0 |
| Outliers >5% | 0 |

Largest differences:

| Ticker | Provider pb | Reconstructed | Abs percentage difference |
| --- | --- | --- | --- |
| GNLN | 0.053 | 0.052602519 | 0.749964% |
| GPMT | 0.151 | 0.150533966 | 0.308632% |
| GTEC | 0.164 | 0.164294514 | 0.179581% |
| ONL | 0.234 | 0.234398715 | 0.170391% |
| CYN | 0.344 | 0.344475732 | 0.138294% |

Maximum absolute ratio residual is 0.0004999145; every row satisfies `abs(pb_reconstructed − pb_provider) ≤ 0.0005001`. Small ratios make ordinary three-decimal rounding relatively larger; GNLN is explained by rounding, not timing or denominator substitution.

Optional same-row capitalization reconstruction `provider_price × sharesbas × sharefactor` is usable for all 1,848 eligible rows. Median absolute percentage difference from provider marketcap is **5.5733e−9%**, with zero cases above 1%. This validates the stored formula without current RawCandle prices. It does not resolve the parent/common-equity distinction or certify external price adjustments.

## Timing Distribution

Publication UTC timestamp is preserved. For delta calculation, convert to **America/New_York**, including DST, because this cohort is US-listed and selected authorities are SEC acceptance events. This is the US event calendar, not Helsinki chat time and not the foreign issuer's home-country date. `delta_calendar_days = Sharadar date − ET authority date`. No trading-date transformation occurs.

| Sharadar date minus authority date | n | % |
| --- | --- | --- |
| Before | 20 | 1.08% |
| Same day | 1178 | 63.74% |
| +1 | 362 | 19.59% |
| +2 | 74 | 4.00% |
| +3–5 | 62 | 3.35% |
| +6–10 | 105 | 5.68% |
| >10 | 47 | 2.54% |

Median **0**, mean **1.199675**, P90 **4**, minimum **−38**, maximum **36** days. Days 0–2 represent **1,614 / 87.34%**; >2 days represent **214 / 11.58%**; before authority **20 / 1.08%**.

Timezone sensitivity: 12 UTC timestamps have a different ET calendar date. Using UTC would produce 1,182 same-day and 354 +1 cases, rather than 1,178 and 362. CSV includes both dates, but all primary deltas consistently use ET.

Empirical provider date checks: all 1,848 have provider source availability and canonical source availability equal to Sharadar date; none has date equal to reportperiod. Only 338 have lastupdated equal to date. These equalities show the stored availability convention, not independent proof of an SEC form-10 acceptance time. Provider observations are fetched later and can be updated. Exact form-10 acceptance matching is not present in this bounded accepted-row/authority evidence set.

Timing extremes retained for review:

| Ticker | Provider date | Authority UTC timestamp | Delta days |
| --- | --- | --- | --- |
| ETD | 2026-09-03 | 2026-07-29T20:16:25Z | 36 |
| WS | 2026-07-30 | 2026-06-25T10:30:23Z | 35 |
| OPK | 2026-08-28 | 2026-07-27T20:08:03Z | 32 |
| FDX | 2026-07-20 | 2026-06-23T20:07:29Z | 27 |
| NOG | 2026-08-07 | 2026-07-13T12:40:55Z | 25 |
| UNH | 2026-08-10 | 2026-07-16T10:00:59Z | 25 |
| HIND | 2026-08-12 | 2026-08-25T20:05:29Z | -13 |
| AVD | 2026-08-10 | 2026-08-11T20:08:23Z | -1 |
| CYCN | 2026-08-04 | 2026-09-11T20:25:17Z | -38 |

Positive gaps are consistent with a later provider filing/availability date than result-related 8-K acceptance. Negative gaps show that the selected authority event is not always the earliest event relative to provider availability; possible delayed 8-K/event matching or provider dates cannot be resolved from date-only values. **Do not automatically call those rows look-ahead or correct authority from this research.** Stored natural-quarter keys and selected evidence remain intact. The tails prevent a universal “result-publication P/B” label.

## Source Split

| Authority source | n | Same day % | Median delta | P90 delta |
| --- | --- | --- | --- | --- |
| SEC_8K_ITEM_2_02 | 1840 | 63.70% | 0.0 | 4.0 |
| SEC_FORM_6K_RESULT | 8 | 75.00% | 0.0 | 1.0 |
| ISSUER_EARNINGS_RELEASE | 0 | NOT_MEASURABLE | NOT_MEASURABLE | NOT_MEASURABLE |
| SEC_FILING_FALLBACK | 0 | NOT_MEASURABLE | NOT_MEASURABLE | NOT_MEASURABLE |
| MANUAL_REVIEW | 0 | NOT_MEASURABLE | NOT_MEASURABLE | NOT_MEASURABLE |

The full canonical authority table has 12,869 VERIFIED 8-K and nine VERIFIED 6-K rows. It has **zero issuer, filing-fallback or manual authority rows**; evidence types are only 8-K and 6-K. Therefore the requested experiment “issuer release precedes 8-K, selected authority is issuer release” has **zero available paired cases**. There is no empirical issuer-release gap estimate, and no proof here of first market release timestamp. Do not infer issuer-vs-8-K alignment from the 8-K subgroup. No fresh SEC/issuer acquisition or policy revisit was performed.

### Nine Live Phase 13G.3.80 Cases

| Ticker | Quarter | Sharadar date | Parent acceptance UTC | ET date | Delta days | Provider pb |
| --- | --- | --- | --- | --- | --- | --- |
| NEGG | 2026-Q2 | 2026-08-27 | 2026-08-27T20:30:01Z | 2026-08-27 | 0 | 2.167 |
| CAMT | 2026-Q2 | 2026-08-10 | 2026-08-10T11:16:13Z | 2026-08-10 | 0 | 10.39 |
| BTDR | 2026-Q2 | 2026-08-10 | 2026-08-10T11:08:07Z | 2026-08-10 | 0 | MISSING |
| VNET | 2026-Q2 | 2026-08-18 | 2026-08-18T10:16:34Z | 2026-08-18 | 0 | 3.085 |
| WPM | 2026-Q2 | 2026-08-07 | 2026-08-06T22:47:58Z | 2026-08-06 | 1 | 6.289 |
| NVMI | 2026-Q2 | 2026-08-06 | 2026-08-06T11:30:57Z | 2026-08-06 | 0 | 8.273 |
| PAAS | 2026-Q2 | 2026-08-13 | 2026-08-12T21:38:01Z | 2026-08-12 | 1 | 2.709 |
| WDH | 2026-Q2 | 2026-09-08 | 2026-09-08T11:30:46Z | 2026-09-08 | 0 | 0.485 |
| CAN | 2026-Q2 | 2026-09-08 | 2026-09-08T11:20:24Z | 2026-09-08 | 0 | 0.8 |

All nine selected authority UTC timestamps equal their selected parent-acceptance evidence timestamps and match the Phase 80 recorded keys. Eight have positive valid P/B inputs. Six are date-aligned, PAAS/WPM are +1; both parent filings occurred after 16:00 ET. Their provider prices match the following day's close, so they are not the parent-filing-day close. BTDR's exact accepted observation lacks provider P/B/marketcap/equityUSD; no alternate provider row was used to fabricate coverage. Its date still aligns with parent acceptance day. No 6-K policy was changed.

## Price-Date Check

Price diagnostic compares the finite positive `osakedata.close` on date, immediate preceding and following stored trading-bar dates (at most seven calendar days away), ticker plus USA market. It does **not** use current close. Absolute price error is `100 × abs(market_close / provider_price − 1)`.

Tolerance is **0.1%**, selected to accommodate rounding without treating the nearest candidate as proof. Multiple candidates within tolerance are classified AMBIGUOUS; unresolved rows retain a nearest-date diagnostic but are not counted as a match. There is no optimization over an extended date window or fitted adjustment factor.

| Match at ≤0.1% | n | % |
| --- | --- | --- |
| SAME | 1720 | 93.07% |
| AMBIGUOUS | 114 | 6.17% |
| UNRECONCILED | 13 | 0.70% |
| NO_MARKET_CANDIDATES | 1 | 0.05% |

1,720 uniquely match SAME; 114 are AMBIGUOUS and all also match SAME. No uniquely matched PREV/NEXT case exists. Total with a neighbor match within 1%: 1,843 / 99.73%. Median best candidate error: 0.0000021311%. One row (BIAF) lacks a usable close within the diagnostic window. There are **zero weekend Sharadar dates**, so weekend behavior cannot be generalized. Holidays were not assigned using an external exchange calendar; observed date-day close coverage is used directly.

For this close-only timing diagnostic, 49 same-date close rows have invalid complete OHLC geometry. Their close can still match provider price, but they are **not eligible production valuation bars** under RawCandle's full-OHLC rule. CSV flags them. This distinction prevents rejection of a matching close from falsely creating a next-day timing inference (e.g. TRU has matching same-date close but invalid OHLC). Only one eligible observation has no same-date close.

1,067 authority events are at/after 16:00 ET; 565 are SAME_DAY provider observations. Their provider close generally precedes or coincides with the result acceptance event, so this is not automatically a post-result close. PAAS/WPM illustrate +1 observation dates after evening acceptance. Price-date and publication timestamps must remain separate even when calendar dates match.

Remaining price discrepancies: 13 fail 0.1% on all three candidates; nine are under 1% and can involve quote rounding/source differences. Larger same-date scale anomalies include **NRDY: provider 12.636 versus close 0.842 (15×)**; **IESC: 372.27 versus 744.54 (2×)**; **MNST: 45.18 versus 90.36 (2×)**. AVB is 187.78 versus 67.2324; GPMT is 1.50 versus 14.8256. These show incompatible stored price bases/source histories in a few cases. No matching split action was available in the narrowly queried 2026 action records for GPMT/NRDY/AVB/IESC; precise causes remain unresolved. Do not invent split corrections or move their price date to the nearest numerical candidate. Most prices are consistent, but **universal split-basis consistency is not proven**.

## Historical Reference Assessment

Classification: **`PROVIDER_OBSERVATION_PB`**. It is an ARQ filing-indexed provider ratio, commonly near authority publication, but the evidence does not prove exact form-10 acceptance for every row or a first-result-publication close. Therefore `RESULT_PUBLICATION_PB` and an unconditional `FILING_DATE_PB` are stronger than this audit supports. “Near publication” describes the measured majority, not a guaranteed field contract.

Historical/reference suitability: **YES**, transparently presented with source observation date, dimensions, input basis and quality flags. PIT-safe: **NO** under current RawCandle contracts. Provider AR claims, retained observation hashes and calendar dates do not prove vintage completeness or intraday price/value availability; revised split bases and current accepted provenance remain as described in P/B.1.

A simple per-quarter accepted ARQ provider-reference series is feasible later, but must preserve observation binding and allow missing values. Choosing the latest provider row per fiscal quarter may replace the originally known vintage. This study uses latest endpoints plus required 6-K keys; it does not validate every historical ARQ quarter, MR restatement behavior or a backtest archive.

## Recommended Data Contract

Reporting-only proposed field: **`PB_PROVIDER_OBSERVATION`**.

- Value: original finite positive Sharadar ARQ `pb`, checked against the same payload's `marketcap/equityusd` with three-decimal absolute rounding tolerance. Retain native original value as audit data; display NULL/reason for missing/nonpositive equity and invalid inputs.
- Date: `provider_observation_date = payload.date`, a date-only provider index; not an intraday publication or trading timestamp. Also retain reportperiod, fiscalperiod, lastupdated, fetched timestamp and source availability.
- Binding: accepted quarter and exact source observation ID/hash/provenance; never mix price/cap/equity from separate rows. Production promotion requires its own accepted derived provenance policy rather than treating shares provenance as canonical equity authority.
- Context: separate `result_publication_timestamp`, source, explicit comparison timezone and calendar delta; separate independently validated provider-price close date. Never rename all three dates “publication date.”
- Meaning: provider parent-book-equity ratio; not certified common equity, not a current ratio, not a score input. Ownership/price anomalies are flagged rather than silently repaired.
- History: current accepted provider-reference series, not PIT-certified. Keep derived/reporting state rebuildable; no storage or production behavior introduced here.

## Next Step

Recommend **both**, in separate later reporting work: current RawCandle P/B using the restricted validated market-cap/latest-parent-equity contract from P/B.1, and provider observation P/B as a dated historical/reference field. Do not expose the latter as result-publication P/B. First define accepted equity/provider-reference provenance and close-adjustment quality gates; the issuer-release gap remains an evidence limitation. Score/model calibration is outside this work.

## Validation and Safety

Deterministic checks: unique company-quarter CSV keys; exact ARQ/fiscal/report binding; shares match; same-row inputs; authority timestamp equals selected evidence; all nine Phase 80 keys included; publication conversion and delta roundtrip; counts sum; positive inputs and ratio-rounding residuals; finite outputs and CSV roundtrip. Percentiles use linear interpolation. No full suite was run. `git diff --check` completed before commit.

Only this report and the compact timing-validation CSV are committed. The research helper and temporary summaries remain under `/tmp`, outside the commit. No production DB, source code, score, publication authority, generation, review queue or scheduler mutation; no refresh/rebuild/live workflow. Unrelated worktree changes preserved. Nothing pushed.
