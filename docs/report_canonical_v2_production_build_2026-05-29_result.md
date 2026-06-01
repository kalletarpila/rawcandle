# Canonical Report V2 Production Build Result — 2026-05-29

## 1. Executive Summary

The first production canonical V2 build completed successfully for `2026-05-29 / DC_TAXONOMY_FULL_V1`.

Verdict:

`ACCEPT_PRODUCTION_CANONICAL_V2_BUILD_AS_BASELINE`

Key points:

* production parity is `OK`
* source table row counts were unchanged
* the production canonical V2 baseline now exists for the accepted target slice
* canonical output is still opt-in only and not a default replacement

## 2. Build Identity

* production DB path:

  * `/home/kalle/projects/rawcandle/data/analysis.db`
* signal date:

  * `2026-05-29`
* taxonomy version:

  * `DC_TAXONOMY_FULL_V1`
* production run id:

  * `REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29`
* created_at_utc:

  * `2026-05-29T00:00:00Z`
* backup path:

  * `/home/kalle/projects/rawcandle/temp/analysis.db.backup.20260601T073739Z.sqlite`
* backup size:

  * `3405672448` bytes

## 3. Pre-build State

* source ticker row count:

  * `236`
* source group row count:

  * `54`
* source synthetic row count:

  * `53`
* V2 total counts before build:

  * `dc_report_run_v2 = 0`
  * `dc_report_context_group_v2 = 0`
  * `dc_report_context_daily_v2 = 0`
  * `dc_report_context_window_v2 = 0`
  * `dc_report_classification_v2 = 0`
* target-slice counts before build for `2026-05-29 / DC_TAXONOMY_FULL_V1`:

  * run rows = `0`
  * group context rows = `0`
  * daily context rows = `0`
  * window context rows = `0`
  * classification rows = `0`
* selected run id row count before build:

  * `0`

## 4. Production Build Result

* migration status:

  * `OK`
* orchestrator status:

  * `OK`
* rows written:

  * group context = `216`
  * daily context = `236`
  * window context = `708`
  * total classification = `1180`
* production row counts for production run id `REPORT_CANONICAL_V2_PROD_BUILD_2026_05_29`:

  * run rows = `1`
  * group context rows = `216`
  * daily context rows = `236`
  * window context rows = `708`
  * classification rows = `1180`

## 5. Classification Distribution

* horizon counts:

  * daily = `236`
  * rolling2 = `236`
  * rolling5 = `236`
  * rolling30 = `472`
* classification type counts:

  * `daily_trigger = 236`
  * `rolling2_sell_pressure = 236`
  * `rolling5_pullback = 236`
  * `rolling30_buy = 236`
  * `rolling30_exit = 236`

## 6. Parity and Output Verification

* production parity:

  * status = `OK`
  * mismatch count = `0`
  * matched count = `1180`
* selected output:

  * path = `/home/kalle/projects/rawcandle/temp/datacenter_rolling30_canonical_v2_prod_2026-05-29.csv`
  * line count = `1301`
  * byte count = `243061`
  * summary path = `/home/kalle/projects/rawcandle/temp/datacenter_rolling30_canonical_v2_prod_2026-05-29.summary.txt`
  * summary status:

    * `SUMMARY status=OK`
    * `SUMMARY parity_status=OK`
    * `SUMMARY parity_mismatch_count=0`
* post-build all-output smoke:

  * status = `OK`
  * verification run id = `REPORT_CANONICAL_V2_POST_PROD_VERIFY_2026_05_29`
  * temp DB = `/home/kalle/projects/rawcandle/temp/analysis_report_canonical_v2_post_prod_verify_2026-05-29.db`
  * parity status = `OK`
  * mismatch count = `0`
  * output family count = `8`
  * summary file path = `/home/kalle/projects/rawcandle/temp/report_canonical_v2_post_prod_verify_2026-05-29.summary.txt`

## 7. Source Table Safety Result

* post-build source ticker count still matches:

  * `236`
* post-build source group count still matches:

  * `54`
* post-build source synthetic count still matches:

  * `53`
* no source table row-count change was detected
* no repo code/tests were modified

## 8. Critical Data Model Reminder

* production V2 rows now exist for `2026-05-29 / DC_TAXONOMY_FULL_V1`
* future builds for the same date/taxonomy must not be run blindly
* `run_id` is not a parallel rowset primary key
* any rebuild for the same slice needs an explicit replace/cleanup plan and separate approval

## 9. Current Operational Status

* the canonical V2 production baseline exists for the first accepted target
* the canonical output CLI can render from production DB with `--require-parity-ok`
* default daily and rolling report paths are unchanged
* scheduler is unchanged
* dashboard is unchanged
* canonical output remains opt-in

## 10. Recommended Operational Next-Step Options

### A. Use canonical output manually for the accepted production slice

* safe if using `run_report_canonical_v2_output.py`
* use `--require-parity-ok`
* write outputs to separate filenames containing `canonical_v2`

### B. Repeat production canonical V2 build for a new date/taxonomy

* requires the same backup, preflight, and parity process
* should use a new explicit run id
* must check target-slice rows first

### C. Plan explicit integration flag or canonical output workflow

* only after preserving current default behavior
* should not replace legacy outputs yet

### D. Dashboard/scheduler integration

* not recommended yet
* requires separate design

## 11. Non-goals / Still Not True

* this is not a default report replacement
* there is no legacy byte-for-byte parity guarantee
* deferred sections remain deferred
* dashboard is not integrated
* scheduler is not integrated
* there is no automatic production build cadence
* there is no cleanup or rebuild workflow yet for already-built canonical slices
