CREATE TABLE IF NOT EXISTS dc_report_group_timing_persistence_v2 (
    run_id TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    report_window TEXT NOT NULL CHECK (report_window IN ('daily', 'rolling2', 'rolling5', 'rolling30')),
    group_scope TEXT NOT NULL CHECK (group_scope IN ('LAYER', 'SUBINDUSTRY', 'ECOSYSTEM', 'WATCHLIST', 'MARKET')),
    group_key TEXT NOT NULL,
    primary_layer TEXT NULL,
    primary_subindustry TEXT NULL,
    timing_signal_name TEXT NOT NULL,
    persistence_class TEXT NOT NULL CHECK (
        persistence_class IN ('PERSISTENT', 'IMPROVING', 'DETERIORATING', 'FADING', 'NEW', 'LOST', 'UNSTABLE', 'UNKNOWN')
    ),
    persistence_days INTEGER NULL CHECK (persistence_days IS NULL OR persistence_days >= 0),
    first_seen_date TEXT NULL,
    last_seen_date TEXT NULL,
    previous_state TEXT NULL,
    current_state TEXT NULL,
    state_delta TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('OK', 'WARN', 'ERROR', 'MISSING', 'INCOMPLETE', 'UNKNOWN')),
    reason TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        run_id,
        signal_date,
        taxonomy_version,
        report_window,
        group_scope,
        group_key,
        timing_signal_name
    ),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE TABLE IF NOT EXISTS dc_report_ma_break_status_v2 (
    run_id TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    report_window TEXT NOT NULL CHECK (report_window IN ('daily', 'rolling2', 'rolling5', 'rolling30')),
    entity_scope TEXT NOT NULL CHECK (entity_scope IN ('TICKER', 'LAYER', 'SUBINDUSTRY', 'ECOSYSTEM', 'WATCHLIST', 'MARKET')),
    entity_key TEXT NOT NULL,
    ticker TEXT NULL,
    primary_layer TEXT NULL,
    primary_subindustry TEXT NULL,
    ma_name TEXT NOT NULL,
    ma_period INTEGER NULL CHECK (ma_period IS NULL OR ma_period >= 0),
    break_status TEXT NOT NULL CHECK (
        break_status IN ('ABOVE', 'BELOW', 'BROKEN_UP', 'BROKEN_DOWN', 'TESTING', 'RECLAIMED', 'LOST', 'NO_BREAK', 'UNKNOWN')
    ),
    break_direction TEXT NOT NULL CHECK (break_direction IN ('UP', 'DOWN', 'FLAT', 'MIXED', 'NONE', 'UNKNOWN')),
    break_date TEXT NULL,
    days_since_break INTEGER NULL CHECK (days_since_break IS NULL OR days_since_break >= 0),
    close_value REAL NULL,
    ma_value REAL NULL,
    distance_pct REAL NULL,
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
        ma_name
    ),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE TABLE IF NOT EXISTS dc_report_signal_freshness_v2 (
    run_id TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    report_window TEXT NOT NULL CHECK (report_window IN ('daily', 'rolling2', 'rolling5', 'rolling30')),
    entity_scope TEXT NOT NULL CHECK (entity_scope IN ('TICKER', 'LAYER', 'SUBINDUSTRY', 'ECOSYSTEM', 'WATCHLIST', 'MARKET')),
    entity_key TEXT NOT NULL,
    ticker TEXT NULL,
    primary_layer TEXT NULL,
    primary_subindustry TEXT NULL,
    signal_name TEXT NOT NULL,
    signal_family TEXT NULL,
    signal_date_observed TEXT NULL,
    freshness_class TEXT NOT NULL CHECK (freshness_class IN ('FRESH', 'AGING', 'STALE', 'EXPIRED', 'MISSING', 'UNKNOWN')),
    age_trading_days INTEGER NULL CHECK (age_trading_days IS NULL OR age_trading_days >= 0),
    age_calendar_days INTEGER NULL CHECK (age_calendar_days IS NULL OR age_calendar_days >= 0),
    max_fresh_trading_days INTEGER NULL CHECK (max_fresh_trading_days IS NULL OR max_fresh_trading_days >= 0),
    max_fresh_calendar_days INTEGER NULL CHECK (max_fresh_calendar_days IS NULL OR max_fresh_calendar_days >= 0),
    is_fresh INTEGER NOT NULL CHECK (is_fresh IN (0, 1)),
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
        signal_name
    ),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE INDEX IF NOT EXISTS idx_dc_report_group_timing_persistence_v2_date_taxonomy_window_scope
ON dc_report_group_timing_persistence_v2 (signal_date, taxonomy_version, report_window, group_scope);

CREATE INDEX IF NOT EXISTS idx_dc_report_group_timing_persistence_v2_persistence_status
ON dc_report_group_timing_persistence_v2 (signal_date, taxonomy_version, report_window, persistence_class, status);

CREATE INDEX IF NOT EXISTS idx_dc_report_ma_break_status_v2_date_taxonomy_window_scope
ON dc_report_ma_break_status_v2 (signal_date, taxonomy_version, report_window, entity_scope);

CREATE INDEX IF NOT EXISTS idx_dc_report_ma_break_status_v2_break_status
ON dc_report_ma_break_status_v2 (signal_date, taxonomy_version, report_window, break_status, status);

CREATE INDEX IF NOT EXISTS idx_dc_report_signal_freshness_v2_date_taxonomy_window_scope
ON dc_report_signal_freshness_v2 (signal_date, taxonomy_version, report_window, entity_scope);

CREATE INDEX IF NOT EXISTS idx_dc_report_signal_freshness_v2_freshness_status
ON dc_report_signal_freshness_v2 (signal_date, taxonomy_version, report_window, freshness_class, status);
