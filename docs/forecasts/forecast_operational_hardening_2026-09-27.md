# Forecast Operational Hardening (2026-09-27)

## 1. Known and unknown schema drift

Operational drift classification is versioned as
`yahoo_known_ignored_fields_v1`. The policy lists the `financialData` paths
observed in the production pilot that are intentionally outside the accepted
price-target contract. Those paths are counted as `known_ignored_count`.
Every other path remains visible as `unknown_drift_count` and in
`distinct_unknown_paths`.

Classification does not alter parsing, canonical payloads, or semantic hashes.
Adding a path to the known list requires a reviewed code change; new Yahoo
fields are never ignored automatically.

## 2. Health command

Run:

```bash
python -m rawcandle.cli.forecasts health --lookback-days 7
```

The compact report covers database integrity and size, latest run state,
acquisition outcomes, identity resolution, AS_KNOWN fiscal links, retries and
rate limits, classified drift, raw evidence, and historical snapshot bounds.
It never emits provider payloads.

## 3. Raw-evidence cleanup

Preview first, then apply explicitly:

```bash
python -m rawcandle.cli.forecasts cleanup-raw --dry-run
python -m rawcandle.cli.forecasts cleanup-raw --apply
```

Only expired `forecast_raw_evidence` rows are eligible. Apply clears their
optional references from fetches and snapshots before deleting the raw body in
one transaction. Fetch history, canonical snapshot JSON, normalized estimates,
price targets, earnings-history references, identities, and fiscal links are
retained. A quick check follows apply.

## 4. Backup format

`backup` uses SQLite's online backup API rather than copying an open database:

```bash
python -m rawcandle.cli.forecasts backup
```

The default destination is `backups/forecasts/`. Files are named
`forecast_<UTC timestamp>.db`, verified, and made read-only. The backup is one
standalone SQLite database; it is not coupled to Fundamentals publication or
recovery state.

## 5. Backup manifest

Each database has a sibling `.manifest.json`. It records contract and schema
versions, UTC creation time, source path, source size and SHA-256, backup path,
backup size and SHA-256, quick-check result, and row counts for all core
forecast tables. Restore and retention accept only a backup whose fingerprint,
schema, integrity, and core counts agree with its manifest.

## 6. Retention policy

Preview or apply only inside the selected forecast backup directory:

```bash
python -m rawcandle.cli.forecasts backup-retention --dry-run
python -m rawcandle.cli.forecasts backup-retention --apply
```

The V1 policy keeps every valid backup for 14 days, one valid backup per ISO
week through eight weeks, and one valid backup per month through 366 days. The
newest valid backup is always protected. Invalid and unrelated files are not
deleted. Apply verifies that a newest valid backup remains.

## 7. Restore procedure

Restore first to a reviewed non-production path:

```bash
python -m rawcandle.cli.forecasts restore \
  --backup backups/forecasts/forecast_<timestamp>.db \
  --target /tmp/forecasts-restored.db
```

Production replacement additionally requires `--apply-production`. The command
validates the immutable backup and manifest, rejects unrelated existing custom
targets, and creates a verified safety backup of a readable current target. It
restores through a temporary database, verifies schema, integrity, and core
counts, atomically replaces the target, fsyncs the directory, and verifies the
result. There is no automatic startup restore.

## 8. Resumable acquisition

Resume an interrupted run with:

```bash
python -m rawcandle.cli.forecasts acquire --resume-run-id <run-id>
```

The stored symbol and family scope is authoritative when `--symbols` is
omitted. If symbols are supplied, they must match that scope exactly. Existing
symbol/family attempts are skipped and only missing attempts run. A resume never
selects an unrelated run silently. Individual failures are persisted and do
not abort remaining attempts; completion derives `SUCCESS`, `PARTIAL`, or
`FAILED` from all persisted attempts.

Repeated real acquisitions remain observable as separate run/fetch rows. Equal
semantics yield `SUCCESS_UNCHANGED` and reuse the semantic snapshot; changed
semantics yield `SUCCESS_CHANGED`; failures preserve prior state; valid no-data
is an explicit successful observation.

## 9. Bounded universe authority

The selected source of truth is the active version in
`fundamentals_operational_universe_active_version`, joined to
`fundamentals_operational_universe_member` and canonical `security` identity.
Selection accepts only `ACTIVE_SINGLE_SECURITY` members with an active security
and a nonempty current ticker. Ordering is deterministic by company identity,
and duplicate routed symbols are removed. Multi-security and historical-only
members are excluded with explicit reasons.

This authority is identity-compatible with Fundamentals V4 and does not depend
on datacenter taxonomy or a duplicate manual watchlist.

## 10. Universe preview

Run:

```bash
python -m rawcandle.cli.forecasts universe-preview
```

Preview is read-only. It reports authority and version, candidate/company/
security/symbol counts, exclusion reasons, the selected symbols, three requests
per symbol, and ideal serial runtime at the configured minimum interval. It
does not contact Yahoo.

## 11. Future daily scheduler command

The scheduler-ready boundary is:

```bash
python -m rawcandle.cli.forecasts daily --max-symbols <reviewed-bound>
```

The bound is mandatory. Execution is preflight, verified backup, canonical
universe resolution capped by that bound, acquisition and identity resolution,
AS_KNOWN linking, CURRENT_RECONCILED linking, and compact reporting with a
terminal status. No scheduler imports or registration were added in this phase.

## 12. Failure policy

Database preflight or backup failure fails closed before acquisition. A failed
symbol/family is retained and allows the run to finish `PARTIAL`; rate-limited
attempts are likewise explicit and retryable through a new or reviewed resumed
run. Fundamentals linkage failures do not erase completed acquisition and make
the daily terminal status `PARTIAL`. Reconciliation and report failures are
reported separately while retained acquisition remains intact.

Forecast execution is independent of OHLCV status and scheduling.

## 13. Backup before acquisition

Every `daily` invocation verifies and backs up the forecast database before
resolving or fetching its bounded universe. One verified pre-run backup is the
V1 rule. There is no per-symbol backup and no post-run replacement of that
recovery point.

## 14. Production database safety

`data/forecasts.db` is non-rebuildable point-in-time history. Phase 6 adds no
schema migration and does not rewrite or prune canonical historical data.
Maintenance uses SQLite transactions, busy timeout behavior from the forecast
connection, explicit quick checks, and the online backup API. Daily execution
does not vacuum. Fundamentals is opened read-only by universe and linkage code.

## 15. Validation results

Validation includes focused tests for drift classification, health aggregation,
cleanup preview/apply and canonical preservation, verified backups and
manifests, retention, guarded restore and safety backup, interrupted-run resume,
partial/repeated acquisitions, universe selection and estimates, backup-first
daily execution, and linkage failure preservation.

The production validation procedure creates exactly one verified backup, then
runs health, universe preview, raw cleanup dry-run, and backup retention dry-run.
It performs no full-universe acquisition and no production cleanup apply.
Concrete paths and counts are recorded in the task completion output.

## 16. Remaining work before scheduler enablement

Review the production preview count, choose and document the first approved
`--max-symbols` bound and rollout cadence, configure external scheduler timeout
and alert handling, define retry ownership for `PARTIAL` runs, and rehearse one
restore to a non-production target from the retained production backup. Then
register the exact daily command separately under change control. Scheduler
enablement and full-universe acquisition are intentionally not part of Phase 6.
