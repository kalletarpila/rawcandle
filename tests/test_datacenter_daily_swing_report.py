from __future__ import annotations

import sqlite3
import pytest

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
    values = list(row)
    if len(values) == 34:
        values[18:18] = [None, None]
        values.insert(32, None)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                close, return_5d, return_10d, return_20d, return_60d,
                ma10, ema10, ema20, distance_to_ema10_pct, distance_to_ema20_pct,
                volume_vs_avg20, highest_close_20d, latest_structure_label,
                latest_structure_age_trading_days, latest_structure_freshness,
                bullish_divergence_signal, bearish_divergence_signal,
                hidden_bullish_divergence_signal, hidden_bearish_divergence_signal,
                bullish_candle_signal, bearish_candle_signal,
                breakout_signal, fast_ema10_pullback_signal, conservative_ema20_pullback_signal,
                pullback_signal, exit_risk_signal, exit_reason, exit_risk_severity, price_data_status,
                signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            "HH", 2, "FRESH",
            "BOS_UP", "2024-01-10", "2024-01-10", 0, "FRESH",
            "2024-01-10", "2024-01-10", "DOUBLE_BOS_UP", 0, "FRESH",
            "UP", 20, 1.01, 1.06, 0.99, 1.04, 0.02, 0.02,
            0.04, 0.06, -0.01, 4, "OK", "DC_SWING_OHLC_V1", "seed", "2026-05-17T10:00:00Z",
        ),
        (
            "2024-01-10", "DC_TAXONOMY_V1", "layer", "Infrastructure",
            8, 7, 100.0, 102.0, 98.0, 101.0,
            200000.0, 99.0, 100.0, 0.01, 0.09,
            10, "2024-01-07", 103.0, "2024-01-03", 97.0,
            "LH", 4, "FRESH",
            "BOS_DOWN", "2024-01-10", "2024-01-10", 0, "FRESH",
            None, None, None, None, None,
            "NEUTRAL", 20, None, None, None, None, None, None,
            None, None, None, 0, "PARTIAL_DATA", "DC_SWING_OHLC_V1", "seed", "2026-05-17T10:00:00Z",
        ),
    ]
    for row in synthetic_rows:
        _insert_synthetic_row(path, row)


def _seed_second_taxonomy_daily_rows(path):
    _insert_group_row(
        path,
        (
            "2024-01-10", "DC_TAXONOMY_OTHER_V1", "subindustry", "Other Taxonomy Group",
            2, 2, 0.11, 0.22, 0.33, 0.44,
            91.0, 92.0, 90.0, -1.0, -2.0,
            80.0, 10.0, None, None, None,
            "OK", "DC_SWING_SIGNAL_V1", "seed2", "2026-05-17T10:00:00Z",
        ),
    )
    _insert_ticker_row(
        path,
        (
            "2024-01-10", "DC_TAXONOMY_OTHER_V1", "ZZZ", "Other Layer", "Other Taxonomy Group",
            200.0, 0.05, 0.06, 0.07, 0.08,
            195.0, 196.0, 197.0, 0.02, 0.03,
            1.5, 200.0, "HH",
            1, 0, 1, 0, 1, 0,
            None, None, None, None, None, None, "OK",
            "DC_SWING_SIGNAL_V1", "seed2", "2026-05-17T10:00:00Z",
        ),
    )
    _insert_synthetic_row(
        path,
        (
            "2024-01-10", "DC_TAXONOMY_OTHER_V1", "subindustry", "Other Taxonomy Group",
            2, 2, 100.0, 101.0, 99.0, 100.5,
            50000.0, 99.0, 100.0, 0.005, 0.04,
            5, None, None, None, None,
            None, None, 20, None, None,
            None, None, None, None,
            None, None, None, 0, "OK", "DC_SWING_OHLC_V1", "seed2", "2026-05-17T10:00:00Z",
        ),
    )


def test_generates_markdown_report_with_required_sections_and_filters(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    _update_ticker_exit_risk_severity(
        analysis_db,
        ticker="CCC",
        signal_date="2024-01-10",
        severity="HIGH",
    )

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
        "## 10. Group Structure Breaks / Resets",
        "## 11. Breakout Ticker Scanner",
        "## 12. Pullback Ticker Scanner",
        "## 13. Exit-Risk Ticker Scanner",
        "## 14. Data Quality",
        "## 15. Missing / Incomplete Inputs Summary",
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
    assert "exit_risk_severity" in markdown
    assert "latest_structure_age_trading_days" in markdown
    assert "latest_structure_freshness" in markdown
    assert "latest_bos_age_trading_days" in markdown
    assert "latest_reset_age_trading_days" in markdown
    assert "ticker_trend_state" in markdown
    assert "latest_bos_event_type" in markdown
    assert "latest_bos_freshness" in markdown
    assert "latest_reset_reason" in markdown
    assert "latest_reset_freshness" in markdown
    assert "| subindustry | AI Chips | BOS_UP | 2024-01-10 | FRESH | DOUBLE_BOS_UP | 2024-01-10 | FRESH | HH | FRESH | UP | BUY_ZONE | LOW |" in markdown
    assert "| layer | Infrastructure | BOS_DOWN | 2024-01-10 | FRESH |  |  |  | LH | FRESH | NEUTRAL | NEUTRAL | LOW |" in markdown
    assert "HIGH" in markdown
    assert "synthetic_ohlc_rows_missing_relative_close_20" in markdown
    assert "ticker_rows_with_scanner_fields_null" in markdown


def test_daily_group_structure_breaks_section_renders_no_rows_when_absent(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
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

    markdown = build_markdown_daily_swing_report(
        load_daily_swing_report_data(
            analysis_db_path=analysis_db,
            signal_date="2024-01-10",
        ),
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )
    section_start = markdown.index("## 10. Group Structure Breaks / Resets")
    next_section = markdown.index("## 11. Breakout Ticker Scanner")
    section = markdown[section_start:next_section]
    assert "No rows." in section


def test_daily_exit_risk_section_sorts_by_severity_before_return_and_distance(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET exit_risk_signal = 1,
                exit_reason = 'subindustry_exit_zone',
                exit_risk_severity = 'MEDIUM'
            WHERE ticker = 'AAA'
              AND signal_date = '2024-01-10'
            """
        )
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET exit_risk_severity = 'HIGH'
            WHERE ticker = 'CCC'
              AND signal_date = '2024-01-10'
            """
        )
        conn.commit()

    markdown = build_markdown_daily_swing_report(
        load_daily_swing_report_data(
            analysis_db_path=analysis_db,
            signal_date="2024-01-10",
        ),
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )
    section_start = markdown.index("## 13. Exit-Risk Ticker Scanner")
    exit_section = markdown[section_start:]
    ccc_index = exit_section.index("| CCC | Infrastructure | Storage |")
    aaa_index = exit_section.index("| AAA | Infrastructure | AI Chips |")
    assert ccc_index < aaa_index


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


def test_daily_report_scopes_rows_to_selected_taxonomy_version(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    _seed_second_taxonomy_daily_rows(analysis_db)

    report_data = load_daily_swing_report_data(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        taxonomy_version="DC_TAXONOMY_V1",
    )
    markdown = build_markdown_daily_swing_report(
        report_data,
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )

    assert report_data["taxonomy_version"] == "DC_TAXONOMY_V1"
    assert report_data["taxonomy_version_inferred"] == 0
    assert len(report_data["group_rows"]) == 6
    assert len(report_data["ticker_rows"]) == 4
    assert len(report_data["synthetic_rows"]) == 2
    assert "taxonomy_version: DC_TAXONOMY_V1" in markdown
    assert "Other Taxonomy Group" not in markdown
    assert "| ticker_rows_with_scanner_fields_null | 1 |" in markdown


def test_daily_report_fails_without_taxonomy_version_when_multiple_versions_exist(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    _seed_second_taxonomy_daily_rows(analysis_db)

    with pytest.raises(ValueError, match="Multiple taxonomy_version values exist"):
        load_daily_swing_report_data(
            analysis_db_path=analysis_db,
            signal_date="2024-01-10",
        )


def test_daily_report_infers_taxonomy_version_when_only_one_exists(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)

    report_data = load_daily_swing_report_data(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
    )

    assert report_data["taxonomy_version"] == "DC_TAXONOMY_V1"
    assert report_data["taxonomy_version_inferred"] == 1
