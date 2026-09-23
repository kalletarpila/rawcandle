# Phase 13G.3.40 Sharadar `sharesbas` Provider Semantics

## Decision

**Result: `PROVIDER_SEMANTICS_PARTIALLY_CONFIRMED`.**

Official Sharadar documentation confirms the ARQ/MRQ dimension contract, the
dimension-specific meaning of `date`, and the distinct economic meanings of
`sharesbas`, `shareswa`, and `shareswadil`. It does not document a rule that
sets `MRQ sharesbas(Q)` to `ARQ sharesbas(Q-1)`.

The best-supported explanation is a dimension/timing construction effect.
`sharesbas` is the split-adjusted shares outstanding stated on the cover of a
related 10-K/10-Q, while AR observations are indexed to the filing date and MR
observations are indexed to the fiscal report period. The local 96.68% exact
prior-ARQ match is consistent with MRQ carrying the previously reported cover
share state at the later quarter's report-period date. That final carry-forward
step remains an empirical inference, not a documented provider rule.

Confidence is **high** for the field and date definitions, **high** for the
existence of the local lag pattern, and **medium** for the construction/timing
explanation. Confidence is **low** that the provider's exact implementation or
intent has been established without a support response.

Keep canonical `shares_outstanding <- ARQ sharesbas` unchanged. Provider
confirmation is required before reconsidering authority or implementing any
MRQ overlay.

Phase 13G.3.40 does not change ARQ/MRQ runtime authority. It verifies whether
official provider semantics explain the observed sharesbas timing behavior.

## Research Question

Phase 13G.3.39 found that, among 81,978 authority-matched ARQ/MRQ
`sharesbas` disagreements, 79,252 (96.675%) satisfy:

`MRQ sharesbas(Q) == ARQ sharesbas(Q-1)`

This study asks whether official provider material defines that behavior and
whether `sharesbas` has a dimension-specific meaning distinct from the
weighted-share fields.

## Official Sources Reviewed

1. [Sharadar Fundamentals documentation](https://sharadar.com/docs/fundamentals),
   including reporting dimensions, restatements, time indexing, table columns,
   and query parameters.
2. [Sharadar Indicator Descriptions documentation](https://sharadar.com/docs/descriptions)
   and its official `descriptions` API for `dimension`, `sharesbas`,
   `shareswa`, `shareswadil`, `date`, `reportperiod`, `calendardate`, and
   `lastupdated`.
3. [Nasdaq Data Link SF1 documentation](https://data.nasdaq.com/databases/SF1/documentation),
   including the current SF1 table identity and metadata route.
4. [Nasdaq/Quandl Sharadar data fact sheet](https://resources.quandl.com/a/res-hub/Sharadar_Datasheet_final.pdf),
   which describes data with and without restatements and indexing to filing
   date or fiscal/report period.

No third-party source was needed as semantic authority. The current Nasdaq
Data Link metadata endpoint identifies `SHARADAR/SF1` as Core US Fundamentals,
with primary key `(ticker, dimension, datekey, reportperiod)`, but returned no
column descriptions anonymously. Sharadar's current official documentation
and descriptions API supplied the field definitions.

## Dimension Definitions

Sharadar defines the dimensions as follows:

| Dimension | Official meaning | Time index | Restatements |
| --- | --- | --- | --- |
| ARQ | As-Reported Quarterly | SEC form 10 filing date | Excluded |
| MRQ | Most-Recent Reported Quarterly | Fiscal/report period | Included |

The AR view is point-in-time, presents the latest reporting period available
at each filing date, and can contain multiple observations in a quarter. The MR
view presents the most recently reported data for each reporting period and is
updated when prior-period financials are restated. Sharadar describes AR as
typically suitable for backtesting and MR as suitable for assessing business
performance after restatements.

These definitions are `CONSISTENT_WITH_LOCAL_DATA`, including the distinct
ARQ/MRQ dates and generally matching economic fields. Restatement inclusion by
itself is `INSUFFICIENT_TO_EXPLAIN` the systematic one-quarter `sharesbas` lag.

## Field Definitions

The official descriptions API defines:

| Field | Official meaning | Implication |
| --- | --- | --- |
| `sharesbas` | Shares or ownership units outstanding, as stated on the cover of the related 10-K/10-Q, after stock-split adjustment | A reported cover-date stock measure, not an EPS denominator |
| `shareswa` | Weighted-average shares used to calculate basic EPS, based on issuance timing during the period | A period-average income-statement measure |
| `shareswadil` | Weighted-average diluted shares used to calculate diluted EPS, based on issuance timing during the period | A period-average diluted EPS denominator |

The provider does **not** define `sharesbas` as necessarily measured on the
fiscal quarter end. This corrects the overly strong local shorthand "actual
period-end basic common shares outstanding." A filing cover commonly states
shares as of a date associated with the filing, which can be later than the
reported fiscal period end.

The official `sharesbas` definition is
`PARTIALLY_EXPLAINS_LOCAL_DATA`: a cover-date stock measure can differ from the
same quarter's weighted averages and can create timing differences when moved
between filing-date and report-period views. It is
`INSUFFICIENT_TO_EXPLAIN` why MRQ selects exactly the prior ARQ value in 96.68%
of disagreements because no official source states that selection rule.

## Date Semantics

| Field | ARQ | MRQ | Point-in-time availability use |
| --- | --- | --- | --- |
| `date` | SEC filing date | `reportperiod` | ARQ: suitable filing-time index; MRQ: not an availability date |
| `reportperiod` | Fiscal period end | Fiscal period end | No; the information is normally published later |
| `calendardate` | Normalized report period | Normalized report period | No; comparison/query bucket only |
| `lastupdated` | Last date the provider entry was updated | Same | Update/discovery metadata, not original market availability |

Sharadar explicitly says `date` is the SEC filing date for AR dimensions and
`reportperiod` for MR dimensions. It is also the observation date used for
price-based fields. The provider warns that the MR report-period date is
typically months before information reaches the market and is subject to
restatement. It also notes that a separate 8-K disclosure can precede the form
10 filing by days or, rarely, weeks.

The local findings that MRQ `date == reportperiod` in 100% of disagreements and
ARQ `date > reportperiod` in 99.999% are therefore
`CONSISTENT_WITH_LOCAL_DATA`. The roughly 37-day difference is not evidence
that MRQ was publicly available earlier; MRQ `date` is a dimension-specific
report-period index.

For point-in-time modeling, ARQ `date` is the safe provider filing-time index,
subject to the documented possibility of an earlier separate disclosure.
`lastupdated` can discover provider record changes but cannot replace original
availability or RawCandle's preserved `first_public_result_date`. MRQ `date`,
`reportperiod`, and `calendardate` must not be used as publication dates.

## Comparison With Local Evidence

| Provider statement | Local observation | Classification |
| --- | --- | --- |
| AR is filing-date indexed and excludes restatements | ARQ `date` is after `reportperiod` in 99.999% of disagreements | `CONSISTENT_WITH_LOCAL_DATA` |
| MR is report-period indexed and includes restatements | MRQ `date == reportperiod` in 100% of disagreements | `CONSISTENT_WITH_LOCAL_DATA` |
| `sharesbas` is the split-adjusted cover-report outstanding count | MRQ usually carries an earlier reported stock state while current ARQ differs | `PARTIALLY_EXPLAINS_LOCAL_DATA` |
| `shareswa` and `shareswadil` are period-weighted EPS denominators | They do not exhibit the dominant exact prior-ARQ lag | `CONSISTENT_WITH_LOCAL_DATA` |
| MR contains the most recently reported data for a reporting period | Latest economic fields generally agree while `sharesbas` diverges | `PARTIALLY_EXPLAINS_LOCAL_DATA` |
| MR includes restatements | Exact prior-quarter equality dominates rather than same-quarter corrections | `INSUFFICIENT_TO_EXPLAIN` |
| `lastupdated` is the last provider-entry update date | ARQ/MRQ `lastupdated` agrees in 98.941% of disagreements | `CONSISTENT_WITH_LOCAL_DATA`, but `INSUFFICIENT_TO_EXPLAIN` the lag |

No official statement directly contradicts the observed rows. The official
cover-report definition does contradict the old local *description* of
`sharesbas` as inherently quarter-end, but it does not invalidate the ARQ
values or authorize MRQ replacement.

## Hypothesis Evaluation

| Hypothesis | Official support | Local support | Confidence |
| --- | --- | --- | --- |
| H1: MRQ intentionally carries prior-quarter period-end shares | None explicit. Official material does not call MRQ `sharesbas` a prior-quarter value or necessarily a period-end value. | Very strong numerical lag pattern. | Medium for observed behavior; low for intent |
| H2: Provider construction mechanically inherits a prior reported state | No carry-forward algorithm is documented. | Strongest direct fit: 96.675% exact prior-ARQ equality. | Medium |
| H3: ARQ and MRQ apply different timing to the same cover-share field | Strong indirect support: `sharesbas` is a cover-report stock measure, AR is filing-date indexed, and MR is report-period indexed. No field-specific MR timing rule is stated. | Strong support from dates, exact lag, and same-quarter economic-field agreement. | Medium-high as explanation; medium overall |
| H4: Undocumented provider implementation/data-quality artifact | Official silence leaves this possible but does not prove an error. | The systematic pattern suggests implementation convention rather than random corruption; exceptions remain. | Medium |
| H5: Another documented rule | No official rule found beyond restatement and time-indexing contracts. | No better local rule identified. | Low |

H3, with an H2-style carry-forward mechanism, is the best-supported working
explanation. The evidence cannot distinguish a deliberately designed
field-specific construction rule from a stable undocumented implementation
artifact. Calling it a confirmed provider rule would overstate the sources.

## Weighted-Share Findings

The documentation explains why weighted fields should not be expected to
follow `sharesbas`. `shareswa` and `shareswadil` summarize shares over the
current income-statement period for EPS calculations. `sharesbas` is a stock
count reported on a filing cover and is adjusted for splits.

That stock-versus-period distinction is consistent with Phase 13G.3.39:

- exact same-quarter equality with ARQ `shareswa`: 0.748%;
- exact same-quarter equality with ARQ `shareswadil`: 0.561%;
- within 0.1% of `shareswa`: 30.896%;
- within 0.1% of `shareswadil`: 12.548%;
- exact equality with prior-quarter ARQ `sharesbas`: 96.675%.

The official definitions explain why the weighted fields remain same-period
EPS denominators and why they cannot replace period ownership counts. They do
not explain the exact MRQ carry-forward algorithm.

## Provider-Support Gap

Official documentation is sufficient for dimension, date, stock-versus-flow,
and restatement semantics. It is not sufficient for the observed field-level
MRQ construction. Provider confirmation is still needed before any authority
change.

### Draft support question

> In current Sharadar Fundamentals/SF1 data, we compared authority-matched ARQ
> and MRQ rows by fiscal quarter. Among 81,978 rows where `sharesbas` differs,
> 79,252 (96.675%) have `MRQ sharesbas(Q) == ARQ sharesbas(Q-1)` exactly, while
> same-quarter `shareswa` and `shareswadil` do not show this pattern. For
> example, AAPL 2026-Q3 has ARQ `sharesbas=14,594,180,000`, but MRQ
> `sharesbas=14,687,356,000`, exactly the AAPL 2026-Q2 ARQ value; AMD 2026-Q2
> similarly uses its 2026-Q1 ARQ value. Your documentation defines
> `sharesbas` as the split-adjusted outstanding count stated on the related
> 10-K/10-Q cover, AR `date` as the filing date, and MR `date` as
> `reportperiod`. Is MRQ `sharesbas` intentionally carried from the most recent
> cover-share observation available at the report-period date? If so, please
> confirm the exact as-of/timing rule and whether it is guaranteed across MRQ.
> If not, is the prior-quarter pattern a data issue or another construction
> rule? Please also confirm whether `shareswa` and `shareswadil` retain
> same-reporting-period EPS-denominator semantics in both dimensions.

Do not send this question as part of the phase.

## Decision Impact

- Provider semantics result: `PROVIDER_SEMANTICS_PARTIALLY_CONFIRMED`.
- Official documentation sufficient: **PARTIALLY**.
- Provider-support question needed: **YES**.
- Current ARQ-only `sharesbas` policy: **remain unchanged**.
- Any reconsideration requires explicit provider confirmation plus a separate
  impact and migration phase.
- Runtime code, databases, workflows, scheduler state, and ARQ/MRQ authority
  remain unchanged.

## Final Confidence

Overall confidence: **medium**. The official definitions and local measurements
fit a coherent timing explanation, but the defining 96.68% prior-quarter rule
is not stated by Sharadar. It remains a highly repeatable empirical behavior,
not a contractual semantic guarantee.
