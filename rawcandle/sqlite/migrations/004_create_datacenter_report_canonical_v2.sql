CREATE TABLE IF NOT EXISTS dc_report_run_v2 (
    run_id TEXT PRIMARY KEY NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    market TEXT NULL,
    calculation_version TEXT NOT NULL,
    source_versions_json TEXT NULL,
    created_at_utc TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('OK', 'OK_WITH_WARNINGS', 'FAILED')),
    warning_count INTEGER NOT NULL DEFAULT 0 CHECK (warning_count >= 0),
    error_count INTEGER NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    notes TEXT NULL
);

CREATE TABLE IF NOT EXISTS dc_report_context_group_v2 (
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    market TEXT NULL,
    horizon TEXT NOT NULL CHECK (horizon IN ('daily', 'rolling2', 'rolling5', 'rolling30')),
    group_type TEXT NOT NULL,
    group_name TEXT NOT NULL,
    parent_group_type TEXT NULL,
    parent_group_name TEXT NULL,
    timing_state TEXT NULL,
    overheat_risk_level TEXT NULL,
    return_2d REAL NULL,
    return_5d REAL NULL,
    return_30d REAL NULL,
    breadth_json TEXT NULL,
    synthetic_close REAL NULL,
    synthetic_ema_distance_json TEXT NULL,
    synthetic_trend_classification TEXT NULL,
    synthetic_latest_structure_label TEXT NULL,
    synthetic_latest_bos_event_type TEXT NULL,
    synthetic_latest_bos_freshness TEXT NULL,
    synthetic_latest_reset_reason TEXT NULL,
    synthetic_latest_reset_freshness TEXT NULL,
    group_context_risk_status TEXT NULL,
    group_context_readiness_status TEXT NOT NULL,
    group_current_status TEXT NULL,
    group_window_status TEXT NULL,
    group_status_change TEXT NULL,
    window_start_date TEXT NULL,
    window_end_date TEXT NOT NULL,
    valid_signal_dates INTEGER NULL CHECK (valid_signal_dates IS NULL OR valid_signal_dates >= 0),
    run_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY (signal_date, taxonomy_version, horizon, group_type, group_name),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE TABLE IF NOT EXISTS dc_report_context_daily_v2 (
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    market TEXT NULL,
    ticker TEXT NOT NULL,
    primary_layer TEXT NULL,
    primary_subindustry TEXT NULL,
    in_datacenter_ecosystem INTEGER NOT NULL DEFAULT 0 CHECK (in_datacenter_ecosystem IN (0, 1)),
    is_watchlist INTEGER NOT NULL DEFAULT 0 CHECK (is_watchlist IN (0, 1)),
    current_watchlist_status TEXT NULL,
    breakout_signal INTEGER NOT NULL DEFAULT 0 CHECK (breakout_signal IN (0, 1)),
    pullback_signal INTEGER NOT NULL DEFAULT 0 CHECK (pullback_signal IN (0, 1)),
    fast_ema10_pullback_signal INTEGER NOT NULL DEFAULT 0 CHECK (fast_ema10_pullback_signal IN (0, 1)),
    conservative_ema20_pullback_signal INTEGER NOT NULL DEFAULT 0 CHECK (conservative_ema20_pullback_signal IN (0, 1)),
    exit_risk_signal INTEGER NOT NULL DEFAULT 0 CHECK (exit_risk_signal IN (0, 1)),
    exit_risk_severity TEXT NULL,
    latest_exit_reason TEXT NULL,
    return_5d REAL NULL,
    return_10d REAL NULL,
    return_20d REAL NULL,
    return_60d REAL NULL,
    distance_to_ema20_pct REAL NULL,
    distance_to_ema50_pct REAL NULL,
    ma_break_status TEXT NULL,
    freshness_status TEXT NULL,
    technical_relevance_status TEXT NULL,
    technical_relevance_reason TEXT NULL,
    trend_state TEXT NULL,
    latest_structure_label TEXT NULL,
    latest_structure_freshness TEXT NULL,
    latest_bos_event_type TEXT NULL,
    latest_bos_freshness TEXT NULL,
    latest_reset_reason TEXT NULL,
    latest_reset_freshness TEXT NULL,
    layer_timing_state TEXT NULL,
    layer_overheat_risk_level TEXT NULL,
    layer_context_risk_status TEXT NULL,
    subindustry_timing_state TEXT NULL,
    subindustry_overheat_risk_level TEXT NULL,
    subindustry_context_risk_status TEXT NULL,
    context_readiness_status TEXT NOT NULL,
    run_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY (signal_date, taxonomy_version, ticker),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE TABLE IF NOT EXISTS dc_report_context_window_v2 (
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    market TEXT NULL,
    ticker TEXT NOT NULL,
    horizon TEXT NOT NULL CHECK (horizon IN ('rolling2', 'rolling5', 'rolling30')),
    window_start_date TEXT NOT NULL,
    window_end_date TEXT NOT NULL,
    valid_signal_dates INTEGER NOT NULL CHECK (valid_signal_dates >= 0),
    incomplete_window INTEGER NOT NULL DEFAULT 0 CHECK (incomplete_window IN (0, 1)),
    primary_layer TEXT NULL,
    primary_subindustry TEXT NULL,
    in_datacenter_ecosystem INTEGER NOT NULL DEFAULT 0 CHECK (in_datacenter_ecosystem IN (0, 1)),
    is_watchlist INTEGER NOT NULL DEFAULT 0 CHECK (is_watchlist IN (0, 1)),
    current_watchlist_status TEXT NULL,
    window_watchlist_status TEXT NULL,
    breakout_days INTEGER NOT NULL DEFAULT 0 CHECK (breakout_days >= 0),
    pullback_days INTEGER NOT NULL DEFAULT 0 CHECK (pullback_days >= 0),
    fast_ema10_pullback_days INTEGER NOT NULL DEFAULT 0 CHECK (fast_ema10_pullback_days >= 0),
    conservative_ema20_pullback_days INTEGER NOT NULL DEFAULT 0 CHECK (conservative_ema20_pullback_days >= 0),
    exit_risk_days INTEGER NOT NULL DEFAULT 0 CHECK (exit_risk_days >= 0),
    high_exit_risk_days INTEGER NOT NULL DEFAULT 0 CHECK (high_exit_risk_days >= 0),
    medium_exit_risk_days INTEGER NOT NULL DEFAULT 0 CHECK (medium_exit_risk_days >= 0),
    first_signal_date TEXT NULL,
    last_signal_date TEXT NULL,
    latest_exit_reason TEXT NULL,
    layer_timing_state TEXT NULL,
    layer_overheat_risk_level TEXT NULL,
    layer_context_risk_status TEXT NULL,
    subindustry_timing_state TEXT NULL,
    subindustry_overheat_risk_level TEXT NULL,
    subindustry_context_risk_status TEXT NULL,
    trend_state TEXT NULL,
    latest_structure_label TEXT NULL,
    latest_structure_freshness TEXT NULL,
    latest_bos_event_type TEXT NULL,
    latest_bos_freshness TEXT NULL,
    latest_reset_reason TEXT NULL,
    latest_reset_freshness TEXT NULL,
    ma_break_status TEXT NULL,
    freshness_status TEXT NULL,
    technical_relevance_status TEXT NULL,
    technical_relevance_reason TEXT NULL,
    close_below_ema20_flag INTEGER NOT NULL DEFAULT 0 CHECK (close_below_ema20_flag IN (0, 1)),
    close_below_ema50_flag INTEGER NOT NULL DEFAULT 0 CHECK (close_below_ema50_flag IN (0, 1)),
    return_10d_lt_minus_8pct_flag INTEGER NOT NULL DEFAULT 0 CHECK (return_10d_lt_minus_8pct_flag IN (0, 1)),
    double_bos_down_flag INTEGER NOT NULL DEFAULT 0 CHECK (double_bos_down_flag IN (0, 1)),
    double_bos_up_flag INTEGER NOT NULL DEFAULT 0 CHECK (double_bos_up_flag IN (0, 1)),
    fresh_bos_flag INTEGER NOT NULL DEFAULT 0 CHECK (fresh_bos_flag IN (0, 1)),
    fresh_reset_flag INTEGER NOT NULL DEFAULT 0 CHECK (fresh_reset_flag IN (0, 1)),
    stale_structure_flag INTEGER NOT NULL DEFAULT 0 CHECK (stale_structure_flag IN (0, 1)),
    layer_overheat_risk_flag INTEGER NOT NULL DEFAULT 0 CHECK (layer_overheat_risk_flag IN (0, 1)),
    subindustry_overheat_risk_flag INTEGER NOT NULL DEFAULT 0 CHECK (subindustry_overheat_risk_flag IN (0, 1)),
    severe_exit_risk_flag INTEGER NOT NULL DEFAULT 0 CHECK (severe_exit_risk_flag IN (0, 1)),
    context_readiness_status TEXT NOT NULL,
    run_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY (signal_date, taxonomy_version, ticker, horizon),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE TABLE IF NOT EXISTS dc_report_classification_v2 (
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    market TEXT NULL,
    ticker TEXT NOT NULL,
    horizon TEXT NOT NULL CHECK (horizon IN ('daily', 'rolling2', 'rolling5', 'rolling30')),
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
    classification_status TEXT NOT NULL CHECK (classification_status IN ('OK', 'SKIPPED', 'FAILED')),
    classification_version TEXT NOT NULL,
    run_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL,
    PRIMARY KEY (signal_date, taxonomy_version, ticker, horizon, classification_type),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE INDEX IF NOT EXISTS idx_dc_report_context_group_v2_date_horizon
ON dc_report_context_group_v2 (signal_date, taxonomy_version, horizon);

CREATE INDEX IF NOT EXISTS idx_dc_report_context_group_v2_group
ON dc_report_context_group_v2 (group_type, group_name, signal_date);

CREATE INDEX IF NOT EXISTS idx_dc_report_context_daily_v2_date
ON dc_report_context_daily_v2 (signal_date, taxonomy_version);

CREATE INDEX IF NOT EXISTS idx_dc_report_context_daily_v2_ticker
ON dc_report_context_daily_v2 (ticker, signal_date);

CREATE INDEX IF NOT EXISTS idx_dc_report_context_window_v2_date_horizon
ON dc_report_context_window_v2 (signal_date, taxonomy_version, horizon);

CREATE INDEX IF NOT EXISTS idx_dc_report_context_window_v2_ticker_horizon
ON dc_report_context_window_v2 (ticker, horizon, signal_date);

CREATE INDEX IF NOT EXISTS idx_dc_report_classification_v2_date_horizon
ON dc_report_classification_v2 (signal_date, taxonomy_version, horizon, classification_type);

CREATE INDEX IF NOT EXISTS idx_dc_report_classification_v2_ticker
ON dc_report_classification_v2 (ticker, signal_date);
