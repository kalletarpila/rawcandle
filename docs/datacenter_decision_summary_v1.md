# Datacenter Decision Summary V1

## Purpose

The Datacenter Daily Decision Summary is a compact daily markdown report intended
as the primary manual analysis input for ChatGPT. It is generated from existing
Datacenter markdown reports and keeps the full daily and rolling reports
available for debugging and drill-down.

V1 is intentionally markdown-in and report-artifact-out only. It does not read
or write production databases, change source reports, or create new analytics.
The primary output is Markdown. It can also write an optional semicolon-delimited
CSV companion intended for Excel-compatible tabular review. The CSV is not an
`.xlsx` workbook.

The standalone CLI remains available for manual use. The Datacenter scheduler
report workflow also attempts to generate this summary automatically after the
daily, rolling 2, rolling 5, and rolling 30 markdown reports have been produced.

Sections 2 through 10 include short static descriptions that explain what the
section contains and how an occasional reader should use it. These descriptions
do not change the parsed source data, deterministic labels, tables, or scanner
logic.

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

The optional CSV output is:

```text
--output-csv
```

## Example

```bash
python3 -m rawcandle.cli.build_datacenter_decision_summary \
  --current-daily reports/datacenter_daily_YYYY-MM-DD_HHMM_full.md \
  --previous-daily reports/datacenter_daily_PREVIOUS-YYYY-MM-DD_HHMM_full.md \
  --current-rolling2 reports/datacenter_rolling_2_YYYY-MM-DD_HHMM_full.md \
  --current-rolling5 reports/datacenter_rolling_5_YYYY-MM-DD_HHMM_full.md \
  --current-rolling30 reports/datacenter_rolling_30_YYYY-MM-DD_HHMM_full.md \
  --output reports/datacenter_decision_summary_YYYY-MM-DD_HHMM_full.md \
  --output-csv reports/datacenter_decision_summary_YYYY-MM-DD_HHMM_full.csv
```

Omit `--output-csv` when only the Markdown summary is needed.

## Comparison Logic

The summary uses deterministic fields parsed from the source markdown:

- Ecosystem dashboard change comes from the current rolling 2 report.
- Ticker and watchlist status changes compare previous daily against current
  daily.
- Rolling 5 and rolling 30 reports provide scanner and broader window context.

The output labels are report-derived states, not investment advice.

The CSV uses a stable generic row schema:

```text
section;subsection;row_type;field;value;previous_value;current_value;change;ticker;group_name;metric;notes
```

Each section is represented as filterable rows rather than preserving Markdown
formatting. This keeps the CSV useful in spreadsheet tools while leaving the
Markdown report unchanged.

In the scheduler/report workflow, `previous_daily` is auto-discovered from the
same output directory by selecting the latest `datacenter_daily_*_full.md` report
with a signal date earlier than the current report. If no previous daily report
is available, automatic summary generation is skipped non-fatally and the source
reports remain usable.

When automatic summary generation succeeds, the scheduler/report workflow
attempts to create both sibling artifacts:

```text
datacenter_decision_summary_YYYY-MM-DD_HHMM_full.md
datacenter_decision_summary_YYYY-MM-DD_HHMM_full.csv
```

## Limitations

- V1 depends on stable markdown section and table formatting in the source
  reports.
- V1 does not generate new analytics or classifications.
- Scheduler integration is non-fatal: missing source markdown reports or a
  missing previous daily report skip the summary without failing the completed
  daily and rolling reports.
- The CSV companion is generated from the same parsed source markdown as the
  Markdown summary. It does not add separate analytics.
- If source report formatting changes, parser tests may need updates.

## Recommended Daily Workflow

1. Run the normal Datacenter report generation.
2. Use the automatically generated decision summary when the scheduler/report
   workflow produced it.
3. If needed, run the standalone decision summary CLI manually with the current
   and previous daily reports plus the current rolling 2, rolling 5, and rolling
   30 reports.
4. Use the generated decision summary as the primary file for manual or ChatGPT
   analysis.
5. Keep the full source reports available for drill-down.
