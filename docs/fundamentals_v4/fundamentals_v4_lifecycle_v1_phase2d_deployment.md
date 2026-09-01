# Lifecycle V1 Phase 2D Production Deployment

## Deployment Identity

- Deployment date: `2026-09-01`
- Code commit: `0a667702d190d48d8782310c873ff79d25d32191`
- Model version: `V4_FUNDAMENTAL_LIFECYCLE_V1`
- Model fingerprint: `db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f`
- History mode: `REVISED_HISTORY`
- Canonical source: `/home/kalle/projects/rawcandle/data/fundamentals_v4.db`
- Production destination: `/home/kalle/projects/rawcandle/data/fundamentals_analysis.db`
- Active table: `lifecycle_revised_result`

The deployment contains no historical information-version reconstruction or as-of query model. Restatements may revise historical lifecycle paths.

## Pre-Deployment Evidence

Both authorized paths resolved to ordinary non-symlink files at the expected absolute locations. The committed worktree was clean.

| Database | Size | mtime epoch | SQLite quick check |
| --- | ---: | ---: | --- |
| `fundamentals_v4.db` | 269,901,824 | 1,788,161,831 | `ok` |
| `fundamentals_analysis.db` | 201,879,552 | 1,788,208,454 | `ok` |

Canonical and TTM each contained 50,585 quarter rows across 2,451 companies. Analysis schema version was `v4_1a_prototype`. Score contained 50,585 results and 354,095 components with fingerprint `47add84845743b33bc9e43d35296871890c1e850d0c9ca23b10e3b10c861f7bc`. The old `lifecycle_result` table contained zero rows and the active revised table did not yet exist.

## Backup

- Path: `/home/kalle/projects/rawcandle/backups/fundamentals_analysis.phase2d.20260901T122332Z.db`
- Method: Python `sqlite3.Connection.backup()` from a read-only source connection
- Started: `2026-09-01T12:23:51.342Z`
- Completed: `2026-09-01T12:23:51.545Z`
- Source size: 201,879,552 bytes
- Backup size: 201,879,552 bytes
- Backup quick check: `ok`
- Backup Score: 50,585 results, 354,095 components, expected fingerprint
- Backup old lifecycle rows: zero

The backup remains preserved. No restore was required.

## Commands

Dry-run:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_lifecycle_revised \
  --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db \
  --destination-db /home/kalle/projects/rawcandle/data/fundamentals_analysis.db \
  --full-universe \
  --model-fingerprint db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f \
  --output-json /home/kalle/projects/rawcandle/temp/fundamentals_v4_lifecycle_phase2d/20260901T122332Z/production_plan.json
```

Production apply, executed twice with only the output filename changing from `production_apply_first.json` to `production_apply_second.json`:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_lifecycle_revised \
  --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db \
  --destination-db /home/kalle/projects/rawcandle/data/fundamentals_analysis.db \
  --full-universe \
  --model-fingerprint db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f \
  --apply --confirm-production \
  --output-json /home/kalle/projects/rawcandle/temp/fundamentals_v4_lifecycle_phase2d/20260901T122332Z/production_apply_first.json
```

## Backfill Results

- Companies: 2,451
- Revised-history rows: 50,585
- Source fingerprint: `561f0daae56043b68820bd945577166d7ca25e9d4a8e988e8d61db0b963ce9df`
- Result fingerprint: `43fee8da28ea454236263c93a09f2a3fe089473509fc4d926b7cc3aae811729c`
- First apply: 50,585 inserts, zero deletes
- First command's built-in replay: zero writes, 50,585 unchanged
- Mandatory second command: zero writes, 50,585 unchanged
- Production growth: 51,994,624 bytes
- Lifecycle quick check: `ok`
- SQLite quick check: `ok`
- Logical duplicates: zero
- History modes: one, `REVISED_HISTORY`
- Lifecycle fingerprints: one, the locked fingerprint

Historical raw-state counts:

```text
DECLINING 7675; DISTRESSED 6219; GROWTH 998; MATURE 3601;
SCALING 4635; STARTUP 3266; STRUGGLING 2874; TRANSITION 5522;
UNCLASSIFIED 15795
```

Historical final-state counts:

```text
DECLINING 7786; DISTRESSED 6822; GROWTH 947; MATURE 3453;
SCALING 4733; STARTUP 3149; STRUGGLING 2663; TRANSITION 5237;
NONE 15795
```

Historical statuses were 34,790 READY and 15,795 NOT_READY. Historical UNCLASSIFIED reasons were source date missing 7,707; lag4 revenue missing 5,623; fiscal chain invalid 1,731; TTM not ready 372; zero-revenue pre-revenue conditions not met 183; current revenue negative 99; and lag4 revenue nonpositive 80.

## Current Universe

Current status counts:

```text
LIFECYCLE_READY 2409; LIFECYCLE_NOT_READY 42
```

Current ready classes:

```text
DECLINING 507; DISTRESSED 362; GROWTH 59; MATURE 272;
SCALING 362; STARTUP 187; STRUGGLING 207; TRANSITION 453
```

Current startup profiles were PRE_REVENUE 169 and REVENUE_GENERATING 18. Current NOT_READY reasons were source date missing 11; lag4 revenue missing 10; current revenue negative 6; TTM not ready 6; lag4 revenue nonpositive 4; fiscal chain invalid 3; and zero-revenue pre-revenue conditions not met 2.

## Readers And Integration

Reader checks covered current READY company 54, current NOT_READY company 85, transitioning company 1, PRE_REVENUE company 63, DISTRESSED company 449, a 20-row full history and a fiscal-quarter lookup. The latest NOT_READY result did not fall back to an older state.

The operational integration point is after the committed Score V1 production stage. No trustworthy changed-company set is currently exposed, so it uses `FULL_UNIVERSE_FALLBACK`. A direct unchanged-source hook check reported 50,585 unchanged rows, zero inserts/deletes, stable source/result fingerprints and a passing quick check. Focused tests prove complete selected-company replay and rollback preservation on failure. No external provider update was run.

The old `lifecycle_result` table remains at zero rows and has no active Lifecycle V1 writer or reader. Score remained at 50,585 results and 354,095 components with its original fingerprint before and after deployment. Canonical remained 269,901,824 bytes with mtime epoch 1,788,161,831. No restore action was needed.
