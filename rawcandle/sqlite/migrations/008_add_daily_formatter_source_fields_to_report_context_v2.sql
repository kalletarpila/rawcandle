ALTER TABLE dc_report_context_group_v2
ADD COLUMN return_10d REAL NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN return_20d REAL NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN return_60d REAL NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN pct_above_ema20 REAL NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN pct_above_ma10 REAL NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN ema20_breadth_delta_5d REAL NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN ma10_breadth_delta_5d REAL NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN trend_breadth REAL NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN weakness_breadth REAL NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN strength_breadth REAL NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN timing_reason TEXT NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN data_quality_status TEXT NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN synthetic_ema20 REAL NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN synthetic_volatility_20d REAL NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN synthetic_latest_structure_age_trading_days INTEGER NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN synthetic_latest_bos_event_date TEXT NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN synthetic_latest_bos_age_trading_days INTEGER NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN synthetic_latest_reset_event_date TEXT NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN synthetic_latest_reset_age_trading_days INTEGER NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN synthetic_relative_close_extension_20 REAL NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN synthetic_relative_upper_wick_20 REAL NULL;

ALTER TABLE dc_report_context_group_v2
ADD COLUMN synthetic_relative_lower_wick_20 REAL NULL;

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN ema10 REAL NULL;

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN ema20 REAL NULL;

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN volume_vs_avg20 REAL NULL;

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN latest_structure_age_trading_days INTEGER NULL;

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN latest_bos_age_trading_days INTEGER NULL;

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN latest_reset_age_trading_days INTEGER NULL;

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN latest_bullish_relevance_reason TEXT NULL;

ALTER TABLE dc_report_context_daily_v2
ADD COLUMN latest_bearish_relevance_reason TEXT NULL;
