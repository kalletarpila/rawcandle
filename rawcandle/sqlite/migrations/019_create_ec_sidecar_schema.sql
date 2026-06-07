CREATE TABLE IF NOT EXISTS ec_ecosystem (
    ecosystem_id INTEGER PRIMARY KEY,
    ecosystem_code TEXT NOT NULL,
    ecosystem_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'DEPRECATED')),
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    UNIQUE (ecosystem_code)
);

CREATE TABLE IF NOT EXISTS ec_taxonomy_version (
    taxonomy_version_id INTEGER PRIMARY KEY,
    ecosystem_id INTEGER NOT NULL,
    taxonomy_version_code TEXT NOT NULL,
    taxonomy_name TEXT NULL,
    source_type TEXT NULL,
    source_reference TEXT NULL,
    source_hash TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'DEPRECATED')),
    is_active INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
    active_from TEXT NULL,
    active_to TEXT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (ecosystem_id, taxonomy_version_code),
    FOREIGN KEY (ecosystem_id) REFERENCES ec_ecosystem (ecosystem_id)
);

CREATE TABLE IF NOT EXISTS ec_entity (
    entity_id INTEGER PRIMARY KEY,
    ecosystem_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('ECOSYSTEM', 'GROUP_L1', 'GROUP_L2', 'TICKER')),
    entity_code TEXT NOT NULL,
    entity_name TEXT NULL,
    ticker TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'DEPRECATED')),
    active_from TEXT NULL,
    active_to TEXT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    UNIQUE (ecosystem_id, entity_type, entity_code),
    UNIQUE (ecosystem_id, ticker),
    FOREIGN KEY (ecosystem_id) REFERENCES ec_ecosystem (ecosystem_id)
);

CREATE TABLE IF NOT EXISTS ec_entity_alias (
    entity_alias_id INTEGER PRIMARY KEY,
    ecosystem_id INTEGER NOT NULL,
    entity_id INTEGER NOT NULL,
    alias_type TEXT NOT NULL CHECK (alias_type IN ('DC_GROUP_NAME', 'TICKER', 'DISPLAY_NAME', 'LEGACY_CODE')),
    alias_value TEXT NOT NULL,
    source_system TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'DEPRECATED')),
    active_from TEXT NULL,
    active_to TEXT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (ecosystem_id, alias_type, alias_value, source_system),
    FOREIGN KEY (ecosystem_id) REFERENCES ec_ecosystem (ecosystem_id),
    FOREIGN KEY (entity_id) REFERENCES ec_entity (entity_id)
);

CREATE TABLE IF NOT EXISTS ec_membership (
    membership_id INTEGER PRIMARY KEY,
    ecosystem_id INTEGER NOT NULL,
    taxonomy_version_id INTEGER NOT NULL,
    parent_entity_id INTEGER NOT NULL,
    child_entity_id INTEGER NOT NULL,
    membership_type TEXT NOT NULL CHECK (membership_type IN ('CONTAINS', 'ASSOCIATED_WITH')),
    membership_role TEXT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    role_weight REAL NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'DEPRECATED')),
    active_from TEXT NULL,
    active_to TEXT NULL,
    source_note TEXT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (taxonomy_version_id, parent_entity_id, child_entity_id, membership_type),
    FOREIGN KEY (ecosystem_id) REFERENCES ec_ecosystem (ecosystem_id),
    FOREIGN KEY (taxonomy_version_id) REFERENCES ec_taxonomy_version (taxonomy_version_id),
    FOREIGN KEY (parent_entity_id) REFERENCES ec_entity (entity_id),
    FOREIGN KEY (child_entity_id) REFERENCES ec_entity (entity_id)
);

CREATE TABLE IF NOT EXISTS ec_watchlist (
    watchlist_id INTEGER PRIMARY KEY,
    ecosystem_id INTEGER NOT NULL,
    watchlist_code TEXT NOT NULL,
    watchlist_name TEXT NOT NULL,
    source_type TEXT NULL,
    source_reference TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'DEPRECATED')),
    active_from TEXT NULL,
    active_to TEXT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    UNIQUE (ecosystem_id, watchlist_code),
    FOREIGN KEY (ecosystem_id) REFERENCES ec_ecosystem (ecosystem_id)
);

CREATE TABLE IF NOT EXISTS ec_watchlist_member (
    watchlist_member_id INTEGER PRIMARY KEY,
    watchlist_id INTEGER NOT NULL,
    entity_id INTEGER NOT NULL,
    member_role TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'DEPRECATED')),
    active_from TEXT NULL,
    active_to TEXT NULL,
    notes TEXT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (watchlist_id, entity_id, active_from),
    FOREIGN KEY (watchlist_id) REFERENCES ec_watchlist (watchlist_id),
    FOREIGN KEY (entity_id) REFERENCES ec_entity (entity_id)
);

CREATE INDEX IF NOT EXISTS idx_ec_entity_ecosystem_type_code
ON ec_entity (ecosystem_id, entity_type, entity_code);

CREATE INDEX IF NOT EXISTS idx_ec_entity_ticker
ON ec_entity (ticker);

CREATE INDEX IF NOT EXISTS idx_ec_entity_alias_lookup
ON ec_entity_alias (ecosystem_id, alias_type, alias_value);

CREATE INDEX IF NOT EXISTS idx_ec_membership_taxonomy_parent
ON ec_membership (taxonomy_version_id, parent_entity_id);

CREATE INDEX IF NOT EXISTS idx_ec_membership_taxonomy_child
ON ec_membership (taxonomy_version_id, child_entity_id);

CREATE INDEX IF NOT EXISTS idx_ec_watchlist_member_watchlist
ON ec_watchlist_member (watchlist_id);

CREATE INDEX IF NOT EXISTS idx_ec_taxonomy_version_ecosystem_active
ON ec_taxonomy_version (ecosystem_id, is_active, status);
