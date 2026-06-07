CREATE TABLE IF NOT EXISTS ec_ticker_signal_daily (
    ecosystem_id INTEGER NOT NULL,
    taxonomy_version_id INTEGER NOT NULL,
    signal_date TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    signal_version TEXT NOT NULL,
    primary_group_l1_entity_id INTEGER NULL,
    primary_group_l2_entity_id INTEGER NULL,
    primary_group_l1_code TEXT NULL,
    primary_group_l2_code TEXT NULL,
    close REAL NULL,
    return_1d REAL NULL,
    return_5d REAL NULL,
    return_10d REAL NULL,
    return_20d REAL NULL,
    return_60d REAL NULL,
    distance_to_ma10_pct REAL NULL,
    distance_to_ema20_pct REAL NULL,
    distance_to_sma50_pct REAL NULL,
    distance_to_sma200_pct REAL NULL,
    ticker_trend_state TEXT NULL,
    latest_structure_label TEXT NULL,
    latest_structure_date TEXT NULL,
    latest_structure_freshness TEXT NULL,
    latest_bos_event_type TEXT NULL,
    latest_bos_date TEXT NULL,
    latest_bos_freshness TEXT NULL,
    latest_reset_reason TEXT NULL,
    latest_reset_date TEXT NULL,
    latest_reset_freshness TEXT NULL,
    breakout_signal INTEGER NULL,
    pullback_signal INTEGER NULL,
    exit_risk_signal INTEGER NULL,
    exit_risk_severity TEXT NULL,
    exit_reason TEXT NULL,
    price_data_status TEXT NULL,
    data_quality_status TEXT NULL,
    source_table TEXT NOT NULL,
    source_pk_json TEXT NOT NULL,
    source_row_hash TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ecosystem_id, taxonomy_version_id, signal_date, entity_id, signal_version),
    FOREIGN KEY (ecosystem_id) REFERENCES ec_ecosystem (ecosystem_id),
    FOREIGN KEY (taxonomy_version_id) REFERENCES ec_taxonomy_version (taxonomy_version_id),
    FOREIGN KEY (entity_id) REFERENCES ec_entity (entity_id),
    FOREIGN KEY (primary_group_l1_entity_id) REFERENCES ec_entity (entity_id),
    FOREIGN KEY (primary_group_l2_entity_id) REFERENCES ec_entity (entity_id),
    FOREIGN KEY (source_run_id) REFERENCES ec_signal_run (run_id)
);

CREATE TABLE IF NOT EXISTS ec_group_signal_daily (
    ecosystem_id INTEGER NOT NULL,
    taxonomy_version_id INTEGER NOT NULL,
    signal_date TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('ECOSYSTEM', 'GROUP_L1', 'GROUP_L2')),
    signal_version TEXT NOT NULL,
    member_count INTEGER NULL,
    eligible_count INTEGER NULL,
    valid_price_count INTEGER NULL,
    return_1d REAL NULL,
    return_5d REAL NULL,
    return_10d REAL NULL,
    return_20d REAL NULL,
    return_60d REAL NULL,
    return_120d REAL NULL,
    pct_above_ma10 REAL NULL,
    pct_above_ema20 REAL NULL,
    pct_above_sma50 REAL NULL,
    pct_above_sma200 REAL NULL,
    ma10_breadth_delta_5d REAL NULL,
    ema20_breadth_delta_5d REAL NULL,
    trend_breadth REAL NULL,
    weakness_breadth REAL NULL,
    timing_state TEXT NULL,
    timing_reason TEXT NULL,
    overheat_risk_level TEXT NULL,
    data_quality_status TEXT NULL,
    source_table TEXT NOT NULL,
    source_pk_json TEXT NOT NULL,
    source_row_hash TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ecosystem_id, taxonomy_version_id, signal_date, entity_id, signal_version),
    FOREIGN KEY (ecosystem_id) REFERENCES ec_ecosystem (ecosystem_id),
    FOREIGN KEY (taxonomy_version_id) REFERENCES ec_taxonomy_version (taxonomy_version_id),
    FOREIGN KEY (entity_id) REFERENCES ec_entity (entity_id),
    FOREIGN KEY (source_run_id) REFERENCES ec_signal_run (run_id)
);

CREATE TABLE IF NOT EXISTS ec_group_synthetic_ohlc_daily (
    ecosystem_id INTEGER NOT NULL,
    taxonomy_version_id INTEGER NOT NULL,
    signal_date TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('ECOSYSTEM', 'GROUP_L1', 'GROUP_L2')),
    ohlc_calc_version TEXT NOT NULL,
    synthetic_open REAL NULL,
    synthetic_high REAL NULL,
    synthetic_low REAL NULL,
    synthetic_close REAL NULL,
    synthetic_volume REAL NULL,
    latest_structure_label TEXT NULL,
    latest_structure_date TEXT NULL,
    structure_freshness TEXT NULL,
    latest_bos_event_type TEXT NULL,
    latest_bos_date TEXT NULL,
    bos_freshness TEXT NULL,
    latest_reset_reason TEXT NULL,
    latest_reset_date TEXT NULL,
    reset_freshness TEXT NULL,
    trend_state TEXT NULL,
    structure_state TEXT NULL,
    relative_strength_5d REAL NULL,
    relative_strength_20d REAL NULL,
    data_quality_status TEXT NULL,
    source_table TEXT NOT NULL,
    source_pk_json TEXT NOT NULL,
    source_row_hash TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ecosystem_id, taxonomy_version_id, signal_date, entity_id, ohlc_calc_version),
    FOREIGN KEY (ecosystem_id) REFERENCES ec_ecosystem (ecosystem_id),
    FOREIGN KEY (taxonomy_version_id) REFERENCES ec_taxonomy_version (taxonomy_version_id),
    FOREIGN KEY (entity_id) REFERENCES ec_entity (entity_id),
    FOREIGN KEY (source_run_id) REFERENCES ec_signal_run (run_id)
);

CREATE TABLE IF NOT EXISTS ec_group_index_daily (
    ecosystem_id INTEGER NOT NULL,
    taxonomy_version_id INTEGER NOT NULL,
    signal_date TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('ECOSYSTEM', 'GROUP_L1', 'GROUP_L2')),
    calc_version TEXT NOT NULL,
    index_value REAL NULL,
    return_1d REAL NULL,
    return_5d REAL NULL,
    return_10d REAL NULL,
    return_20d REAL NULL,
    return_60d REAL NULL,
    return_120d REAL NULL,
    volatility_20d REAL NULL,
    trend_breadth REAL NULL,
    weakness_breadth REAL NULL,
    relative_strength_20d REAL NULL,
    data_quality_status TEXT NULL,
    source_table TEXT NOT NULL,
    source_pk_json TEXT NOT NULL,
    source_row_hash TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ecosystem_id, taxonomy_version_id, signal_date, entity_id, calc_version),
    FOREIGN KEY (ecosystem_id) REFERENCES ec_ecosystem (ecosystem_id),
    FOREIGN KEY (taxonomy_version_id) REFERENCES ec_taxonomy_version (taxonomy_version_id),
    FOREIGN KEY (entity_id) REFERENCES ec_entity (entity_id),
    FOREIGN KEY (source_run_id) REFERENCES ec_signal_run (run_id)
);

CREATE TABLE IF NOT EXISTS ec_pipeline_watermark (
    ecosystem_id INTEGER NOT NULL,
    pipeline_name TEXT NOT NULL,
    source_table TEXT NOT NULL,
    latest_signal_date TEXT NULL,
    latest_run_id TEXT NULL,
    status TEXT NOT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NULL,
    PRIMARY KEY (ecosystem_id, pipeline_name, source_table),
    FOREIGN KEY (ecosystem_id) REFERENCES ec_ecosystem (ecosystem_id),
    FOREIGN KEY (latest_run_id) REFERENCES ec_signal_run (run_id)
);

CREATE INDEX IF NOT EXISTS idx_ec_ticker_signal_daily_ecosystem_signal_date
ON ec_ticker_signal_daily (ecosystem_id, signal_date);

CREATE INDEX IF NOT EXISTS idx_ec_ticker_signal_daily_entity_signal_date
ON ec_ticker_signal_daily (entity_id, signal_date);

CREATE INDEX IF NOT EXISTS idx_ec_ticker_signal_daily_ticker_signal_date
ON ec_ticker_signal_daily (ticker, signal_date);

CREATE INDEX IF NOT EXISTS idx_ec_ticker_signal_daily_source_run_id
ON ec_ticker_signal_daily (source_run_id);

CREATE INDEX IF NOT EXISTS idx_ec_group_signal_daily_ecosystem_signal_date
ON ec_group_signal_daily (ecosystem_id, signal_date);

CREATE INDEX IF NOT EXISTS idx_ec_group_signal_daily_entity_signal_date
ON ec_group_signal_daily (entity_id, signal_date);

CREATE INDEX IF NOT EXISTS idx_ec_group_signal_daily_entity_type_signal_date
ON ec_group_signal_daily (entity_type, signal_date);

CREATE INDEX IF NOT EXISTS idx_ec_group_signal_daily_source_run_id
ON ec_group_signal_daily (source_run_id);

CREATE INDEX IF NOT EXISTS idx_ec_group_synthetic_ohlc_daily_ecosystem_signal_date
ON ec_group_synthetic_ohlc_daily (ecosystem_id, signal_date);

CREATE INDEX IF NOT EXISTS idx_ec_group_synthetic_ohlc_daily_entity_signal_date
ON ec_group_synthetic_ohlc_daily (entity_id, signal_date);

CREATE INDEX IF NOT EXISTS idx_ec_group_synthetic_ohlc_daily_entity_type_signal_date
ON ec_group_synthetic_ohlc_daily (entity_type, signal_date);

CREATE INDEX IF NOT EXISTS idx_ec_group_synthetic_ohlc_daily_source_run_id
ON ec_group_synthetic_ohlc_daily (source_run_id);

CREATE INDEX IF NOT EXISTS idx_ec_group_index_daily_ecosystem_signal_date
ON ec_group_index_daily (ecosystem_id, signal_date);

CREATE INDEX IF NOT EXISTS idx_ec_group_index_daily_entity_signal_date
ON ec_group_index_daily (entity_id, signal_date);

CREATE INDEX IF NOT EXISTS idx_ec_group_index_daily_entity_type_signal_date
ON ec_group_index_daily (entity_type, signal_date);

CREATE INDEX IF NOT EXISTS idx_ec_group_index_daily_source_run_id
ON ec_group_index_daily (source_run_id);

CREATE INDEX IF NOT EXISTS idx_ec_pipeline_watermark_ecosystem_status
ON ec_pipeline_watermark (ecosystem_id, status);
