CREATE TABLE IF NOT EXISTS eco_report_run (
    run_id TEXT PRIMARY KEY,
    ecosystem_id INTEGER NOT NULL,
    taxonomy_version_id INTEGER NOT NULL,
    signal_date TEXT NOT NULL,
    run_type TEXT NOT NULL CHECK (run_type IN ('BUILD', 'IMPORT', 'SMOKE', 'BACKFILL')),
    status TEXT NOT NULL CHECK (status IN ('STARTED', 'OK', 'OK_WITH_WARNINGS', 'FAILED', 'CANCELLED')),
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at_utc TEXT NULL,
    warning_count INTEGER NOT NULL DEFAULT 0 CHECK (warning_count >= 0),
    error_count INTEGER NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    notes TEXT NULL,
    FOREIGN KEY (ecosystem_id) REFERENCES eco_ecosystem (ecosystem_id),
    FOREIGN KEY (taxonomy_version_id) REFERENCES eco_taxonomy_version (taxonomy_version_id)
);

CREATE TABLE IF NOT EXISTS eco_entity_window_snapshot (
    run_id TEXT NOT NULL,
    ecosystem_id INTEGER NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version_id INTEGER NOT NULL,
    window_code TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    snapshot_status TEXT NOT NULL CHECK (snapshot_status IN ('OK', 'WARN', 'MISSING', 'INCOMPLETE', 'ERROR', 'UNKNOWN')),
    timing_state TEXT NULL,
    trend_state TEXT NULL,
    summary_state TEXT NULL,
    classification_state TEXT NULL,
    freshness_status TEXT NULL CHECK (
        freshness_status IS NULL OR freshness_status IN ('FRESH', 'AGING', 'STALE', 'EXPIRED', 'MISSING', 'UNKNOWN')
    ),
    quality_status TEXT NULL CHECK (
        quality_status IS NULL OR quality_status IN ('OK', 'WARN', 'MISSING', 'INCOMPLETE', 'ERROR', 'UNKNOWN')
    ),
    asof_observed_at TEXT NULL,
    source_run_id TEXT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    PRIMARY KEY (run_id, signal_date, taxonomy_version_id, window_code, entity_id),
    FOREIGN KEY (run_id) REFERENCES eco_report_run (run_id),
    FOREIGN KEY (ecosystem_id) REFERENCES eco_ecosystem (ecosystem_id),
    FOREIGN KEY (taxonomy_version_id) REFERENCES eco_taxonomy_version (taxonomy_version_id),
    FOREIGN KEY (window_code) REFERENCES eco_report_window (window_code),
    FOREIGN KEY (entity_id) REFERENCES eco_entity (entity_id)
);

CREATE TABLE IF NOT EXISTS eco_entity_metric_value (
    run_id TEXT NOT NULL,
    ecosystem_id INTEGER NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version_id INTEGER NOT NULL,
    window_code TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    metric_value_num REAL NULL,
    metric_value_text TEXT NULL,
    metric_unit TEXT NULL,
    value_status TEXT NOT NULL CHECK (value_status IN ('OK', 'MISSING', 'INCOMPLETE', 'ERROR', 'UNKNOWN')),
    source_run_id TEXT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    PRIMARY KEY (run_id, signal_date, taxonomy_version_id, window_code, entity_id, metric_name),
    FOREIGN KEY (run_id) REFERENCES eco_report_run (run_id),
    FOREIGN KEY (ecosystem_id) REFERENCES eco_ecosystem (ecosystem_id),
    FOREIGN KEY (taxonomy_version_id) REFERENCES eco_taxonomy_version (taxonomy_version_id),
    FOREIGN KEY (window_code) REFERENCES eco_report_window (window_code),
    FOREIGN KEY (entity_id) REFERENCES eco_entity (entity_id)
);

CREATE TABLE IF NOT EXISTS eco_entity_coverage (
    run_id TEXT NOT NULL,
    ecosystem_id INTEGER NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version_id INTEGER NOT NULL,
    window_code TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    in_taxonomy INTEGER NOT NULL CHECK (in_taxonomy IN (0, 1)),
    in_watchlist INTEGER NOT NULL CHECK (in_watchlist IN (0, 1)),
    has_instrument INTEGER NOT NULL CHECK (has_instrument IN (0, 1)),
    has_price_data INTEGER NOT NULL CHECK (has_price_data IN (0, 1)),
    has_daily_signal INTEGER NOT NULL CHECK (has_daily_signal IN (0, 1)),
    has_window_context INTEGER NOT NULL CHECK (has_window_context IN (0, 1)),
    coverage_status TEXT NOT NULL CHECK (
        coverage_status IN (
            'OK',
            'MISSING_INSTRUMENT',
            'MISSING_PRICE_DATA',
            'MISSING_DAILY_SIGNAL',
            'MISSING_WINDOW_CONTEXT',
            'WATCHLIST_ONLY',
            'TAXONOMY_ONLY',
            'EXCLUDED',
            'UNKNOWN'
        )
    ),
    source_row_count INTEGER NULL CHECK (source_row_count IS NULL OR source_row_count >= 0),
    missing_component_count INTEGER NULL CHECK (missing_component_count IS NULL OR missing_component_count >= 0),
    coverage_notes TEXT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    PRIMARY KEY (run_id, signal_date, taxonomy_version_id, window_code, entity_id),
    FOREIGN KEY (run_id) REFERENCES eco_report_run (run_id),
    FOREIGN KEY (ecosystem_id) REFERENCES eco_ecosystem (ecosystem_id),
    FOREIGN KEY (taxonomy_version_id) REFERENCES eco_taxonomy_version (taxonomy_version_id),
    FOREIGN KEY (window_code) REFERENCES eco_report_window (window_code),
    FOREIGN KEY (entity_id) REFERENCES eco_entity (entity_id)
);

CREATE TABLE IF NOT EXISTS eco_quality_summary (
    quality_summary_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    ecosystem_id INTEGER NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version_id INTEGER NOT NULL,
    window_code TEXT NOT NULL,
    quality_scope TEXT NOT NULL CHECK (quality_scope IN ('RUN', 'WINDOW', 'ECOSYSTEM', 'LAYER', 'SUBINDUSTRY', 'TICKER', 'SOURCE')),
    scope_entity_id INTEGER NOT NULL,
    quality_status TEXT NOT NULL CHECK (quality_status IN ('OK', 'WARN', 'MISSING', 'INCOMPLETE', 'ERROR', 'UNKNOWN')),
    expected_count INTEGER NULL CHECK (expected_count IS NULL OR expected_count >= 0),
    actual_count INTEGER NULL CHECK (actual_count IS NULL OR actual_count >= 0),
    missing_count INTEGER NULL CHECK (missing_count IS NULL OR missing_count >= 0),
    incomplete_count INTEGER NULL CHECK (incomplete_count IS NULL OR incomplete_count >= 0),
    stale_count INTEGER NULL CHECK (stale_count IS NULL OR stale_count >= 0),
    warning_count INTEGER NULL CHECK (warning_count IS NULL OR warning_count >= 0),
    error_count INTEGER NULL CHECK (error_count IS NULL OR error_count >= 0),
    summary_note TEXT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    UNIQUE (run_id, signal_date, taxonomy_version_id, window_code, quality_scope, scope_entity_id),
    FOREIGN KEY (run_id) REFERENCES eco_report_run (run_id),
    FOREIGN KEY (ecosystem_id) REFERENCES eco_ecosystem (ecosystem_id),
    FOREIGN KEY (taxonomy_version_id) REFERENCES eco_taxonomy_version (taxonomy_version_id),
    FOREIGN KEY (window_code) REFERENCES eco_report_window (window_code),
    FOREIGN KEY (scope_entity_id) REFERENCES eco_entity (entity_id)
);

CREATE INDEX IF NOT EXISTS idx_eco_report_run_ecosystem_signal_date
ON eco_report_run (ecosystem_id, signal_date);

CREATE INDEX IF NOT EXISTS idx_eco_report_run_taxonomy_signal_date
ON eco_report_run (taxonomy_version_id, signal_date);

CREATE INDEX IF NOT EXISTS idx_eco_report_run_status_signal_date
ON eco_report_run (status, signal_date);

CREATE INDEX IF NOT EXISTS idx_eco_entity_window_snapshot_date_taxonomy_window
ON eco_entity_window_snapshot (signal_date, taxonomy_version_id, window_code);

CREATE INDEX IF NOT EXISTS idx_eco_entity_window_snapshot_entity_date
ON eco_entity_window_snapshot (entity_id, signal_date);

CREATE INDEX IF NOT EXISTS idx_eco_entity_window_snapshot_ecosystem_window_status
ON eco_entity_window_snapshot (ecosystem_id, window_code, snapshot_status);

CREATE INDEX IF NOT EXISTS idx_eco_entity_metric_value_date_taxonomy_window_metric
ON eco_entity_metric_value (signal_date, taxonomy_version_id, window_code, metric_name);

CREATE INDEX IF NOT EXISTS idx_eco_entity_metric_value_entity_metric_date
ON eco_entity_metric_value (entity_id, metric_name, signal_date);

CREATE INDEX IF NOT EXISTS idx_eco_entity_metric_value_ecosystem_metric
ON eco_entity_metric_value (ecosystem_id, metric_name);

CREATE INDEX IF NOT EXISTS idx_eco_entity_coverage_date_taxonomy_window_status
ON eco_entity_coverage (signal_date, taxonomy_version_id, window_code, coverage_status);

CREATE INDEX IF NOT EXISTS idx_eco_entity_coverage_entity_date
ON eco_entity_coverage (entity_id, signal_date);

CREATE INDEX IF NOT EXISTS idx_eco_entity_coverage_ecosystem_status
ON eco_entity_coverage (ecosystem_id, coverage_status);

CREATE INDEX IF NOT EXISTS idx_eco_quality_summary_date_taxonomy_window_status
ON eco_quality_summary (signal_date, taxonomy_version_id, window_code, quality_status);

CREATE INDEX IF NOT EXISTS idx_eco_quality_summary_ecosystem_scope_status
ON eco_quality_summary (ecosystem_id, quality_scope, quality_status);

CREATE INDEX IF NOT EXISTS idx_eco_quality_summary_scope_entity_date
ON eco_quality_summary (scope_entity_id, signal_date);
