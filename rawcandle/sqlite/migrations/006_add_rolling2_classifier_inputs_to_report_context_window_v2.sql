ALTER TABLE dc_report_context_window_v2
ADD COLUMN price_data_status TEXT NULL;

ALTER TABLE dc_report_context_window_v2
ADD COLUMN exit_risk_severity TEXT NULL;

ALTER TABLE dc_report_context_window_v2
ADD COLUMN latest_bearish_relevance_class TEXT NULL;

ALTER TABLE dc_report_context_window_v2
ADD COLUMN distance_to_ema20_pct REAL NULL;

ALTER TABLE dc_report_context_window_v2
ADD COLUMN all_price_rows_missing INTEGER NOT NULL DEFAULT 0 CHECK (all_price_rows_missing IN (0, 1));
