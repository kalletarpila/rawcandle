# Relative Position V1 Phase 4D Production Deployment

## Outcome

Status: `PRODUCTION_ACTIVE`

Relative Position V1 was deployed on 2026-09-01 UTC from branch `chore/ignore-backups`. The production authorization and pipeline integration commit was `75377e07f46913d2af21cc5c858f3ff85d43e265`. No external provider update ran, no model method changed, no rollback was required, and no commit was pushed.

Locked identities:

- model: `CURRENT_REVISED_SNAPSHOT_RELATIVE_POSITION_V1`
- model fingerprint: `983dc38a2805806d4e2709a6956f51bf9cb06ebb61fdb3d9e78344bca58cd7e2`
- persistence: `V4_RELATIVE_POSITION_CURRENT_SNAPSHOT_V1`
- calculation source fingerprint: `692106e6edca56a18d0c1ec34247093a9b936d0be7a2bc7abb03deedec05cf5a`
- source-content fingerprint: `bffeeee03a8003c31a52b58acf0655b4b858acb1097dd02c87d2221b1da4485c`
- result fingerprint: `841ab14cd9861123cb01fb0adb9dd4b1f0053a90df318a5e11625876b6f08ff1`
- active snapshot: `42efd2f3d42e019a21dee2fb03acf9b1cc698502b189e930ec83e24ac135c1ff`
- previous snapshot: none; the first deployment retains one complete snapshot and the retention ceiling is two

Deployment evidence is under:

```text
temp/fundamentals_v4_relative_position_phase4d/20260901T233000Z
```

## Preflight and backup

The worktree was clean at `aa64f9db335a2c88608111d59694135e3a890b52`, Phase 4C was present, all paths resolved to the exact configured regular non-symlink files, and the five database paths were distinct. SQLite headers, ownership and permissions were valid. All database `quick_check` results were `ok`; foreign-key checks were clean where applicable. Available disk space was 609,179,275,264 bytes, exceeding the database, backup, anticipated WAL, artifacts, and margin requirement.

Only `data/fundamentals_analysis.db` is writable by this deployment. It was backed up with SQLite online backup before the first write:

```text
temp/fundamentals_v4_relative_position_phase4d/20260901T233000Z/backups/fundamentals_analysis_before_relative_position.db
```

The backup is a regular non-symlink file, 302,678,016 bytes, SHA-256 `cc7eda2be6c8c40ea7a88904d1d97271f4e4df7e9001d398a498f55a24d66d4c`, `quick_check=ok`, foreign-key violations 0, page count 73,896, freelist 0, and no Relative Position objects. It retains 50,585 Score rows, 354,095 Score component rows, 50,585 Lifecycle rows, and 50,585 Valuation rows.

The documented restore procedure is in `temp/fundamentals_v4_relative_position_phase4d/20260901T233000Z/RESTORE_INSTRUCTIONS.txt`. Its essential command is an offline SQLite restore after stopping writers and retaining the failed database:

```bash
sqlite3 /home/kalle/projects/rawcandle/data/fundamentals_analysis.db ".restore '/home/kalle/projects/rawcandle/temp/fundamentals_v4_relative_position_phase4d/20260901T233000Z/backups/fundamentals_analysis_before_relative_position.db'"
```

The restored database must then pass `PRAGMA quick_check`, `PRAGMA foreign_key_check`, and upstream row/fingerprint verification before service resumes. The backup is retained pending owner acceptance and a normal successful daily cycle.

## Commands

The production CLI help and exact-path gates were inspected before execution. Dry-run used the following exact command without `--apply` or `--confirm-production`:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_relative_position_production --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db --provider-db /home/kalle/projects/rawcandle/data/fundamentals_provider.db --analysis-db /home/kalle/projects/rawcandle/data/fundamentals_analysis.db --market-db /home/kalle/projects/rawcandle/data/osakedata.db --taxonomy-db /home/kalle/projects/rawcandle/data/analysis.db --snapshot-date 2026-09-01 --model-fingerprint 983dc38a2805806d4e2709a6956f51bf9cb06ebb61fdb3d9e78344bca58cd7e2 --full-universe --output-dir /home/kalle/projects/rawcandle/temp/fundamentals_v4_relative_position_phase4d/20260901T233000Z/dry_run
```

The first and identical second production applies used this command, changing only `--output-dir` from `first_apply` to `second_apply`:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_relative_position_production --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db --provider-db /home/kalle/projects/rawcandle/data/fundamentals_provider.db --analysis-db /home/kalle/projects/rawcandle/data/fundamentals_analysis.db --market-db /home/kalle/projects/rawcandle/data/osakedata.db --taxonomy-db /home/kalle/projects/rawcandle/data/analysis.db --snapshot-date 2026-09-01 --model-fingerprint 983dc38a2805806d4e2709a6956f51bf9cb06ebb61fdb3d9e78344bca58cd7e2 --full-universe --output-dir /home/kalle/projects/rawcandle/temp/fundamentals_v4_relative_position_phase4d/20260901T233000Z/first_apply --apply --confirm-production
```

Pipeline smoke used the same command with output directory `pipeline_smoke` and the additional `--pipeline-smoke` flag. It intentionally exercised the post-Valuation Relative Position stage without invoking the external provider path. Observed wall time was 28.2 seconds for the second apply and 28.5 seconds for pipeline smoke; the JSON reports preserve UTC completion timestamps for every run but do not persist CLI wall duration.

## Dry-run and apply results

Dry-run completed at `2026-09-01T19:56:43Z`, calculated the full expected snapshot, and made zero writes. Analysis database size, mtime, SHA-256, schema hash, page count, freelist, and upstream row counts were identical before and after.

First apply completed at `2026-09-01T19:57:12Z`:

- outcome `ACTIVATED`
- snapshot inserts 1 and active-pointer changes 1
- result inserts 13,737; deletes 0; unchanged 0
- coverage inserts 19,596; deletes 0; unchanged 0
- audit inserts 1; retained snapshots 1
- `quick_check=ok`; foreign-key violations 0

The identical second apply completed at `2026-09-01T19:58:32Z`:

- outcome `NO_CHANGE`
- result inserts/deletes 0/0; unchanged 13,737
- coverage inserts/deletes 0/0; unchanged 19,596
- snapshot inserts/deletes 0/0; active-pointer changes 0
- bounded audit inserts 1
- active snapshot and all fingerprints unchanged

Production schema objects are `relative_position_schema_meta`, `relative_position_snapshot`, `relative_position_active_snapshot`, `relative_position_result`, `relative_position_coverage`, `relative_position_refresh_audit`, and five supporting indexes. There are no taxonomy-layer rows and no logical duplicates.

## Population and readers

The active snapshot contains 13,737 result rows and 19,596 coverage rows. Eligible counts are Fundamental 2,198 and Valuation 2,246. Ready sector counts are 2,188 and 2,236; ready industry counts are 1,911 and 1,947; DATACENTER counts are 204 and 201 respectively.

CRMD Valuation percentiles reproduced the locked values: universe `99.88864142538975`, Healthcare `99.82847341337907`, Biotechnology `100`, and no ecosystem result. The Valuation zero tie contains 631 companies at `14.031180400890868`; the 100 tie contains 6 companies at `99.88864142538975`.

Reader verification also covered SITM as `EXTENDED`, VRT as deduplicated `CORE`, ASPI `WATCH_ONLY` exclusion, AAT Fundamental-only eligibility, ABOS Valuation-only eligibility, AIN's below-minimum industry, O's `VALUATION_NOT_APPLICABLE`, company lookup, universe/sector/industry/ecosystem group lookup, unavailable coverage explanations, and wrong-fingerprint isolation. All checks passed.

## Pipeline activation

The Score production orchestrator now refreshes Relative Position after successfully committed Score, Lifecycle, and Absolute Valuation stages. Relative Position owns its transaction. A failure preserves its previous active snapshot, cannot roll back committed upstream data, is recorded as `POST_VALUATION_RELATIVE_POSITION_REFRESH_FAILED`, and fails the operational run. The full-universe refresh is intentional because relative ranks have cross-company dependencies.

Pipeline smoke completed at `2026-09-01T19:59:54Z` with stage `AFTER_ABSOLUTE_VALUATION`, status `COMPLETE`, outcome `NO_CHANGE`, and `provider_update_triggered=false`. It inserted or deleted no result, coverage, snapshot, or pointer rows and added one bounded audit row. Ordering, failure isolation, first/unchanged/changed refreshes, fingerprint propagation, and no-provider behavior are covered by focused orchestration tests.

## Final integrity

The analysis database changed only for the intended schema, one active snapshot, and three audit records. It grew from 302,678,016 bytes / 73,896 pages to 322,220,032 bytes / 78,667 pages; freelist remained 0. Final mtime was `1788292808944296089` ns and final SHA-256 was `3c56f082817584dedb4f4c5712380f646a960f802cd639fb879d37088b472ab7`. Schema SHA-256 changed from `aa549fefb5df7edc554ea5b7d191576e26817956452f6336774879b9683c9e58` to `ba59122ee795b1743634207fe731c24a33ff410f6a18eaf6b31f929a6dc7feac`. Final `quick_check` is `ok`, foreign-key violations are 0, journal mode is `delete`, and WAL/SHM sizes are 0.

Canonical, provider, osakedata, and taxonomy database file hashes match preflight exactly. Complete deterministic row hashes of `score_result` plus `score_component`, `lifecycle_revised_result`, and `valuation_revised_result` match the pre-deployment online backup. Their row counts remain 50,585, 354,095, 50,585, and 50,585. Evidence is in `final_integrity_and_readers.json`.

## Verification and decision

Before production, 56 focused tests passed, the final focused gate passed 25 tests, all 452 Fundamentals V4 tests passed in 49.02 seconds, `compileall` passed, and `git diff --check` passed. The full repository suite was not run because the complete Fundamentals V4 group and focused production/orchestration tests cover the changed model pipeline, schema, persistence, reader, and safety-gate surfaces.

Rollback was not required: every acceptance criterion passed and only intended analysis objects changed. Remaining operational risk is limited to future source/classification changes creating a larger second retained snapshot and to the first ordinary scheduled cycle not yet having occurred. Bounded retention was stress-tested in Phase 4C.1; the retained backup remains the recovery point until owner acceptance after that normal cycle.
