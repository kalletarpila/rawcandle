CREATE TABLE IF NOT EXISTS dc_dashboard_ticker_enrichment_daily (
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    ticker TEXT NOT NULL,
    primary_layer TEXT NULL,
    primary_subindustry TEXT NULL,
    close REAL NULL,
    return_5d REAL NULL,
    return_10d REAL NULL,
    return_20d REAL NULL,
    return_60d REAL NULL,
    action TEXT NULL,
    severity TEXT NULL,
    primary_reason TEXT NULL,
    current_status TEXT NULL,
    start_status_30d TEXT NULL,
    status_change_30d TEXT NULL,
    status_change_5d TEXT NULL,
    window_status_30d TEXT NULL,
    window_status_5d TEXT NULL,
    window_status_2d TEXT NULL,
    ma_break_status TEXT NULL,
    freshness_status TEXT NULL,
    trend_state TEXT NULL,
    trend_state_age_td INTEGER NULL,
    latest_structure_label TEXT NULL,
    latest_structure_age_td INTEGER NULL,
    latest_bos_event_type TEXT NULL,
    latest_bos_age_td INTEGER NULL,
    latest_reset_reason TEXT NULL,
    latest_reset_age_td INTEGER NULL,
    latest_candle TEXT NULL,
    latest_candle_age_td INTEGER NULL,
    latest_divergence TEXT NULL,
    latest_divergence_age_td INTEGER NULL,
    latest_chart_pattern TEXT NULL,
    latest_chart_pattern_age_td INTEGER NULL,
    pullback_validity TEXT NULL,
    entry_readiness TEXT NULL,
    candidate_priority TEXT NULL,
    candidate_priority_label TEXT NULL,
    daily_status TEXT NULL,
    rolling_2d_status TEXT NULL,
    rolling_5d_status TEXT NULL,
    rolling_30d_status TEXT NULL,
    horizons_present TEXT NULL,
    source_run_ids TEXT NULL,
    source_components TEXT NULL,
    is_watchlist INTEGER NOT NULL DEFAULT 0,
    data_quality_status TEXT NOT NULL,
    calc_version TEXT NOT NULL,
    run_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY (signal_date, taxonomy_version, ticker)
);

CREATE INDEX IF NOT EXISTS idx_dc_dashboard_ticker_enrichment_ticker_date
ON dc_dashboard_ticker_enrichment_daily (ticker, signal_date);

CREATE INDEX IF NOT EXISTS idx_dc_dashboard_ticker_enrichment_date_action
ON dc_dashboard_ticker_enrichment_daily (signal_date, action);

CREATE INDEX IF NOT EXISTS idx_dc_dashboard_ticker_enrichment_date_watchlist
ON dc_dashboard_ticker_enrichment_daily (signal_date, is_watchlist);

CREATE INDEX IF NOT EXISTS idx_dc_dashboard_ticker_enrichment_date_taxonomy
ON dc_dashboard_ticker_enrichment_daily (signal_date, primary_layer, primary_subindustry);

CREATE TABLE IF NOT EXISTS dc_dashboard_group_enrichment_daily (
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    market_level TEXT NOT NULL,
    taxonomy_key TEXT NOT NULL,
    name TEXT NOT NULL,
    parent_name TEXT NULL,
    layer TEXT NULL,
    subindustry TEXT NULL,
    taxonomy_path TEXT NULL,
    current_status TEXT NULL,
    start_status_30d TEXT NULL,
    status_change_30d TEXT NULL,
    status_change_5d TEXT NULL,
    window_status_30d TEXT NULL,
    window_status_5d TEXT NULL,
    window_status_2d TEXT NULL,
    overheat_risk TEXT NULL,
    pct_above_ema20 REAL NULL,
    pct_above_ma10 REAL NULL,
    ema20_breadth_delta_5d REAL NULL,
    return_5d REAL NULL,
    return_10d REAL NULL,
    return_20d REAL NULL,
    return_60d REAL NULL,
    dow_trend_state TEXT NULL,
    dow_trend_state_age_td INTEGER NULL,
    latest_structure_label TEXT NULL,
    latest_structure_age_td INTEGER NULL,
    latest_bos_event_type TEXT NULL,
    latest_bos_age_td INTEGER NULL,
    latest_reset_reason TEXT NULL,
    latest_reset_age_td INTEGER NULL,
    latest_candle TEXT NULL,
    latest_candle_age_td INTEGER NULL,
    latest_divergence TEXT NULL,
    latest_divergence_age_td INTEGER NULL,
    latest_chart_pattern TEXT NULL,
    latest_chart_pattern_age_td INTEGER NULL,
    source_horizons TEXT NULL,
    source_run_ids TEXT NULL,
    source_components TEXT NULL,
    data_quality_status TEXT NOT NULL,
    calc_version TEXT NOT NULL,
    run_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY (signal_date, taxonomy_version, market_level, taxonomy_key)
);

CREATE INDEX IF NOT EXISTS idx_dc_dashboard_group_enrichment_date_level
ON dc_dashboard_group_enrichment_daily (signal_date, market_level);

CREATE INDEX IF NOT EXISTS idx_dc_dashboard_group_enrichment_date_layer
ON dc_dashboard_group_enrichment_daily (signal_date, layer);

CREATE INDEX IF NOT EXISTS idx_dc_dashboard_group_enrichment_date_taxonomy_path
ON dc_dashboard_group_enrichment_daily (signal_date, taxonomy_path);

CREATE TABLE IF NOT EXISTS dc_dashboard_action_summary_daily (
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    action TEXT NOT NULL,
    count INTEGER NOT NULL,
    calc_version TEXT NOT NULL,
    run_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY (signal_date, taxonomy_version, action)
);

CREATE INDEX IF NOT EXISTS idx_dc_dashboard_action_summary_date
ON dc_dashboard_action_summary_daily (signal_date, taxonomy_version);

CREATE TABLE IF NOT EXISTS dc_dashboard_decision_trace_daily (
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    ticker TEXT NOT NULL,
    trace_index INTEGER NOT NULL,
    action TEXT NULL,
    matched_rule TEXT NULL,
    matched_token TEXT NULL,
    matched_value TEXT NULL,
    horizon TEXT NULL,
    field TEXT NULL,
    calc_version TEXT NOT NULL,
    run_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY (signal_date, taxonomy_version, ticker, trace_index)
);

CREATE INDEX IF NOT EXISTS idx_dc_dashboard_decision_trace_date_ticker
ON dc_dashboard_decision_trace_daily (signal_date, ticker);

CREATE INDEX IF NOT EXISTS idx_dc_dashboard_decision_trace_date_action
ON dc_dashboard_decision_trace_daily (signal_date, action);

CREATE TABLE IF NOT EXISTS dc_dashboard_enrichment_run_daily (
    run_id TEXT PRIMARY KEY,
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    status TEXT NOT NULL,
    readiness TEXT NOT NULL,
    ticker_rows INTEGER NOT NULL,
    group_rows INTEGER NOT NULL,
    action_summary_rows INTEGER NOT NULL,
    decision_trace_rows INTEGER NOT NULL,
    warnings TEXT NULL,
    calc_version TEXT NOT NULL,
    created_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dc_dashboard_enrichment_run_date
ON dc_dashboard_enrichment_run_daily (signal_date, taxonomy_version);

CREATE INDEX IF NOT EXISTS idx_dc_dashboard_enrichment_run_status
ON dc_dashboard_enrichment_run_daily (status, readiness);
