CREATE TABLE IF NOT EXISTS dc_report_technical_relevance_context_v2 (
    run_id TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    report_window TEXT NOT NULL CHECK (report_window IN ('daily', 'rolling2', 'rolling5', 'rolling30')),
    ticker TEXT NOT NULL,
    timeframe TEXT NULL,
    signal_name TEXT NOT NULL,
    signal_source_id TEXT NULL,
    signal_direction TEXT NULL CHECK (
        signal_direction IS NULL OR signal_direction IN ('BULLISH', 'BEARISH', 'NEUTRAL', 'MIXED', 'UNKNOWN')
    ),
    signal_family TEXT NULL,
    signal_confirmed_as_of_date TEXT NULL,
    relevance_class TEXT NOT NULL CHECK (
        relevance_class IN (
            'RELEVANT',
            'NOT_RELEVANT',
            'CONTEXTUAL',
            'CONFIRMING',
            'COUNTER_TREND',
            'STALE',
            'UNKNOWN'
        )
    ),
    relevance_reason TEXT NULL,
    trend_state TEXT NULL,
    dow_context TEXT NULL,
    bos_context TEXT NULL,
    reset_context TEXT NULL,
    trend_alignment TEXT NULL,
    counter_trend_context TEXT NULL,
    source_run_id TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        run_id,
        signal_date,
        taxonomy_version,
        report_window,
        ticker,
        signal_name,
        signal_confirmed_as_of_date
    ),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE TABLE IF NOT EXISTS dc_report_data_quality_summary_v2 (
    run_id TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    report_window TEXT NOT NULL CHECK (report_window IN ('daily', 'rolling2', 'rolling5', 'rolling30')),
    quality_scope TEXT NOT NULL CHECK (
        quality_scope IN ('RUN', 'WINDOW', 'TAXONOMY', 'WATCHLIST', 'LAYER', 'SUBINDUSTRY', 'TICKER', 'SOURCE')
    ),
    scope_key TEXT NOT NULL,
    quality_status TEXT NOT NULL CHECK (
        quality_status IN ('OK', 'WARN', 'ERROR', 'MISSING', 'INCOMPLETE', 'STALE', 'UNKNOWN')
    ),
    expected_count INTEGER NULL CHECK (expected_count IS NULL OR expected_count >= 0),
    actual_count INTEGER NULL CHECK (actual_count IS NULL OR actual_count >= 0),
    missing_count INTEGER NULL CHECK (missing_count IS NULL OR missing_count >= 0),
    incomplete_count INTEGER NULL CHECK (incomplete_count IS NULL OR incomplete_count >= 0),
    stale_count INTEGER NULL CHECK (stale_count IS NULL OR stale_count >= 0),
    warning_count INTEGER NULL CHECK (warning_count IS NULL OR warning_count >= 0),
    error_count INTEGER NULL CHECK (error_count IS NULL OR error_count >= 0),
    detail TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        run_id,
        signal_date,
        taxonomy_version,
        report_window,
        quality_scope,
        scope_key
    ),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE INDEX IF NOT EXISTS idx_dc_report_technical_relevance_context_v2_date_taxonomy_window_ticker
ON dc_report_technical_relevance_context_v2 (signal_date, taxonomy_version, report_window, ticker);

CREATE INDEX IF NOT EXISTS idx_dc_report_technical_relevance_context_v2_relevance_family
ON dc_report_technical_relevance_context_v2 (relevance_class, signal_family, signal_date);

CREATE INDEX IF NOT EXISTS idx_dc_report_data_quality_summary_v2_date_taxonomy_window_status
ON dc_report_data_quality_summary_v2 (signal_date, taxonomy_version, report_window, quality_status);

CREATE INDEX IF NOT EXISTS idx_dc_report_data_quality_summary_v2_scope
ON dc_report_data_quality_summary_v2 (quality_scope, scope_key, signal_date);
