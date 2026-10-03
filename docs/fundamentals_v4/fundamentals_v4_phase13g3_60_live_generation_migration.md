# Phase 13G.3.60 Live Fundamentals Generation Migration

Date: 2026-10-03

## Result

The explicit live migration completed successfully and activated the reader-atomic
Fundamentals generation layout.

- Migration result: `MIGRATED_AND_ACTIVATED`
- Active generation: `migration_20261003T103216Z`
- Activation manifest: `data/fundamentals_active_generation.json`
- Local completion evidence timestamp: `2026-10-03T13:33:45+03:00`
- UTC completion evidence timestamp: `2026-10-03T10:33:45Z`
- Financial semantic content changed: `NO`
- Refresh Preview/Test/Production executed: `NO`
- Operational Review Queue changed: `NO`
- Scheduler mode changed: `NO`
- Legacy flat production databases deleted: `NO`

## Source State

- Branch: `chore/ignore-backups`
- HEAD: `cf0fe5cadaf914d02b689f453c7cbb8da21fc16c`
- Upstream: `origin/chore/ignore-backups`
- Local commits ahead of upstream: `5`
- Phase 13G.3.59 generation implementation: present in `ce562f84`
- Pre-existing worktree change preserved and not touched:
  `data/.fundamentals_admin_publication_journal.json`

No source change was required. Runtime-generated generation files and the active
manifest are intentionally not committed.

## Pre-flight

All required migration gates passed before the migration command ran.

| Check | Result |
|---|---|
| Active generation before migration | `LEGACY_FLAT` |
| Admin Production kernel lock | `AVAILABLE` |
| Scheduler kernel lock | `AVAILABLE` |
| Admin UI operation kernel lock | `AVAILABLE` |
| Add Tickers Production kernel lock | `AVAILABLE` |
| Remove Tickers Test kernel lock | `AVAILABLE` |
| Taxonomy writer lock | absent / inactive |
| Relevant active process | none found |
| Relevant running systemd service | none found |
| Publication journal state | `COMPLETED` |
| Publication postflight | `PASSED` |
| Publication recovery state | `NOT_REQUIRED` |
| Production writes blocked | `NO` |
| Active manifest before migration | absent |
| Available disk bytes | `748047548416` |
| Source generation bytes | `2553339904` |

The scheduler status JSON contained stale `RUNNING` metadata from
`2026-10-03T01:30:53Z`. It did not represent an active scheduler: the authoritative
kernel lock was available, no corresponding process or running service existed, and
the migration acquired both the Admin Production and scheduler locks successfully.
The status JSON was not modified.

## Flat Production Baseline

All flat databases were opened read-only and passed `PRAGMA quick_check` before
migration.

| Role | Path | Size bytes | SHA-256 | quick_check |
|---|---|---:|---|---|
| Provider | `data/fundamentals_provider.db` | 968331264 | `f04b1fb1817fd03aa03751e4e1e17a69d28cec076259d17c8efed3c2d260ff55` | `ok` |
| Canonical | `data/fundamentals_v4.db` | 674869248 | `b417095cd062c04d59575442da08aee11a2add829448f5784f4dd0a15cb8edeb` | `ok` |
| Analysis | `data/fundamentals_analysis.db` | 910139392 | `1dd70c4ea1ce66850cc43bff6b7159c37c7913f85bdbf904c3056d76f50caa5b` | `ok` |

These hashes also matched the candidate fingerprints recorded by the last completed
Production publication journal.

## Migration Command

The reviewed operator command was executed exactly as specified:

```bash
python3 -m rawcandle.cli.migrate_fundamentals_generation \
  --confirm CONFIRM_FUNDAMENTALS_GENERATION_MIGRATION
```

It returned `MIGRATED_AND_ACTIVATED` and created exactly one generation directory:

```text
data/fundamentals_generations/migration_20261003T103216Z/
```

No temporary `.migrating` generation entry remained after completion.

## Active Manifest

The active manifest is a regular file with format version 1 and SHA-256:

```text
0b0f8d07d229b0b96fe2b9eaa86ea3afe9b111f3232004e0a7299f9837418150
```

Its authoritative fields are:

```json
{
  "format_version": 1,
  "generation_id": "migration_20261003T103216Z",
  "layout": "GENERATION_DIRECTORY",
  "source": "EXPLICIT_FLAT_LAYOUT_MIGRATION",
  "roles": {
    "provider": "fundamentals_provider.db",
    "canonical": "fundamentals_v4.db",
    "analysis": "fundamentals_analysis.db"
  }
}
```

The generation ID passed the central resolver's validation. The generation directory
is a direct child of `data/fundamentals_generations`, and every role path is a direct
child of that generation directory. No symlink or path traversal was accepted.

## Active Generation Verification

| Role | Active path | Size bytes | SHA-256 | quick_check | Equals flat source |
|---|---|---:|---|---|---|
| Provider | `data/fundamentals_generations/migration_20261003T103216Z/fundamentals_provider.db` | 968331264 | `f04b1fb1817fd03aa03751e4e1e17a69d28cec076259d17c8efed3c2d260ff55` | `ok` | YES |
| Canonical | `data/fundamentals_generations/migration_20261003T103216Z/fundamentals_v4.db` | 674869248 | `b417095cd062c04d59575442da08aee11a2add829448f5784f4dd0a15cb8edeb` | `ok` | YES |
| Analysis | `data/fundamentals_generations/migration_20261003T103216Z/fundamentals_analysis.db` | 910139392 | `1dd70c4ea1ce66850cc43bff6b7159c37c7913f85bdbf904c3056d76f50caa5b` | `ok` | YES |

Both size and SHA-256 equality were verified for every active/flat role pair after
activation and again after the idempotency run.

## Flat Files Retained

The original flat production databases remain present and unchanged:

- `data/fundamentals_provider.db`
- `data/fundamentals_v4.db`
- `data/fundamentals_analysis.db`

Each retained flat database still passes `PRAGMA quick_check = ok` and retains its
pre-migration size and SHA-256.

## Reader Resolution

`resolve_active_generation(..., require_generation=True)` and
`resolved_production_paths()` both resolve all three Fundamentals roles to
`migration_20261003T103216Z`, not to the legacy flat paths.

Resolver result: `ACTIVE_GENERATION` / `GENERATION_DIRECTORY`.

## Journal And Recovery

The migration did not rewrite the publication journal. Its mtime remained
`2026-10-02T18:28:10.881080924+03:00` and its final state remains:

- state: `COMPLETED`
- current publication step: `COMPLETED`
- postflight: `PASSED`
- rollback/recovery: `NOT_REQUIRED`
- incomplete journal: `NO`
- production writes blocked: `NO`
- recovery required: `NO`

## Idempotency

The exact migration command was run a second time under the documented idempotency
contract. It returned:

```text
ALREADY_MIGRATED
```

The second invocation kept the same generation ID, did not create another generation,
and did not change any financial database size or SHA-256.

## Safety Confirmation

- Financial semantic content changed: `NO`
- Operational Review Queue changed: `NO`
- Live Refresh workflow executed: `NO`
- Add/Remove Tickers executed: `NO`
- Scheduler mode changed: `NO` (`PREVIEW_ONLY` remains configured)
- Scheduler/systemd state altered: `NO`
- Rollback backups deleted: `NO`
- Legacy flat databases deleted: `NO`
- Runtime generation files committed: `NO`
- Git push performed: `NO`

The first post-migration Full Workflow remains a separate future live-validation task.
