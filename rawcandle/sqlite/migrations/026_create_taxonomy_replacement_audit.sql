-- Datacenter taxonomy replacement backend foundation.
-- SQLite-safe additive column patching is applied by ec_sidecar_migration.py.

CREATE TABLE IF NOT EXISTS ec_taxonomy_change_deployment (
    taxonomy_change_id INTEGER PRIMARY KEY,
    ecosystem_code TEXT NOT NULL,
    previous_taxonomy_version TEXT NOT NULL,
    proposed_taxonomy_version TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    change_summary TEXT NOT NULL,
    added_ticker_count INTEGER NOT NULL,
    removed_ticker_count INTEGER NOT NULL,
    membership_change_count INTEGER NOT NULL,
    group_change_count INTEGER NOT NULL,
    loaded_at_utc TEXT NULL,
    status TEXT NOT NULL,
    rebuild_required INTEGER NOT NULL CHECK (rebuild_required IN (0, 1)),
    rebuild_start_date TEXT NOT NULL,
    dc_rebuild_status TEXT NOT NULL DEFAULT 'NOT_STARTED',
    ec_rebuild_status TEXT NOT NULL DEFAULT 'NOT_STARTED',
    coverage_status TEXT NOT NULL DEFAULT 'NOT_STARTED',
    parity_status TEXT NOT NULL DEFAULT 'NOT_STARTED',
    activation_status TEXT NOT NULL DEFAULT 'NOT_ACTIVE',
    activated_at_utc TEXT NULL,
    invocation_source TEXT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    UNIQUE (ecosystem_code, proposed_taxonomy_version)
);
