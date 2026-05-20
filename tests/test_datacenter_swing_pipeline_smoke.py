from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.persistence import run_datacenter_indices
from analysis.datacenter_indices.swing_group_persistence import (
    persist_datacenter_group_overheat_risk,
    persist_datacenter_group_swing_signals,
    persist_datacenter_group_timing_states,
)
from analysis.datacenter_indices.swing_group_synthetic_ohlc import (
    persist_datacenter_group_relative_ohlc,
    persist_datacenter_group_structure,
    persist_datacenter_group_synthetic_ohlc,
)
from analysis.datacenter_indices.swing_ticker_persistence import (
    persist_datacenter_ticker_scanner_signals,
    persist_datacenter_ticker_swing_snapshots,
)
from analysis.datacenter_indices.swing_weekly_report import load_weekly_swing_report_data
from run_datacenter_daily_signal_report import main as run_datacenter_daily_signal_report_main
from run_datacenter_weekly_swing_report import main as run_datacenter_weekly_swing_report_main


TAXONOMY_VERSION = "DC_TAXONOMY_V1"
MARKET = "usa"
CREATED_AT_UTC = "2026-05-17T12:00:00Z"
UNIVERSE_TICKERS = ("AAA", "AAB", "AAC", "BBA", "BBB", "BBC")
BENCHMARK_TICKERS = ("SPY", "QQQ")


def _write_taxonomy_csv(tmp_path):
    path = tmp_path / "taxonomy.csv"
    path.write_text(
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Compute,AI Chips,CORE,1,1.0,
DC_TAXONOMY_V1,AAB,Compute,AI Chips,CORE,1,1.0,
DC_TAXONOMY_V1,AAC,Compute,AI Chips,CORE,1,1.0,
DC_TAXONOMY_V1,BBA,Infrastructure,Storage Systems,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Infrastructure,Storage Systems,CORE,1,1.0,
DC_TAXONOMY_V1,BBC,Infrastructure,Storage Systems,CORE,1,1.0,
""",
        encoding="utf-8",
    )
    return path


def _business_dates(start_date: date, count: int) -> list[str]:
    dates: list[str] = []
    current = start_date
    while len(dates) < count:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates


def _create_price_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT,
                pvm TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                market TEXT
            )
            """
        )
        conn.commit()


def _create_analysis_db(path):
    DatabaseManager(str(path)).close()
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS stock_dow_structure_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                market TEXT NULL,
                event_date TEXT NOT NULL,
                confirmed_as_of_date TEXT NOT NULL,
                event_type TEXT NOT NULL,
                dow_label_high TEXT NULL,
                dow_label_low TEXT NULL,
                trend_state TEXT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS divergence_data (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                bullish_strength REAL,
                bearish_strength REAL,
                hidden_bullish_strength REAL,
                hidden_bearish_strength REAL,
                rsi REAL,
                is_bullish_divergence_r3 INTEGER,
                is_bearish_divergence_r3 INTEGER,
                is_hidden_bullish_divergence_r3 INTEGER,
                is_hidden_bearish_divergence_r3 INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                pattern TEXT,
                signal_strength REAL,
                rsi14 REAL
            )
            """
        )
        conn.commit()


def _insert_price_rows(path, rows):
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def _insert_dow_event(path, row):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO stock_dow_structure_events (
                ticker, market, event_date, confirmed_as_of_date, event_type,
                dow_label_high, dow_label_low, trend_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()


def _insert_divergence_row(path, row):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO divergence_data (
                ticker, date, bullish_strength, bearish_strength,
                hidden_bullish_strength, hidden_bearish_strength, rsi,
                is_bullish_divergence_r3, is_bearish_divergence_r3,
                is_hidden_bullish_divergence_r3, is_hidden_bearish_divergence_r3
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()


def _insert_finding(path, row):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14)
            VALUES (?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()


def _close_for_ticker(ticker: str, index: int, total_count: int) -> float:
    if ticker == "AAA":
        value = 50.0 + index * 0.42
        if index >= total_count - 3:
            value += 1.2 * (index - (total_count - 3) + 1)
        return round(value, 4)
    if ticker == "AAB":
        value = 46.0 + index * 0.34
        if index >= total_count - 6:
            value -= 0.35 * (index - (total_count - 6) + 1)
        return round(value, 4)
    if ticker == "AAC":
        return round(44.0 + index * 0.30, 4)
    if ticker == "BBA":
        value = 58.0 + index * 0.22
        if index >= total_count - 8:
            value -= 0.30 * (index - (total_count - 8) + 1)
        return round(value, 4)
    if ticker == "BBB":
        value = 56.0 + index * 0.20
        if index >= total_count - 10:
            value -= 0.45 * (index - (total_count - 10) + 1)
        return round(value, 4)
    if ticker == "BBC":
        value = 54.0 + index * 0.18
        if index >= total_count - 12:
            value -= 0.85 * (index - (total_count - 12) + 1)
        return round(value, 4)
    if ticker == "SPY":
        return round(420.0 + index * 0.25, 4)
    if ticker == "QQQ":
        return round(360.0 + index * 0.28, 4)
    raise ValueError(f"Unexpected ticker: {ticker}")


def _volume_for_ticker(ticker: str, index: int, total_count: int) -> int:
    base = {
        "AAA": 100_000,
        "AAB": 95_000,
        "AAC": 90_000,
        "BBA": 85_000,
        "BBB": 80_000,
        "BBC": 75_000,
        "SPY": 500_000,
        "QQQ": 450_000,
    }[ticker]
    value = base + index * 500
    if ticker == "AAA" and index >= total_count - 3:
        value += 70_000
    return value


def _seed_price_db(path, dates: list[str]):
    rows = []
    all_tickers = UNIVERSE_TICKERS + BENCHMARK_TICKERS
    total_count = len(dates)
    for ticker in all_tickers:
        previous_close: float | None = None
        for index, current_date in enumerate(dates):
            close = _close_for_ticker(ticker, index, total_count)
            open_value = close - 0.35 if previous_close is None else previous_close + (close - previous_close) * 0.4
            high_value = max(open_value, close) + 0.8
            low_value = min(open_value, close) - 0.8
            volume = _volume_for_ticker(ticker, index, total_count)
            rows.append(
                (
                    ticker,
                    current_date,
                    round(open_value, 4),
                    round(high_value, 4),
                    round(low_value, 4),
                    close,
                    volume,
                    MARKET,
                )
            )
            previous_close = close
    _insert_price_rows(path, rows)


def _seed_analysis_outputs(path, signal_dates: list[str]):
    dow_rows = [
        ("AAA", MARKET, signal_dates[0], signal_dates[0], "PIVOT_HIGH", "HH", None, "UP"),
        ("AAB", MARKET, signal_dates[1], signal_dates[1], "PIVOT_LOW", None, "HL", "UP"),
        ("AAC", MARKET, signal_dates[0], signal_dates[0], "PIVOT_HIGH", "HH", None, "UP"),
        ("BBA", MARKET, signal_dates[1], signal_dates[1], "PIVOT_HIGH", "LH", None, "DOWN"),
        ("BBB", MARKET, signal_dates[2], signal_dates[2], "PIVOT_LOW", None, "LL", "DOWN"),
        ("BBC", MARKET, signal_dates[-2], signal_dates[-2], "PIVOT_LOW", None, "LL", "DOWN"),
    ]
    for row in dow_rows:
        _insert_dow_event(path, row)

    for ticker in UNIVERSE_TICKERS:
        for current_date in signal_dates:
            if ticker in {"AAA", "AAB", "AAC"}:
                divergence_row = (
                    ticker,
                    current_date,
                    1.2,
                    0.0,
                    0.6 if ticker == "AAB" else 0.0,
                    0.0,
                    58.0,
                    1,
                    0,
                    1 if ticker == "AAB" else 0,
                    0,
                )
            else:
                divergence_row = (
                    ticker,
                    current_date,
                    0.0,
                    1.0 if ticker == "BBC" and current_date == signal_dates[-1] else 0.4,
                    0.0,
                    0.5 if ticker == "BBC" else 0.0,
                    42.0,
                    0,
                    1 if ticker == "BBC" and current_date == signal_dates[-1] else 0,
                    0,
                    1 if ticker == "BBC" and current_date == signal_dates[-1] else 0,
                )
            _insert_divergence_row(path, divergence_row)

    candle_rows = [
        ("AAA", signal_dates[-1], "Bullish Engulfing", 0.9, 55.0),
        ("AAB", signal_dates[-1], "Hammer", 0.8, 50.0),
        ("BBC", signal_dates[-1], "Shooting Star", 0.9, 35.0),
        ("BBB", signal_dates[-2], "Bearish Engulfing", 0.7, 40.0),
    ]
    for row in candle_rows:
        _insert_finding(path, row)


def _count_rows(path, table_name: str) -> int:
    with sqlite3.connect(path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]


def test_datacenter_swing_pipeline_smoke(tmp_path, capsys):
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    daily_output_md = tmp_path / "daily_report.md"
    weekly_output_md = tmp_path / "weekly_report.md"
    daily_expected_output_md = tmp_path / "daily_report_1200.md"
    weekly_expected_output_md = tmp_path / "weekly_report_1200.md"

    all_dates = _business_dates(date(2025, 1, 2), 220)
    signal_dates = all_dates[-7:]
    weekly_expected_dates = signal_dates[-5:]
    start_date = all_dates[0]
    end_date = signal_dates[-1]

    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    _seed_price_db(price_db, all_dates)
    _seed_analysis_outputs(analysis_db, signal_dates)

    index_summary = run_datacenter_indices(
        ohlcv_db_path=price_db,
        analysis_db_path=analysis_db,
        taxonomy_csv=taxonomy_csv,
        taxonomy_version=TAXONOMY_VERSION,
        market=MARKET,
        index_base_date=start_date,
        start_date=start_date,
        end_date=end_date,
        write_mode="replace-range",
        run_id="smoke-index",
        created_at_utc=CREATED_AT_UTC,
    )
    assert index_summary["rows_inserted"] > 0
    assert _count_rows(analysis_db, "dc_group_index_daily") > 0

    for current_date in signal_dates:
        ticker_summary = persist_datacenter_ticker_swing_snapshots(
            analysis_db_path=analysis_db,
            price_db_path=price_db,
            taxonomy_csv_path=taxonomy_csv,
            as_of_date=current_date,
            market=MARKET,
            signal_version="DC_SWING_SIGNAL_V1",
            run_id=f"smoke-ticker-{current_date}",
            created_at_utc=CREATED_AT_UTC,
            write_mode="replace-date",
        )
        assert ticker_summary["inserted_count"] > 0

    ticker_row_count = _count_rows(analysis_db, "dc_ticker_swing_signal_daily")
    assert ticker_row_count >= len(signal_dates) * len(UNIVERSE_TICKERS)

    for current_date in signal_dates:
        group_summary = persist_datacenter_group_swing_signals(
            analysis_db_path=analysis_db,
            taxonomy_csv_path=taxonomy_csv,
            signal_date=current_date,
            signal_version="DC_SWING_SIGNAL_V1",
            run_id=f"smoke-group-{current_date}",
            created_at_utc=CREATED_AT_UTC,
            write_mode="replace-date",
        )
        assert group_summary["inserted_count"] > 0

    group_row_count = _count_rows(analysis_db, "dc_group_swing_signal_daily")
    assert group_row_count >= len(signal_dates) * 5

    synthetic_summary = persist_datacenter_group_synthetic_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date=start_date,
        end_date=end_date,
        market=MARKET,
        calc_version="DC_SWING_OHLC_V1",
        run_id="smoke-synth-base",
        created_at_utc=CREATED_AT_UTC,
        write_mode="replace-range",
    )
    assert synthetic_summary["inserted_count"] > 0
    assert _count_rows(analysis_db, "dc_group_synthetic_ohlc_daily") > 0

    relative_summary = persist_datacenter_group_relative_ohlc(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        start_date=start_date,
        end_date=end_date,
        market=MARKET,
        calc_version="DC_SWING_OHLC_V1",
        run_id="smoke-synth-relative",
        created_at_utc=CREATED_AT_UTC,
        relative_base_window=20,
        write_mode="replace-relative-range",
    )
    assert relative_summary["updated_count"] > 0

    structure_summary = persist_datacenter_group_structure(
        analysis_db_path=analysis_db,
        start_date=start_date,
        end_date=end_date,
        calc_version="DC_SWING_OHLC_V1",
        run_id="smoke-synth-structure",
        created_at_utc=CREATED_AT_UTC,
        write_mode="replace-structure-range",
    )
    assert structure_summary["updated_count"] > 0

    timing_summary = persist_datacenter_group_timing_states(
        analysis_db_path=analysis_db,
        start_date=signal_dates[0],
        end_date=end_date,
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="smoke-timing",
        created_at_utc=CREATED_AT_UTC,
        write_mode="replace-timing-range",
    )
    assert timing_summary["updated_count"] > 0

    overheat_summary = persist_datacenter_group_overheat_risk(
        analysis_db_path=analysis_db,
        start_date=signal_dates[0],
        end_date=end_date,
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="smoke-overheat",
        created_at_utc=CREATED_AT_UTC,
        write_mode="replace-overheat-range",
    )
    assert overheat_summary["updated_count"] > 0

    scanner_summary = persist_datacenter_ticker_scanner_signals(
        analysis_db_path=analysis_db,
        start_date=signal_dates[0],
        end_date=end_date,
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="smoke-scanner",
        created_at_utc=CREATED_AT_UTC,
        write_mode="replace-scanner-range",
    )
    assert scanner_summary["updated_count"] > 0

    with sqlite3.connect(analysis_db) as conn:
        timing_non_null = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_group_swing_signal_daily
            WHERE signal_date BETWEEN ? AND ?
              AND signal_version = 'DC_SWING_SIGNAL_V1'
              AND timing_state IS NOT NULL
            """,
            (signal_dates[0], end_date),
        ).fetchone()[0]
        overheat_non_null = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_group_swing_signal_daily
            WHERE signal_date BETWEEN ? AND ?
              AND signal_version = 'DC_SWING_SIGNAL_V1'
              AND overheat_risk_level IS NOT NULL
            """,
            (signal_dates[0], end_date),
        ).fetchone()[0]
        scanner_null_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_ticker_swing_signal_daily
            WHERE signal_date BETWEEN ? AND ?
              AND signal_version = 'DC_SWING_SIGNAL_V1'
              AND (
                  breakout_signal IS NULL OR
                  fast_ema10_pullback_signal IS NULL OR
                  conservative_ema20_pullback_signal IS NULL OR
                  pullback_signal IS NULL OR
                  exit_risk_signal IS NULL
              )
            """,
            (signal_dates[0], end_date),
        ).fetchone()[0]
        before_report_counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "dc_group_index_daily",
                "dc_ticker_swing_signal_daily",
                "dc_group_swing_signal_daily",
                "dc_group_synthetic_ohlc_daily",
            )
        }
    assert timing_non_null > 0
    assert overheat_non_null > 0
    assert scanner_null_count == 0

    daily_exit_code = run_datacenter_daily_signal_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--signal-date",
            end_date,
            "--output-md",
            str(daily_output_md),
            "--generated-at-utc",
            CREATED_AT_UTC,
        ]
    )
    assert daily_exit_code == 0
    daily_stdout = capsys.readouterr().out
    assert "SUMMARY signal_date=" in daily_stdout

    weekly_exit_code = run_datacenter_weekly_swing_report_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--end-date",
            end_date,
            "--output-md",
            str(weekly_output_md),
            "--generated-at-utc",
            CREATED_AT_UTC,
        ]
    )
    assert weekly_exit_code == 0
    weekly_stdout = capsys.readouterr().out
    assert "SUMMARY valid_signal_dates_count=5" in weekly_stdout

    daily_markdown = daily_expected_output_md.read_text(encoding="utf-8")
    weekly_markdown = weekly_expected_output_md.read_text(encoding="utf-8")

    for heading in (
        "Datacenter Daily Swing Signal Report",
        "Dashboard",
        "Breakout Ticker Scanner",
        "Pullback Ticker Scanner",
        "Exit-Risk Ticker Scanner",
        "Missing / Incomplete Inputs Summary",
    ):
        assert heading in daily_markdown
    assert "Ecosystem row missing." not in daily_markdown
    assert "Missing required tables" not in daily_markdown

    for heading in (
        "Datacenter Rolling Swing Report",
        "Window type: last 5 valid trading days, not calendar week",
        "Window summary",
        "Repeated breakout tickers",
        "Repeated pullback tickers",
        "Repeated exit-risk tickers",
        "Missing / incomplete inputs summary",
    ):
        assert heading in weekly_markdown
    assert "INCOMPLETE WINDOW" not in weekly_markdown
    assert "Ecosystem row missing." not in weekly_markdown
    assert "Missing required tables" not in weekly_markdown

    weekly_report_data = load_weekly_swing_report_data(
        analysis_db_path=analysis_db,
        end_date=end_date,
        signal_version="DC_SWING_SIGNAL_V1",
        ohlc_calc_version="DC_SWING_OHLC_V1",
    )
    assert weekly_report_data["valid_signal_dates"] == weekly_expected_dates

    with sqlite3.connect(analysis_db) as conn:
        after_report_counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "dc_group_index_daily",
                "dc_ticker_swing_signal_daily",
                "dc_group_swing_signal_daily",
                "dc_group_synthetic_ohlc_daily",
            )
        }
    assert before_report_counts == after_report_counts
