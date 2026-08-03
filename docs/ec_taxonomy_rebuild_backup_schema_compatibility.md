# EC Taxonomy Rebuild Backup Schema Compatibility

The Datacenter V2 EC full rebuild reuses the full production backup created
before the first DC V2 rebuild write. That backup is the required
pre-DC-rebuild restore point and must not be replaced just because the live DB
later received additive deployment or audit columns.

Existing-backup validation therefore separates three outcomes:

```text
EXACT_MATCH
COMPATIBLE_ADDITIVE_DRIFT
INCOMPATIBLE_SCHEMA_DRIFT
```

Canonical EC/DC facts, sidecar identity tables, and pipeline watermarks remain
strict. Missing tables, removed columns, changed primary keys, changed
uniqueness or index identity, changed required column definitions, and arbitrary
additive canonical-table columns block before EC writes.

Compatible additive drift is limited to operational/audit tables. The current
accepted production shape is live-only nullable deployment evidence columns on
`ec_taxonomy_change_deployment`:

```text
prepared_at_utc
validation_completed_at_utc
rebuild_evidence_json
rebuild_evidence_sha256
validation_evidence_json
validation_evidence_sha256
last_error
```

For this shape the expected structured output is:

```text
backup_validation_status=OK
backup_schema_compatibility_status=COMPATIBLE_ADDITIVE_DRIFT
backup_schema_exact_match=false
backup_schema_compatible_with_live=true
backup_schema_critical_mismatch_count=0
backup_schema_allowed_difference_count=7
backup_restore_requires_forward_schema_reapply=true
backup_error=null
```

This does not mean the old backup already contains the later columns. If manual
restore is chosen, restore the original backup first, reapply the current
forward schema preparation, verify integrity and schema, and then restore or
reconstruct post-backup deployment evidence as appropriate.

The orchestrator does not perform restore automatically, does not mutate the
original backup, and does not create a fallback full backup when an existing
backup is rejected.

The future controlled production retry should continue to use the same original
backup path and SHA-256:

```text
temp/datacenter_taxonomy_v2_full_rebuild_20260803T102454Z/analysis_before_datacenter_v2_full_rebuild.sqlite
ef63868f55073dd3a9eedccea5097871446b02af1577f8c4659fe6dd325db3ea
```
