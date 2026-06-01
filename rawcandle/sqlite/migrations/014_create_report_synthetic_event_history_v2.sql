CREATE TABLE IF NOT EXISTS dc_report_synthetic_event_history_v2 (
    run_id TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    report_window TEXT NOT NULL CHECK (report_window IN ('daily', 'rolling2', 'rolling5', 'rolling30')),
    entity_scope TEXT NOT NULL CHECK (entity_scope IN ('LAYER', 'SUBINDUSTRY', 'ECOSYSTEM', 'WATCHLIST', 'MARKET')),
    entity_key TEXT NOT NULL,
    primary_layer TEXT NULL,
    primary_subindustry TEXT NULL,
    event_date TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN ('STRUCTURE_CHANGE', 'BOS', 'RESET', 'STRUCTURE_BREAK', 'TREND_STATE_CHANGE', 'FRESHNESS_CHANGE', 'UNKNOWN')
    ),
    event_direction TEXT NOT NULL CHECK (event_direction IN ('UP', 'DOWN', 'NEUTRAL', 'MIXED', 'NONE', 'UNKNOWN')),
    structure_label_before TEXT NULL,
    structure_label_after TEXT NULL,
    trend_state_before TEXT NULL,
    trend_state_after TEXT NULL,
    bos_event_type TEXT NULL CHECK (
        bos_event_type IS NULL OR bos_event_type IN ('BOS_UP', 'BOS_DOWN', 'DOUBLE_BOS_UP', 'DOUBLE_BOS_DOWN', 'NONE', 'UNKNOWN')
    ),
    reset_reason TEXT NULL,
    freshness_class TEXT NULL CHECK (
        freshness_class IS NULL OR freshness_class IN ('FRESH', 'AGING', 'STALE', 'EXPIRED', 'MISSING', 'UNKNOWN')
    ),
    age_trading_days INTEGER NULL CHECK (age_trading_days IS NULL OR age_trading_days >= 0),
    source_run_id TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('OK', 'WARN', 'ERROR', 'MISSING', 'INCOMPLETE', 'UNKNOWN')),
    reason TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        run_id,
        signal_date,
        taxonomy_version,
        report_window,
        entity_scope,
        entity_key,
        event_date,
        event_type
    ),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE INDEX IF NOT EXISTS idx_dc_report_synthetic_event_history_v2_date_taxonomy_window_scope
ON dc_report_synthetic_event_history_v2 (signal_date, taxonomy_version, report_window, entity_scope);

CREATE INDEX IF NOT EXISTS idx_dc_report_synthetic_event_history_v2_event_type_direction
ON dc_report_synthetic_event_history_v2 (signal_date, taxonomy_version, report_window, event_type, event_direction);

CREATE INDEX IF NOT EXISTS idx_dc_report_synthetic_event_history_v2_bos_reset
ON dc_report_synthetic_event_history_v2 (signal_date, taxonomy_version, report_window, bos_event_type, reset_reason);
