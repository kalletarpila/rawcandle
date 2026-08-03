# Datacenter Taxonomy V2 EC Full Rebuild Retry 2 - 2026-08-03

## Final Classification

```text
DATACENTER_EC_V2_FULL_REBUILD_FAILED_V1_REMAINS_ACTIVE
```

The controlled production DATACENTER EC full historical rebuild for
`DC_TAXONOMY_FULL_V2` was retried once using the corrected proposed-taxonomy
validation from:

```text
e9567fe Fix EC rebuild proposed taxonomy validation
```

The retry did not complete. Chunk 1 failed during ticker fact loading before
any chunk completed, canonical EC watermarks were not finalized, V2 was not
activated, and the scheduler taxonomy configuration remained on V1.

## Source And Repository Verification

Repository state before the retry:

```text
branch=chore/ignore-backups
HEAD=e9567fe1987a109afdf60d877fe226e98e26b822
origin/chore/ignore-backups=e9567fe1987a109afdf60d877fe226e98e26b822
working_tree_expected_change= M watchlists/datacenter_watchlist.txt
```

Relevant backend commits present in history:

```text
174de0e Implement Datacenter V2 DC rebuild acceptance
da52920 Add EC taxonomy full rebuild orchestrator
88bb13f Allow EC taxonomy rebuild to reuse production backup
ba68865 Allow compatible EC rebuild backup schema drift
e9567fe Fix EC rebuild proposed taxonomy validation
```

Taxonomy and backup hashes:

```text
data/datacenter_ecosystem_taxonomy_full_v1.csv
sha256=1ad6ef41b91ef429174090bfcd338acf1e79680d939b4b788c834a79c73e9e5d

data/datacenter_taxonomy_full_v2.csv
sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1

temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite
sha256=ef63868f55073dd3a9eedccea5097871446b02af1577f8c4659fe6dd325db3ea
```

## Initial Production State

Deployment row:

```text
taxonomy_change_id=1
ecosystem_code=DATACENTER
previous_taxonomy_version=DC_TAXONOMY_FULL_V1
proposed_taxonomy_version=DC_TAXONOMY_FULL_V2
source_sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
status=VALIDATION_REQUIRED
dc_rebuild_status=OK
ec_rebuild_status=FAILED
coverage_status=NOT_STARTED
parity_status=NOT_STARTED
activation_status=NOT_ACTIVE
previous_last_error=planner gate did not pass: BLOCKED_TAXONOMY_SOURCE
```

Taxonomy state:

```text
DC_TAXONOMY_FULL_V1 status=ACTIVE is_active=1
DC_TAXONOMY_FULL_V2 status=INACTIVE is_active=0
scheduler datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
scheduler ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
```

Accepted V2 DC rebuild coverage was already present through:

```text
2026-07-31
```

No Datacenter pipeline or DC stage was rerun during this retry.

## Evidence Directory

Evidence was written under:

```text
temp/datacenter_taxonomy_v2_ec_full_rebuild_retry2_20260803T145749Z/
```

Important evidence files:

```text
backup_validation.json
ec_full_rebuild_plan.stdout
ec_full_rebuild_plan.stderr
ec_full_rebuild_plan.json
ec_source_layer_backfill_plan_full_range.json
ec_full_rebuild_run.stdout
ec_full_rebuild_run.stderr
ec_taxonomy_full_rebuild_progress.json
deployment_before.csv
deployment_after_failure.csv
ec_fact_summary_before.csv
ec_fact_summary_after_failure.csv
ec_watermarks_before.csv
ec_watermarks_after_failure.csv
taxonomy_versions_before.csv
taxonomy_versions_after_failure.csv
scheduler_config.before_guard.json
scheduler_config.guard_on.json
scheduler_config.before_restore.json
scheduler_config.restored.json
```

Evidence hashes:

```text
ec_taxonomy_full_rebuild_progress.json
sha256=0c23d18b0fb7bec2eb92fcc10225bf36be521dab2afdb2585158f0049869fc72

ec_full_rebuild_plan.json
sha256=2458623ff9e1afacb5988d1d8ce32999116422474dfeca3fe84597d5d57011d6

ec_source_layer_backfill_plan_full_range.json
sha256=dad725e0ff2ff7fbd704aca5cc1437e14c2b8c5146648dd011e95a991f835820
```

## Scheduler Guard

Before writes, a scheduler config backup was created in the retry evidence
directory. Only this key was changed:

```text
skip_next_run=true
```

Verification after setting the guard:

```text
changed_keys=skip_next_run
unexpected_changed_keys=NONE
datacenter_taxonomy_version=DC_TAXONOMY_FULL_V1
ec_source_layer_taxonomy_version=DC_TAXONOMY_FULL_V1
```

After the failed retry, the guard was restored:

```text
skip_next_run=false
changed_keys=skip_next_run
unexpected_changed_keys=NONE
```

The restored `scheduler_config.json` matched the pre-guard scheduler config.

## Active Writer Check

Before the production EC write attempt, host-level process and file-handle
checks showed no active writer or open `analysis.db` handle from:

```text
stock update scheduler
Datacenter pipeline
EC latest refresh
EC historical backfill
EC taxonomy full rebuild
taxonomy activation
migration runner
UI process with open analysis.db handle
```

`data/analysis.db-wal` existed but was 0 bytes at the final pre-write check.

## Existing Backup Validation

The original pre-DC-rebuild backup was reused in place. No new full production
DB backup was created.

Validation result:

```text
backup_mode=EXISTING_BACKUP
backup_created_by_orchestrator=false
backup_reused=true
backup_validation_status=OK
backup_schema_compatibility_status=COMPATIBLE_ADDITIVE_DRIFT
backup_schema_exact_match=false
backup_schema_compatible_with_live=true
backup_schema_critical_mismatch_count=0
backup_schema_allowed_difference_count=7
backup_restore_requires_forward_schema_reapply=true
backup_sha256=ef63868f55073dd3a9eedccea5097871446b02af1577f8c4659fe6dd325db3ea
backup_error=None
```

Allowed live-only columns were all in `ec_taxonomy_change_deployment`:

```text
last_error
prepared_at_utc
rebuild_evidence_json
rebuild_evidence_sha256
validation_completed_at_utc
validation_evidence_json
validation_evidence_sha256
```

The retry evidence directory contained no `.sqlite` or `.db` backup file after
the run.

## EC Full-Rebuild Plan

Command:

```bash
python3 -m rawcandle.cli.plan_ec_taxonomy_full_rebuild \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V2 \
  --taxonomy-csv /home/kalle/projects/rawcandle/data/datacenter_taxonomy_full_v2.csv \
  --watchlist /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt \
  --deployment-id 1 \
  --date-from 2025-08-01 \
  --date-to 2026-07-31 \
  --backup-dir /home/kalle/projects/rawcandle/temp/datacenter_taxonomy_v2_ec_full_rebuild_retry2_20260803T145749Z \
  --evidence-output-root /home/kalle/projects/rawcandle/temp/datacenter_taxonomy_v2_ec_full_rebuild_retry2_20260803T145749Z \
  --confirm-db /home/kalle/projects/rawcandle/data/analysis.db \
  --confirm-ecosystem DATACENTER \
  --confirm-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --confirm-deployment-id 1 \
  --confirm-date-from 2025-08-01 \
  --confirm-date-to 2026-07-31 \
  --expected-active-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --scheduler-config /home/kalle/projects/rawcandle/scheduler_config.json
```

Plan result:

```text
exit_code=0
status=READY_TAXONOMY_FULL_REBUILD_PLAN
rebuild_mode=TAXONOMY_FULL_REBUILD
deployment_id=1
taxonomy_version=DC_TAXONOMY_FULL_V2
taxonomy_version_id=2
requested_start=2025-08-01
requested_end=2026-07-31
chunk_count=7
chunk_plan_hash=d18633422e76197901112f89b514eac940634869122538d6012eda9d20375e76
```

Chunk plan:

```text
chunk 1: 2025-08-01..2025-09-29 span=60
chunk 2: 2025-09-30..2025-11-28 span=60
chunk 3: 2025-11-29..2026-01-27 span=60
chunk 4: 2026-01-28..2026-03-28 span=60
chunk 5: 2026-03-29..2026-05-27 span=60
chunk 6: 2026-05-28..2026-07-26 span=60
chunk 7: 2026-07-27..2026-07-31 span=5
```

The chunk sequence was chronological, gapless, non-overlapping, and each chunk
respected the 60-calendar-day limit.

## Corrected Proposed-Taxonomy Source Validation

The high-level rebuild planner does not expose the EC source-layer taxonomy
diagnostics at the root level, so the source-layer backfill planner was also run
read-only in taxonomy-rebuild mode for the accepted range.

Structured diagnostics path:

```text
compatibility_summary
```

Diagnostics:

```text
taxonomy_validation_mode=PROPOSED_TAXONOMY_REBUILD
taxonomy_expected_source=LOADED_PROPOSED_TAXONOMY
taxonomy_expected_version=DC_TAXONOMY_FULL_V2
taxonomy_expected_sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
taxonomy_actual_sha256=178de3b56891a37b7472748b3f05b77625cc5c9dde4637cb63be50aed807e2e1
taxonomy_expected_row_count=350
taxonomy_actual_row_count=350
taxonomy_expected_ticker_count=257
taxonomy_actual_ticker_count=257
taxonomy_expected_layer_count=16
taxonomy_actual_layer_count=16
taxonomy_expected_subindustry_count=37
taxonomy_actual_subindustry_count=37
taxonomy_expected_primary_membership_count=257
taxonomy_actual_primary_membership_count=257
taxonomy_expected_secondary_membership_count=93
taxonomy_actual_secondary_membership_count=93
taxonomy_source_match=true
taxonomy_source_error=NONE
```

The previous V1 active-policy counts `329 / 236` were not used for the V2
taxonomy rebuild gate.

## Orchestrated Rebuild Attempt

Command:

```bash
python3 -m rawcandle.cli.run_ec_taxonomy_full_rebuild \
  --db /home/kalle/projects/rawcandle/data/analysis.db \
  --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V2 \
  --taxonomy-csv /home/kalle/projects/rawcandle/data/datacenter_taxonomy_full_v2.csv \
  --watchlist /home/kalle/projects/rawcandle/watchlists/datacenter_watchlist.txt \
  --deployment-id 1 \
  --date-from 2025-08-01 \
  --date-to 2026-07-31 \
  --backup-dir /home/kalle/projects/rawcandle/temp/datacenter_taxonomy_v2_ec_full_rebuild_retry2_20260803T145749Z \
  --evidence-output-root /home/kalle/projects/rawcandle/temp/datacenter_taxonomy_v2_ec_full_rebuild_retry2_20260803T145749Z \
  --confirm-db /home/kalle/projects/rawcandle/data/analysis.db \
  --confirm-ecosystem DATACENTER \
  --confirm-taxonomy-version DC_TAXONOMY_FULL_V2 \
  --confirm-deployment-id 1 \
  --confirm-date-from 2025-08-01 \
  --confirm-date-to 2026-07-31 \
  --existing-backup-path temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite \
  --confirm-existing-backup-path /home/kalle/projects/rawcandle/temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite \
  --expected-active-taxonomy-version DC_TAXONOMY_FULL_V1 \
  --scheduler-config /home/kalle/projects/rawcandle/scheduler_config.json
```

Result:

```text
exit_code=1
overall_status=FAILED
retry_required=True
watermark_finalization_performed=False
progress_path=/home/kalle/projects/rawcandle/temp/datacenter_taxonomy_v2_ec_full_rebuild_retry2_20260803T145749Z/ec_taxonomy_full_rebuild_progress.json
```

Failed chunk:

```text
failed_chunk_index=1
failed_chunk_range=2025-08-01..2025-09-29
failed_chunk_status=BACKFILL_FAILED
failed_step=load_ec_ticker_signal_daily_from_dc
failed_date=2025-08-01
error=Ticker fact loader returned FAILED
selected_dates_count=41
completed_dates_count=0
skipped_dates_count=19
total_mismatch_count=0
coverage_status=OK
parity_status=OK
watermark_advance_status=NOT_RUN
watermark_advanced=false
```

Skipped dates in chunk 1 were non-selected calendar dates:

```text
2025-08-02,2025-08-03,2025-08-09,2025-08-10,2025-08-16,
2025-08-17,2025-08-23,2025-08-24,2025-08-30,2025-08-31,
2025-09-01,2025-09-06,2025-09-07,2025-09-13,2025-09-14,
2025-09-20,2025-09-21,2025-09-27,2025-09-28
```

The orchestrator did not proceed to chunks 2-7 and no automatic retry was run.

## Post-Failure Production State

Deployment row after the failed retry:

```text
taxonomy_change_id=1
status=VALIDATION_REQUIRED
dc_rebuild_status=OK
ec_rebuild_status=FAILED
coverage_status=NOT_STARTED
parity_status=NOT_STARTED
activation_status=NOT_ACTIVE
last_error=Ticker fact loader returned FAILED
```

EC V2 fact rows after failure:

```text
ec_ticker_signal_daily taxonomy_version_id=2 rows=0
ec_group_signal_daily taxonomy_version_id=2 rows=0
ec_group_synthetic_ohlc_daily taxonomy_version_id=2 rows=0
ec_group_index_daily taxonomy_version_id=2 rows=0
```

EC V1 fact rows remained at the pre-retry counts:

```text
ec_ticker_signal_daily taxonomy_version_id=1 rows=12272 distinct_dates=52 max_date=2026-07-31
ec_group_signal_daily taxonomy_version_id=1 rows=2808 distinct_dates=52 max_date=2026-07-31
ec_group_synthetic_ohlc_daily taxonomy_version_id=1 rows=2756 distinct_dates=52 max_date=2026-07-31
ec_group_index_daily taxonomy_version_id=1 rows=2808 distinct_dates=52 max_date=2026-07-31
```

EC watermark snapshots before and after the failed retry had no diff.

Taxonomy version snapshots before and after the failed retry had no diff:

```text
DC_TAXONOMY_FULL_V1 status=ACTIVE is_active=1
DC_TAXONOMY_FULL_V2 status=INACTIVE is_active=0
```

No whole-range validation was run because the orchestrated rebuild did not
complete. No canonical EC watermark lineage was finalized to V2.

No activation evidence was applied and no activation plan was run after the
failed rebuild, because the successful EC rebuild precondition was not met.

## Explicit Non-Actions

During this retry:

```text
Datacenter pipeline rerun=false
Datacenter stage rerun=false
accepted V2 DC facts altered=false
V2 DC watermarks altered=false
V2 activated=false
V1 marked inactive=false
scheduler taxonomy switched=false
ordinary stock update scheduler run=false
external data fetched=false
unrelated migration applied=false
unrelated cleanup performed=false
new full production DB backup created=false
automatic restore performed=false
manual chunk execution=false
automatic retry=false
network access used=false
taxonomy CSV modified=false
watchlist modified_by_this_retry=false
```

The pre-existing `watchlists/datacenter_watchlist.txt` working-tree modification
remained unstaged and was not altered by this retry.

## Next Action

Do not retry the full rebuild again until the ticker fact loader failure is
diagnosed. The next investigation should start from:

```text
failed_step=load_ec_ticker_signal_daily_from_dc
failed_date=2025-08-01
error=Ticker fact loader returned FAILED
progress=/home/kalle/projects/rawcandle/temp/datacenter_taxonomy_v2_ec_full_rebuild_retry2_20260803T145749Z/ec_taxonomy_full_rebuild_progress.json
```
