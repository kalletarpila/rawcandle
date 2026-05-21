CREATE TABLE IF NOT EXISTS technical_signal_relevance_runs (
    run_id TEXT PRIMARY KEY NOT NULL,
    relevance_rule_version TEXT NOT NULL,
    mapping_version TEXT NOT NULL,
    reason_version TEXT NOT NULL,
    config_snapshot_json TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS technical_signal_relevance (
    ticker TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    signal_confirmed_as_of_date TEXT NOT NULL,
    signal_name TEXT NOT NULL,
    signal_close_price REAL NULL,
    signal_direction TEXT NULL,
    signal_family TEXT NULL,
    signal_source_type TEXT NOT NULL,
    signal_source_id TEXT NOT NULL,
    dow_trend_state TEXT NULL,
    dow_context_state TEXT NULL,
    latest_bos_direction TEXT NULL,
    bars_since_latest_bos INTEGER NULL,
    latest_reset_reason TEXT NULL,
    bars_since_latest_reset INTEGER NULL,
    near_latest_pivot INTEGER NOT NULL,
    near_active_bos_level INTEGER NOT NULL,
    is_trend_aligned INTEGER NOT NULL,
    is_counter_trend INTEGER NOT NULL,
    relevance_class TEXT NOT NULL,
    relevance_reason TEXT NOT NULL,
    relevance_rule_version TEXT NOT NULL,
    mapping_version TEXT NOT NULL,
    reason_version TEXT NOT NULL,
    rule_trace TEXT NULL,
    created_at_utc TEXT NOT NULL,
    run_id TEXT NOT NULL,
    PRIMARY KEY (
        run_id,
        ticker,
        timeframe,
        signal_date,
        signal_name,
        signal_source_type,
        signal_source_id,
        relevance_rule_version
    ),
    FOREIGN KEY (run_id) REFERENCES technical_signal_relevance_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_technical_signal_relevance_ticker_tf_date
ON technical_signal_relevance(ticker, timeframe, signal_date);

CREATE INDEX IF NOT EXISTS idx_technical_signal_relevance_ticker_tf_class_date
ON technical_signal_relevance(ticker, timeframe, relevance_class, signal_date);

CREATE INDEX IF NOT EXISTS idx_technical_signal_relevance_run_id
ON technical_signal_relevance(run_id);
