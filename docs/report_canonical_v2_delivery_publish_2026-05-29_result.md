# Canonical Report V2 Final Delivery Publish Result — 2026-05-29

## 1. Executive Summary

The final delivery publish completed successfully for the first accepted production canonical V2 slice.

Verdict:

`ACCEPT_CANONICAL_V2_FINAL_DELIVERY_PUBLISH_AS_BASELINE`

Key points:

- all 8 canonical V2 outputs were written to the separate canonical delivery directory
- parity is `OK`
- mismatch count is `0`
- production DB was not modified by publish
- legacy/default report paths were not touched
- canonical output remains opt-in and not a default replacement

## 2. Delivery Identity

- production DB path:
  - `/home/kalle/projects/rawcandle/data/analysis.db`
- signal date:
  - `2026-05-29`
- taxonomy version:
  - `DC_TAXONOMY_FULL_V1`
- production run id:
  - `REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29`
- delivery directory:
  - `/home/kalle/projects/rawcandle/canonical_reports/2026-05-29`
- summary file path:
  - `/home/kalle/projects/rawcandle/canonical_reports/2026-05-29/publish_summary.txt`

## 3. V2 Slice and Parity Verification

- group context rows: `216`
- daily context rows: `236`
- window context rows: `708`
- classification rows: `1180`
- required classification type coverage:
  - `daily_trigger = 236`
  - `rolling2_sell_pressure = 236`
  - `rolling5_pullback = 236`
  - `rolling30_buy = 236`
  - `rolling30_exit = 236`
- parity status: `OK`
- parity mismatch count: `0`

## 4. Published Output Files

- `/home/kalle/projects/rawcandle/canonical_reports/2026-05-29/datacenter_daily_canonical_v2_2026-05-29.md`
  - `563` lines
  - `78536` bytes
- `/home/kalle/projects/rawcandle/canonical_reports/2026-05-29/datacenter_daily_canonical_v2_2026-05-29.csv`
  - `541` lines
  - `88774` bytes
- `/home/kalle/projects/rawcandle/canonical_reports/2026-05-29/datacenter_rolling2_canonical_v2_2026-05-29.md`
  - `767` lines
  - `122564` bytes
- `/home/kalle/projects/rawcandle/canonical_reports/2026-05-29/datacenter_rolling2_canonical_v2_2026-05-29.csv`
  - `732` lines
  - `140453` bytes
- `/home/kalle/projects/rawcandle/canonical_reports/2026-05-29/datacenter_rolling5_canonical_v2_2026-05-29.md`
  - `825` lines
  - `129189` bytes
- `/home/kalle/projects/rawcandle/canonical_reports/2026-05-29/datacenter_rolling5_canonical_v2_2026-05-29.csv`
  - `790` lines
  - `146678` bytes
- `/home/kalle/projects/rawcandle/canonical_reports/2026-05-29/datacenter_rolling30_canonical_v2_2026-05-29.md`
  - `1342` lines
  - `217518` bytes
- `/home/kalle/projects/rawcandle/canonical_reports/2026-05-29/datacenter_rolling30_canonical_v2_2026-05-29.csv`
  - `1301` lines
  - `243061` bytes

## 5. Output Sanity Checks

- Markdown headings were correct:
  - daily
  - rolling2
  - rolling5
  - rolling30
- CSV parse checks passed
- required family-specific CSV sections existed:
  - daily: `daily_trigger_rows`
  - rolling2: `rolling2_sell_pressure_rows`
  - rolling5: `rolling5_pullback_rows`
  - rolling30: `rolling30_buy_rows`, `rolling30_exit_rows`
- rolling30 CSV has no `next_action` column

## 6. Safety Boundary Result

- production DB was not modified by publish
- repo code/tests/docs were not modified by publish
- legacy/default report paths were not touched
- scheduler was not touched
- dashboard was not touched
- only files under `/home/kalle/projects/rawcandle/canonical_reports/2026-05-29/` were written

## 7. Current Parity Caveat

- canonical rendering uses V2 rows
- parity gate still uses the existing parity audit
- current parity audit reads source/current rows
- source/current tables were present in production DB
- parity-gated publish is therefore not yet fully V2-only
- this is acceptable for current production `analysis.db`
- future V2-only parity audit would be a separate improvement

## 8. Operational Meaning

- this is the first accepted canonical V2 publish in the final canonical delivery directory
- it publishes from an already-built production V2 slice
- it is not a production build
- it is not a default report replacement
- it is not legacy layout parity
- canonical outputs remain opt-in

## 9. Residual Risks / Follow-ups

- parity gate remains source/current dependent
- canonical outputs differ from legacy layout/shape
- deferred sections remain deferred
- delivery is file-based only
- email/scheduler/dashboard integration is not active
- future date builds still require backup/preflight/parity process

## 10. Recommended Next-Step Options

### A. Use canonical reports manually from canonical delivery directory

- safe for accepted `2026-05-29` slice

### B. Plan email attachment integration

- requires separate design
- must not alter legacy attachment logic accidentally

### C. Plan V2-only parity audit

- would remove the current source/current parity dependency

### D. Wait for next source-data update

- required before next new-date production build
