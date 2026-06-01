CREATE TABLE IF NOT EXISTS eco_ecosystem (
    ecosystem_id INTEGER PRIMARY KEY,
    ecosystem_code TEXT NOT NULL UNIQUE,
    ecosystem_name TEXT NOT NULL,
    description TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'PLANNED', 'ARCHIVED')),
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL
);

CREATE TABLE IF NOT EXISTS eco_taxonomy_version (
    taxonomy_version_id INTEGER PRIMARY KEY,
    ecosystem_id INTEGER NOT NULL,
    version_code TEXT NOT NULL,
    version_label TEXT NULL,
    source_type TEXT NULL,
    source_reference TEXT NULL,
    effective_from TEXT NULL,
    effective_to TEXT NULL,
    is_active INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'ACTIVE', 'INACTIVE', 'ARCHIVED')),
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    UNIQUE (ecosystem_id, version_code),
    FOREIGN KEY (ecosystem_id) REFERENCES eco_ecosystem (ecosystem_id)
);

CREATE TABLE IF NOT EXISTS eco_entity (
    entity_id INTEGER PRIMARY KEY,
    ecosystem_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('ECOSYSTEM', 'LAYER', 'SUBINDUSTRY', 'TICKER')),
    entity_code TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    ticker TEXT NULL,
    exchange TEXT NULL,
    market TEXT NULL,
    currency TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'WATCH_ONLY', 'ARCHIVED')),
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    UNIQUE (ecosystem_id, entity_type, entity_code),
    FOREIGN KEY (ecosystem_id) REFERENCES eco_ecosystem (ecosystem_id)
);

CREATE TABLE IF NOT EXISTS eco_taxonomy_entity_relation (
    relation_id INTEGER PRIMARY KEY,
    taxonomy_version_id INTEGER NOT NULL,
    ecosystem_id INTEGER NOT NULL,
    parent_entity_id INTEGER NOT NULL,
    child_entity_id INTEGER NOT NULL,
    relation_type TEXT NOT NULL CHECK (relation_type IN ('CONTAINS', 'ASSOCIATED_WITH')),
    membership_role TEXT NULL CHECK (
        membership_role IS NULL OR membership_role IN ('CORE', 'ADJACENT', 'WATCH_ONLY', 'OPTIONAL')
    ),
    weight REAL NULL CHECK (weight IS NULL OR weight >= 0.0),
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    sort_order INTEGER NULL,
    effective_from TEXT NULL,
    effective_to TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'ARCHIVED')),
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    UNIQUE (taxonomy_version_id, parent_entity_id, child_entity_id, relation_type),
    FOREIGN KEY (taxonomy_version_id) REFERENCES eco_taxonomy_version (taxonomy_version_id),
    FOREIGN KEY (ecosystem_id) REFERENCES eco_ecosystem (ecosystem_id),
    FOREIGN KEY (parent_entity_id) REFERENCES eco_entity (entity_id),
    FOREIGN KEY (child_entity_id) REFERENCES eco_entity (entity_id)
);

CREATE TABLE IF NOT EXISTS eco_watchlist (
    watchlist_id INTEGER PRIMARY KEY,
    ecosystem_id INTEGER NOT NULL,
    watchlist_code TEXT NOT NULL,
    watchlist_name TEXT NOT NULL,
    description TEXT NULL,
    source_type TEXT NULL,
    source_reference TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'ARCHIVED')),
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    UNIQUE (ecosystem_id, watchlist_code),
    FOREIGN KEY (ecosystem_id) REFERENCES eco_ecosystem (ecosystem_id)
);

CREATE TABLE IF NOT EXISTS eco_watchlist_member (
    watchlist_member_id INTEGER PRIMARY KEY,
    watchlist_id INTEGER NOT NULL,
    entity_id INTEGER NOT NULL,
    member_role TEXT NULL CHECK (
        member_role IS NULL OR member_role IN ('CORE', 'ADJACENT', 'WATCH_ONLY', 'OPTIONAL')
    ),
    member_status TEXT NOT NULL CHECK (member_status IN ('ACTIVE', 'INACTIVE', 'ARCHIVED')),
    effective_from TEXT NULL,
    effective_to TEXT NULL,
    sort_order INTEGER NULL,
    added_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    removed_at_utc TEXT NULL,
    notes TEXT NULL,
    UNIQUE (watchlist_id, entity_id),
    FOREIGN KEY (watchlist_id) REFERENCES eco_watchlist (watchlist_id),
    FOREIGN KEY (entity_id) REFERENCES eco_entity (entity_id)
);

CREATE TABLE IF NOT EXISTS eco_report_window (
    window_code TEXT PRIMARY KEY CHECK (window_code IN ('daily', 'rolling2', 'rolling5', 'rolling30')),
    window_label TEXT NOT NULL,
    window_days INTEGER NOT NULL CHECK (window_days > 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_eco_taxonomy_version_ecosystem_status
ON eco_taxonomy_version (ecosystem_id, status);

CREATE INDEX IF NOT EXISTS idx_eco_entity_ecosystem_type_status
ON eco_entity (ecosystem_id, entity_type, status);

CREATE INDEX IF NOT EXISTS idx_eco_entity_ticker
ON eco_entity (ticker);

CREATE INDEX IF NOT EXISTS idx_eco_taxonomy_relation_parent
ON eco_taxonomy_entity_relation (taxonomy_version_id, parent_entity_id);

CREATE INDEX IF NOT EXISTS idx_eco_taxonomy_relation_child
ON eco_taxonomy_entity_relation (taxonomy_version_id, child_entity_id);

CREATE INDEX IF NOT EXISTS idx_eco_watchlist_ecosystem_status
ON eco_watchlist (ecosystem_id, status);

CREATE INDEX IF NOT EXISTS idx_eco_watchlist_member_watchlist_status
ON eco_watchlist_member (watchlist_id, member_status);

CREATE INDEX IF NOT EXISTS idx_eco_watchlist_member_entity
ON eco_watchlist_member (entity_id);

INSERT OR IGNORE INTO eco_report_window (
    window_code,
    window_label,
    window_days,
    is_active,
    sort_order
) VALUES
    ('daily', 'Daily', 1, 1, 1),
    ('rolling2', 'Rolling 2', 2, 1, 2),
    ('rolling5', 'Rolling 5', 5, 1, 3),
    ('rolling30', 'Rolling 30', 30, 1, 4);
