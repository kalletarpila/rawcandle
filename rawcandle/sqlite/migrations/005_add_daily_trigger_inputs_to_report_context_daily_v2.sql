ALTER TABLE dc_report_context_daily_v2
ADD COLUMN price_data_status TEXT NULL;

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN close REAL NULL;

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN latest_bullish_relevance_class TEXT NULL;

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN latest_bearish_relevance_class TEXT NULL;

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN bullish_candle_signal INTEGER NOT NULL DEFAULT 0 CHECK (bullish_candle_signal IN (0, 1));

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN bullish_divergence_signal INTEGER NOT NULL DEFAULT 0 CHECK (bullish_divergence_signal IN (0, 1));

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN hidden_bullish_divergence_signal INTEGER NOT NULL DEFAULT 0 CHECK (hidden_bullish_divergence_signal IN (0, 1));

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN bearish_candle_signal INTEGER NOT NULL DEFAULT 0 CHECK (bearish_candle_signal IN (0, 1));

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN bearish_divergence_signal INTEGER NOT NULL DEFAULT 0 CHECK (bearish_divergence_signal IN (0, 1));

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN hidden_bearish_divergence_signal INTEGER NOT NULL DEFAULT 0 CHECK (hidden_bearish_divergence_signal IN (0, 1));
