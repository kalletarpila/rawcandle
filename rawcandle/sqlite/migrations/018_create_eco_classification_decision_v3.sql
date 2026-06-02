CREATE TABLE IF NOT EXISTS eco_classification_decision (
    classification_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    ecosystem_id INTEGER NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version_id INTEGER NOT NULL,
    window_code TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    classification_type TEXT NOT NULL CHECK (
        classification_type IN (
            'daily_trigger',
            'rolling2_sell_pressure',
            'rolling5_pullback',
            'rolling30_buy',
            'rolling30_exit'
        )
    ),
    classification_state TEXT NOT NULL,
    primary_reason TEXT NULL,
    blocking_reason TEXT NULL,
    risk_reason TEXT NULL,
    next_action TEXT NULL,
    priority_score REAL NULL CHECK (priority_score IS NULL OR priority_score >= 0.0),
    priority_label TEXT NULL,
    sort_rank INTEGER NULL CHECK (sort_rank IS NULL OR sort_rank >= 0),
    source_classifier TEXT NULL,
    classification_version TEXT NULL,
    source_run_id TEXT NULL,
    decision_status TEXT NOT NULL CHECK (
        decision_status IN ('OK', 'WARN', 'MISSING', 'INCOMPLETE', 'ERROR', 'UNKNOWN')
    ),
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    UNIQUE (run_id, signal_date, taxonomy_version_id, window_code, entity_id, classification_type),
    FOREIGN KEY (run_id) REFERENCES eco_report_run (run_id),
    FOREIGN KEY (ecosystem_id) REFERENCES eco_ecosystem (ecosystem_id),
    FOREIGN KEY (taxonomy_version_id) REFERENCES eco_taxonomy_version (taxonomy_version_id),
    FOREIGN KEY (window_code) REFERENCES eco_report_window (window_code),
    FOREIGN KEY (entity_id) REFERENCES eco_entity (entity_id)
);

CREATE INDEX IF NOT EXISTS idx_eco_classification_decision_run_window_type
ON eco_classification_decision (run_id, window_code, classification_type);

CREATE INDEX IF NOT EXISTS idx_eco_classification_decision_entity_window
ON eco_classification_decision (entity_id, window_code);

CREATE INDEX IF NOT EXISTS idx_eco_classification_decision_state
ON eco_classification_decision (classification_type, classification_state);

CREATE INDEX IF NOT EXISTS idx_eco_classification_decision_status
ON eco_classification_decision (decision_status);

CREATE INDEX IF NOT EXISTS idx_eco_classification_decision_priority
ON eco_classification_decision (classification_type, priority_score);
