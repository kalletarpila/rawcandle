from __future__ import annotations

import sqlite3
import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices import swing_daily_report as daily_report_module
from analysis.datacenter_indices import swing_weekly_report as weekly_report_module
from rawcandle.technical_signal_relevance import TechnicalSignalRelevanceConfig
from rawcandle.technical_signal_relevance_persistence import (
    TechnicalSignalRelevanceStoredRow,
    apply_technical_signal_relevance_migration,
    build_relevance_run_row,
    insert_relevance_records,
    insert_relevance_run,
)
from analysis.datacenter_indices.swing_weekly_report import (
    DEFAULT_WATCHLIST_FILE,
    build_markdown_weekly_swing_report,
    load_weekly_swing_report_data,
    write_weekly_swing_report,
)
from tests.test_datacenter_technical_relevance_context import (
    _connect as _connect_relevance_db,
    _insert_record as _insert_relevance_record,
    _insert_run as _insert_relevance_run,
)


WINDOW_DATES = [
    "2024-01-01",
    "2024-01-02",
    "2024-01-03",
    "2024-01-05",
    "2024-01-08",
    "2024-01-10",
]


def _create_analysis_db(path):
    DatabaseManager(str(path)).close()


def _insert_group_row(path, row):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_group_swing_signal_daily (
                signal_date, taxonomy_version, group_type, group_name,
                member_count, eligible_count, return_5d, return_10d, return_20d, return_60d,
                pct_above_ma10, pct_above_ema20, pct_above_rising_ema20,
                ma10_breadth_delta_5d, ema20_breadth_delta_5d,
                trend_breadth, weakness_breadth, overheat_risk_level,
                timing_state, timing_reason, data_quality_status,
                signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()


def _insert_ticker_row(path, row):
    values = list(row)
    if len(values) == 31:
        values[15:15] = [None, None]
        values.insert(29, None)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                close, return_5d, return_10d, return_20d, return_60d,
                ema10, ema20, volume_vs_avg20, distance_to_ema20_pct,
                latest_structure_label, latest_structure_age_trading_days, latest_structure_freshness,
                bullish_divergence_signal, bearish_divergence_signal,
                hidden_bullish_divergence_signal, hidden_bearish_divergence_signal,
                bullish_candle_signal, bearish_candle_signal,
                breakout_signal, fast_ema10_pullback_signal, conservative_ema20_pullback_signal,
                pullback_signal, exit_risk_signal, exit_reason, exit_risk_severity, price_data_status,
                signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(values),
        )
        conn.commit()


def _insert_synthetic_row(path, row):
    values = list(row)
    if len(values) == 37:
        values[21:21] = [None] * 12
    elif len(values) == 39:
        values[23:23] = [None] * 10
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_group_synthetic_ohlc_daily (
                ohlc_date, taxonomy_version, group_type, group_name,
                member_count, eligible_count, synthetic_open, synthetic_high, synthetic_low, synthetic_close,
                synthetic_volume, ma20, ema20, distance_to_ema20_pct, volatility_20d,
                pivot_radius, latest_pivot_high_date, latest_pivot_high_value, latest_pivot_low_date, latest_pivot_low_value,
                latest_structure_label, latest_structure_age_trading_days, latest_structure_freshness,
                latest_bos_event_type, latest_bos_event_date, latest_bos_confirmed_as_of_date,
                latest_bos_age_trading_days, latest_bos_freshness, latest_reset_event_date,
                latest_reset_confirmed_as_of_date, latest_reset_reason,
                latest_reset_age_trading_days, latest_reset_freshness,
                trend_classification, relative_base_window, relative_open_20, relative_high_20,
                relative_low_20, relative_close_20, relative_upper_wick_20, relative_lower_wick_20,
                relative_close_extension_20, relative_high_extension_20, relative_low_extension_20,
                relative_eligible_count, data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(values),
        )
        conn.commit()


def _update_ticker_exit_risk_severity(path, *, ticker: str, signal_date: str, severity: str | None):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET exit_risk_severity = ?
            WHERE ticker = ?
              AND signal_date = ?
            """,
            (severity, ticker, signal_date),
        )
        conn.commit()


def _seed_weekly_report_db(path):
    _create_analysis_db(path)
    ai_timing = {
        "2024-01-01": "NEUTRAL",
        "2024-01-02": "BUY_ZONE",
        "2024-01-03": "BUY_ZONE",
        "2024-01-05": "ADD_ON_PULLBACK",
        "2024-01-08": "BUY_ZONE",
        "2024-01-10": "BUY_ZONE",
    }
    storage_timing = {
        "2024-01-01": "TRIM_WATCH",
        "2024-01-02": "EXIT_ZONE",
        "2024-01-03": "EXIT_ZONE",
        "2024-01-05": "TRIM_WATCH",
        "2024-01-08": "EXIT_ZONE",
        "2024-01-10": "EXIT_ZONE",
    }
    ai_overheat = {
        "2024-01-01": "LOW",
        "2024-01-02": "LOW",
        "2024-01-03": "LOW",
        "2024-01-05": "ELEVATED",
        "2024-01-08": "HIGH",
        "2024-01-10": "HIGH",
    }
    storage_overheat = {
        "2024-01-01": "HIGH",
        "2024-01-02": "HIGH",
        "2024-01-03": "HIGH",
        "2024-01-05": "EXTREME",
        "2024-01-08": "EXTREME",
        "2024-01-10": "EXTREME",
    }
    for index, signal_date in enumerate(WINDOW_DATES):
        ecosystem_values = (
            signal_date, "DC_TAXONOMY_V1", "ecosystem", "DC_ECOSYSTEM_TOTAL",
            12, 11, 0.01 + index * 0.005, 0.02 + index * 0.01, 0.05 + index * 0.015, 0.12 + index * 0.02,
            60.0 + index, 65.0 + index * 2, 55.0, -6.0 + index, -5.0 + index,
            42.0 + index * 2, 35.0 - index * 2, "LOW" if index < 4 else "ELEVATED", "NEUTRAL",
            "NEUTRAL:no_state_rule_matched", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        )
        ai_values = (
            signal_date, "DC_TAXONOMY_V1", "subindustry", "AI Chips",
            4, 4, 0.00 + index * 0.01, 0.01 + index * 0.015, 0.05 + index * 0.02, 0.12 + index * 0.03,
            70.0 + index, 75.0 + index * 3, 60.0, -5.0 + index, -4.0 + index,
            50.0 + index * 4, 30.0 - index * 2, ai_overheat[signal_date], ai_timing[signal_date],
            f"{ai_timing[signal_date]}:seed", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        )
        storage_values = (
            signal_date, "DC_TAXONOMY_V1", "subindustry", "Storage",
            4, 3, -0.02 - index * 0.01, -0.01 - index * 0.02, 0.00 - index * 0.03, -0.05 - index * 0.04,
            45.0 - index * 2, 50.0 - index * 3, 35.0, -8.0 - index, -11.0 - index,
            30.0 - index * 3, 45.0 + index * 4, storage_overheat[signal_date], storage_timing[signal_date],
            f"{storage_timing[signal_date]}:seed", "PARTIAL_DATA" if signal_date == "2024-01-10" else "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        )
        layer_values = (
            signal_date, "DC_TAXONOMY_V1", "layer", "Infrastructure",
            8, 7, 0.00, 0.01 + index * 0.005, 0.04 + index * 0.01, 0.10 + index * 0.02,
            58.0 + index, 62.0 + index, 50.0, -4.0 + index * 0.5, -3.0 + index * 0.5,
            40.0 + index, 30.0 - index, "LOW", "NEUTRAL",
            "NEUTRAL:no_state_rule_matched", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        )
        for row in (ecosystem_values, ai_values, storage_values, layer_values):
            _insert_group_row(path, row)

        aaa_breakout = 1 if signal_date in {"2024-01-02", "2024-01-05", "2024-01-10"} else 0
        bbb_fast = 1 if signal_date in {"2024-01-03", "2024-01-10"} else 0
        bbb_cons = 1 if signal_date in {"2024-01-05", "2024-01-10"} else 0
        bbb_pullback = 1 if (bbb_fast or bbb_cons) else 0
        ccc_exit = 1 if signal_date in {"2024-01-02", "2024-01-03", "2024-01-08", "2024-01-10"} else 0
        ticker_rows = [
            (
                signal_date, "DC_TAXONOMY_V1", "AAA", "Infrastructure", "AI Chips",
                100.0 + index * 2, 0.01 + index * 0.01, 0.02 + index * 0.015, 0.05 + index * 0.02, 0.10 + index * 0.025,
                98.0 + index, 97.0 + index, 1.5 + index * 0.1, 0.03 + index * 0.005,
                "HH", 1, 0, 1, 0, 1, 0,
                aaa_breakout, 0, 0, 0, 0, None, "OK",
                "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
            ),
            (
                signal_date, "DC_TAXONOMY_V1", "BBB", "Infrastructure", "AI Chips",
                95.0 + index, -0.01 + index * 0.005, 0.01 + index * 0.01, 0.06 + index * 0.02, 0.12 + index * 0.03,
                94.0 + index, 93.0 + index, 1.1 + index * 0.05, 0.02 + index * 0.003,
                "HL", 1, 0, 1, 0, 0, 0,
                0, bbb_fast, bbb_cons, bbb_pullback, 0, None, "OK",
                "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
            ),
            (
                signal_date, "DC_TAXONOMY_V1", "CCC", "Infrastructure", "Storage",
                88.0 - index, -0.03 - index * 0.005, -0.05 - index * 0.01, -0.08 - index * 0.015, -0.10 - index * 0.02,
                90.0 - index, 92.0 - index, 0.9, -0.04 - index * 0.005,
                "LL", 0, 1, 0, 1, 0, 1,
                0, 0, 0, 0, ccc_exit, "close_below_ema20;latest_structure_label_ll" if ccc_exit else None, "MISSING_AS_OF_DATE" if signal_date == "2024-01-10" else "OK",
                "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
            ),
            (
                signal_date, "DC_TAXONOMY_V1", "DDD", "Infrastructure", "Storage",
                None if signal_date == "2024-01-10" else 80.0, None, None, None, None,
                None, None, None, None,
                None, None, None, None, None, None, None,
                None if signal_date == "2024-01-10" else 0,
                None if signal_date == "2024-01-10" else 0,
                None if signal_date == "2024-01-10" else 0,
                None if signal_date == "2024-01-10" else 0,
                None if signal_date == "2024-01-10" else 0,
                None, "MISSING_CLOSE_AS_OF_DATE" if signal_date == "2024-01-10" else "OK",
                "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
            ),
        ]
        for row in ticker_rows:
            _insert_ticker_row(path, row)

        synthetic_rows = [
            (
                signal_date, "DC_TAXONOMY_V1", "subindustry", "AI Chips",
                4, 4, 100.0, 102.0 + index, 99.0, 100.0 + index * 2,
                100000.0, 98.0 + index, 99.0 + index, 0.01 + index * 0.01, 0.10 + index * 0.01,
                5, "2024-01-01", 100.0 + index, "2024-01-01", 95.0 + index,
                "HH" if index >= 2 else "HL", 1 if index >= 2 else 0, "FRESH" if index >= 2 else "FRESH",
                "BOS_UP" if signal_date in {"2024-01-08", "2024-01-10"} else None,
                "2024-01-08" if signal_date in {"2024-01-08", "2024-01-10"} else None,
                "2024-01-08" if signal_date == "2024-01-08" else ("2024-01-08" if signal_date == "2024-01-10" else None),
                0 if signal_date == "2024-01-08" else (1 if signal_date == "2024-01-10" else None),
                "FRESH" if signal_date in {"2024-01-08", "2024-01-10"} else None,
                "2024-01-08" if signal_date in {"2024-01-08", "2024-01-10"} else None,
                "2024-01-08" if signal_date == "2024-01-08" else ("2024-01-08" if signal_date == "2024-01-10" else None),
                "DOUBLE_BOS_UP" if signal_date in {"2024-01-08", "2024-01-10"} else None,
                0 if signal_date == "2024-01-08" else (1 if signal_date == "2024-01-10" else None),
                "FRESH" if signal_date in {"2024-01-08", "2024-01-10"} else None,
                "UP" if index >= 3 else "NEUTRAL", 20, 1.01, 1.03, 0.99, 1.0 + index * 0.01, 0.02, 0.01,
                0.01 + index * 0.01, 0.02, -0.01, 4, "OK", "DC_SWING_OHLC_V1", "seed", "2026-05-17T10:00:00Z",
            ),
            (
                signal_date, "DC_TAXONOMY_V1", "layer", "Infrastructure",
                8, 7, 100.0, 101.0, 98.0, 100.0 + index,
                200000.0, 99.0, 99.5, 0.005 + index * 0.002, 0.08 + index * 0.005,
                10, "2024-01-01", 101.0, "2024-01-01", 97.0,
                "LH", 2, "FRESH",
                "BOS_DOWN" if signal_date == "2024-01-10" else None,
                "2024-01-10" if signal_date == "2024-01-10" else None,
                "2024-01-10" if signal_date == "2024-01-10" else None,
                0 if signal_date == "2024-01-10" else None,
                "FRESH" if signal_date == "2024-01-10" else None,
                None, None, None, None, None,
                "NEUTRAL", 20, None, None, None, None, None, None,
                None, None, None, 0, "PARTIAL_DATA", "DC_SWING_OHLC_V1", "seed", "2026-05-17T10:00:00Z",
            ),
        ]
        for row in synthetic_rows:
            _insert_synthetic_row(path, row)


def _seed_second_taxonomy_weekly_rows(path):
    second_dates = ["2024-01-03", "2024-01-05", "2024-01-10"]
    for index, signal_date in enumerate(second_dates):
        _insert_group_row(
            path,
            (
                signal_date, "DC_TAXONOMY_OTHER_V1", "subindustry", "Other Group",
                2, 2, 0.20 + index, 0.30 + index, 0.40 + index, 0.50 + index,
                90.0, 91.0, 89.0, -1.0, -2.0,
                80.0, 10.0, "LOW", "BUY_ZONE",
                "BUY_ZONE:seed", "OK", "DC_SWING_SIGNAL_V1", "seed2", "2026-05-17T10:00:00Z",
            ),
        )
        _insert_ticker_row(
            path,
            (
                signal_date, "DC_TAXONOMY_OTHER_V1", "ZZZ", "Other Layer", "Other Group",
                200.0, 0.05, 0.06, 0.07, 0.08,
                195.0, 196.0, 1.4, 0.02,
                "HH", 1, 0, 1, 0, 1, 0,
                None, None, None, None, None, None, "OK",
                "DC_SWING_SIGNAL_V1", "seed2", "2026-05-17T10:00:00Z",
            ),
        )
        _insert_synthetic_row(
            path,
            (
                signal_date, "DC_TAXONOMY_OTHER_V1", "subindustry", "Other Group",
                2, 2, 100.0, 101.0, 99.0, 100.5 + index,
                50000.0, 99.0, 100.0, 0.01, 0.04,
                5, None, None, None, None,
                None, None, 20, None, None,
                None, None, None, None,
                None, None, None, 0, "OK", "DC_SWING_OHLC_V1", "seed2", "2026-05-17T10:00:00Z",
            ),
        )


def test_finds_last_five_valid_signal_dates_and_generates_report(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    for signal_date in ("2024-01-02", "2024-01-03", "2024-01-08", "2024-01-10"):
        _update_ticker_exit_risk_severity(
            analysis_db,
            ticker="CCC",
            signal_date=signal_date,
            severity="HIGH",
        )

    report_data = load_weekly_swing_report_data(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
    )
    assert report_data["valid_signal_dates"] == ["2024-01-02", "2024-01-03", "2024-01-05", "2024-01-08", "2024-01-10"]

    markdown = build_markdown_weekly_swing_report(
        report_data,
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )
    for heading in [
        "# Datacenter Rolling Swing Report",
        "## 1. Title and run metadata",
        "## 2. Window summary",
        "## Watchlist Summary",
        "## 4. Ecosystem window change",
        "## 5. Overheat / rotation risk progression",
        "## 6. Subindustry timing persistence",
        "## 7. Subindustry improvement / deterioration",
        "## 8. Repeated breakout tickers",
        "## 9. Repeated pullback tickers",
        "## 10. Repeated exit-risk tickers",
        "## 11. Synthetic OHLC structure changes",
        "## 12. Group Structure Break / Reset History",
        "## 13. Data quality over the window",
        "## 14. Missing / incomplete inputs summary",
        "## Datacenter Taxonomy Listing",
    ]:
        assert heading in markdown
    assert "### A. BOS / RESET events during window" in markdown
    assert "### B. Latest BOS / RESET state at window end" in markdown
    assert "window_size: 5" in markdown
    assert "Window type: last 5 valid trading days, not calendar week" in markdown
    assert "# Datacenter Weekly Swing Report" not in markdown
    assert "### A. Best relative subindustry changes" in markdown
    assert "### B. Weakest relative subindustry changes" in markdown
    assert "### A. Most improved subindustries" not in markdown
    assert "### B. Most deteriorated subindustries" not in markdown
    assert "EXTREME RISK – TIGHTEN STOPS / NO NEW LONGS" in markdown
    assert "2024-01-02, 2024-01-03, 2024-01-05, 2024-01-08, 2024-01-10" in markdown
    assert "| AI Chips | BUY_ZONE | 4 | 1 | 0 | 0 |" in markdown
    assert "| AAA | 3 | 2024-01-02 | 2024-01-10 |" in markdown
    assert "| BBB | 3 | 2 | 2 | 2024-01-03 | 2024-01-10 |" in markdown
    assert "| CCC | 4 | 2024-01-02 | 2024-01-10 |" in markdown
    assert "close_below_ema20;latest_structure_label_ll" in markdown
    assert "last_exit_risk_severity" in markdown
    assert "last_latest_structure_age_trading_days" in markdown
    assert "last_latest_structure_freshness" in markdown
    assert "last_ticker_trend_state" in markdown
    assert "last_latest_bos_event_type" in markdown
    assert "last_latest_bos_freshness" in markdown
    assert "last_latest_reset_reason" in markdown
    assert "last_latest_reset_freshness" in markdown
    assert "first_latest_bos_event_type" in markdown
    assert "last_latest_bos_event_type" in markdown
    assert "first_latest_reset_reason" in markdown
    assert "last_latest_reset_reason" in markdown
    assert "| 2024-01-08 | subindustry | AI Chips | BOS_UP | 2024-01-08 | FRESH | DOUBLE_BOS_UP | 2024-01-08 | FRESH | HH | FRESH | UP | BUY_ZONE | HIGH |" in markdown
    assert "| layer | Infrastructure | BOS_DOWN | 2024-01-10 | FRESH |  |  |  | LH | FRESH | NEUTRAL | NEUTRAL | LOW |" in markdown
    assert "HIGH" in markdown
    assert "| 2024-01-02 | ecosystem | LOW | 1 |" in markdown
    assert "| 2024-01-02 | layer | LOW | 1 |" in markdown
    assert "| 2024-01-02 | subindustry | HIGH | 1 |" in markdown
    assert "| 2024-01-02 | subindustry | LOW | 1 |" in markdown
    assert "### Layer: Infrastructure" in markdown
    assert "| row_type | layer | subindustry | ticker | current_status | window_status |" in markdown
    assert "last_trend_state" in markdown
    assert "| LAYER | Infrastructure |  |  |" in markdown
    assert "| SUBINDUSTRY | Infrastructure | AI Chips |  |" in markdown
    assert "| TICKER | Infrastructure | AI Chips | AAA |" in markdown


def test_rolling_watchlist_summary_renders_counts_outside_ticker_and_last_group_context(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    watchlist_file = tmp_path / "watchlist.txt"
    _seed_weekly_report_db(analysis_db)
    watchlist_file.write_text("aaa\nbbb\nccc\noutside\n", encoding="utf-8")
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET exit_risk_signal = 1,
                exit_reason = 'subindustry_exit_zone',
                exit_risk_severity = 'HIGH'
            WHERE ticker = 'BBB'
              AND signal_date = '2024-01-10'
            """
        )
        for signal_date in ("2024-01-02", "2024-01-03", "2024-01-08", "2024-01-10"):
            conn.execute(
                """
                UPDATE dc_ticker_swing_signal_daily
                SET exit_risk_severity = 'HIGH'
                WHERE ticker = 'CCC'
                  AND signal_date = ?
                """,
                (signal_date,),
            )
        conn.commit()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        watchlist_file=watchlist_file,
        generated_at_utc="2026-05-17T12:00:00Z",
    )
    markdown = result["markdown"]

    assert "## Watchlist Summary" in markdown
    assert markdown.index("## Watchlist Summary") < markdown.index("## 4. Ecosystem window change")
    assert "| watchlist_tickers_total | 4 |" in markdown
    assert "| watchlist_in_datacenter_taxonomy | 3 |" in markdown
    assert "| watchlist_not_in_datacenter_taxonomy | 1 |" in markdown
    assert "| watchlist_missing_price_end_date | 1 |" in markdown
    assert "| watchlist_subindustry_context_risk_count | 3 |" in markdown
    assert "| watchlist_layer_context_risk_count | 0 |" in markdown
    assert "| watchlist_both_context_risk_count | 0 |" in markdown
    assert "| watchlist_with_breakout_days | 1 |" in markdown
    assert "| watchlist_with_pullback_days | 1 |" in markdown
    assert "| watchlist_with_exit_risk_days | 2 |" in markdown
    assert "| watchlist_with_high_exit_risk_days | 2 |" in markdown
    assert "current_watchlist_status" in markdown
    assert "window_watchlist_status" in markdown
    assert "subindustry_context_risk" in markdown
    assert "layer_context_risk" in markdown
    assert "last_subindustry_trend_classification" in markdown
    assert "last_subindustry_latest_structure_label" in markdown
    assert "last_layer_trend_classification" in markdown
    assert "last_layer_latest_structure_label" in markdown
    assert "| OUTSIDE | NOT_PART_OF_DATACENTER_ECOSYSTEM | NOT_PART_OF_DATACENTER_ECOSYSTEM |  |  |  |  |  |  | NO |" in markdown
    assert "| AAA | BREAKOUT_CANDIDATE | BREAKOUT_CANDIDATE | YES | NO | UP | HH | NEUTRAL | LH | YES | Infrastructure | AI Chips | 2024-01-02 | 2024-01-10 | 110 | 3 | 0 | 0 | 0 | 0 |  |  |  | HH |  |  |  |  |  | BUY_ZONE | HIGH | NEUTRAL | LOW | OK |" in markdown
    assert "| BBB | HIGH_EXIT_RISK | HIGH_EXIT_RISK | YES | NO | UP | HH | NEUTRAL | LH | YES | Infrastructure | AI Chips | 2024-01-02 | 2024-01-10 | 100 | 0 | 3 | 1 | 1 | 0 | HIGH | subindustry_exit_zone |  | HL |  |  |  |  |  | BUY_ZONE | HIGH | NEUTRAL | LOW | OK |" in markdown
    assert "| CCC | MISSING_PRICE | MISSING_PRICE | YES | NO |  |  | NEUTRAL | LH | YES | Infrastructure | Storage | 2024-01-02 | 2024-01-10 | 83 | 0 | 0 | 4 | 4 | 0 | HIGH | close_below_ema20;latest_structure_label_ll |  | LL |  |  |  |  |  | EXIT_ZONE | EXTREME | NEUTRAL | LOW | MISSING_AS_OF_DATE |" in markdown


def test_rolling_watchlist_distinguishes_current_group_risk_from_prior_high_exit_risk(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    watchlist_file = tmp_path / "watchlist.txt"
    _seed_weekly_report_db(analysis_db)
    watchlist_file.write_text("AAA\n", encoding="utf-8")
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET exit_risk_signal = 1,
                exit_risk_severity = 'HIGH',
                exit_reason = 'subindustry_exit_zone'
            WHERE ticker = 'AAA'
              AND signal_date = '2024-01-08'
            """
        )
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET breakout_signal = 0
            WHERE ticker = 'AAA'
              AND signal_date = '2024-01-10'
            """
        )
        conn.commit()

    markdown = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        watchlist_file=watchlist_file,
        generated_at_utc="2026-05-17T12:00:00Z",
    )["markdown"]

    assert "| AAA | GROUP_RISK | HIGH_EXIT_RISK | YES | NO | UP | HH | NEUTRAL | LH | YES |" in markdown


def test_rolling_watchlist_distinguishes_current_neutral_from_prior_pullback_days(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    watchlist_file = tmp_path / "watchlist.txt"
    _seed_weekly_report_db(analysis_db)
    watchlist_file.write_text("BBB\n", encoding="utf-8")
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET primary_subindustry = 'Cloud'
            WHERE ticker = 'BBB'
              AND signal_date = '2024-01-10'
            """
        )
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET fast_ema10_pullback_signal = 0,
                conservative_ema20_pullback_signal = 0,
                pullback_signal = 0,
                exit_risk_signal = 0,
                exit_risk_severity = NULL,
                exit_reason = NULL
            WHERE ticker = 'BBB'
              AND signal_date = '2024-01-10'
            """
        )
        conn.commit()

    markdown = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        watchlist_file=watchlist_file,
        generated_at_utc="2026-05-17T12:00:00Z",
    )["markdown"]

    assert "| BBB | NEUTRAL_MONITOR | PULLBACK_CANDIDATE | NO | NO |  |  | NEUTRAL | LH | YES |" in markdown


def test_rolling_watchlist_context_risk_fields_show_subindustry_layer_or_both(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    watchlist_file = tmp_path / "watchlist.txt"
    _seed_weekly_report_db(analysis_db)
    watchlist_file.write_text("AAA\nBBB\nCCC\n", encoding="utf-8")
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET breakout_signal = 0,
                fast_ema10_pullback_signal = 0,
                conservative_ema20_pullback_signal = 0,
                pullback_signal = 0,
                exit_risk_signal = 0,
                exit_risk_severity = NULL,
                exit_reason = NULL
            WHERE ticker = 'AAA'
            """
        )
        conn.execute(
            """
            UPDATE dc_group_swing_signal_daily
            SET timing_state = 'TRIM_WATCH',
                overheat_risk_level = 'HIGH'
            WHERE signal_date = '2024-01-10'
              AND taxonomy_version = 'DC_TAXONOMY_V1'
              AND group_type = 'layer'
              AND group_name = 'Infrastructure'
            """
        )
        conn.commit()

    markdown = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        watchlist_file=watchlist_file,
        generated_at_utc="2026-05-17T12:00:00Z",
    )["markdown"]

    assert "| watchlist_subindustry_context_risk_count | 3 |" in markdown
    assert "| watchlist_layer_context_risk_count | 3 |" in markdown
    assert "| watchlist_both_context_risk_count | 3 |" in markdown
    assert "| AAA | GROUP_RISK | GROUP_RISK | YES | YES | UP | HH | NEUTRAL | LH | YES |" in markdown
    assert "| BBB | PULLBACK_CANDIDATE | PULLBACK_CANDIDATE | YES | YES | UP | HH | NEUTRAL | LH | YES |" in markdown
    assert "| CCC | MISSING_PRICE | MISSING_PRICE | YES | YES |  |  | NEUTRAL | LH | YES |" in markdown


def test_weekly_overheat_progression_groups_by_group_type_and_orders_deterministically(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)

    markdown = build_markdown_weekly_swing_report(
        load_weekly_swing_report_data(
            analysis_db_path=analysis_db,
            end_date="2024-01-10",
        ),
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )
    section_start = markdown.index("## 5. Overheat / rotation risk progression")
    next_section = markdown.index("Worsened groups")
    section = markdown[section_start:next_section]
    assert "| 2024-01-10 | ecosystem | ELEVATED | 1 |" in section
    assert "| 2024-01-10 | layer | LOW | 1 |" in section
    assert "| 2024-01-10 | subindustry | EXTREME | 1 |" in section
    assert "| 2024-01-10 | subindustry | HIGH | 1 |" in section
    assert "| 2024-01-10 |  |" not in section

    ecosystem_index = section.index("| 2024-01-10 | ecosystem | ELEVATED | 1 |")
    layer_index = section.index("| 2024-01-10 | layer | LOW | 1 |")
    subindustry_extreme_index = section.index("| 2024-01-10 | subindustry | EXTREME | 1 |")
    subindustry_high_index = section.index("| 2024-01-10 | subindustry | HIGH | 1 |")
    assert ecosystem_index < layer_index < subindustry_extreme_index < subindustry_high_index


def test_weekly_overheat_progression_renders_null_status_deterministically(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_group_swing_signal_daily
            SET overheat_risk_level = NULL
            WHERE signal_date = '2024-01-10'
              AND taxonomy_version = 'DC_TAXONOMY_V1'
              AND group_type = 'layer'
              AND group_name = 'Infrastructure'
            """
        )
        conn.commit()

    markdown = build_markdown_weekly_swing_report(
        load_weekly_swing_report_data(
            analysis_db_path=analysis_db,
            end_date="2024-01-10",
        ),
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )
    section_start = markdown.index("## 5. Overheat / rotation risk progression")
    next_section = markdown.index("Worsened groups")
    section = markdown[section_start:next_section]
    assert "| 2024-01-10 | layer | NULL | 1 |" in section


def test_weekly_group_structure_break_reset_section_ignores_carried_forward_context(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)

    markdown = build_markdown_weekly_swing_report(
        load_weekly_swing_report_data(
            analysis_db_path=analysis_db,
            end_date="2024-01-10",
        ),
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )
    section_start = markdown.index("### A. BOS / RESET events during window")
    next_section = markdown.index("### B. Latest BOS / RESET state at window end")
    section = markdown[section_start:next_section]
    assert "| 2024-01-08 | subindustry | AI Chips | BOS_UP | 2024-01-08 |" in section
    assert "| 2024-01-10 | subindustry | AI Chips | BOS_UP | 2024-01-08 |" not in section


def test_weekly_group_structure_break_reset_section_renders_no_rows_when_absent(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_group_synthetic_ohlc_daily
            SET latest_bos_event_type = NULL,
                latest_bos_event_date = NULL,
                latest_bos_confirmed_as_of_date = NULL,
                latest_bos_age_trading_days = NULL,
                latest_bos_freshness = NULL,
                latest_reset_event_date = NULL,
                latest_reset_confirmed_as_of_date = NULL,
                latest_reset_reason = NULL,
                latest_reset_age_trading_days = NULL,
                latest_reset_freshness = NULL
            """
        )
        conn.commit()

    markdown = build_markdown_weekly_swing_report(
        load_weekly_swing_report_data(
            analysis_db_path=analysis_db,
            end_date="2024-01-10",
        ),
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )
    heading = markdown.index("## 12. Group Structure Break / Reset History")
    next_heading = markdown.index("## 13. Data quality over the window")
    section = markdown[heading:next_heading]
    assert section.count("No rows.") == 2


def test_weekly_report_uses_default_watchlist_path_and_missing_file_is_non_fatal(tmp_path, monkeypatch):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    missing_watchlist = tmp_path / "missing_watchlist.txt"
    monkeypatch.setattr(daily_report_module, "DEFAULT_WATCHLIST_FILE", str(missing_watchlist))
    monkeypatch.setattr(weekly_report_module, "DEFAULT_WATCHLIST_FILE", str(missing_watchlist))

    report_data = load_weekly_swing_report_data(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
    )
    markdown = build_markdown_weekly_swing_report(
        report_data,
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )

    assert report_data["watchlist_file_path"] == str(missing_watchlist)
    assert report_data["watchlist_file_missing"] is True
    assert "## Watchlist Summary" in markdown
    assert "| watchlist_tickers_total | 0 |" in markdown
    assert f"No watchlist file found: {missing_watchlist}" in markdown


def test_weekly_report_can_omit_taxonomy_listing(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)

    markdown = build_markdown_weekly_swing_report(
        load_weekly_swing_report_data(
            analysis_db_path=analysis_db,
            end_date="2024-01-10",
        ),
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
        include_taxonomy_listing=False,
    )

    assert "## Datacenter Taxonomy Listing" not in markdown


def test_weekly_taxonomy_listing_uses_last_available_row_per_ticker(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)

    markdown = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
    )["markdown"]

    section = markdown[markdown.index("## Datacenter Taxonomy Listing") :]
    assert "### Layer: Infrastructure" in section
    assert "row_type" in section
    assert "current_status" in section
    assert "window_status" in section
    assert "subindustry_context_risk" in section
    assert "layer_context_risk" in section
    assert "exit_risk_days" in section
    assert "last_price_data_status" in section
    assert "| LAYER | Infrastructure |  |  |" in section
    assert "| SUBINDUSTRY | Infrastructure | AI Chips |  |" in section
    assert "| SUBINDUSTRY | Infrastructure | Storage |  |" in section
    assert section.count("| TICKER | Infrastructure | AI Chips | AAA |") == 1
    assert section.count("| TICKER | Infrastructure | AI Chips | BBB |") == 1
    assert section.count("| TICKER | Infrastructure | Storage | CCC |") == 1
    assert section.count("| TICKER | Infrastructure | Storage | DDD |") == 1
    assert "| ZZZ |" not in section
    assert section.index("| LAYER | Infrastructure |") < section.index("| SUBINDUSTRY | Infrastructure | AI Chips |") < section.index("| TICKER | Infrastructure | AI Chips | AAA |")


def test_weekly_exit_risk_section_sorts_by_severity_after_day_count(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        for signal_date in ("2024-01-02", "2024-01-03", "2024-01-08", "2024-01-10"):
            conn.execute(
                """
                UPDATE dc_ticker_swing_signal_daily
                SET exit_risk_severity = 'HIGH'
                WHERE ticker = 'CCC'
                  AND signal_date = ?
                """,
                (signal_date,),
            )
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET exit_risk_signal = 1,
                exit_reason = 'subindustry_exit_zone',
                exit_risk_severity = 'MEDIUM'
            WHERE ticker = 'AAA'
              AND signal_date IN ('2024-01-08', '2024-01-10')
            """
        )
        conn.commit()

    markdown = build_markdown_weekly_swing_report(
        load_weekly_swing_report_data(
            analysis_db_path=analysis_db,
            end_date="2024-01-10",
        ),
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )
    ccc_index = markdown.index("| CCC | 4 | 2024-01-02 | 2024-01-10 |")
    aaa_index = markdown.index("| AAA | 2 | 2024-01-08 | 2024-01-10 |")
    assert ccc_index < aaa_index


def test_marks_incomplete_window_when_fewer_than_five_valid_dates_exist(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)

    report_data = load_weekly_swing_report_data(
        analysis_db_path=analysis_db,
        end_date="2024-01-03",
    )
    assert report_data["valid_signal_dates"] == ["2024-01-01", "2024-01-02", "2024-01-03"]

    markdown = build_markdown_weekly_swing_report(
        report_data,
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )
    assert "INCOMPLETE WINDOW – FEWER THAN 5 VALID SIGNAL DATES" in markdown
    assert "incomplete_window | YES" in markdown or "YES" in markdown


def test_supports_custom_window_size_and_selected_dates(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)

    report_data = load_weekly_swing_report_data(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        window_size=3,
    )
    assert report_data["valid_signal_dates"] == ["2024-01-05", "2024-01-08", "2024-01-10"]

    markdown = build_markdown_weekly_swing_report(
        report_data,
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )
    assert "window_size: 3" in markdown
    assert "Window type: last 3 valid trading days, not calendar week" in markdown
    assert "2024-01-05, 2024-01-08, 2024-01-10" in markdown
    assert "| AAA | 2 | 2024-01-05 | 2024-01-10 |" in markdown
    assert "| BBB | 2 | 1 | 2 | 2024-01-05 | 2024-01-10 |" in markdown
    assert "| CCC | 2 | 2024-01-08 | 2024-01-10 |" in markdown


def test_rolling_30_role_sections_and_summary_render_for_window_size_30(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET ticker_trend_state = 'NEUTRAL'
            WHERE ticker = 'BBB'
            """
        )
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET exit_risk_severity = 'HIGH'
            WHERE ticker = 'CCC'
              AND exit_risk_signal = 1
            """
        )
        conn.commit()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=30,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    markdown = result["markdown"]
    csv_text = result["csv"]
    summary = result["summary"]

    assert "## Rolling 30 Buy Filter" in markdown
    assert "## Rolling 30 Exit Prefilter" in markdown
    assert "section;rolling_30_buy_filter" in csv_text
    assert "section;rolling_30_exit_prefilter" in csv_text
    assert "rolling_30_buy_filter;AAA;BUY_ZONE;" in csv_text
    assert "rolling_30_buy_filter;BBB;BUY_ZONE;" in csv_text
    assert "rolling_30_buy_filter;CCC;INSUFFICIENT_DATA;" in csv_text
    assert "rolling_30_buy_filter;DDD;INSUFFICIENT_DATA;" in csv_text
    assert "rolling_30_exit_prefilter;CCC;INSUFFICIENT_DATA;" in csv_text
    assert "rolling_30_exit_prefilter;DDD;INSUFFICIENT_DATA;" in csv_text
    assert "| AAA | BUY_ZONE |" in markdown
    assert "| BBB | BUY_ZONE |" in markdown
    assert "| CCC | INSUFFICIENT_DATA |" in markdown
    assert summary["rolling_30_buy_zone_count"] == 2
    assert summary["rolling_30_watch_zone_count"] == 0
    assert summary["rolling_30_avoid_count"] == 0
    assert summary["rolling_30_buy_filter_insufficient_data_count"] == 2
    assert summary["rolling_30_extreme_count"] == 0
    assert summary["rolling_30_exit_prefilter_insufficient_data_count"] == 2


def test_rolling_30_role_fixture_can_produce_avoid_and_extreme(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET breakout_signal = 0,
                exit_risk_signal = 1,
                exit_risk_severity = 'CRITICAL',
                exit_reason = 'distribution_pressure'
            WHERE ticker = 'AAA'
              AND signal_date IN ('2024-01-05', '2024-01-08', '2024-01-10')
            """
        )
        conn.commit()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=30,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    assert "rolling_30_buy_filter;AAA;AVOID;" in result["csv"]
    assert "rolling_30_exit_prefilter;AAA;EXTREME;" in result["csv"]


def test_rolling_30_exit_risk_days_without_severity_maps_to_watch_not_extreme_or_buy_avoid(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET ticker_trend_state = 'NEUTRAL',
                exit_risk_signal = 1,
                exit_risk_severity = NULL,
                exit_reason = NULL
            WHERE ticker = 'AAA'
              AND signal_date IN ('2024-01-08', '2024-01-10')
            """
        )
        conn.commit()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=30,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    assert "rolling_30_buy_filter;AAA;WATCH_ZONE;" in result["csv"]
    assert "rolling_30_exit_prefilter;AAA;WATCH;" in result["csv"]


def test_rolling_30_stale_reset_and_bos_up_do_not_force_avoid_or_extreme(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET latest_bos_event_type = 'BOS_UP',
                latest_bos_event_date = '2024-01-10',
                latest_bos_confirmed_as_of_date = '2024-01-10',
                latest_bos_age_trading_days = 3,
                latest_bos_freshness = 'AGING',
                latest_reset_reason = 'DOUBLE_BOS_UP',
                latest_reset_event_date = '2024-01-10',
                latest_reset_confirmed_as_of_date = '2024-01-10',
                latest_reset_age_trading_days = 5,
                latest_reset_freshness = 'STALE'
            WHERE ticker = 'AAA'
              AND signal_date = '2024-01-10'
            """
        )
        conn.commit()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=30,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    assert "rolling_30_buy_filter;AAA;BUY_ZONE;" in result["csv"]
    assert "rolling_30_exit_prefilter;AAA;WATCH;" in result["csv"]


def test_rolling_30_fresh_bos_down_forces_avoid_and_exit_zone(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET latest_bos_event_type = 'BOS_DOWN',
                latest_bos_event_date = '2024-01-10',
                latest_bos_confirmed_as_of_date = '2024-01-10',
                latest_bos_age_trading_days = 0,
                latest_bos_freshness = 'FRESH',
                latest_reset_reason = NULL,
                latest_reset_event_date = NULL,
                latest_reset_confirmed_as_of_date = NULL,
                latest_reset_age_trading_days = NULL,
                latest_reset_freshness = NULL
            WHERE ticker = 'AAA'
              AND signal_date = '2024-01-10'
            """
        )
        conn.commit()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=30,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    assert "rolling_30_buy_filter;AAA;AVOID;" in result["csv"]
    assert "rolling_30_exit_prefilter;AAA;EXIT_ZONE;" in result["csv"]


def test_rolling_30_explicit_high_exit_risk_status_forces_avoid_and_exit_zone(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET exit_risk_signal = 1,
                exit_risk_severity = 'HIGH',
                exit_reason = 'distribution_pressure'
            WHERE ticker = 'AAA'
              AND signal_date = '2024-01-10'
            """
        )
        conn.commit()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=30,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    assert "rolling_30_buy_filter;AAA;AVOID;" in result["csv"]
    assert "rolling_30_exit_prefilter;AAA;EXIT_ZONE;" in result["csv"]
    assert "CURRENT_HIGH_EXIT_RISK" in result["csv"]


def test_rolling_30_historical_window_high_exit_risk_reason_is_precise(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET breakout_signal = 1,
                exit_risk_signal = 1,
                exit_risk_severity = 'HIGH',
                exit_reason = 'distribution_pressure',
                ticker_trend_state = 'UP'
            WHERE ticker = 'AAA'
              AND signal_date = '2024-01-08'
            """
        )
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET breakout_signal = 1,
                pullback_signal = 0,
                exit_risk_signal = 0,
                exit_risk_severity = NULL,
                exit_reason = NULL,
                ticker_trend_state = 'UP'
            WHERE ticker = 'AAA'
              AND signal_date = '2024-01-10'
            """
        )
        conn.commit()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=30,
        generated_at_utc="2026-05-24T12:00:00Z",
    )

    assert "rolling_30_buy_filter;AAA;WATCH_ZONE;" in result["csv"]
    assert "rolling_30_exit_prefilter;AAA;WATCH;" in result["csv"]
    assert "HISTORICAL_WINDOW_HIGH_EXIT_RISK" in result["csv"]
    assert ";WINDOW_HIGH_EXIT_RISK;" not in result["csv"]


def test_rolling_30_role_sections_do_not_render_for_non_30_windows(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)

    result_5 = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=5,
        generated_at_utc="2026-05-17T12:00:00Z",
    )
    result_2 = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=2,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    for result in (result_5, result_2):
        assert "Rolling 30 Buy Filter" not in result["markdown"]
        assert "Rolling 30 Exit Prefilter" not in result["markdown"]
        assert "section;rolling_30_buy_filter" not in result["csv"]
        assert "section;rolling_30_exit_prefilter" not in result["csv"]
        assert "rolling_30_buy_zone_count" not in result["summary"]
        assert "rolling_30_exit_zone_count" not in result["summary"]


def test_rolling_5_pullback_alert_section_and_summary_render_for_window_size_5(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=5,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    markdown = result["markdown"]
    csv_text = result["csv"]
    summary = result["summary"]

    assert "## Rolling 5 Pullback Alerts" in markdown
    assert "section;rolling_5_pullback_alerts" in csv_text
    assert "rolling_5_pullback_alerts;BBB;PULLBACK_CANDIDATE;" in csv_text
    assert "rolling_5_pullback_alerts;AAA;NO_PULLBACK;" in csv_text
    assert "rolling_5_pullback_alerts;CCC;INSUFFICIENT_DATA;" in csv_text
    assert "rolling_5_pullback_alerts;DDD;INSUFFICIENT_DATA;" in csv_text
    assert "| BBB | PULLBACK_CANDIDATE |" in markdown
    assert "| AAA | NO_PULLBACK |" in markdown
    assert summary["rolling_5_pullback_candidate_count"] == 1
    assert summary["rolling_5_early_pullback_count"] == 0
    assert summary["rolling_5_failed_pullback_count"] == 0
    assert summary["rolling_5_short_term_breakdown_count"] == 0
    assert summary["rolling_5_no_pullback_count"] == 1
    assert summary["rolling_5_insufficient_data_count"] == 2


def test_rolling_5_pullback_fixture_can_produce_early_pullback(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET exit_risk_signal = 1,
                exit_risk_severity = NULL,
                exit_reason = NULL
            WHERE ticker = 'BBB'
              AND signal_date = '2024-01-10'
            """
        )
        conn.commit()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=5,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    assert "rolling_5_pullback_alerts;BBB;EARLY_PULLBACK;" in result["csv"]


def test_rolling_5_pullback_fixture_can_produce_failed_pullback(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET latest_bos_event_type = 'BOS_DOWN',
                latest_bos_event_date = '2024-01-10',
                latest_bos_confirmed_as_of_date = '2024-01-10',
                latest_bos_age_trading_days = 0,
                latest_bos_freshness = 'FRESH'
            WHERE ticker = 'BBB'
              AND signal_date = '2024-01-10'
            """
        )
        conn.commit()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=5,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    assert "rolling_5_pullback_alerts;BBB;FAILED_PULLBACK;" in result["csv"]


def test_rolling_5_no_pullback_with_window_high_exit_risk_stays_no_pullback(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET exit_risk_signal = 1,
                exit_risk_severity = 'HIGH',
                exit_reason = 'window_high_exit_risk'
            WHERE ticker = 'AAA'
              AND signal_date = '2024-01-08'
            """
        )
        conn.commit()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=5,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    assert "rolling_5_pullback_alerts;AAA;NO_PULLBACK;" in result["csv"]


def test_rolling_5_no_pullback_with_relevant_bearish_context_alone_stays_no_pullback(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    conn = _connect_relevance_db(analysis_db)
    apply_technical_signal_relevance_migration(conn)
    insert_relevance_run(
        conn,
        build_relevance_run_row(
            run_id="REL_ROLLING_5_BEARISH",
            config=TechnicalSignalRelevanceConfig(),
            created_at_utc="2026-05-17T12:00:00Z",
        ),
    )
    insert_relevance_records(
        conn,
        [
            TechnicalSignalRelevanceStoredRow(
                ticker="AAA",
                timeframe="1d",
                signal_date="2024-01-10",
                signal_confirmed_as_of_date="2024-01-10",
                signal_name="Bearish",
                signal_close_price=110.0,
                signal_direction="BEARISH",
                signal_family="REVERSAL_MEDIUM",
                signal_source_type="CANDLE",
                signal_source_id="CANDLE",
                dow_trend_state="UP",
                dow_context_state="NORMAL",
                latest_bos_direction="BOS_UP",
                bars_since_latest_bos=2,
                latest_reset_reason=None,
                bars_since_latest_reset=None,
                near_latest_pivot=0,
                near_active_bos_level=0,
                is_trend_aligned=0,
                is_counter_trend=1,
                relevance_class="RELEVANT",
                relevance_reason="BEARISH_CONTEXT",
                relevance_rule_version="TECH_SIGNAL_RELEVANCE_V1",
                mapping_version="TECH_SIGNAL_MAPPING_V1",
                reason_version="TECH_SIGNAL_RELEVANCE_REASON_V1",
                rule_trace='[]',
                created_at_utc="2026-05-17T12:00:00Z",
                run_id="REL_ROLLING_5_BEARISH",
            )
        ],
    )
    conn.commit()
    conn.close()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=5,
        generated_at_utc="2026-05-17T12:00:00Z",
        technical_relevance_run_id="REL_ROLLING_5_BEARISH",
    )

    assert "rolling_5_pullback_alerts;AAA;NO_PULLBACK;" in result["csv"]


def test_rolling_5_no_pullback_with_fresh_bos_down_becomes_short_term_breakdown(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET latest_bos_event_type = 'BOS_DOWN',
                latest_bos_event_date = '2024-01-10',
                latest_bos_confirmed_as_of_date = '2024-01-10',
                latest_bos_age_trading_days = 0,
                latest_bos_freshness = 'FRESH'
            WHERE ticker = 'AAA'
              AND signal_date = '2024-01-10'
            """
        )
        conn.commit()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=5,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    assert "rolling_5_pullback_alerts;AAA;SHORT_TERM_BREAKDOWN;" in result["csv"]
    assert "SHORT_TERM_BREAKDOWN_WITHOUT_PULLBACK_SETUP" in result["csv"]


def test_rolling_5_no_pullback_with_fresh_reset_plus_negative_context_becomes_short_term_breakdown(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET latest_reset_reason = 'DOUBLE_BOS_DOWN',
                latest_reset_event_date = '2024-01-10',
                latest_reset_confirmed_as_of_date = '2024-01-10',
                latest_reset_age_trading_days = 0,
                latest_reset_freshness = 'FRESH',
                ticker_trend_state = 'DOWN',
                exit_risk_signal = 1,
                exit_risk_severity = 'HIGH',
                exit_reason = 'trend_break'
            WHERE ticker = 'AAA'
              AND signal_date = '2024-01-10'
            """
        )
        conn.commit()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=5,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    assert "rolling_5_pullback_alerts;AAA;SHORT_TERM_BREAKDOWN;" in result["csv"]


def test_rolling_5_no_pullback_with_critical_severity_becomes_short_term_breakdown(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET exit_risk_signal = 1,
                exit_risk_severity = 'CRITICAL',
                exit_reason = 'critical_break'
            WHERE ticker = 'AAA'
              AND signal_date = '2024-01-10'
            """
        )
        conn.commit()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=5,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    assert "rolling_5_pullback_alerts;AAA;SHORT_TERM_BREAKDOWN;" in result["csv"]


def test_rolling_5_pullback_with_relevant_bearish_context_fails_pullback(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    conn = _connect_relevance_db(analysis_db)
    apply_technical_signal_relevance_migration(conn)
    insert_relevance_run(
        conn,
        build_relevance_run_row(
            run_id="REL_ROLLING_5_PULLBACK_BEARISH",
            config=TechnicalSignalRelevanceConfig(),
            created_at_utc="2026-05-17T12:00:00Z",
        ),
    )
    insert_relevance_records(
        conn,
        [
            TechnicalSignalRelevanceStoredRow(
                ticker="BBB",
                timeframe="1d",
                signal_date="2024-01-10",
                signal_confirmed_as_of_date="2024-01-10",
                signal_name="Bearish Engulfing",
                signal_close_price=100.0,
                signal_direction="BEARISH",
                signal_family="REVERSAL_MEDIUM",
                signal_source_type="CANDLE",
                signal_source_id="CANDLE",
                dow_trend_state="UP",
                dow_context_state="NORMAL",
                latest_bos_direction="BOS_UP",
                bars_since_latest_bos=2,
                latest_reset_reason=None,
                bars_since_latest_reset=None,
                near_latest_pivot=0,
                near_active_bos_level=0,
                is_trend_aligned=0,
                is_counter_trend=1,
                relevance_class="RELEVANT",
                relevance_reason="BEARISH_CONTEXT",
                relevance_rule_version="TECH_SIGNAL_RELEVANCE_V1",
                mapping_version="TECH_SIGNAL_MAPPING_V1",
                reason_version="TECH_SIGNAL_RELEVANCE_REASON_V1",
                rule_trace='[]',
                created_at_utc="2026-05-17T12:00:00Z",
                run_id="REL_ROLLING_5_PULLBACK_BEARISH",
            )
        ],
    )
    conn.commit()
    conn.close()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=5,
        generated_at_utc="2026-05-17T12:00:00Z",
        technical_relevance_run_id="REL_ROLLING_5_PULLBACK_BEARISH",
    )

    assert "rolling_5_pullback_alerts;BBB;FAILED_PULLBACK;" in result["csv"]


def test_rolling_5_pullback_with_mild_exit_risk_stays_early_pullback(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET exit_risk_signal = 1,
                exit_risk_severity = NULL,
                exit_reason = NULL
            WHERE ticker = 'BBB'
              AND signal_date = '2024-01-10'
            """
        )
        conn.commit()

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=5,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    assert "rolling_5_pullback_alerts;BBB;EARLY_PULLBACK;" in result["csv"]


def test_rolling_5_pullback_sections_do_not_render_for_non_5_windows(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)

    result_30 = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=30,
        generated_at_utc="2026-05-17T12:00:00Z",
    )
    result_2 = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        window_size=2,
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    for result in (result_30, result_2):
        assert "Rolling 5 Pullback Alerts" not in result["markdown"]
        assert "section;rolling_5_pullback_alerts" not in result["csv"]
        assert "rolling_5_pullback_candidate_count" not in result["summary"]
        assert "rolling_5_failed_pullback_count" not in result["summary"]
        assert "rolling_5_short_term_breakdown_count" not in result["summary"]


def test_custom_window_size_marks_incomplete_when_fewer_than_requested_dates_exist(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)

    report_data = load_weekly_swing_report_data(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        window_size=10,
    )
    assert report_data["valid_signal_dates"] == WINDOW_DATES

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        window_size=10,
        generated_at_utc="2026-05-17T12:00:00Z",
    )
    assert result["summary"]["window_size"] == 10
    assert result["summary"]["valid_signal_dates_count"] == 6
    assert result["summary"]["incomplete_window"] == "YES"


def test_weekly_report_is_read_only(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)

    with sqlite3.connect(analysis_db) as conn:
        before_counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "dc_group_swing_signal_daily",
                "dc_ticker_swing_signal_daily",
                "dc_group_synthetic_ohlc_daily",
            )
        }

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
    )
    assert result["summary"]["validation_status"] == "OK"

    with sqlite3.connect(analysis_db) as conn:
        after_counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "dc_group_swing_signal_daily",
                "dc_ticker_swing_signal_daily",
                "dc_group_synthetic_ohlc_daily",
            )
        }
    assert before_counts == after_counts


def test_weekly_report_scopes_to_selected_taxonomy_version(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    _seed_second_taxonomy_weekly_rows(analysis_db)

    report_data = load_weekly_swing_report_data(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
    )
    markdown = build_markdown_weekly_swing_report(
        report_data,
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )

    assert report_data["taxonomy_version"] == "DC_TAXONOMY_V1"
    assert report_data["taxonomy_version_inferred"] == 0
    assert report_data["valid_signal_dates"] == ["2024-01-02", "2024-01-03", "2024-01-05", "2024-01-08", "2024-01-10"]
    assert len(report_data["group_rows"]) == 20
    assert len(report_data["ticker_rows"]) == 20
    assert len(report_data["synthetic_rows"]) == 10
    assert "taxonomy_version: DC_TAXONOMY_V1" in markdown
    assert "Other Group" not in markdown
    assert "ticker_rows_with_scanner_fields_null | 1 |" in markdown


def test_weekly_report_fails_without_taxonomy_version_when_multiple_versions_exist(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    _seed_second_taxonomy_weekly_rows(analysis_db)

    with pytest.raises(ValueError, match="Multiple taxonomy_version values exist"):
        load_weekly_swing_report_data(
            analysis_db_path=analysis_db,
            end_date="2024-01-10",
        )


def test_weekly_report_infers_taxonomy_version_when_only_one_exists(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)

    report_data = load_weekly_swing_report_data(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
    )

    assert report_data["taxonomy_version"] == "DC_TAXONOMY_V1"
    assert report_data["taxonomy_version_inferred"] == 1


def test_weekly_report_without_technical_relevance_run_id_remains_unchanged(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)

    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    assert "## 15. Technical Relevance Context" not in result["markdown"]
    assert "section;technical_relevance_context" not in result["csv"]
    assert "latest_bullish_relevance_signal_name" not in result["markdown"]
    assert "latest_bearish_relevance_signal_name" not in result["markdown"]


def test_weekly_report_with_technical_relevance_run_id_includes_context_section(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_weekly_report_db(analysis_db)
    conn = _connect_relevance_db(analysis_db)
    _insert_relevance_run(conn, "REL_WEEKLY")
    _insert_relevance_record(
        conn,
        run_id="REL_WEEKLY",
        ticker="AAA",
        signal_date="2024-01-05",
        signal_name="Hammer",
        relevance_class="RELEVANT",
        relevance_reason="UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_WEEKLY",
        ticker="BBB",
        signal_date="2024-01-10",
        signal_name="Bullish Divergence",
        relevance_class="WEAK_CONTEXT",
        relevance_reason="UP_TREND_REGULAR_BULLISH_DIVERGENCE_WEAK",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_WEEKLY",
        ticker="BBB",
        signal_date="2024-01-05",
        signal_name="Hammer",
        relevance_class="RELEVANT",
        relevance_reason="UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_WEEKLY",
        ticker="BBB",
        signal_date="2024-01-10",
        signal_name="Bearish Divergence",
        relevance_class="RELEVANT",
        relevance_reason="UP_TREND_BEARISH_DIVERGENCE_AFTER_BOS_DOWN",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_WEEKLY",
        ticker="BBB",
        signal_date="2024-01-10",
        signal_name="Morning Star",
        relevance_class="NOISE",
        relevance_reason="NOISE_REASON",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_WEEKLY",
        ticker="CCC",
        signal_date="2024-01-08",
        signal_name="Hammer",
        relevance_class="WEAK_CONTEXT",
        relevance_reason="UP_TREND_BULLISH_REVERSAL_WITHOUT_PIVOT_CONTEXT",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_WEEKLY",
        ticker="CCC",
        signal_date="2024-01-10",
        signal_name="Bearish Engulfing",
        relevance_class="RELEVANT",
        relevance_reason="UP_TREND_BEARISH_REVERSAL_AFTER_BOS_DOWN",
    )
    conn.commit()
    conn.close()

    baseline = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        generated_at_utc="2026-05-17T12:00:00Z",
    )
    result = write_weekly_swing_report(
        analysis_db_path=analysis_db,
        end_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
        generated_at_utc="2026-05-17T12:00:00Z",
        technical_relevance_run_id="REL_WEEKLY",
    )

    assert baseline["summary"]["repeated_pullback_tickers"] == result["summary"]["repeated_pullback_tickers"]
    assert baseline["summary"]["repeated_exit_risk_tickers"] == result["summary"]["repeated_exit_risk_tickers"]
    assert "## 15. Technical Relevance Context" in result["markdown"]
    assert "technical_relevance_run_id: REL_WEEKLY" in result["markdown"]
    assert "latest_bullish_relevance_signal_name" in result["markdown"]
    assert "latest_bearish_relevance_signal_name" in result["markdown"]
    assert "section;technical_relevance_context" in result["csv"]
    assert "section;technical_relevance_run_id;REL_WEEKLY" in result["csv"]
    assert "technical_relevance_context;AAA;1d;2024-01-05;2024-01-05;Hammer;CANDLE;RELEVANT;" in result["csv"]
    assert "technical_relevance_context;BBB;1d;2024-01-10;2024-01-10;Bullish Divergence;CANDLE;WEAK_CONTEXT;" in result["csv"]
    assert "15. Technical Relevance Context" not in result["csv"]
    assert "\n15. Technical Relevance Context;" not in result["csv"]
    assert "Datacenter Taxonomy Listing" in result["csv"]
    assert result["csv"].index("section;technical_relevance_context") < result["csv"].index("Datacenter Taxonomy Listing")
    assert result["csv"].count("section;technical_relevance_context") == 1
    assert "| BBB | 3 | 2 | 2 | 2024-01-03 | 2024-01-10 | Infrastructure | AI Chips |" in result["markdown"]
    assert "| 2024-01-05 | Hammer | RELEVANT | UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW | 2024-01-10 | Bearish Divergence | RELEVANT | UP_TREND_BEARISH_DIVERGENCE_AFTER_BOS_DOWN |" in result["markdown"]
    assert "| CCC | 4 | 2024-01-02 | 2024-01-10 | Infrastructure | Storage |" in result["markdown"]
    assert "| 2024-01-08 | Hammer | WEAK_CONTEXT | UP_TREND_BULLISH_REVERSAL_WITHOUT_PIVOT_CONTEXT | 2024-01-10 | Bearish Engulfing | RELEVANT | UP_TREND_BEARISH_REVERSAL_AFTER_BOS_DOWN |" in result["markdown"]
    pullback_start = result["markdown"].index("## 9. Repeated pullback tickers")
    technical_section_start = result["markdown"].index("## 15. Technical Relevance Context")
    scanner_section_markdown = result["markdown"][pullback_start:technical_section_start]
    assert "NOISE_REASON" not in scanner_section_markdown
