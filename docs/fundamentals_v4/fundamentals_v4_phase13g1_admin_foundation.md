# Fundamentals V4 Phase 13G.1 Administration Foundation

Date: 2026-09-15

Outcome: **OUTCOME A — SHARED ADMINISTRATION CONTRACTS AND DURABLE RUN-LOGGING FOUNDATION READY**

Phase 13G.1 adds the shared administration foundation for later Add Tickers, Sector/Industry Update and Taxonomy Update workflows. It does not implement those economic operations, perform production writes, call providers, refresh packages, refresh Relative Position, refresh Relative Valuation, or change the Scheduler UI.

## Durable Run Root

Persistent administration run history uses the existing ignored Fundamentals report root:

`fundamental_reports/admin_runs/`

## Role-Aware Database Verification

Administration operations must derive verification from explicit database roles:

- `production_writable_roles`
- `production_readonly_roles`
- `copy_writable_roles`
- `copy_readonly_roles`

Heavy integrity, backup, rollback and full logical-inventory checks apply only to databases the operation may write. Read-only databases receive only the targeted source and identity checks required by the operation.

If a production writable role crosses a production write boundary, full pre/post integrity, verified backup and rollback protection apply. If a write-capable operation does not cross the production write boundary, redundant post-write scans are skipped in favor of targeted no-write confirmation. Copy-writable lanes carry copy integrity, repeat and rollback checks. Unknown or contradictory roles fail closed.

This keeps compact user-facing evidence outside Git while avoiding the existing taxonomy helper limitation that evidence roots must live under `temp/`. Heavy transient database copies remain reserved for phase/run-specific `temp` roots in later apply phases.

## Contracts

The shared model is implemented in `rawcandle.fundamentals.admin.contracts`.

Supported future operation types:

- `ADD_TICKERS`
- `UPDATE_SECTOR_INDUSTRY`
- `UPDATE_TAXONOMY`

Core contracts:

- normalized batch request;
- immutable preview with request, change-set and preview fingerprints;
- per-item decisions with plain-language status messages;
- checkpoint/stage records;
- final result with summary counts, rollback state, downstream outcomes and artifact references.

The generic item CSV keeps stable common columns: requested value, normalized value, item key, market, company name, status, reason, old value, new value, source category, warning and applied action. Operation-specific detail stays in JSON so taxonomy or classification data is not forced into misleading common fields.

## Fingerprints

Fingerprints use canonical JSON serialization and SHA-256. Run-local audit fields are excluded from economic fingerprints, including run IDs, timestamps, process IDs, output paths, temporary paths, heartbeat counters and sequence numbers.

The same normalized request and proposed actions produce the same preview fingerprint. Changes to inputs, proposed actions, source state, identity decisions or classification decisions change the relevant fingerprint.

## Lifecycle

The lifecycle supports:

- request created;
- preview started;
- preview ready;
- apply confirmation pending;
- apply started;
- write boundary not crossed;
- write boundary crossed;
- rollback started;
- rollback complete;
- completed;
- partially completed;
- failed before write;
- failed after write;
- interrupted.

Invalid transitions are rejected, including terminal stages returning to running, rollback completion without a crossed write boundary, and apply using a mismatched preview fingerprint.

## Artifacts

The artifact writer persists state-bearing files atomically:

- `request.json`
- `preview.json`
- `status.json`
- `result.json`
- `report.md`
- `artifact_manifest.json`
- `exit_code`

Heartbeat is append-only JSONL; each line is independently parseable. Error evidence is redacted before persistence.

## Secret Redaction

`rawcandle.fundamentals.admin.redaction` recursively redacts sensitive field names, authorization headers, secret-bearing URLs/query parameters and explicitly configured sentinel secrets. Tests prove a sentinel secret is absent from generated JSON, Markdown, traceback/error and manifest artifacts. The real Sharadar secret was not read for testing.

## Run-History Reader

`AdminRunHistory` lists runs without querying production databases, sorts newest first by deterministic run directory name, loads summaries, opens only approved artifacts by artifact name, rejects path traversal and rejects symlink escapes.

Interruption rule: when a run has no final result and no recent heartbeat or matching active process evidence, it is reported as `INTERRUPTED`, not successful. If no readable status exists, it is reported as `corrupt_or_incomplete`.

## Orchestration Interface

`AdminOrchestrator` provides a small callback-based interface for future services:

- preview calculation;
- apply operation;
- rollback operation;
- progress checkpoints through `AdminRunWriter`;
- final report/artifact persistence.

Synthetic tests cover preview success, apply success, pre-write failure semantics, post-write rollback reporting and preview fingerprint mismatch rejection.

## Read-Only CLI

`rawcandle/cli/inspect_fundamentals_admin_runs.py` can list runs, show a run summary and resolve approved artifact paths. It is read-only and cannot perform production writes.

## Production Isolation

Read-only production checks were run before and after implementation.

All five production databases reported `quick_check=ok` and zero foreign-key errors:

- `data/fundamentals_provider.db`
- `data/fundamentals_v4.db`
- `data/fundamentals_analysis.db`
- `data/osakedata.db`
- `data/analysis.db`

The active package pointer remained:

`f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`

The active Relative Valuation snapshot remained:

`76c2974108b2c5085b7dfa102acd4bb04eea36a5267bbdb1930a2bc7dc8cb35e`

Production database sizes and mtimes matched before and after. No provider API or network request was made. Scheduler state was not changed.

## Tests

Focused Phase 13G.1 suite:

- `python3 -m pytest tests/test_fundamentals_admin_foundation.py` — 13 passed

Relevant regressions:

- `python3 -m pytest tests/test_phase13d_backend.py tests/test_phase13f4_13_durable_runner.py tests/test_production_database_isolation.py tests/test_fundamentals_snapshot_ui.py` — 72 passed
- `python3 -m compileall rawcandle/fundamentals/admin rawcandle/cli/inspect_fundamentals_admin_runs.py`

The full repository suite was not run because this phase adds an isolated administration foundation and does not modify production economic calculation code, provider code, Scheduler UI code or existing production orchestration.

## Disk Hygiene

Free space before and after: 599G available on `/home/kalle/projects/rawcandle`.

No synthetic database copies, WAL, SHM or journal files were created. No Phase 13G.1 temp run directory remained after tests; pytest-managed temporary fixtures were used for synthetic artifacts.

## Remaining Risks

- Future Phases 13G.2-13G.4 must wire real operation-specific source-state fingerprints into the shared preview model.
- Future production apply phases must add operation-specific backup/restore manifests and database-copy cleanup under phase-owned `temp` roots.
- Scheduler UI integration remains intentionally deferred to Phase 13H.
