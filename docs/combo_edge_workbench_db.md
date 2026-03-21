# Combo Edge Workbench Database Guide

This document explains the purpose, fields, and calculations of the database
[`data/combo_edge_workbench.db`](/home/kalle/projects/rawcandle/data/combo_edge_workbench.db)
in plain language.

The goal of this database is to make combo and bullish divergence research
faster and easier to repeat. It is a research database, not a production
signal database.

## 1. What This Database Is For

The workbench database collects two kinds of rows:

- pure bullish divergence events
- bullish divergence + candle combo events

It links each finding to the underlying confirmed R3 bullish divergence event
and stores a small set of research-friendly values, such as:

- pivot gap
- pivot drop percent
- RSI
- forward returns
- winsorized forward returns

This makes it possible to study questions such as:

- Which combo patterns work best?
- Does the setup work better when the drop is shallow or deep?
- Does the combo work better on pivot day or one day after?

## 2. Tables in the Database

The database currently has two tables:

- `edge_cases`
- `edge_area_summary`

### `edge_cases`

This is the row-level research table.

Each row is one research case:

- either one pure `Bullish Divergence`
- or one combo such as `BullDiv & Hammer`

### `edge_area_summary`

This is the aggregated summary table.

It groups cases into wider research buckets so you can study broader regions
instead of only exact single values.

Examples of bucketed regions:

- gap `11-14`
- drop `>7`
- RSI scope `LT_36`

## 3. Where the Source Data Comes From

The workbench is built from two existing databases:

- `analysis.db`
- `osakedata.db`

Source tables used:

- `analysis_findings`
- `divergence_data`
- `osakedata`

### Source role of each table

`analysis_findings`
- tells us that a signal was found
- examples:
  - `Bullish Divergence`
  - `BullDiv & Hammer`
  - `BullDiv & Bullish Engulfing`

`divergence_data`
- tells us the confirmed R3 bullish divergence event details
- examples:
  - event date
  - pivot2 date
  - pivot gap
  - pivot drop percent
  - RSI

`osakedata`
- gives the ticker's trading-day price history
- used to calculate forward returns
- also used to calculate combo offset using trading-day positions

## 4. How Rows Are Built

### Pure bullish divergence row

If the finding pattern is:

- `Bullish Divergence`

then the workbench links it directly to the same-day R3 bullish divergence event:

- `analysis_findings.date = divergence_data.date`

### Combo row

If the finding pattern is a combo:

- `BullDiv & Hammer`
- `BullDiv & Piercing Pattern`
- `BullDiv & Bullish Engulfing`
- `BullDiv & Dragonfly Doji`

then the workbench links the combo finding to an R3 bullish divergence event
for the same ticker using the current combo-linking logic:

1. First preference:
   - exact event-day match
   - `finding_date == event_date`

2. Otherwise:
   - pivot2-window match
   - combo day must be within trading-day window `[-3, +3]` around `pivot2_date_r3`

3. If several candidates are possible:
   - choose deterministically
   - event-day match wins over window-only match
   - then nearest pivot2 distance wins
   - then earlier `event_date` wins lexically

If no matching divergence event is found, that finding is not inserted into
the workbench.

## 5. Field Explanations: `edge_cases`

Below is the meaning of each field in `edge_cases`.

### `case_kind`

Text label telling what kind of research row this is.

Possible values:

- `bull_div`
- `combo`

Meaning:

- `bull_div` = pure bullish divergence event
- `combo` = candle + bullish divergence combo

### `source_pattern`

The exact pattern name from `analysis_findings`.

Examples:

- `Bullish Divergence`
- `BullDiv & Hammer`
- `BullDiv & Bullish Engulfing`

### `ticker`

The stock symbol.

Examples:

- `AAPL`
- `NOKIA.HE`

### `finding_date`

The day when the finding itself exists in `analysis_findings`.

This is the anchor day for return calculation in this workbench.

Meaning:

- for pure `Bullish Divergence`, this is the event day
- for combos, this is the combo day

### `linked_event_date`

The R3 bullish divergence event date in `divergence_data` that this case is
linked to.

For pure bullish divergence rows:

- `linked_event_date` is the same as `finding_date`

For combo rows:

- `linked_event_date` may be the same day
- or a nearby linked event found by the combo-linking logic

### `pivot2_date_r3`

The stored R3 pivot2 date from `divergence_data`.

This is the second price pivot date used by the confirmed R3 divergence event.

### `combo_offset`

Trading-day distance between the combo day and the R3 pivot2 day.

Formula:

```text
combo_offset = trading_day_index(finding_date) - trading_day_index(pivot2_date_r3)
```

Important:

- this uses trading-day positions from `osakedata`
- it does not use calendar-day difference

Examples:

- `0` = combo happened on the pivot2 trading day
- `1` = combo happened one trading day after pivot2
- `-1` = combo happened one trading day before pivot2

For pure bullish divergence rows:

- `combo_offset` is `NULL`

### `pivot_gap_r3`

The R3 pivot gap from the linked divergence event.

Formula:

```text
pivot_gap_r3 = p2_index - p1_index
```

Plain-language meaning:

- how many trading bars separate the two price pivots used by the R3 event

### `pivot_drop_pct_r3`

The drop percentage stored for the linked R3 event.

Plain-language meaning:

- how deep the price decline was around the divergence setup

The exact geometric meaning comes from the existing divergence engine and is not
redefined by the workbench. The workbench only copies the stored value from
`divergence_data`.

### `rsi`

The RSI value copied from the linked divergence event row in `divergence_data`.

This is event-level RSI, not combo-finding-local RSI from `analysis_findings`.

### `bullish_strength`

Bullish divergence strength copied from the linked event in `divergence_data`.

### `bearish_strength`

Bearish divergence strength copied from the linked event in `divergence_data`.

This is included for context even when the row itself is a bullish case.

### `ret_10`, `ret_20`, `ret_30`

Raw forward returns in percent from `finding_date`.

Formula:

```text
ret_h = ((close(t+h) / close(t0)) - 1) * 100
```

Where:

- `t0 = finding_date`
- `h` is `10`, `20`, or `30` trading days

Important:

- the horizon uses ticker-local trading days from `osakedata`
- if there is not enough future price data, the return is `NULL`

Example:

- if the close rises from `10.00` to `11.50` in 20 trading days:
  - `ret_20 = 15.0`

### `winsor_ret_10`, `winsor_ret_20`, `winsor_ret_30`

Winsorized versions of the raw returns.

Winsorization rule:

```text
min = -50.0
max =  50.0
```

Formula:

```text
winsor_ret_h = clamp(ret_h, -50.0, 50.0)
```

Meaning:

- any return below `-50%` is stored as `-50`
- any return above `50%` is stored as `50`

Why this is useful:

- it reduces the effect of extreme outliers
- it makes averages more stable in research summaries

## 6. Field Explanations: `edge_area_summary`

This table does not store individual cases. It stores grouped summaries.

### `source_pattern`

Pattern being summarized.

Examples:

- `Bullish Divergence`
- `BullDiv & Hammer`

### `rsi_scope`

Simple RSI grouping used in the workbench summary.

Possible values:

- `ALL`
- `LT_36`

Meaning:

- `ALL` = all rows in that bucket
- `LT_36` = only rows where event-level `rsi < 36`

### `gap_bin`

Bucketed version of `pivot_gap_r3`.

Current bin rules:

- `05-07`
- `08-10`
- `11-14`
- `15-18`
- `19-22`
- `23-30`
- `OTHER`
- `UNKNOWN`

### `drop_bin`

Bucketed version of `pivot_drop_pct_r3`.

Current bin rules:

- `<3`
- `3-5`
- `5-7`
- `>7`
- `UNKNOWN`

### `n`

How many `edge_cases` rows belong to that bucket.

### `win_rate_30`

Share of rows with positive raw 30-day return.

Formula:

```text
win_rate_30 = positive_ret_30_count / valid_ret_30_count * 100
```

### `median_ret_30`

Median of raw 30-day returns in that bucket.

Meaning:

- half of the rows are above this value
- half are below

This is often more robust than the ordinary mean when the data contains big
outliers.

### `winsor_ret_10`, `winsor_ret_20`, `winsor_ret_30`

Average winsorized return for the bucket.

Example:

- `winsor_ret_30 = 12.4`
  means the bucket's average 30-day return is `12.4%` after outlier capping

## 7. Current Gap and Drop Buckets

These are the exact grouping rules currently used by the workbench summary.

### Gap buckets

```text
5-7   -> 05-07
8-10  -> 08-10
11-14 -> 11-14
15-18 -> 15-18
19-22 -> 19-22
23-30 -> 23-30
else  -> OTHER
NULL  -> UNKNOWN
```

### Drop buckets

```text
drop < 3.0  -> <3
drop < 5.0  -> 3-5
drop < 7.0  -> 5-7
else         -> >7
NULL         -> UNKNOWN
```

## 8. Important Practical Notes

### This is a research database

This database is meant for analysis, slicing, validation, and reporting.

It is not the source of truth for production divergence calculation.

### Return anchor is `finding_date`

The workbench always calculates forward returns from `finding_date`.

So:

- pure `Bullish Divergence` rows are measured from event day
- combo rows are measured from combo day

### Combo linking is deterministic

Combo rows are not stored with a fixed event link in the source databases.

The workbench creates that link deterministically during the build process,
using the current rules described above.

### Winsorized values are for robustness

The winsorized return fields are not "true realized returns".

They are capped research values that help reduce the impact of extreme outlier
moves when comparing groups.

## 9. Typical Questions This Database Can Answer

Examples:

- Which combo pattern has the strongest median 30-day return?
- Does a setup work better when `combo_offset = 0` or `1`?
- Does a deeper `pivot_drop_pct_r3` improve performance?
- Which `gap_bin` and `drop_bin` regions look strongest?
- Does `rsi < 36` improve edge quality?

## 10. Files Produced Alongside the Database

The workbench pipeline also writes:

- `reports/combo_edge_area_summary.csv`
- `reports/combo_edge_tree_rules.txt`

Meaning:

- `combo_edge_area_summary.csv`
  - exported copy of the `edge_area_summary` table
- `combo_edge_tree_rules.txt`
  - a shallow decision-tree report used for exploratory research only

The tree report is not production logic. It is only a suggestion tool for
finding possible broader edge regions worth validating.
