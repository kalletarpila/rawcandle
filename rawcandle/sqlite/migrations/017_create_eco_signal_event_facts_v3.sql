CREATE TABLE IF NOT EXISTS eco_signal_observation (
    signal_observation_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    ecosystem_id INTEGER NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version_id INTEGER NOT NULL,
    window_code TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    signal_name TEXT NOT NULL,
    signal_family TEXT NULL,
    signal_direction TEXT NULL CHECK (
        signal_direction IS NULL OR signal_direction IN ('BULLISH', 'BEARISH', 'NEUTRAL', 'MIXED', 'UP', 'DOWN', 'NONE', 'UNKNOWN')
    ),
    signal_value TEXT NULL,
    observed_date TEXT NOT NULL,
    source_table TEXT NULL,
    source_run_id TEXT NULL,
    source_event_id TEXT NULL,
    signal_status TEXT NOT NULL CHECK (signal_status IN ('ACTIVE', 'INACTIVE', 'STALE', 'EXPIRED', 'MISSING', 'UNKNOWN')),
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    UNIQUE (run_id, signal_date, taxonomy_version_id, window_code, entity_id, signal_name, observed_date),
    FOREIGN KEY (run_id) REFERENCES eco_report_run (run_id),
    FOREIGN KEY (ecosystem_id) REFERENCES eco_ecosystem (ecosystem_id),
    FOREIGN KEY (taxonomy_version_id) REFERENCES eco_taxonomy_version (taxonomy_version_id),
    FOREIGN KEY (window_code) REFERENCES eco_report_window (window_code),
    FOREIGN KEY (entity_id) REFERENCES eco_entity (entity_id)
);

CREATE TABLE IF NOT EXISTS eco_signal_relevance (
    signal_relevance_id INTEGER PRIMARY KEY,
    signal_observation_id INTEGER NOT NULL,
    relevance_label TEXT NOT NULL CHECK (
        relevance_label IN ('RELEVANT', 'NOT_RELEVANT', 'CONTEXTUAL', 'CONFIRMING', 'COUNTER_TREND', 'WEAK_CONTEXT', 'NOISE', 'STALE', 'UNKNOWN')
    ),
    relevance_score REAL NULL CHECK (relevance_score IS NULL OR relevance_score >= 0.0),
    relevance_reason TEXT NULL,
    trend_alignment TEXT NULL,
    dow_context TEXT NULL,
    bos_context TEXT NULL,
    reset_context TEXT NULL,
    counter_trend_context TEXT NULL,
    assigned_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    UNIQUE (signal_observation_id, relevance_label),
    FOREIGN KEY (signal_observation_id) REFERENCES eco_signal_observation (signal_observation_id)
);

CREATE TABLE IF NOT EXISTS eco_entity_event (
    entity_event_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    ecosystem_id INTEGER NOT NULL,
    taxonomy_version_id INTEGER NOT NULL,
    entity_id INTEGER NOT NULL,
    event_date TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'BOS',
            'RESET',
            'STRUCTURE_CHANGE',
            'STRUCTURE_BREAK',
            'TREND_STATE_CHANGE',
            'MA_BREAK',
            'CLASSIFICATION_CHANGE',
            'FRESHNESS_CHANGE',
            'GROUP_ROTATION',
            'OVERHEAT_TRANSITION',
            'UNKNOWN'
        )
    ),
    source_table TEXT NULL,
    source_run_id TEXT NULL,
    source_event_id TEXT NULL,
    event_key TEXT NOT NULL,
    event_label TEXT NULL,
    event_direction TEXT NULL CHECK (
        event_direction IS NULL OR event_direction IN ('UP', 'DOWN', 'BULLISH', 'BEARISH', 'NEUTRAL', 'MIXED', 'NONE', 'UNKNOWN')
    ),
    event_status TEXT NOT NULL CHECK (event_status IN ('ACTIVE', 'SUPERSEDED', 'STALE', 'MISSING', 'UNKNOWN')),
    event_payload_ref TEXT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    UNIQUE (run_id, taxonomy_version_id, entity_id, event_date, event_type, event_key),
    FOREIGN KEY (run_id) REFERENCES eco_report_run (run_id),
    FOREIGN KEY (ecosystem_id) REFERENCES eco_ecosystem (ecosystem_id),
    FOREIGN KEY (taxonomy_version_id) REFERENCES eco_taxonomy_version (taxonomy_version_id),
    FOREIGN KEY (entity_id) REFERENCES eco_entity (entity_id)
);

CREATE INDEX IF NOT EXISTS idx_eco_signal_observation_date_taxonomy_window_entity
ON eco_signal_observation (signal_date, taxonomy_version_id, window_code, entity_id);

CREATE INDEX IF NOT EXISTS idx_eco_signal_observation_ecosystem_family_status
ON eco_signal_observation (ecosystem_id, signal_family, signal_status);

CREATE INDEX IF NOT EXISTS idx_eco_signal_observation_entity_name_observed_date
ON eco_signal_observation (entity_id, signal_name, observed_date);

CREATE INDEX IF NOT EXISTS idx_eco_signal_observation_source_run_id
ON eco_signal_observation (source_run_id);

CREATE INDEX IF NOT EXISTS idx_eco_signal_relevance_signal_observation_id
ON eco_signal_relevance (signal_observation_id);

CREATE INDEX IF NOT EXISTS idx_eco_signal_relevance_label
ON eco_signal_relevance (relevance_label);

CREATE INDEX IF NOT EXISTS idx_eco_signal_relevance_assigned_at_utc
ON eco_signal_relevance (assigned_at_utc);

CREATE INDEX IF NOT EXISTS idx_eco_entity_event_ecosystem_type_status
ON eco_entity_event (ecosystem_id, event_type, event_status);

CREATE INDEX IF NOT EXISTS idx_eco_entity_event_taxonomy_entity_date
ON eco_entity_event (taxonomy_version_id, entity_id, event_date);

CREATE INDEX IF NOT EXISTS idx_eco_entity_event_source_run_id
ON eco_entity_event (source_run_id);

CREATE INDEX IF NOT EXISTS idx_eco_entity_event_date_type
ON eco_entity_event (event_date, event_type);
