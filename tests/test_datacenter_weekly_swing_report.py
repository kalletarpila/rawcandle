from __future__ import annotations

import sqlite3
import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_weekly_report import (
    build_markdown_weekly_swing_report,
    load_weekly_swing_report_data,
    write_weekly_swing_report,
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
        values[21:21] = [None, None]
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO dc_group_synthetic_ohlc_daily (
                ohlc_date, taxonomy_version, group_type, group_name,
                member_count, eligible_count, synthetic_open, synthetic_high, synthetic_low, synthetic_close,
                synthetic_volume, ma20, ema20, distance_to_ema20_pct, volatility_20d,
                pivot_radius, latest_pivot_high_date, latest_pivot_high_value, latest_pivot_low_date, latest_pivot_low_value,
                latest_structure_label, latest_structure_age_trading_days, latest_structure_freshness,
                trend_classification, relative_base_window, relative_open_20, relative_high_20,
                relative_low_20, relative_close_20, relative_upper_wick_20, relative_lower_wick_20,
                relative_close_extension_20, relative_high_extension_20, relative_low_extension_20,
                relative_eligible_count, data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                "HH" if index >= 2 else "HL", "UP" if index >= 3 else "NEUTRAL", 20, 1.01, 1.03, 0.99, 1.0 + index * 0.01, 0.02, 0.01,
                0.01 + index * 0.01, 0.02, -0.01, 4, "OK", "DC_SWING_OHLC_V1", "seed", "2026-05-17T10:00:00Z",
            ),
            (
                signal_date, "DC_TAXONOMY_V1", "layer", "Infrastructure",
                8, 7, 100.0, 101.0, 98.0, 100.0 + index,
                200000.0, 99.0, 99.5, 0.005 + index * 0.002, 0.08 + index * 0.005,
                10, "2024-01-01", 101.0, "2024-01-01", 97.0,
                None, None, 20, None, None, None, None, None, None,
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
        "# Datacenter Weekly Swing Report",
        "## 1. Title and run metadata",
        "## 2. Window summary",
        "## 3. Ecosystem 5-day change",
        "## 4. Overheat / rotation risk progression",
        "## 5. Subindustry timing persistence",
        "## 6. Subindustry improvement / deterioration",
        "## 7. Repeated breakout tickers",
        "## 8. Repeated pullback tickers",
        "## 9. Repeated exit-risk tickers",
        "## 10. Synthetic OHLC structure changes",
        "## 11. Data quality over the window",
        "## 12. Missing / incomplete inputs summary",
    ]:
        assert heading in markdown
    assert "Window type: last 5 valid trading days, not calendar week" in markdown
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
    assert "HIGH" in markdown


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
