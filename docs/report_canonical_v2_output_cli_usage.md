# Canonical Report V2 Output CLI Usage

## 1. Purpose

This CLI renders one selected canonical Report V2 output by horizon and format.

Important boundaries:

- it is an explicit canonical output path
- it is not the legacy/default report path
- it is not a default replacement
- it reads existing canonical V2 tables

Use it when canonical V2 rows already exist in the target database and you want one specific output rendered in a controlled, opt-in way.

## 2. Command

CLI path:

```bash
PYTHONPATH=. python3 dev_tools/run_report_canonical_v2_output.py
```

Required args:

- `--db`
- `--signal-date`
- `--taxonomy-version`
- `--horizon`
- `--format`

Optional args:

- `--market`
- `--run-id`
- `--output`
- `--summary-output`
- `--require-parity-ok`
- `--parity-horizons`

## 3. Supported horizons and formats

Supported horizons:

- `daily`
- `rolling2`
- `rolling5`
- `rolling30`

Supported formats:

- `markdown`
- `csv`

| Horizon | Markdown family | CSV family |
| --- | --- | --- |
| `daily` | Daily canonical V2 report | Daily canonical V2 report |
| `rolling2` | Rolling2 canonical V2 report | Rolling2 canonical V2 report |
| `rolling5` | Rolling5 canonical V2 report | Rolling5 canonical V2 report |
| `rolling30` | Rolling30 canonical V2 report | Rolling30 canonical V2 report |

## 4. Examples

Known-good temp smoke database used in accepted canonical V2 output smokes:

- DB: `/home/kalle/projects/rawcandle/temp/analysis_report_canonical_v2_all_outputs_smoke_2026-05-29.db`
- signal date: `2026-05-29`
- taxonomy version: `DC_TAXONOMY_FULL_V1`
- run id: `REPORT_CANONICAL_V2_ALL_OUTPUTS_SMOKE_2026_05_29`

Production DB paths should be used only when canonical V2 tables already exist there and the user intentionally wants to read them.

### Daily Markdown to file

```bash
PYTHONPATH=. python3 dev_tools/run_report_canonical_v2_output.py \
  --db /home/kalle/projects/rawcandle/temp/analysis_report_canonical_v2_all_outputs_smoke_2026-05-29.db \
  --signal-date 2026-05-29 \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --run-id REPORT_CANONICAL_V2_ALL_OUTPUTS_SMOKE_2026_05_29 \
  --horizon daily \
  --format markdown \
  --output /home/kalle/projects/rawcandle/temp/datacenter_daily_canonical_v2_output_cli_2026-05-29.md
```

### Rolling2 CSV to file

```bash
PYTHONPATH=. python3 dev_tools/run_report_canonical_v2_output.py \
  --db /home/kalle/projects/rawcandle/temp/analysis_report_canonical_v2_all_outputs_smoke_2026-05-29.db \
  --signal-date 2026-05-29 \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --run-id REPORT_CANONICAL_V2_ALL_OUTPUTS_SMOKE_2026_05_29 \
  --horizon rolling2 \
  --format csv \
  --output /home/kalle/projects/rawcandle/temp/datacenter_rolling2_canonical_v2_output_cli_2026-05-29.csv
```

### Rolling5 Markdown with parity gate

```bash
PYTHONPATH=. python3 dev_tools/run_report_canonical_v2_output.py \
  --db /home/kalle/projects/rawcandle/temp/analysis_report_canonical_v2_all_outputs_smoke_2026-05-29.db \
  --signal-date 2026-05-29 \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --run-id REPORT_CANONICAL_V2_ALL_OUTPUTS_SMOKE_2026_05_29 \
  --horizon rolling5 \
  --format markdown \
  --require-parity-ok \
  --output /home/kalle/projects/rawcandle/temp/datacenter_rolling5_canonical_v2_output_cli_2026-05-29.md
```

### Rolling30 CSV with parity gate and summary output

```bash
PYTHONPATH=. python3 dev_tools/run_report_canonical_v2_output.py \
  --db /home/kalle/projects/rawcandle/temp/analysis_report_canonical_v2_all_outputs_smoke_2026-05-29.db \
  --signal-date 2026-05-29 \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --run-id REPORT_CANONICAL_V2_ALL_OUTPUTS_SMOKE_2026_05_29 \
  --horizon rolling30 \
  --format csv \
  --require-parity-ok \
  --output /home/kalle/projects/rawcandle/temp/datacenter_rolling30_canonical_v2_output_cli_2026-05-29.csv \
  --summary-output /home/kalle/projects/rawcandle/temp/rolling30_output_cli.summary.txt
```

## 5. Safety boundaries

This CLI:

- opens DB read-only
- does not run migrations
- does not run orchestrator
- does not write DB
- does not call legacy daily/rolling report builders
- does not call dashboard code
- does not change current default report paths
- is opt-in only
- should write output filenames that include `canonical_v2`

## 6. Parity gate

`--require-parity-ok` runs the read-only parity audit before rendering.

Rules:

- default parity horizon is the selected `--horizon`
- `--parity-horizons` can override this with a comma-separated list
- allowed parity horizons are `daily`, `rolling2`, `rolling5`, `rolling30`
- non-OK parity exits nonzero
- no automatic repair is attempted

Important scope note:

- parity here means classification/content-decision parity
- it does not mean visual/layout parity

## 7. What this does not guarantee

This CLI does not guarantee:

- byte-for-byte legacy Markdown parity
- byte-for-byte legacy CSV parity
- visual/layout parity
- completed rendering of deferred sections
- presence of source-era fields that were not copied into canonical V2
- suitability as a default replacement

Canonical output is not a default replacement yet.

## 8. Recommended workflow

1. Build canonical V2 tables separately, or use the temp DB created by the all-output smoke tool.
2. Run the all-output smoke release gate when changing canonical code.
3. Use `run_report_canonical_v2_output.py` for one selected horizon/format.
4. Use `--require-parity-ok` for important manual outputs.
5. Keep canonical output files separate from legacy report files.

## 9. Related tools

- `dev_tools/run_report_canonical_v2_all_outputs_smoke.py`
  - temp-copy release gate that builds canonical V2 rows, runs parity, and emits all 8 outputs
- `dev_tools/run_report_canonical_v2_parity_audit.py`
  - explicit read-only parity audit tool
- per-horizon canonical dev-tools
  - `dev_tools/run_report_canonical_v2_daily_markdown.py`
  - `dev_tools/run_report_canonical_v2_daily_csv.py`
  - `dev_tools/run_report_canonical_v2_rolling2_markdown.py`
  - `dev_tools/run_report_canonical_v2_rolling2_csv.py`
  - `dev_tools/run_report_canonical_v2_rolling5_markdown.py`
  - `dev_tools/run_report_canonical_v2_rolling5_csv.py`
  - `dev_tools/run_report_canonical_v2_rolling30_markdown.py`
  - `dev_tools/run_report_canonical_v2_rolling30_csv.py`

The all-output smoke tool is the release gate.

## 10. Current checkpoint

Current accepted checkpoint:

- daily Markdown: smoke accepted
- daily CSV: smoke accepted
- rolling2 Markdown: smoke accepted
- rolling2 CSV: smoke accepted
- rolling5 Markdown: smoke accepted
- rolling5 CSV: smoke accepted
- rolling30 Markdown: smoke accepted
- rolling30 CSV: smoke accepted
- combined all-output smoke: accepted
- selected horizon/format output CLI smoke: accepted
