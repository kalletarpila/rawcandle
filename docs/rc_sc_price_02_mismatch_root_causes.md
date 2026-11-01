# RC-SC-PRICE-02: mismatch causes and materiality

Study completed 2026-11-01, Europe/Helsinki. This report incorporates the user's
materiality addendum. Investigation only; no bridge implementation or activation.
See [append semantics](rc_sc_price_02_adjusted_price_and_append_semantics.md),
[split/scheduler safety](rc_sc_price_02_split_safety_and_scheduler.md),
[implementation plan](rc_sc_price_02_implementation_plan.md) and
[acceptance evidence](rc_sc_price_02_acceptance_evidence.md).

## What the 931 actually contain

The PRICE-01 mismatch cohort is preserved, not reselected to improve results.
All 931 were remeasured against accepted Source rows for October 23, 26–30.
Current canonical-reader requalification reproduces the 4,201 identity matches,
4,169 with recent usable observations, 24 unavailable and eight partly HELD.
Every remeasured usable ticker's dependency still matched its requalification token.

| Difference dimensions, mutually exclusive | Tickers |
| --- | ---: |
| Volume only | 690 |
| OHLC only | 74 |
| Both | 167 |
| Total | 931 |

There are **5,582 common observations**, 773 with an OHLC difference and 2,394 with
a volume difference. OHLC affects 241 tickers, volume 857; those sets overlap.
The full nominal six-position cohort is 5,586: four positions lack a common
qualified observation. No missing position is filled for this study.

A second, exclusive classification assigns the strongest observed explanatory
signature, with invalid legacy bars taking precedence:

| Signature | Tickers | What is established |
| --- | ---: | --- |
| Recorded dividend and uniform OHLC factor scaling | 81 | Accepted Adj Close/Close scales OHLC; ordinary OHLC supports the pre-dividend RC vintage |
| Dividend plus other raw-bar differences | 11 | Both patterns exist; dividend alone does not explain every field |
| Other nonuniform raw OHLC differences | 86 | Bar revisions/quality differences are real; exact upstream cause remains unproven |
| Invalid stored RC OHLC somewhere in overlap | 63 | 86 legacy observations: zero OHLC or Open/Close outside High/Low; Source bars remain qualified |
| Volume-only revision signature | 690 | Same prices, different historical provider volume; not explained by dividend multiplication |
| Total | 931 | Signatures are not blanket production qualification |

These signatures can coexist with action or availability exclusions. Across the
931, 99 have a dividend together with finite price differences (81 pure scaling,
18 with other differences, including seven assigned to the legacy-quality row).
Six have independent reverse-ledger split/action holds in the final matrix; neither
of the two shared-date ratio conflicts belongs to this original 931 cohort.
There are no precision-only tickers. Four missing common positions and the genuinely
unresolved raw-bar/provider-revision causes are retained explicitly rather than
claimed resolved from a representative sample.

Among the 63 legacy-quality tickers, 14 have zero Open/High/Low on October 28
(42 undefined relative-price denominators). The others have unordered positive
bars. Only **five** have an invalid *actual latest append anchor*: ASG, BULLW, CCOR,
EDF and EIC. Older defects are retained and reported; they are not converted into
valid observations by tolerance, returned as new prices, or silently repaired.
PRICE-01's exact-overlap restriction conflated these historical issues with a
requirement to rewrite or exactly reproduce all history.

No ticker's entire mismatch is floating-point-only at a 1e-12 relative screen.
No full six-observation window shows a constant price/volume multiplier under the
study's stated pattern tests. This does not mean there are no shorter level shifts:
65 tickers have three-or-more-observation uniform historical price-scaling segments,
all with the recorded-dividend signature. ONDS has one nearly constant older
three-observation volume ratio near 1.00237; it then changes to 1.00308, 1.02247
and 1.0. That is not a persistent current share-unit multiplier. New unexplained
scale steps must still be withheld independently of numerical tolerance.

## Magnitudes

Relative error is `abs(Source_reconstructed - RC) / abs(RC)`. Price statistics
below multiply that ratio by 100 to show **percent**, not percentage points of
return. Quantiles use NumPy's linear quantile convention. Undefined zero-denominator
fields are counted separately, never assigned a zero error or denominator floor.

| Changed price fields | Fields | Median % | p90 % | p95 % | p99 % | Maximum % |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Open | 375 | 0.574681 | 1.988070 | 2.327603 | 67.704891 | 72.658295 |
| High | 587 | 0.368623 | 1.434060 | 2.188278 | 3.403376 | 63.565894 |
| Low | 588 | 0.350810 | 1.367988 | 1.988070 | 3.177407 | 63.565894 |
| Close | 366 | 0.568743 | 1.523003 | 2.240148 | 63.565890 | 63.565894 |
| All changed finite fields | 1,916 | 0.475860 | 1.471672 | 2.197805 | 63.565891 | 72.658295 |

These numerical measurements include finite fields in invalid RC bars, so BULLW's
72.66% Open difference is not treated as a tolerable valid-price observation.
Across all 22,286 finite relative fields, including unchanged ones, median and p90
are zero, p95 0.370918%, p99 1.434060%. Full valid-bar changed-observation maximum
error has median 0.190046%, p90 1.340783%, p95 1.940780%, p99 3.191587%, maximum
63.565894% (687 observations); this exposes the distribution without invalid-bar inflation.

| Volume statistic | Observations | Median | p90 | p95 | p99 | Maximum |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Changed, relative % | 2,394 | 0.341722 | 3.037542 | 5.682308 | 57.347928 | 6,628.832852 |
| Changed, absolute provider units | 2,394 | 19,150 | 159,620 | 354,990 | 2,748,277 | 15,258,365,849 |
| All positive-RC-volume observations, relative % | 5,490 | 0 | 1.170277 | 2.642510 | 12.406656 | 6,628.832852 |

There are 92 both-zero volumes and one RC-positive/Source-zero observation; relative
error for RC=0 is undefined, not zero. The single zero/nonzero mismatch is in an
already invalid RC October 28 bar. The maximum absolute difference belongs to
BTC-USD, whose legacy RC market label is usa but volume/calendar are crypto-specific;
it is separately held for missing Source coverage and is not a share-volume exemplar.

For observations with both volumes <=1,000, 22 changed observations have absolute
median 28.5, p90 93.1, p95 100.85, p99 407.52 and maximum 489 units; relative
median 6.5483%, maximum 118.9781%. Excluding the zero/nonzero invalid-bar case leaves
21 changed positive pairs. Examples: 864→900 (36 units, 4.17%), 652→700 (48,
7.36%), and 202→300 (98, 48.51%). Equal percentages mean very different absolute
changes at these volumes. At <=100, there are no changed valid positive examples;
the sole changed observation is the invalid zero/nonzero case.

## Dates, vintages and normalization

| Session | Common observations | OHLC changed | Volume changed |
| --- | ---: | ---: | ---: |
| 2026-10-23 | 930 | 189 | 436 |
| 2026-10-26 | 931 | 145 | 389 |
| 2026-10-27 | 931 | 142 | 408 |
| 2026-10-28 | 931 | 129 | 482 |
| 2026-10-29 | 930 | 108 | 580 |
| 2026-10-30 | 929 | 60 | 99 |

**832 of 931 have an exactly matching latest common OHLCV observation**, even though
earlier overlap differs. October 30 changed price observations have median maximum
field error 0.047502%; changed-volume median is 0.012831%. Outliers remain substantial.

The retained RC October 31 USA log records 04:35–07:23 EET, 4,226 inserts and no
ticker failures. Accepted Source captures for AMD and QQQ are respectively
09:15:49 UTC and 10:38:38 UTC that day, after that RC run. RC does not preserve
per-row capture receipts, so these clocks establish workflow ordering, not an
original-response audit for every price. Source per-row receipts/vintages are retained
in ignored evidence references.

Of changed-volume pairs, 2,105 increase and 289 decrease; 2,369/2,394 Source volumes
are multiples of 100, versus 1,715 RC volumes. This is a strong historical response
quantization/revision signature. Both installed yfinance versions fill missing volume
with zero and cast to int64; neither inspected effective path rounds volume to 100
or multiplies it by a dividend factor. Thus library normalization alone does not
explain these observed changes. Range-dependent/provider-vintage revisions are a
supported explanation; the original RC payloads are unavailable to prove the exact
upstream cause of every pair. Source's permitted missing-volume/Adj-Close substitutions
also have UNKNOWN original provenance and are not retroactively guessed from values.

Examples:

- AAPL October 29: RC volume 42,382,900, Source 42,582,100 (+0.4700%); October 30
  both 67,797,500. Prices match at both recent dates.
- HCMAU October 30: 5,865→5,900 volume (+35, 0.5968%); maximum OHLC difference
  0.000963%. This supports accepting marginal differences rather than bitwise equality.
- ARI October 29: RC Close 6.4499998093 equals Source ordinary Close; accepted
  Adj Close 2.3499999046, factor 0.3643410813. The recorded October 30 dividend
  is 4.1. October 30 Close is 2.3299999237 in both systems. This is an observed
  adjustment-vintage transition, not a guessed factor derived from cash sums.
- BULLW October 30: RC Open 4.3888998032 exceeds RC High 1.1999000311; Source
  Open/High are 1.2000000477. The invalid anchor is a hard hold.
- BEAG October 30: 11,421→768,500 volume (67.2883×); ETY 382,054→392,700
  (+2.7865%). Neither is admitted by the recommended volume gate.

## Proposed tolerances and coverage sensitivity

Recommend separate, explicit rules **after** identity, session, action, currency,
Source-quality and unit gates:

| Purpose | Proposed rule | Evidence/reason |
| --- | --- | --- |
| Floating-point roundoff | Relative <=1e-12, no economic absolute-price floor | Same-vintage reconstruction is exact in both libraries; operation-order noise is much smaller than quoted price revisions |
| OHLC materiality | Each field relative <=0.1% (10 basis points) at the actual append anchor | Latest changed-field median 0.0475%; 0.01% unnecessarily rejects marginal revisions, while 0.5% admits larger unresolved raw-bar changes |
| Normal volume | Relative <=1% | Admits measured marginal updates such as HCMAU 0.5968%; 2% adds no anchor coverage under the bounded absolute rule, 5% would admit ETY's 2.79% |
| Small counted volume | If both positive, max volume >100 and <=5,000, Source volume is a multiple of 100: absolute <=50 units and relative <=10% may qualify | 50 is half the observed 100-unit quantization; 5,000=50/1%, where the absolute allowance ceases to add coverage. Accepts 1,014→1,000 without a cliff at 1,000 |
| Very small/zero volume | Both <=100: exact; zero/nonzero always hold | No valid changed small observations support widening; denominator inflation is forbidden |

The small-volume rule requires verified compatible counted units, not arbitrary
currency/crypto units. The observed quantization supports an error allowance; the
adapter does **not** round or change accepted volume. Tests with absolute allowances
0, 10, 50 and 100 show two added raw anchor cases at 50 and no further gain at 100.
These thresholds are bounded recommendations for this temporary bridge, not an
optimized policy or a proof that every passing observation is correct.

The following counts are **additional candidates from the original 931**, after the
current hard gates, using the actual latest common RC anchor. Small-volume rules
above are included. The other 3,202 previously exact candidates are held fixed.

| OHLC limit | Volume 0.5% | Volume 1% | Volume 2% | Volume 5% |
| --- | ---: | ---: | ---: | ---: |
| 0.0001% (1 ppm) | 838 | 838 | 838 | 839 |
| 0.01% | 852 | 853 | 853 | 854 |
| **0.1%** | 878 | **879** | 879 | 880 |
| 0.5% | 888 | 889 | 889 | 890 |

Of the recommended 879 additions, **801 already match exactly at the anchor**;
their differences concern history. Only **78 require marginal anchor tolerances**.
The recommended model yields 4,081 prospective numerical/contract candidates,
not 4,081 newly available rows or activated tickers. The mutually exclusive full
matrix and remaining holds are in the [plan](rc_sc_price_02_implementation_plan.md).

Requiring every historical session to match is not the RC append contract. As a
diagnostic, applying numerical limits to three whole tail observations would leave
3,759 candidates after hard gates and hold 55 normal historical dividend-factor
transitions. That screen is not recommended as an automatic admission requirement.
The anchor plus context/action checks distinguish current unit compatibility from
historical revisions; see the append report for the separately qualified dividend case.
