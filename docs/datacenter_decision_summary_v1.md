# Datacenter Decision Summary V1

## Purpose

The Datacenter Daily Decision Summary is a compact daily markdown report intended
as the primary manual analysis input for ChatGPT. It is generated from existing
Datacenter markdown reports and keeps the full daily and rolling reports
available for debugging and drill-down.

V1 is intentionally markdown-in / markdown-out only. It does not read or write
production databases, change source reports, or create new analytics.

## Required Inputs

The CLI requires all source reports explicitly:

```text
--current-daily
--previous-daily
--current-rolling2
--current-rolling5
--current-rolling30
--output
```

## Example

```bash
python3 -m rawcandle.cli.build_datacenter_decision_summary \
  --current-daily reports/datacenter_daily_YYYY-MM-DD_HHMM_full.md \
  --previous-daily reports/datacenter_daily_PREVIOUS-YYYY-MM-DD_HHMM_full.md \
  --current-rolling2 reports/datacenter_rolling_2_YYYY-MM-DD_HHMM_full.md \
  --current-rolling5 reports/datacenter_rolling_5_YYYY-MM-DD_HHMM_full.md \
  --current-rolling30 reports/datacenter_rolling_30_YYYY-MM-DD_HHMM_full.md \
  --output reports/datacenter_decision_summary_YYYY-MM-DD_HHMM_full.md
```

## Comparison Logic

The summary uses deterministic fields parsed from the source markdown:

- Ecosystem dashboard change comes from the current rolling 2 report.
- Ticker and watchlist status changes compare previous daily against current
  daily.
- Rolling 5 and rolling 30 reports provide scanner and broader window context.

The output labels are report-derived states, not investment advice.

## Limitations

- V1 depends on stable markdown section and table formatting in the source
  reports.
- V1 does not generate new analytics or classifications.
- V1 is not scheduler-integrated.
- If source report formatting changes, parser tests may need updates.

## Recommended Daily Workflow

1. Run the normal Datacenter report generation.
2. Run the decision summary CLI with the current and previous daily reports plus
   the current rolling 2, rolling 5, and rolling 30 reports.
3. Use the generated decision summary as the primary file for manual or ChatGPT
   analysis.
4. Keep the full source reports available for drill-down.
