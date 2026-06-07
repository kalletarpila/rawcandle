CREATE TABLE IF NOT EXISTS ec_signal_run (
    run_id TEXT PRIMARY KEY,
    ecosystem_id INTEGER NOT NULL,
    taxonomy_version_id INTEGER NULL,
    signal_date TEXT NOT NULL,
    run_type TEXT NOT NULL CHECK (run_type IN ('FULL_DAILY', 'TICKER_SIGNAL', 'GROUP_SIGNAL', 'SYNTHETIC_OHLC', 'GROUP_INDEX', 'BACKFILL', 'PARITY', 'MANUAL')),
    signal_version TEXT NULL,
    ohlc_calc_version TEXT NULL,
    source_mode TEXT NOT NULL CHECK (source_mode IN ('DC_BACKFILL', 'EC_NATIVE', 'MANUAL', 'TEST')),
    status TEXT NOT NULL CHECK (status IN ('STARTED', 'OK', 'OK_WITH_WARNINGS', 'FAILED', 'PARTIAL')),
    started_at_utc TEXT NOT NULL,
    finished_at_utc TEXT NULL,
    source_hash TEXT NULL,
    config_hash TEXT NULL,
    notes TEXT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ecosystem_id) REFERENCES ec_ecosystem (ecosystem_id),
    FOREIGN KEY (taxonomy_version_id) REFERENCES ec_taxonomy_version (taxonomy_version_id)
);

CREATE TABLE IF NOT EXISTS ec_signal_calendar (
    ecosystem_id INTEGER NOT NULL,
    signal_date TEXT NOT NULL,
    market_code TEXT NOT NULL,
    is_valid_signal_date INTEGER NOT NULL CHECK (is_valid_signal_date IN (0, 1)),
    validity_reason TEXT NULL,
    data_quality_status TEXT NOT NULL CHECK (data_quality_status IN ('OK', 'PARTIAL', 'MISSING')),
    source_run_id TEXT NULL,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ecosystem_id, signal_date),
    FOREIGN KEY (ecosystem_id) REFERENCES ec_ecosystem (ecosystem_id),
    FOREIGN KEY (source_run_id) REFERENCES ec_signal_run (run_id)
);

CREATE INDEX IF NOT EXISTS idx_ec_signal_run_ecosystem_signal_date
ON ec_signal_run (ecosystem_id, signal_date);

CREATE INDEX IF NOT EXISTS idx_ec_signal_run_ecosystem_run_type_signal_date
ON ec_signal_run (ecosystem_id, run_type, signal_date);

CREATE INDEX IF NOT EXISTS idx_ec_signal_run_status
ON ec_signal_run (status);

CREATE INDEX IF NOT EXISTS idx_ec_signal_calendar_validity
ON ec_signal_calendar (ecosystem_id, is_valid_signal_date, signal_date);
