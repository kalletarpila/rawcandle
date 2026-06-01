CREATE TABLE IF NOT EXISTS dc_report_valid_signal_date_v2 (
    run_id TEXT NOT NULL,
    signal_date TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    report_window TEXT NOT NULL CHECK (report_window IN ('daily', 'rolling2', 'rolling5', 'rolling30')),
    source_run_id TEXT NULL,
    source_signal_date TEXT NULL,
    is_valid INTEGER NOT NULL CHECK (is_valid IN (0, 1)),
    status TEXT NOT NULL,
    reason TEXT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, signal_date, taxonomy_version, report_window),
    FOREIGN KEY (run_id) REFERENCES dc_report_run_v2(run_id)
);

CREATE INDEX IF NOT EXISTS idx_dc_report_valid_signal_date_v2_date_taxonomy_window
ON dc_report_valid_signal_date_v2 (signal_date, taxonomy_version, report_window);
