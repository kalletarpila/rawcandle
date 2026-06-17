# Canonical Report V2 Production Publish Workflow

## 1. Purpose

This workflow publishes canonical V2 reports from an already-built production canonical V2 slice.

Important boundaries:

- this is publish only
- this is not a production build
- this does not run migrations
- this does not run orchestrator
- this does not replace legacy/default reports
- canonical outputs remain opt-in

Use this workflow only after the target canonical V2 slice already exists in production and has been accepted for publish use.

## 2. Current Accepted Production Slice

- production DB path:
  - `/home/kalle/projects/rawcandle/data/analysis.db`
- signal date:
  - `2026-05-29`
- taxonomy version:
  - `DC_TAXONOMY_FULL_V1`
- production run id:
  - `REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29`
- production parity:
  - `OK`
- mismatch count:
  - `0`

## 3. Publish Command

CLI path:

```bash
PYTHONPATH=. python3 dev_tools/run_report_canonical_v2_publish_outputs.py
```

Required args:

- `--db`
- `--output-dir`
- `--signal-date`
- `--taxonomy-version`
- `--run-id`

Optional args:

- `--market`
- `--summary-output`
- `--overwrite-output`

Accepted production publish command:

```bash
PYTHONPATH=. python3 dev_tools/run_report_canonical_v2_publish_outputs.py \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --output-dir /home/kalle/projects/rawcandle/temp/report_canonical_v2_prod_publish_2026-05-29 \
  --signal-date 2026-05-29 \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --run-id REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29 \
  --summary-output /home/kalle/projects/rawcandle/temp/report_canonical_v2_prod_publish_2026-05-29.summary.txt \
  --overwrite-output
```

## 4. What The Publish Tool Does

The publish tool:

- opens DB read-only
- verifies the requested V2 slice exists
- checks nonzero V2 row coverage
- checks required classification types
- runs parity audit before successful publish
- writes all 8 outputs to a caller-provided output dir
- writes deterministic summary lines
- enforces overwrite protection unless `--overwrite-output` is used

Output families emitted:

- daily Markdown
- daily CSV
- rolling2 Markdown
- rolling2 CSV
- rolling5 Markdown
- rolling5 CSV
- rolling30 Markdown
- rolling30 CSV

## 5. What The Publish Tool Does Not Do

The publish tool does not:

- run migrations
- run orchestrator
- write DB
- modify source tables
- call legacy report builders
- write to default report paths
- modify dashboard tables
- modify scheduler state

## 6. Current Parity Dependency Caveat

This caveat is important and should be stated directly.

- canonical rendering itself uses canonical V2 rows
- the publish parity gate currently uses the existing parity audit
- the existing parity audit reads source/current rows
- therefore parity-gated publish currently requires source/current tables to be present
- this is acceptable for production `analysis.db`
- this means parity-gated publish is not yet fully V2-only
- do not claim publish is source-table-free while parity is enabled
- a future V2-only parity audit would be a separate improvement

## 7. Accepted Production Publish Result

Accepted DB-V2-64 publish result:

- command exit code: `0`
- parity status: `OK`
- mismatch count: `0`
- all 8 outputs emitted
- no production DB writes
- no repo changes

Accepted output files and sizes:

- daily Markdown: `563` lines, `78536` bytes
- daily CSV: `541` lines, `88774` bytes
- rolling2 Markdown: `767` lines, `122564` bytes
- rolling2 CSV: `732` lines, `140453` bytes
- rolling5 Markdown: `825` lines, `129189` bytes
- rolling5 CSV: `790` lines, `146678` bytes
- rolling30 Markdown: `1342` lines, `217518` bytes
- rolling30 CSV: `1301` lines, `243061` bytes

Published filenames:

- `datacenter_daily_canonical_v2_2026-05-29.md`
- `datacenter_daily_canonical_v2_2026-05-29.csv`
- `datacenter_rolling2_canonical_v2_2026-05-29.md`
- `datacenter_rolling2_canonical_v2_2026-05-29.csv`
- `datacenter_rolling5_canonical_v2_2026-05-29.md`
- `datacenter_rolling5_canonical_v2_2026-05-29.csv`
- `datacenter_rolling30_canonical_v2_2026-05-29.md`
- `datacenter_rolling30_canonical_v2_2026-05-29.csv`

## 8. Safety Boundaries

- output directory must be explicit
- output filenames include `canonical_v2`
- canonical output is not legacy layout parity
- canonical output is not default replacement
- deferred sections remain deferred
- default daily/rolling report paths remain unchanged
- scheduler/dashboard integration is not included

## 9. Recommended Operational Use

1. Build the canonical V2 slice separately using the production build runbook.
2. Confirm parity is OK.
3. Use the publish tool to emit all 8 outputs to a separate `canonical_v2` directory.
4. Review output and summary.
5. Only later decide whether these outputs should be copied, emailed, or surfaced elsewhere.

Clarifications:

- this is currently a manual publish workflow
- it should not be scheduled automatically yet
- any move to a final report delivery path needs separate planning

## 10. Follow-up Options

### A. Use current publish workflow manually

Safe for accepted production slices.

### B. Add V2-only parity audit later

Would remove the current source/current-row parity dependency.

### C. Add final report delivery integration

Not yet recommended without separate design.

### D. Scheduler/dashboard integration

Out of scope for now.
