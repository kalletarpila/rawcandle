CREATE TABLE IF NOT EXISTS dc_report_watchlist_ticker_v2 (
    run_id TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    report_window TEXT NOT NULL CHECK (report_window IN ('daily', 'rolling2', 'rolling5', 'rolling30')),
    ticker TEXT NOT NULL,
    watchlist_source TEXT NULL,
    primary_layer TEXT NULL,
    primary_subindustry TEXT NULL,
    coverage_status TEXT NOT NULL CHECK (
        coverage_status IN (
            'OK',
            'MISSING_INSTRUMENT',
            'MISSING_PRICE_DATA',
            'MISSING_DAILY_SIGNAL',
            'MISSING_ROLLING_CONTEXT',
            'WATCHLIST_ONLY',
            'EXCLUDED'
        )
    ),
    is_included INTEGER NOT NULL CHECK (is_included IN (0, 1)),
    missing_reason TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, signal_date, taxonomy_version, report_window, ticker),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE TABLE IF NOT EXISTS dc_report_taxonomy_ticker_coverage_v2 (
    run_id TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    ticker TEXT NOT NULL,
    primary_layer TEXT NULL,
    primary_subindustry TEXT NULL,
    coverage_status TEXT NOT NULL CHECK (
        coverage_status IN (
            'OK',
            'MISSING_INSTRUMENT',
            'MISSING_PRICE_DATA',
            'MISSING_DAILY_SIGNAL',
            'MISSING_ROLLING_CONTEXT',
            'TAXONOMY_ONLY'
        )
    ),
    has_instrument INTEGER NOT NULL CHECK (has_instrument IN (0, 1)),
    has_price_data INTEGER NOT NULL CHECK (has_price_data IN (0, 1)),
    has_daily_signal INTEGER NOT NULL CHECK (has_daily_signal IN (0, 1)),
    has_rolling_context INTEGER NOT NULL CHECK (has_rolling_context IN (0, 1)),
    missing_reason TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, signal_date, taxonomy_version, ticker),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE INDEX IF NOT EXISTS idx_dc_report_watchlist_ticker_v2_date_taxonomy_window_status
ON dc_report_watchlist_ticker_v2 (signal_date, taxonomy_version, report_window, coverage_status);

CREATE INDEX IF NOT EXISTS idx_dc_report_watchlist_ticker_v2_ticker
ON dc_report_watchlist_ticker_v2 (ticker, signal_date);

CREATE INDEX IF NOT EXISTS idx_dc_report_taxonomy_ticker_coverage_v2_date_taxonomy_status
ON dc_report_taxonomy_ticker_coverage_v2 (signal_date, taxonomy_version, coverage_status);

CREATE INDEX IF NOT EXISTS idx_dc_report_taxonomy_ticker_coverage_v2_ticker
ON dc_report_taxonomy_ticker_coverage_v2 (ticker, signal_date);
