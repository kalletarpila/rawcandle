# Canonical Report V2 Production Rollout Checkpoint

## 1. Executive Summary

Status:

`CANONICAL_V2_PRODUCTION_PUBLISH_BASELINE_COMPLETE`

Canonical Report V2 has reached the first full production publish checkpoint for the accepted `2026-05-29 / DC_TAXONOMY_FULL_V1` slice.

At this checkpoint:

* the first production canonical V2 build is complete
* the first final canonical delivery publish is complete
* all 8 canonical outputs exist in the final canonical delivery directory
* parity is `OK`
* canonical output is still opt-in
* this is not a default report replacement

## 2. Accepted Production Slice

* production DB path:

  * `/home/kalle/projects/rawcandle/data/analysis.db`
* signal date:

  * `2026-05-29`
* taxonomy version:

  * `DC_TAXONOMY_FULL_V1`
* production run id:

  * `REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29`
* canonical delivery directory:

  * `/home/kalle/projects/rawcandle/canonical_reports/2026-05-29`
* backup path from production build:

  * `/home/kalle/projects/rawcandle/temp/analysis.db.backup.20260601T073739Z.sqlite`
* production build result doc path:

  * `docs/report_canonical_v2_production_build_2026-05-29_result.md`
* final delivery result doc path:

  * `docs/report_canonical_v2_delivery_publish_2026-05-29_result.md`

## 3. Completed Milestones

| Milestone | Status | Evidence / doc reference path | Notes |
| --- | --- | --- | --- |
| canonical V2 schema present in production | complete | `docs/report_canonical_v2_production_build_runbook.md` | Production canonical V2 schema was established before accepted production use. |
| production build completed | complete | `docs/report_canonical_v2_production_build_2026-05-29_result.md` | First accepted production slice build completed for `2026-05-29`. |
| production parity audit passed | complete | `docs/report_canonical_v2_production_build_2026-05-29_result.md` | Production parity recorded as `OK` with mismatch count `0`. |
| selected output render passed | complete | `docs/report_canonical_v2_production_build_2026-05-29_result.md` | Selected production output render completed with summary `OK`. |
| all-output smoke passed | complete | `docs/report_canonical_v2_production_build_2026-05-29_result.md` | Post-build all-output smoke completed with parity `OK`. |
| production publish workflow accepted | complete | `docs/report_canonical_v2_production_publish_workflow.md` | Explicit production canonical V2 publish workflow documented and accepted for manual use. |
| final canonical delivery directory accepted | complete | `docs/report_canonical_v2_delivery_policy.md` | Separate canonical delivery directory policy accepted. |
| delivery/naming policy documented | complete | `docs/report_canonical_v2_delivery_policy.md` | Canonical files stay separate from legacy/default report naming. |
| final delivery publish result documented | complete | `docs/report_canonical_v2_delivery_publish_2026-05-29_result.md` | Final delivery publish to `canonical_reports/2026-05-29` accepted as baseline. |

## 4. Delivered Output Family

| Output family | Filename | Line count | Byte count | Status |
| --- | --- | ---: | ---: | --- |
| daily Markdown | `datacenter_daily_canonical_v2_2026-05-29.md` | 563 | 78536 | delivered |
| daily CSV | `datacenter_daily_canonical_v2_2026-05-29.csv` | 541 | 88774 | delivered |
| rolling2 Markdown | `datacenter_rolling2_canonical_v2_2026-05-29.md` | 767 | 122564 | delivered |
| rolling2 CSV | `datacenter_rolling2_canonical_v2_2026-05-29.csv` | 732 | 140453 | delivered |
| rolling5 Markdown | `datacenter_rolling5_canonical_v2_2026-05-29.md` | 825 | 129189 | delivered |
| rolling5 CSV | `datacenter_rolling5_canonical_v2_2026-05-29.csv` | 790 | 146678 | delivered |
| rolling30 Markdown | `datacenter_rolling30_canonical_v2_2026-05-29.md` | 1342 | 217518 | delivered |
| rolling30 CSV | `datacenter_rolling30_canonical_v2_2026-05-29.csv` | 1301 | 243061 | delivered |

## 5. Safety Boundaries Preserved

The following safety boundaries were preserved across the first production canonical V2 rollout checkpoint:

* source DB was backed up before the production build
* source table row counts were unchanged
* publish workflow uses read-only DB access
* default daily/rolling report paths are unchanged
* legacy report generation is unchanged
* scheduler is unchanged
* dashboard is unchanged
* no email integration was added
* outputs are under `/home/kalle/projects/rawcandle/canonical_reports/2026-05-29/`
* canonical outputs remain opt-in

## 6. Current Operational Use

Safe now:

* manually read and use canonical outputs from `/home/kalle/projects/rawcandle/canonical_reports/2026-05-29/`
* manually run `run_report_canonical_v2_output.py` for a selected horizon/format when canonical V2 rows already exist
* manually run `run_report_canonical_v2_publish_outputs.py` for an already-built slice
* always use the parity gate or parity-aware publish workflow
* keep canonical files separate from legacy reports

Not safe yet:

* automatic scheduling
* replacing legacy outputs
* sending canonical outputs automatically by email
* dashboard integration
* rebuilding an existing slice without an explicit replacement policy

## 7. Known Caveats

* parity-gated publish is not fully V2-only yet
* parity audit currently reads source/current rows
* canonical output is not legacy layout parity
* canonical CSV is not legacy byte-for-byte parity
* deferred sections remain deferred
* source-era fields not copied into canonical V2 may be absent
* production V2 slices are authoritative per date/taxonomy/key, not parallel archives by `run_id`

## 8. Remaining Roadmap Options

### A. V2-only parity audit

Goal:

* remove source/current dependency from parity-gated publish

When useful:

* before trying to make publish fully canonical-table-only
* before broader automation

### B. Email attachment integration

Goal:

* optionally include canonical reports in email delivery

Rules:

* separate design required
* explicit `*canonical_v2*` patterns only
* legacy attachment behavior unchanged unless explicitly changed

### C. Scheduler integration

Goal:

* automate canonical build and publish later

Rules:

* not recommended yet
* requires multiple successful manual production builds first
* must define latest complete source-date selection

### D. Next production date build

Goal:

* build the next new source date when available

Rules:

* only after source data update
* backup, preflight, zero target-slice check, and parity are required

### E. Backfill policy

Goal:

* optionally build older unbuilt dates such as `2026-05-28`

Rules:

* separate policy required
* not part of the normal next-date production cadence

### F. Replacement / cleanup policy

Goal:

* safely rebuild existing slices if needed

Rules:

* separate design required
* no blind overwrite
* backup and explicit approval required

## 9. Recommended Immediate Position

At this checkpoint:

* do not run another production build now unless a new complete source date appears
* do not schedule canonical build or publish yet
* do not change legacy or default reports yet
* canonical reports can be used manually from the delivery directory
* the next technical branch should be chosen deliberately

## 10. Recommended Next-Step Candidates

Candidate next tasks:

* `DB-V2-71 — Read-only design for V2-only parity audit, no behavior changes.`
* `DB-V2-71 — Read-only design for canonical V2 email attachment opt-in, no behavior changes.`
* `DB-V2-71 — Wait for next source-data update and run candidate check, no production write.`
* `DB-V2-71 — Read-only backfill policy design for historical canonical V2 slices, no writes.`

Primary recommendation:

* `DB-V2-71 — Read-only design for V2-only parity audit, no behavior changes.`

Rationale:

* it removes the main known caveat
* it strengthens publish isolation
* it should be done before automation or scheduler work
