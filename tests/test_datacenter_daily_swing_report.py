from __future__ import annotations

import sqlite3
import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices import swing_daily_report as daily_report_module
from analysis.datacenter_indices.swing_daily_report import (
    DEFAULT_WATCHLIST_FILE,
    _load_watchlist_tickers,
    build_markdown_daily_swing_report,
    load_daily_swing_report_data,
    write_daily_swing_signal_report,
)
from tests.test_datacenter_technical_relevance_context import (
    _connect as _connect_relevance_db,
    _insert_record as _insert_relevance_record,
    _insert_run as _insert_relevance_run,
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


def _update_ticker_fields(path, *, ticker: str, signal_date: str, assignments: dict[str, object]):
    columns = ", ".join(f"{column} = ?" for column in assignments)
    values = [*assignments.values(), ticker, signal_date]
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"""
            UPDATE dc_ticker_swing_signal_daily
            SET {columns}
            WHERE ticker = ?
              AND signal_date = ?
            """,
            values,
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
        "## Watchlist Summary",
        "## 3. Dashboard",
        "## 4. Rotation Risk / Overheat Index",
        "## 5. Subindustry Timing States",
        "## 6. Buy-Zone Subindustries",
        "## 7. Add-On Pullback Subindustries",
        "## 8. Trim/Watch Subindustries",
        "## 9. Exit-Zone Subindustries",
        "## 10. Synthetic OHLC Structure Summary",
        "## 11. Group Structure Breaks / Resets",
        "## 12. Breakout Ticker Scanner",
        "## 13. Pullback Ticker Scanner",
        "## 14. Exit-Risk Ticker Scanner",
        "## 15. Daily Triggers",
        "## 16. Data Quality",
        "## 17. Missing / Incomplete Inputs Summary",
        "## Datacenter Taxonomy Listing",
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
    assert "### Layer: Infrastructure" in markdown
    assert "| row_type | layer | subindustry | ticker | status |" in markdown
    assert "| LAYER | Infrastructure |  |  |" in markdown
    assert "| SUBINDUSTRY | Infrastructure | AI Chips |  |" in markdown
    assert "| TICKER | Infrastructure | AI Chips | AAA |" in markdown


def test_watchlist_file_parser_normalizes_comments_whitespace_case_and_duplicates(tmp_path):
    watchlist_file = tmp_path / "watchlist.txt"
    watchlist_file.write_text("\n nvda \n# comment\nAVGO\nnvda\n\n tsm \n", encoding="utf-8")

    assert _load_watchlist_tickers(watchlist_file) == ["NVDA", "AVGO", "TSM"]


def test_daily_watchlist_summary_renders_inside_outside_group_context_and_status_priority(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    watchlist_file = tmp_path / "watchlist.txt"
    _seed_report_db(analysis_db)
    watchlist_file.write_text("aaa\nbbb\nccc\noutside\nbbb\n", encoding="utf-8")
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
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET exit_risk_severity = 'HIGH'
            WHERE ticker = 'CCC'
              AND signal_date = '2024-01-10'
            """
        )
        conn.commit()

    result = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        watchlist_file=watchlist_file,
        generated_at_utc="2026-05-17T12:00:00Z",
    )
    markdown = result["markdown"]

    assert "## Watchlist Summary" in markdown
    assert markdown.index("## Watchlist Summary") < markdown.index("## 3. Dashboard")
    assert "| watchlist_tickers_total | 4 |" in markdown
    assert "| watchlist_in_datacenter_taxonomy | 3 |" in markdown
    assert "| watchlist_not_in_datacenter_taxonomy | 1 |" in markdown
    assert "| watchlist_missing_price | 1 |" in markdown
    assert "| watchlist_subindustry_context_risk_count | 1 |" in markdown
    assert "| watchlist_layer_context_risk_count | 0 |" in markdown
    assert "| watchlist_both_context_risk_count | 0 |" in markdown
    assert "| watchlist_breakout_count | 1 |" in markdown
    assert "| watchlist_pullback_count | 1 |" in markdown
    assert "| watchlist_high_exit_risk_count | 2 |" in markdown
    assert "subindustry_context_risk" in markdown
    assert "layer_context_risk" in markdown
    assert "subindustry_trend_classification" in markdown
    assert "subindustry_latest_structure_label" in markdown
    assert "layer_trend_classification" in markdown
    assert "layer_latest_structure_label" in markdown
    assert "| OUTSIDE | NOT_PART_OF_DATACENTER_ECOSYSTEM |  |  |  |  |  |  | NO |" in markdown
    assert "| AAA | BREAKOUT_CANDIDATE | NO | NO | UP | HH | NEUTRAL | LH | YES | Infrastructure | AI Chips | 110 | 0.03 | 0.08 | 0.12 | 0.0476 |  | HH |  |  |  |  |  | 1 | 0 | 0 |  |  | BUY_ZONE | LOW | NEUTRAL | LOW | OK |" in markdown
    assert "| BBB | HIGH_EXIT_RISK | NO | NO |  |  | NEUTRAL | LH | YES | Infrastructure | Cloud | 102 | -0.02 | 0.04 | 0.15 | 0.0303 |  | HL |  |  |  |  |  | 0 | 1 | 1 | HIGH | subindustry_exit_zone | ADD_ON_PULLBACK | ELEVATED | NEUTRAL | LOW | OK |" in markdown
    assert "| CCC | MISSING_PRICE | YES | NO |  |  | NEUTRAL | LH | YES | Infrastructure | Storage | 90 | -0.04 | -0.1 | -0.15 | -0.0526 |  | LL |  |  |  |  |  | 0 | 0 | 1 | HIGH | close_below_ema20;latest_structure_label_ll | EXIT_ZONE | EXTREME | NEUTRAL | LOW | MISSING_AS_OF_DATE |" in markdown


def test_daily_watchlist_context_risk_fields_show_subindustry_layer_or_both(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    watchlist_file = tmp_path / "watchlist.txt"
    _seed_report_db(analysis_db)
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
              AND signal_date = '2024-01-10'
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

    markdown = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        watchlist_file=watchlist_file,
        generated_at_utc="2026-05-17T12:00:00Z",
    )["markdown"]

    assert "| watchlist_subindustry_context_risk_count | 1 |" in markdown
    assert "| watchlist_layer_context_risk_count | 3 |" in markdown
    assert "| watchlist_both_context_risk_count | 1 |" in markdown
    assert "| AAA | GROUP_RISK | NO | YES | UP | HH | NEUTRAL | LH | YES |" in markdown
    assert "| BBB | PULLBACK_CANDIDATE | NO | YES |  |  | NEUTRAL | LH | YES |" in markdown
    assert "| CCC | MISSING_PRICE | YES | YES |  |  | NEUTRAL | LH | YES |" in markdown


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
    section_start = markdown.index("## 11. Group Structure Breaks / Resets")
    next_section = markdown.index("## 12. Breakout Ticker Scanner")
    section = markdown[section_start:next_section]
    assert "No rows." in section


def test_daily_report_uses_default_watchlist_path_and_missing_file_is_non_fatal(tmp_path, monkeypatch):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    missing_watchlist = tmp_path / "missing_watchlist.txt"
    monkeypatch.setattr(daily_report_module, "DEFAULT_WATCHLIST_FILE", str(missing_watchlist))

    report_data = load_daily_swing_report_data(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
    )
    markdown = build_markdown_daily_swing_report(
        report_data,
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
    )

    assert report_data["watchlist_file_path"] == str(missing_watchlist)
    assert report_data["watchlist_file_missing"] is True
    assert "## Watchlist Summary" in markdown
    assert "| watchlist_tickers_total | 0 |" in markdown
    assert f"No watchlist file found: {missing_watchlist}" in markdown


def test_daily_report_can_omit_taxonomy_listing(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)

    markdown = build_markdown_daily_swing_report(
        load_daily_swing_report_data(
            analysis_db_path=analysis_db,
            signal_date="2024-01-10",
        ),
        generated_at_utc="2026-05-17T12:00:00Z",
        top_n=20,
        include_taxonomy_listing=False,
    )

    assert "## Datacenter Taxonomy Listing" not in markdown


def test_daily_taxonomy_listing_includes_all_scoped_ticker_rows_with_compact_columns(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)

    markdown = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
    )["markdown"]

    section = markdown[markdown.index("## Datacenter Taxonomy Listing") :]
    assert "### Layer: Infrastructure" in section
    assert "row_type" in section
    assert "status" in section
    assert "layer" in section
    assert "subindustry" in section
    assert "subindustry_context_risk" in section
    assert "layer_context_risk" in section
    assert "exit_risk_severity" in section
    assert "price_data_status" in section
    assert "| trend_state |" in section
    assert "| LAYER | Infrastructure |  |  | NEUTRAL |  | NO | 101 | 0 | 0.02 | 0.06 | 0.01 | NEUTRAL | LH | FRESH | BOS_DOWN | FRESH |  |  |  |  |  |  |  | OK |" in section
    assert "| SUBINDUSTRY | Infrastructure | AI Chips |  | BUY_ZONE | NO | NO | 104 | 0.01 | 0.07 | 0.15 | 0.0297 | UP | HH | FRESH | BOS_UP | FRESH | DOUBLE_BOS_UP | FRESH |  |  |  |  |  | OK |" in section
    assert "| TICKER | Infrastructure | AI Chips | AAA | BREAKOUT_CANDIDATE | NO | NO | 110 | 0.03 | 0.08 | 0.12 | 0.0476 |" in section
    assert "| TICKER | Infrastructure | Cloud | BBB | PULLBACK_CANDIDATE | NO | NO | 102 | -0.02 | 0.04 | 0.15 | 0.0303 |" in section
    assert "| TICKER | Infrastructure | Storage | CCC | MISSING_PRICE | YES | NO | 90 | -0.04 | -0.1 | -0.15 | -0.0526 |" in section
    assert "close_below_ema20;latest_structure_label_ll | MISSING_AS_OF_DATE |" in section
    assert "| TICKER | Infrastructure | Servers | DDD | MISSING_PRICE | YES | NO |" in section
    assert "MISSING_CLOSE_AS_OF_DATE |" in section
    assert "| ZZZ |" not in section
    assert section.index("| LAYER | Infrastructure |") < section.index("| SUBINDUSTRY | Infrastructure | AI Chips |") < section.index("| TICKER | Infrastructure | AI Chips | AAA |")


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
    section_start = markdown.index("## 14. Exit-Risk Ticker Scanner")
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


def test_daily_report_without_technical_relevance_run_id_remains_unchanged(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)

    result = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    assert "## 18. Technical Relevance Context" not in result["markdown"]
    assert "section;technical_relevance_context" not in result["csv"]
    assert "latest_bullish_relevance_signal_name" not in result["markdown"]
    assert "latest_bearish_relevance_signal_name" not in result["markdown"]


def test_daily_report_with_technical_relevance_run_id_adds_context_section_without_changing_scanner_counts(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    conn = _connect_relevance_db(analysis_db)
    _insert_relevance_run(conn, "REL_RUN_A")
    _insert_relevance_record(
        conn,
        run_id="REL_RUN_A",
        ticker="AAA",
        signal_date="2024-01-10",
        signal_name="Hammer",
        relevance_class="RELEVANT",
        relevance_reason="UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_RUN_A",
        ticker="AAA",
        signal_date="2024-01-10",
        signal_name="Bearish Divergence",
        relevance_class="WEAK_CONTEXT",
        relevance_reason="NEUTRAL_DIVERGENCE_WEAK_CONTEXT",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_RUN_A",
        ticker="BBB",
        signal_date="2024-01-10",
        signal_name="Bullish Divergence",
        relevance_class="WEAK_CONTEXT",
        relevance_reason="UP_TREND_REGULAR_BULLISH_DIVERGENCE_WEAK",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_RUN_A",
        ticker="BBB",
        signal_date="2024-01-10",
        signal_name="Bearish Engulfing",
        relevance_class="RELEVANT",
        relevance_reason="UP_TREND_BEARISH_REVERSAL_AFTER_BOS_DOWN",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_RUN_A",
        ticker="BBB",
        signal_date="2024-01-10",
        signal_name="Morning Star",
        relevance_class="NOISE",
        relevance_reason="NOISE_REASON",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_RUN_A",
        ticker="CCC",
        signal_date="2024-01-10",
        signal_name="Bearish Engulfing",
        relevance_class="RELEVANT",
        relevance_reason="UP_TREND_BEARISH_REVERSAL_AFTER_BOS_DOWN",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_RUN_A",
        ticker="CCC",
        signal_date="2024-01-10",
        signal_name="Hammer",
        relevance_class="WEAK_CONTEXT",
        relevance_reason="UP_TREND_BULLISH_REVERSAL_WITHOUT_PIVOT_CONTEXT",
    )
    conn.commit()
    conn.close()

    baseline = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
    )
    enriched = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
        technical_relevance_run_id="REL_RUN_A",
    )

    assert baseline["summary"]["breakout_count"] == enriched["summary"]["breakout_count"]
    assert baseline["summary"]["pullback_count"] == enriched["summary"]["pullback_count"]
    assert baseline["summary"]["exit_risk_count"] == enriched["summary"]["exit_risk_count"]
    assert "## 18. Technical Relevance Context" in enriched["markdown"]
    assert "technical_relevance_run_id: REL_RUN_A" in enriched["markdown"]
    assert "bullish_candle_signal" in enriched["markdown"]
    assert "bearish_divergence_signal" in enriched["markdown"]
    assert "latest_bullish_relevance_signal_name" in enriched["markdown"]
    assert "latest_bearish_relevance_signal_name" in enriched["markdown"]
    assert "latest_bullish_relevance_class" in enriched["markdown"]
    assert "latest_bearish_relevance_class" in enriched["markdown"]
    assert "section;technical_relevance_context" in enriched["csv"]
    assert "section;technical_relevance_run_id;REL_RUN_A" in enriched["csv"]
    assert (
        "section;ticker;timeframe;signal_date;signal_confirmed_as_of_date;signal_name;"
        "signal_source_id;relevance_class;relevance_reason;dow_trend_state;"
        "dow_context_state;latest_bos_direction;bars_since_latest_bos;"
        "bars_since_latest_reset;near_latest_pivot;near_active_bos_level;"
        "is_trend_aligned;is_counter_trend"
    ) in enriched["csv"]
    assert "technical_relevance_context;AAA;1d;2024-01-10;2024-01-10;Hammer;CANDLE;RELEVANT;" in enriched["csv"]
    assert "technical_relevance_context;BBB;1d;2024-01-10;2024-01-10;Bullish Divergence;CANDLE;WEAK_CONTEXT;" in enriched["csv"]
    assert "technical_relevance_context;CCC;1d;2024-01-10;2024-01-10;Bearish Engulfing;CANDLE;RELEVANT;" in enriched["csv"]
    assert "18. Technical Relevance Context" not in enriched["csv"]
    assert "section;technical_relevance_context\nsection;technical_relevance_run_id;REL_RUN_A\nsection;ticker;timeframe;signal_date;signal_confirmed_as_of_date;" in enriched["csv"]
    assert "\n18. Technical Relevance Context;" not in enriched["csv"]
    assert "Datacenter Taxonomy Listing" in enriched["csv"]
    assert enriched["csv"].index("section;technical_relevance_context") < enriched["csv"].index("Datacenter Taxonomy Listing")
    assert enriched["csv"].count("section;technical_relevance_context") == 1
    assert "| AAA | Infrastructure | AI Chips |" in enriched["markdown"]
    assert "| 2024-01-10 | Hammer | RELEVANT | UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW | 2024-01-10 | Bearish Divergence | WEAK_CONTEXT | NEUTRAL_DIVERGENCE_WEAK_CONTEXT |" in enriched["markdown"]
    assert "| BBB | Infrastructure | Cloud |" in enriched["markdown"]
    assert "| 2024-01-10 | Bullish Divergence | WEAK_CONTEXT | UP_TREND_REGULAR_BULLISH_DIVERGENCE_WEAK | 2024-01-10 | Bearish Engulfing | RELEVANT | UP_TREND_BEARISH_REVERSAL_AFTER_BOS_DOWN |" in enriched["markdown"]
    assert "| CCC | Infrastructure | Storage |" in enriched["markdown"]
    assert "| 2024-01-10 | Hammer | WEAK_CONTEXT | UP_TREND_BULLISH_REVERSAL_WITHOUT_PIVOT_CONTEXT | 2024-01-10 | Bearish Engulfing | RELEVANT | UP_TREND_BEARISH_REVERSAL_AFTER_BOS_DOWN |" in enriched["markdown"]
    breakout_start = enriched["markdown"].index("## 12. Breakout Ticker Scanner")
    technical_section_start = enriched["markdown"].index("## 18. Technical Relevance Context")
    scanner_section_markdown = enriched["markdown"][breakout_start:technical_section_start]
    assert "NOISE_REASON" not in scanner_section_markdown


def test_daily_trigger_section_renders_markdown_csv_and_summary(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    _update_ticker_fields(
        analysis_db,
        ticker="AAA",
        signal_date="2024-01-10",
        assignments={
            "pullback_signal": 1,
            "ticker_trend_state": "UP",
            "latest_bos_event_type": "BOS_UP",
            "latest_bos_freshness": "FRESH",
            "latest_reset_reason": None,
            "latest_reset_freshness": None,
        },
    )

    conn = _connect_relevance_db(analysis_db)
    _insert_relevance_run(conn, "REL_DAILY_TRIGGER")
    _insert_relevance_record(
        conn,
        run_id="REL_DAILY_TRIGGER",
        ticker="AAA",
        signal_date="2024-01-10",
        signal_name="Hammer",
        relevance_class="RELEVANT",
        relevance_reason="UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW",
    )
    conn.commit()
    conn.close()

    result = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
        technical_relevance_run_id="REL_DAILY_TRIGGER",
    )

    assert "## 15. Daily Triggers" in result["markdown"]
    assert "section;daily_triggers" in result["csv"]
    assert result["summary"]["daily_trigger_section_enabled"] == 1
    assert "daily_buy_trigger_count" in result["summary"]


def test_daily_triggers_cover_all_states_and_protective_precedence(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    _update_ticker_fields(
        analysis_db,
        ticker="AAA",
        signal_date="2024-01-10",
        assignments={
            "pullback_signal": 1,
            "ticker_trend_state": "UP",
            "latest_bos_event_type": "BOS_UP",
            "latest_bos_freshness": "FRESH",
            "latest_reset_reason": None,
            "latest_reset_freshness": None,
        },
    )
    _update_ticker_fields(
        analysis_db,
        ticker="BBB",
        signal_date="2024-01-10",
        assignments={
            "pullback_signal": 1,
            "ticker_trend_state": "UP",
            "bearish_candle_signal": 1,
            "exit_risk_signal": 1,
            "exit_risk_severity": "HIGH",
            "exit_reason": "close_below_ema20",
            "latest_bos_event_type": "BOS_DOWN",
            "latest_bos_freshness": "FRESH",
            "latest_reset_reason": "RESET",
            "latest_reset_freshness": "FRESH",
        },
    )
    _update_ticker_fields(
        analysis_db,
        ticker="CCC",
        signal_date="2024-01-10",
        assignments={
            "price_data_status": "OK",
            "close": 90.0,
            "exit_risk_signal": 1,
            "exit_risk_severity": "MEDIUM",
            "exit_reason": "close_below_ema20",
            "ticker_trend_state": "NEUTRAL",
            "latest_bos_event_type": None,
            "latest_bos_freshness": None,
            "latest_reset_reason": None,
            "latest_reset_freshness": None,
        },
    )
    _update_ticker_fields(
        analysis_db,
        ticker="DDD",
        signal_date="2024-01-10",
        assignments={
            "close": 100.0,
            "price_data_status": "OK",
            "pullback_signal": 0,
            "breakout_signal": 0,
            "exit_risk_signal": 0,
            "exit_risk_severity": None,
            "exit_reason": None,
            "ticker_trend_state": "NEUTRAL",
            "distance_to_ema20_pct": -0.01,
            "latest_bos_event_type": "BOS_DOWN",
            "latest_bos_freshness": "STALE",
            "latest_reset_reason": None,
            "latest_reset_freshness": None,
        },
    )

    conn = _connect_relevance_db(analysis_db)
    _insert_relevance_run(conn, "REL_DAILY_STATES")
    _insert_relevance_record(
        conn,
        run_id="REL_DAILY_STATES",
        ticker="AAA",
        signal_date="2024-01-10",
        signal_name="Hammer",
        relevance_class="RELEVANT",
        relevance_reason="UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_DAILY_STATES",
        ticker="BBB",
        signal_date="2024-01-10",
        signal_name="Bearish Engulfing",
        relevance_class="RELEVANT",
        relevance_reason="DOWN_TREND_BEARISH_REVERSAL_AFTER_BREAK",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_DAILY_STATES",
        ticker="CCC",
        signal_date="2024-01-10",
        signal_name="Bearish Divergence",
        relevance_class="RELEVANT",
        relevance_reason="NEAR_LOWER_HIGH_WITH_BEARISH_CONTEXT",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_DAILY_STATES",
        ticker="DDD",
        signal_date="2024-01-10",
        signal_name="Hammer",
        relevance_class="WEAK_CONTEXT",
        relevance_reason="WEAK_BULLISH_CONTEXT",
    )
    conn.commit()
    conn.close()

    result = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
        technical_relevance_run_id="REL_DAILY_STATES",
    )

    csv_lines = result["csv"].splitlines()
    section_index = csv_lines.index("section;daily_triggers")
    header = csv_lines[section_index + 1].split(";")[1:]
    rows = {}
    for line in csv_lines[section_index + 2 :]:
        if not line or line.startswith("section;") or line.startswith("Datacenter Taxonomy Listing;"):
            break
        parts = line.split(";")
        row = dict(zip(header, parts[1:]))
        rows[row["ticker"]] = row

    assert rows["AAA"]["daily_trigger_state"] == "BUY_TRIGGER"
    assert rows["BBB"]["daily_trigger_state"] == "STOP_TRIGGER"
    assert rows["CCC"]["daily_trigger_state"] == "SELL_TRIGGER"
    assert rows["DDD"]["daily_trigger_state"] == "EXIT_WATCH"
    assert rows["BBB"]["next_action"] == "CHECK_STOP_OR_EXIT"
    assert rows["AAA"]["next_action"] == "REVIEW_WITH_ROLLING_CONTEXT"

    assert result["summary"]["daily_stop_trigger_count"] == 1
    assert result["summary"]["daily_sell_trigger_count"] == 1
    assert result["summary"]["daily_exit_watch_count"] == 1
    assert result["summary"]["daily_buy_trigger_count"] == 1
    assert result["summary"]["daily_buy_watch_count"] == 0
    assert result["summary"]["daily_no_trigger_count"] == 0
    assert result["summary"]["daily_trigger_insufficient_data_count"] == 0


def test_daily_trigger_handles_buy_watch_no_trigger_and_insufficient_data(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    _update_ticker_fields(
        analysis_db,
        ticker="AAA",
        signal_date="2024-01-10",
        assignments={
            "pullback_signal": 1,
            "ticker_trend_state": "NEUTRAL",
            "latest_bos_event_type": None,
            "latest_bos_freshness": None,
            "latest_reset_reason": None,
            "latest_reset_freshness": None,
            "exit_risk_signal": 0,
            "exit_risk_severity": None,
            "exit_reason": None,
        },
    )
    _update_ticker_fields(
        analysis_db,
        ticker="BBB",
        signal_date="2024-01-10",
        assignments={
            "pullback_signal": 0,
            "breakout_signal": 0,
            "fast_ema10_pullback_signal": 0,
            "conservative_ema20_pullback_signal": 0,
            "bullish_candle_signal": 0,
            "bullish_divergence_signal": 0,
            "hidden_bullish_divergence_signal": 0,
            "exit_risk_signal": 0,
            "exit_risk_severity": None,
            "exit_reason": None,
            "distance_to_ema10_pct": 0.08,
            "distance_to_ema20_pct": 0.08,
            "latest_bos_event_type": "BOS_UP",
            "latest_bos_freshness": "FRESH",
            "latest_reset_reason": None,
            "latest_reset_freshness": None,
            "ticker_trend_state": "UP",
        },
    )
    _update_ticker_fields(
        analysis_db,
        ticker="CCC",
        signal_date="2024-01-10",
        assignments={
            "price_data_status": "OK",
            "close": 90.0,
            "pullback_signal": 1,
            "ticker_trend_state": "UP",
            "bearish_candle_signal": 0,
            "bearish_divergence_signal": 0,
            "hidden_bearish_divergence_signal": 0,
            "latest_bos_event_type": "BOS_DOWN",
            "latest_bos_freshness": "STALE",
            "latest_reset_reason": None,
            "latest_reset_freshness": None,
            "exit_risk_signal": 0,
            "exit_risk_severity": None,
            "exit_reason": None,
        },
    )

    result = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
    )

    csv_lines = result["csv"].splitlines()
    section_index = csv_lines.index("section;daily_triggers")
    header = csv_lines[section_index + 1].split(";")[1:]
    rows = {}
    for line in csv_lines[section_index + 2 :]:
        if not line or line.startswith("section;") or line.startswith("Datacenter Taxonomy Listing;"):
            break
        parts = line.split(";")
        row = dict(zip(header, parts[1:]))
        rows[row["ticker"]] = row

    assert rows["AAA"]["daily_trigger_state"] == "BUY_WATCH"
    assert rows["BBB"]["daily_trigger_state"] == "NO_TRIGGER"
    assert rows["CCC"]["daily_trigger_state"] == "EXIT_WATCH"
    assert rows["DDD"]["daily_trigger_state"] == "INSUFFICIENT_DATA"


def test_fresh_bos_down_blocks_buy_trigger_but_stale_bos_down_does_not(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    _update_ticker_fields(
        analysis_db,
        ticker="AAA",
        signal_date="2024-01-10",
        assignments={
            "pullback_signal": 1,
            "ticker_trend_state": "UP",
            "latest_bos_event_type": "BOS_DOWN",
            "latest_bos_freshness": "FRESH",
            "exit_risk_signal": 0,
            "exit_risk_severity": None,
            "exit_reason": None,
        },
    )
    _update_ticker_fields(
        analysis_db,
        ticker="BBB",
        signal_date="2024-01-10",
        assignments={
            "pullback_signal": 1,
            "ticker_trend_state": "UP",
            "latest_bos_event_type": "BOS_DOWN",
            "latest_bos_freshness": "STALE",
            "exit_risk_signal": 0,
            "exit_risk_severity": None,
            "exit_reason": None,
        },
    )

    conn = _connect_relevance_db(analysis_db)
    _insert_relevance_run(conn, "REL_FRESHNESS")
    _insert_relevance_record(
        conn,
        run_id="REL_FRESHNESS",
        ticker="AAA",
        signal_date="2024-01-10",
        signal_name="Hammer",
        relevance_class="RELEVANT",
        relevance_reason="UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_FRESHNESS",
        ticker="BBB",
        signal_date="2024-01-10",
        signal_name="Hammer",
        relevance_class="RELEVANT",
        relevance_reason="UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW",
    )
    conn.commit()
    conn.close()

    result = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
        technical_relevance_run_id="REL_FRESHNESS",
    )

    csv_lines = result["csv"].splitlines()
    section_index = csv_lines.index("section;daily_triggers")
    header = csv_lines[section_index + 1].split(";")[1:]
    rows = {}
    for line in csv_lines[section_index + 2 :]:
        if not line or line.startswith("section;") or line.startswith("Datacenter Taxonomy Listing;"):
            break
        parts = line.split(";")
        row = dict(zip(header, parts[1:]))
        rows[row["ticker"]] = row

    assert rows["AAA"]["daily_trigger_state"] != "BUY_TRIGGER"
    assert rows["BBB"]["daily_trigger_state"] == "BUY_TRIGGER"


def test_daily_high_severity_close_below_ema20_alone_is_sell_trigger_not_stop(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    _update_ticker_fields(
        analysis_db,
        ticker="AAA",
        signal_date="2024-01-10",
        assignments={
            "exit_risk_signal": 1,
            "exit_risk_severity": "HIGH",
            "exit_reason": "close_below_ema20",
            "ticker_trend_state": "UP",
            "latest_structure_label": "HL",
            "latest_bos_event_type": None,
            "latest_bos_freshness": None,
            "latest_reset_reason": None,
            "latest_reset_freshness": None,
        },
    )

    result = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
    )
    section = result["csv"].split("section;daily_triggers\n", 1)[1]
    assert "daily_triggers;AAA;SELL_TRIGGER;" in section
    assert "HIGH_EXIT_RISK_WITHOUT_FULL_STOP_CONFIRMATION" in section


def test_daily_high_severity_with_close_below_ema20_and_return_10d_lt_minus_8pct_is_stop(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    _update_ticker_fields(
        analysis_db,
        ticker="AAA",
        signal_date="2024-01-10",
        assignments={
            "exit_risk_signal": 1,
            "exit_risk_severity": "HIGH",
            "exit_reason": "close_below_ema20;return_10d_lt_minus_8pct",
            "ticker_trend_state": "UP",
            "latest_structure_label": "HL",
            "latest_bos_event_type": None,
            "latest_bos_freshness": None,
            "latest_reset_reason": None,
            "latest_reset_freshness": None,
        },
    )

    result = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
    )
    section = result["csv"].split("section;daily_triggers\n", 1)[1]
    assert "daily_triggers;AAA;STOP_TRIGGER;" in section
    assert "HIGH_RISK_WITH_STRUCTURAL_BREAKDOWN" in section


def test_daily_high_severity_with_ll_or_down_lh_structure_is_stop(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    _update_ticker_fields(
        analysis_db,
        ticker="AAA",
        signal_date="2024-01-10",
        assignments={
            "exit_risk_signal": 1,
            "exit_risk_severity": "HIGH",
            "exit_reason": "close_below_ema20",
            "ticker_trend_state": "DOWN",
            "latest_structure_label": "LH",
        },
    )
    _update_ticker_fields(
        analysis_db,
        ticker="BBB",
        signal_date="2024-01-10",
        assignments={
            "exit_risk_signal": 1,
            "exit_risk_severity": "HIGH",
            "exit_reason": "close_below_ema20",
            "ticker_trend_state": "UP",
            "latest_structure_label": "LL",
        },
    )

    result = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
    )
    section = result["csv"].split("section;daily_triggers\n", 1)[1]
    assert "daily_triggers;AAA;STOP_TRIGGER;" in section
    assert "daily_triggers;BBB;STOP_TRIGGER;" in section


def test_daily_high_severity_with_fresh_bos_down_or_reset_is_stop(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    _update_ticker_fields(
        analysis_db,
        ticker="AAA",
        signal_date="2024-01-10",
        assignments={
            "exit_risk_signal": 1,
            "exit_risk_severity": "HIGH",
            "exit_reason": "close_below_ema20",
            "latest_bos_event_type": "BOS_DOWN",
            "latest_bos_freshness": "FRESH",
            "latest_reset_reason": None,
            "latest_reset_freshness": None,
        },
    )
    _update_ticker_fields(
        analysis_db,
        ticker="BBB",
        signal_date="2024-01-10",
        assignments={
            "exit_risk_signal": 1,
            "exit_risk_severity": "HIGH",
            "exit_reason": "close_below_ema20",
            "latest_bos_event_type": None,
            "latest_bos_freshness": None,
            "latest_reset_reason": "RESET",
            "latest_reset_freshness": "FRESH",
        },
    )

    result = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
    )
    section = result["csv"].split("section;daily_triggers\n", 1)[1]
    assert "daily_triggers;AAA;STOP_TRIGGER;" in section
    assert "daily_triggers;BBB;STOP_TRIGGER;" in section


def test_daily_extreme_or_critical_exit_severity_is_stop(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    _update_ticker_fields(
        analysis_db,
        ticker="AAA",
        signal_date="2024-01-10",
        assignments={"exit_risk_signal": 1, "exit_risk_severity": "EXTREME"},
    )
    _update_ticker_fields(
        analysis_db,
        ticker="BBB",
        signal_date="2024-01-10",
        assignments={"exit_risk_signal": 1, "exit_risk_severity": "CRITICAL"},
    )

    result = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
    )
    section = result["csv"].split("section;daily_triggers\n", 1)[1]
    assert "daily_triggers;AAA;STOP_TRIGGER;" in section
    assert "daily_triggers;BBB;STOP_TRIGGER;" in section


def test_daily_fresh_bos_down_without_reset_is_sell_but_with_reset_is_stop(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    _update_ticker_fields(
        analysis_db,
        ticker="AAA",
        signal_date="2024-01-10",
        assignments={
            "exit_risk_signal": 1,
            "exit_risk_severity": "MEDIUM",
            "latest_bos_event_type": "BOS_DOWN",
            "latest_bos_freshness": "FRESH",
            "latest_reset_reason": None,
            "latest_reset_freshness": None,
        },
    )
    _update_ticker_fields(
        analysis_db,
        ticker="BBB",
        signal_date="2024-01-10",
        assignments={
            "exit_risk_signal": 1,
            "exit_risk_severity": "MEDIUM",
            "latest_bos_event_type": "BOS_DOWN",
            "latest_bos_freshness": "FRESH",
            "latest_reset_reason": "RESET",
            "latest_reset_freshness": "FRESH",
        },
    )

    result = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
    )
    section = result["csv"].split("section;daily_triggers\n", 1)[1]
    assert "daily_triggers;AAA;SELL_TRIGGER;" in section
    assert "daily_triggers;BBB;STOP_TRIGGER;" in section


def test_daily_relevant_bearish_context_with_and_without_current_high_risk_maps_to_stop_or_sell(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _seed_report_db(analysis_db)
    _update_ticker_fields(
        analysis_db,
        ticker="AAA",
        signal_date="2024-01-10",
        assignments={"exit_risk_signal": 1, "exit_risk_severity": "HIGH"},
    )
    _update_ticker_fields(
        analysis_db,
        ticker="BBB",
        signal_date="2024-01-10",
        assignments={"exit_risk_signal": 0, "exit_risk_severity": None},
    )
    conn = _connect_relevance_db(analysis_db)
    _insert_relevance_run(conn, "REL_DAILY_BEARISH")
    _insert_relevance_record(
        conn,
        run_id="REL_DAILY_BEARISH",
        ticker="AAA",
        signal_date="2024-01-10",
        signal_name="Bearish Engulfing",
        relevance_class="RELEVANT",
        relevance_reason="DOWN_TREND_BEARISH_REVERSAL_AFTER_BREAK",
    )
    _insert_relevance_record(
        conn,
        run_id="REL_DAILY_BEARISH",
        ticker="BBB",
        signal_date="2024-01-10",
        signal_name="Bearish Engulfing",
        relevance_class="RELEVANT",
        relevance_reason="DOWN_TREND_BEARISH_REVERSAL_AFTER_BREAK",
    )
    conn.commit()
    conn.close()

    result = write_daily_swing_signal_report(
        analysis_db_path=analysis_db,
        signal_date="2024-01-10",
        generated_at_utc="2026-05-17T12:00:00Z",
        technical_relevance_run_id="REL_DAILY_BEARISH",
    )
    section = result["csv"].split("section;daily_triggers\n", 1)[1]
    assert "daily_triggers;AAA;STOP_TRIGGER;" in section
    assert "daily_triggers;BBB;SELL_TRIGGER;" in section
