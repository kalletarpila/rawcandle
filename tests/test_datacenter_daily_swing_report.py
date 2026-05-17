from __future__ import annotations

import sqlite3

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_daily_report import (
    build_markdown_daily_swing_report,
    load_daily_swing_report_data,
    write_daily_swing_signal_report,
)


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
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                close, return_5d, return_10d, return_20d, return_60d,
                ma10, ema10, ema20, distance_to_ema10_pct, distance_to_ema20_pct,
                volume_vs_avg20, highest_close_20d, latest_structure_label,
                bullish_divergence_signal, bearish_divergence_signal,
                hidden_bullish_divergence_signal, hidden_bearish_divergence_signal,
                bullish_candle_signal, bearish_candle_signal,
                breakout_signal, fast_ema10_pullback_signal, conservative_ema20_pullback_signal,
                pullback_signal, exit_risk_signal, exit_reason, price_data_status,
                signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()


def _insert_synthetic_row(path, row):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_group_synthetic_ohlc_daily (
                ohlc_date, taxonomy_version, group_type, group_name,
                member_count, eligible_count, synthetic_open, synthetic_high, synthetic_low, synthetic_close,
                synthetic_volume, ma20, ema20, distance_to_ema20_pct, volatility_20d,
                pivot_radius, latest_pivot_high_date, latest_pivot_high_value, latest_pivot_low_date, latest_pivot_low_value,
                latest_structure_label, trend_classification, relative_base_window, relative_open_20, relative_high_20,
                relative_low_20, relative_close_20, relative_upper_wick_20, relative_lower_wick_20,
                relative_close_extension_20, relative_high_extension_20, relative_low_extension_20,
                relative_eligible_count, data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()


def _seed_report_db(path, *, with_ecosystem: bool = True):
    _create_analysis_db(path)
    group_rows = [
        (
            "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "AI Chips",
            4, 4, 0.01, 0.07, 0.15, 0.25,
            82.0, 88.0, 70.0, -2.0, -3.0,
            75.0, 15.0, "LOW", "BUY_ZONE",
            "BUY_ZONE:return_5d_pos;return_10d_pos;pct_above_ema20_ge_80;ema20_breadth_delta_5d_ge_minus_10;data_quality_ok",
            "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "Cloud",
            4, 4, -0.01, 0.03, 0.12, 0.22,
            75.0, 81.0, 68.0, -4.0, -6.0,
            60.0, 20.0, "ELEVATED", "ADD_ON_PULLBACK",
            "ADD_ON_PULLBACK:return_20d_pos;return_60d_pos;return_5d_pullback_ge_minus_5pct;pct_above_ema20_ge_65;data_quality_ok",
            "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "Servers",
            4, 3, -0.02, -0.01, 0.02, 0.10,
            48.0, 55.0, 40.0, -7.0, -11.0,
            35.0, 45.0, "HIGH", "TRIM_WATCH",
            "TRIM_WATCH:ema20_breadth_delta_5d_lt_minus_10", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "Storage",
            4, 3, -0.05, -0.09, -0.12, -0.18,
            30.0, 35.0, 20.0, -12.0, -16.0,
            10.0, 70.0, "EXTREME", "EXIT_ZONE",
            "EXIT_ZONE:return_20d_neg;pct_above_ema20_lt_40", "PARTIAL_DATA",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "layer", "Infrastructure",
            8, 7, 0.00, 0.02, 0.06, 0.12,
            65.0, 70.0, 55.0, -3.0, -4.0,
            52.0, 28.0, "LOW", "NEUTRAL",
            "NEUTRAL:no_state_rule_matched", "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    ]
    if with_ecosystem:
        group_rows.append(
            (
                "2024-01-10", "DC_TAXONOMY_V1", "ecosystem", "DC_ECOSYSTEM_TOTAL",
                16, 14, 0.02, 0.04, 0.08, 0.16,
                71.0, 74.0, 58.0, -2.0, -4.0,
                50.0, 25.0, "LOW", "NEUTRAL",
                "NEUTRAL:no_state_rule_matched", "OK",
                "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
            )
        )
    for row in group_rows:
        _insert_group_row(path, row)

    ticker_rows = [
        (
            "2024-01-10", "DC_TAXONOMY_V1", "AAA", "Infrastructure", "AI Chips",
            110.0, 0.03, 0.08, 0.12, 0.18,
            104.0, 107.0, 105.0, 0.028, 0.0476,
            2.1, 110.0, "HH",
            1, 0, 1, 0, 1, 0,
            1, 0, 0, 0, 0, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "BBB", "Infrastructure", "Cloud",
            102.0, -0.02, 0.04, 0.15, 0.30,
            103.0, 101.0, 99.0, 0.0099, 0.0303,
            1.2, 108.0, "HL",
            1, 0, 1, 0, 0, 0,
            0, 1, 1, 1, 0, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "CCC", "Infrastructure", "Storage",
            90.0, -0.04, -0.10, -0.15, -0.22,
            92.0, 93.0, 95.0, -0.0323, -0.0526,
            0.8, 96.0, "LL",
            0, 1, 0, 1, 0, 1,
            0, 0, 0, 0, 1, "close_below_ema20;latest_structure_label_ll", "MISSING_AS_OF_DATE",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "DDD", "Infrastructure", "Servers",
            None, None, None, None, None,
            None, None, None, None, None,
            None, None, None,
            None, None, None, None, None, None,
            None, None, None, None, None, None, "MISSING_CLOSE_AS_OF_DATE",
            "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    ]
    for row in ticker_rows:
        _insert_ticker_row(path, row)

    synthetic_rows = [
        (
            "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "AI Chips",
            4, 4, 100.0, 105.0, 99.0, 104.0,
            100000.0, 98.0, 101.0, 0.0297, 0.12,
            5, "2024-01-08", 105.0, "2024-01-04", 95.0,
            "HH", "UP", 20, 1.01, 1.06, 0.99, 1.04, 0.02, 0.02,
            0.04, 0.06, -0.01, 4, "OK", "DC_SWING_OHLC_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "layer", "Infrastructure",
            8, 7, 100.0, 102.0, 98.0, 101.0,
            200000.0, 99.0, 100.0, 0.01, 0.09,
            10, "2024-01-07", 103.0, "2024-01-03", 97.0,
            None, None, 20, None, None, None, None, None, None,
            None, None, None, 0, "PARTIAL_DATA", "DC_SWING_OHLC_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    ]
    for row in synthetic_rows:
        _insert_synthetic_row(path, row)


def test_generates_markdown_report_with_required_sections_and_filters(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)

    report_data = load_daily_swing_report_data(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
    )
    markdown = build_markdown_daily_swing_report(
        report_data,
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )

    for heading in [
        "# Datacenter Daily Swing Signal Report",
        "## 1. Title and run metadata",
        "## 2. Dashboard",
        "## 3. Rotation Risk / Overheat Index",
        "## 4. Subindustry Timing States",
        "## 5. Buy-Zone Subindustries",
        "## 6. Add-On Pullback Subindustries",
        "## 7. Trim/Watch Subindustries",
        "## 8. Exit-Zone Subindustries",
        "## 9. Synthetic OHLC Structure Summary",
        "## 10. Breakout Ticker Scanner",
        "## 11. Pullback Ticker Scanner",
        "## 12. Exit-Risk Ticker Scanner",
        "## 13. Data Quality",
        "## 14. Missing / Incomplete Inputs Summary",
    ]:
        assert heading in markdown

    assert "signal_date: 2024-01-10" in markdown
    assert "generated_at_utc: 2026-05-17T12:00:00Z" in markdown
    assert "ecosystem_return_5d" in markdown
    assert "EXTREME RISK – TIGHTEN STOPS / NO NEW LONGS" in markdown
    assert "| AI Chips | BUY_ZONE |" in markdown
    assert "| Cloud | ADD_ON_PULLBACK |" in markdown
    assert "| Servers | TRIM_WATCH |" in markdown
    assert "| Storage | EXIT_ZONE |" in markdown
    assert "| AAA | Infrastructure | AI Chips |" in markdown
    assert "| BBB | Infrastructure | Cloud |" in markdown
    assert "close_below_ema20;latest_structure_label_ll" in markdown
    assert "synthetic_ohlc_rows_missing_relative_close_20" in markdown
    assert "ticker_rows_with_scanner_fields_null" in markdown


def test_report_handles_missing_ecosystem_and_empty_sections_with_stable_messages(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db, with_ecosystem=False)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET breakout_signal = 0,
                fast_ema10_pullback_signal = 0,
                conservative_ema20_pullback_signal = 0,
                pullback_signal = 0,
                exit_risk_signal = 0,
                exit_reason = NULL
            """
        )
        conn.commit()

    report_data = load_daily_swing_report_data(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
    )
    markdown = build_markdown_daily_swing_report(
        report_data,
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )

    assert "Ecosystem row missing." in markdown
    assert markdown.count("No rows.") >= 2


def test_subindustry_rows_are_ordered_by_timing_priority(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)

    report_data = load_daily_swing_report_data(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
    )
    markdown = build_markdown_daily_swing_report(
        report_data,
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )

    exit_index = markdown.index("| Storage | EXIT_ZONE |")
    trim_index = markdown.index("| Servers | TRIM_WATCH |")
    add_on_index = markdown.index("| Cloud | ADD_ON_PULLBACK |")
    buy_index = markdown.index("| AI Chips | BUY_ZONE |")
    assert exit_index < trim_index < add_on_index < buy_index


def test_report_generation_is_read_only(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)

    with sqlite3.connect(analysis_db) as conn:
        before_counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "dc_group_swing_signal_daily",
                "dc_ticker_swing_signal_daily",
                "dc_group_synthetic_ohlc_daily",
            )
        }

    result = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
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
