# Canonical Report V2 Delivery Directory and Naming Policy

## 1. Purpose

This policy defines where canonical V2 published report files should be written and how they should be named.

Important boundaries:

- this is not a scheduler integration
- this is not an email integration
- this is not a dashboard integration
- this is not a default report replacement
- this is for explicit/manual canonical V2 publishes

## 2. Recommended Delivery Model

`READY_FOR_SEPARATE_CANONICAL_DELIVERY_DIR`

Recommended model:

- use a separate canonical delivery directory
- do not use `temp/` for accepted production publishes
- do not use the legacy report directory yet
- do not use legacy filenames

Why this model is recommended:

- avoids overwriting legacy reports
- keeps canonical outputs easy to find
- preserves opt-in separation
- allows future email/report delivery to include canonical outputs explicitly

## 3. Directory Policy

- `/home/kalle/projects/rawcandle/temp/`
  - use only for test, smoke, and temporary validation outputs
- `/home/kalle/projects/rawcandle/canonical_reports/<YYYY-MM-DD>/`
  - use for manual production canonical V2 publish outputs
- existing legacy report directory
  - do not use unless explicitly approved later

Recommended example:

- `/home/kalle/projects/rawcandle/canonical_reports/2026-05-29/`

## 4. Filename Policy

Use these exact filenames:

- `datacenter_daily_canonical_v2_<YYYY-MM-DD>.md`
- `datacenter_daily_canonical_v2_<YYYY-MM-DD>.csv`
- `datacenter_rolling2_canonical_v2_<YYYY-MM-DD>.md`
- `datacenter_rolling2_canonical_v2_<YYYY-MM-DD>.csv`
- `datacenter_rolling5_canonical_v2_<YYYY-MM-DD>.md`
- `datacenter_rolling5_canonical_v2_<YYYY-MM-DD>.csv`
- `datacenter_rolling30_canonical_v2_<YYYY-MM-DD>.md`
- `datacenter_rolling30_canonical_v2_<YYYY-MM-DD>.csv`

Rules:

- must include `canonical_v2`
- must include signal date
- must not include spaces
- must use stable lowercase horizon markers
- must not collide with legacy filenames

## 5. Publish Command Example

`DO NOT RUN IN THIS TASK`

```bash
PYTHONPATH=. python3 dev_tools/run_report_canonical_v2_publish_outputs.py \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --output-dir /home/kalle/projects/rawcandle/canonical_reports/2026-05-29 \
  --signal-date 2026-05-29 \
  --taxonomy-version DC_TAXONOMY_FULL_V1 \
  --run-id REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29 \
  --summary-output /home/kalle/projects/rawcandle/canonical_reports/2026-05-29/publish_summary.txt \
  --overwrite-output
```

Clarifications:

- DB is read-only
- no migrations
- no orchestrator
- no DB writes
- parity gate still uses source/current rows through existing parity audit
- output path is separate from legacy report path

## 6. Email / Attachment Policy

- do not modify email scripts yet
- do not send canonical outputs automatically yet
- later attachment logic must explicitly select:
  - `*canonical_v2*.md`
  - `*canonical_v2*.csv`
- legacy attachment logic must remain unchanged until explicitly modified
- if both legacy and canonical reports are sent, subject/body must clearly label canonical V2 as opt-in/non-default

## 7. Safety Rules

- never overwrite legacy report files
- never publish canonical V2 reports under ambiguous names
- never use legacy filenames for canonical outputs
- keep canonical outputs opt-in
- keep default report paths unchanged
- do not schedule canonical publishing yet
- do not send canonical outputs automatically yet
- document every production publish run
- maintain parity-gate caveat until V2-only parity exists

## 8. Current Accepted Example

Accepted first production publish:

- source production slice:
  - `2026-05-29 / DC_TAXONOMY_FULL_V1`
- production run id:
  - `REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29`
- temp publish dir used:
  - `/home/kalle/projects/rawcandle/temp/report_canonical_v2_prod_publish_2026-05-29`
- status:
  - publish accepted with parity `OK`
- note:
  - future accepted manual production publishes should use `/home/kalle/projects/rawcandle/canonical_reports/<YYYY-MM-DD>/`, not `temp/`

## 9. Non-goals

- no default report replacement
- no legacy layout parity guarantee
- no email integration
- no scheduler integration
- no dashboard integration
- no automatic publish cadence
- no cleanup/rebuild policy
