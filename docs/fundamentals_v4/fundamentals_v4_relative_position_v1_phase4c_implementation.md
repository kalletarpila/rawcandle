# Relative Position V1 Phase 4C Implementation

## Scope and status

Phase 4C adds persistence, active-snapshot readers, a protected rehearsal CLI, and deployment preparation for `CURRENT_REVISED_SNAPSHOT_RELATIVE_POSITION_V1`. It does not migrate a production database, enable production writes, or connect Relative Position to the daily pipeline.

Locked identities:

- model fingerprint: `983dc38a2805806d4e2709a6956f51bf9cb06ebb61fdb3d9e78344bca58cd7e2`
- persistence schema: `V4_RELATIVE_POSITION_CURRENT_SNAPSHOT_V1`
- Phase 4B source fingerprint: `692106e6edca56a18d0c1ec34247093a9b936d0be7a2bc7abb03deedec05cf5a`
- Phase 4B result fingerprint: `841ab14cd9861123cb01fb0adb9dd4b1f0053a90df318a5e11625876b6f08ff1`

The Phase 4B ranking method is unchanged. There is no component, composite, taxonomy-layer, historical PIT, or current-price result.

## Persistence architecture

One complete snapshot is active per model fingerprint. A separate active pointer makes visibility atomic. A refresh writes and validates all metadata, result, and coverage rows in one `BEGIN IMMEDIATE` transaction before moving the pointer. Any exception rolls the transaction back, leaving the previous snapshot readable.

The bulk retention limit is two complete snapshots per model: active plus the immediately previous active snapshot. Obsolete result and coverage rows are cascade-deleted transactionally. SQLite can reuse freed pages; routine `VACUUM` is not part of the contract. Compact refresh audit is capped at 64 rows per model and is not historical rank availability.

Schema objects:

- `relative_position_schema_meta`
- `relative_position_snapshot`
- `relative_position_active_snapshot`
- `relative_position_result`
- `relative_position_coverage`
- `relative_position_refresh_audit`
- indexes for snapshot/model, company reads, peer-group reads, coverage reads, and audit reads

Constraints restrict measures to Fundamental and Absolute Valuation, and scopes to universe, sector, industry, and ecosystem. Result and coverage identities are unique within a snapshot. Foreign keys bind all bulk rows and the active pointer to snapshot metadata.

## Date-only no-op

The locked Phase 4B source and result fingerprints include the literal snapshot date. Persistence additionally calculates `source_content_fingerprint`, which excludes only nominal snapshot-date serialization while retaining scores, eligibility, observation identities/dates, classifications, memberships, coverage, ranks, and all economic results.

If source content is unchanged, persistence writes no snapshot, result, coverage, or active-pointer rows. It writes one bounded audit row and advances `validated_through_date`. This preserves honest as-of metadata without daily full-snapshot churn. Any freshness-boundary eligibility change changes coverage/content and triggers a complete snapshot.

## Public APIs

`apply_snapshot` validates a complete deterministic snapshot and atomically persists or no-ops it. `validate_snapshot` checks model identity, fingerprints, vocabularies, ordering, uniqueness, coverage completeness, peer-group completeness, ties, minimums, and the percentile formula.

`RelativePositionRepository` provides:

- `active_metadata`
- `current_company`
- `company_scope`
- `current_universe`
- `peer_group`
- `explain_unavailable`

Every read requires an explicit model fingerprint and joins only the active `COMPLETE` snapshot. Readers return snapshot and source identity metadata, do not fall back to broader peers, and cannot synthesize taxonomy-layer results.

`quick_check` rehydrates and validates the active snapshot, fingerprints, row counts, duplicate state, scope vocabulary, retention, SQLite integrity, foreign keys, and wrong-fingerprint isolation.

## Protected CLI

The entry point is:

```text
python3 -m rawcandle.cli.run_fundamentals_v4_relative_position_phase4c --help
```

It defaults to dry-run and requires explicit absolute source paths, destination, locked fingerprint, and `--full-universe`. Writes require `--apply`. It rejects exact production paths, normalized aliases, symlinks, source-as-destination, relative database paths, and missing destinations. `--create-online-backup` uses SQLite online backup. There is no production confirmation option.

## Production-copy rehearsal

Artifact directory:

```text
temp/fundamentals_v4_relative_position_phase4c/20260901T210000Z
```

The analysis copy grew from 302,678,016 bytes / 73,896 pages to 341,823,488 bytes / 83,453 pages after retaining two full snapshots. Growth was 39,145,472 bytes (12.93%). Page size was 4,096 bytes and freelist remained zero. No `VACUUM` was used or needed.

First apply:

- 13,737 result inserts
- 19,596 coverage inserts
- one active snapshot
- result fingerprint `841ab14cd9861123cb01fb0adb9dd4b1f0053a90df318a5e11625876b6f08ff1`

Identical second apply:

- zero result and coverage inserts/deletes
- zero active-pointer changes
- 13,737 result rows unchanged

The changed-source simulation inserted one complete second snapshot and switched atomically. Metadata, result, pre-activation, and cleanup failure injections all preserved the previous active snapshot. Final quick check was `ok`, foreign-key violations were zero, and retention was two bulk snapshots.

Persisted active counts reproduced Phase 4B: Fundamental eligible 2,198; Valuation eligible 2,246; DATACENTER 204/201; ready sectors 2,188/2,236; ready industries 1,911/1,947. CRMD reader values were universe `99.88864142538975`, Healthcare `99.82847341337907`, Biotechnology `100`, and no ecosystem result.

Canonical, analysis source, market, and taxonomy production database SHA-256, size, mtime, schema hash, and SQLite checks were identical before and after. The rehearsal report contains the evidence. The provider database was never opened by the workflow; its post-run SHA-256 remained `17660df9f00837fbb52668aff17144d1b167aae4458dfa1a3c057701924b6d9c`, size 546,754,560 bytes, mtime epoch 1,788,157,472, and quick check `ok`, matching the recorded pre-run baseline. No production database was migrated or written.

## Phase 4D boundary

Phase 4D must add a separately reviewed production authorization wrapper, execute the deployment runbook, and only then connect one full Relative Position refresh after the completed daily Valuation step. Phase 4C code is callable by that wrapper but cannot authorize production itself.
