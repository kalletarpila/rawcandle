import sqlite3

import pandas as pd

from analysis.analyzer import AnalysisEngine
from analysis.candlestick_patterns import (
    is_bearish_engulfing,
    is_bullish_abandoned_baby,
    is_dark_cloud_cover,
    is_evening_star,
    is_falling_three_methods,
    is_hanging_man,
    is_shooting_star,
)
from analysis.results_generator import ResultsGenerator
from analysis.run_analysis import run_candlestick_analysis
from results.excel_exporter import ExcelExporter


def _row(open_price, high, low, close):
    return pd.Series(
        {
            "Open": float(open_price),
            "High": float(high),
            "Low": float(low),
            "Close": float(close),
        }
    )


def _create_candles_test_dbs(tmp_path, rows):
    osake_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"

    with sqlite3.connect(osake_db) as conn:
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
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            CREATE TABLE divergence_data (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                bullish_strength REAL DEFAULT 0,
                bearish_strength REAL DEFAULT 0,
                rsi REAL,
                pivot2_date_r3 TEXT,
                is_bullish_divergence_r3 INTEGER DEFAULT 0,
                PRIMARY KEY (ticker, date)
            )
            """
        )

    return osake_db, analysis_db


def test_bearish_engulfing_detected():
    prev_row = _row(100.0, 105.0, 99.0, 104.0)
    row = _row(105.0, 106.0, 98.0, 99.0)

    assert is_bearish_engulfing(prev_row, row) == True


def test_shooting_star_detected():
    row = _row(100.2, 108.0, 99.95, 100.0)

    assert is_shooting_star(row) == True


def test_dark_cloud_cover_detected():
    prev_row = _row(100.0, 111.0, 99.0, 110.0)
    row = _row(111.0, 112.0, 103.0, 104.0)

    assert is_dark_cloud_cover(prev_row, row) == True


def test_evening_star_detected():
    df = pd.DataFrame(
        [
            {"Open": 100.0, "High": 111.0, "Low": 99.0, "Close": 110.0},
            {"Open": 111.0, "High": 113.0, "Low": 110.0, "Close": 112.0},
            {"Open": 111.0, "High": 112.0, "Low": 103.0, "Close": 104.0},
        ]
    )

    assert is_evening_star(df, 2) == True


def test_hanging_man_detected():
    row = _row(106.2, 106.3, 100.0, 106.0)

    assert is_hanging_man(row) == True


def test_bullish_abandoned_baby_detected():
    df = pd.DataFrame(
        [
            {"Open": 100.0, "High": 101.0, "Low": 89.0, "Close": 90.0},
            {"Open": 88.0, "High": 88.5, "Low": 87.5, "Close": 88.1},
            {"Open": 89.0, "High": 100.0, "Low": 89.0, "Close": 99.0},
        ]
    )

    assert is_bullish_abandoned_baby(df, 2) == True


def test_falling_three_methods_detected():
    df = pd.DataFrame(
        [
            {"Open": 110.0, "High": 111.0, "Low": 99.0, "Close": 100.0},
            {"Open": 101.0, "High": 104.0, "Low": 101.0, "Close": 103.0},
            {"Open": 102.5, "High": 104.5, "Low": 102.0, "Close": 104.0},
            {"Open": 103.5, "High": 104.0, "Low": 102.0, "Close": 103.0},
            {"Open": 102.0, "High": 103.0, "Low": 94.0, "Close": 95.0},
        ]
    )

    assert is_falling_three_methods(df, 4) == True


def test_bearish_engulfing_not_detected_without_full_body_engulf():
    prev_row = _row(100.0, 105.0, 99.0, 104.0)
    row = _row(103.0, 106.0, 98.0, 101.0)

    assert is_bearish_engulfing(prev_row, row) == False


def test_shooting_star_not_detected_when_upper_shadow_too_small():
    row = _row(100.0, 101.0, 99.5, 100.5)

    assert is_shooting_star(row) == False


def test_hanging_man_not_detected_when_lower_shadow_too_small():
    row = _row(106.0, 106.4, 105.6, 106.2)

    assert is_hanging_man(row) == False


def test_run_candlestick_analysis_detects_bearish_patterns_with_downtrend_filter_enabled(
    tmp_path,
):
    osake_db, analysis_db = _create_candles_test_dbs(
        tmp_path,
        [
            ("TEST", "2026-03-01", 100.0, 105.0, 99.0, 104.0, 1_000, "usa"),
            ("TEST", "2026-03-02", 105.0, 106.0, 98.0, 99.0, 1_200, "usa"),
            ("TEST", "2026-03-03", 100.2, 108.0, 99.95, 100.0, 1_300, "usa"),
            ("TEST", "2026-03-04", 100.0, 111.0, 99.0, 110.0, 1_100, "usa"),
            ("TEST", "2026-03-05", 111.0, 112.0, 103.0, 104.0, 1_100, "usa"),
            ("TEST", "2026-03-06", 100.0, 111.0, 99.0, 110.0, 1_100, "usa"),
            ("TEST", "2026-03-07", 111.0, 113.0, 110.0, 112.0, 1_050, "usa"),
            ("TEST", "2026-03-08", 111.0, 112.0, 103.0, 104.0, 1_250, "usa"),
            ("TEST", "2026-03-09", 106.2, 106.3, 100.0, 106.0, 1_000, "usa"),
        ],
    )

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=[
            "Bearish Engulfing",
            "Shooting Star",
            "Dark Cloud Cover",
            "Evening Star",
            "Hanging Man",
        ],
        start_date="2026-03-01",
        end_date="2026-03-09",
        progress_callback=None,
        downtrend_filter=True,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    detected_patterns = {
        finding["pattern"]
        for findings in results.values()
        for finding in findings
    }
    assert "Bearish Engulfing" in detected_patterns
    assert "Shooting Star" in detected_patterns
    assert "Dark Cloud Cover" in detected_patterns
    assert "Evening Star" in detected_patterns
    assert "Hanging Man" in detected_patterns


def test_run_candlestick_analysis_detects_new_patterns_without_downtrend_filter(tmp_path):
    osake_db, analysis_db = _create_candles_test_dbs(
        tmp_path,
        [
            ("TEST", "2026-03-01", 100.0, 101.0, 89.0, 90.0, 1_000, "usa"),
            ("TEST", "2026-03-02", 88.0, 88.5, 87.5, 88.1, 1_050, "usa"),
            ("TEST", "2026-03-03", 89.0, 100.0, 89.0, 99.0, 1_300, "usa"),
            ("TEST", "2026-03-04", 110.0, 111.0, 99.0, 100.0, 1_400, "usa"),
            ("TEST", "2026-03-05", 101.0, 104.0, 101.0, 103.0, 950, "usa"),
            ("TEST", "2026-03-06", 102.5, 104.5, 102.0, 104.0, 900, "usa"),
            ("TEST", "2026-03-07", 103.5, 104.0, 102.0, 103.0, 920, "usa"),
            ("TEST", "2026-03-08", 102.0, 103.0, 94.0, 95.0, 1_600, "usa"),
        ],
    )

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=[
            "Bullish Abandoned Baby",
            "Falling Three Methods",
        ],
        start_date="2026-03-01",
        end_date="2026-03-08",
        progress_callback=None,
        downtrend_filter=False,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    detected_patterns = {
        finding["pattern"]
        for findings in results.values()
        for finding in findings
    }
    assert "Bullish Abandoned Baby" in detected_patterns
    assert "Falling Three Methods" in detected_patterns


def test_run_candlestick_analysis_detects_first_chart_pattern_package(tmp_path):
    osake_db, analysis_db = _create_candles_test_dbs(
        tmp_path,
        [
            ("TEST", "2026-03-01", 100.0, 104.0, 99.0, 103.0, 1_000, "usa"),
            ("TEST", "2026-03-02", 103.0, 107.0, 102.0, 106.0, 1_100, "usa"),
            ("TEST", "2026-03-03", 106.0, 111.0, 105.5, 110.0, 1_150, "usa"),
            ("TEST", "2026-03-04", 109.5, 110.0, 108.5, 109.0, 900, "usa"),
            ("TEST", "2026-03-05", 109.0, 109.2, 108.0, 108.6, 920, "usa"),
            ("TEST", "2026-03-06", 108.8, 111.5, 108.7, 111.2, 1_350, "usa"),
            ("TEST", "2026-03-07", 110.0, 110.5, 106.5, 107.0, 1_200, "usa"),
            ("TEST", "2026-03-08", 107.0, 107.2, 103.5, 104.0, 1_220, "usa"),
            ("TEST", "2026-03-09", 104.0, 104.2, 100.5, 101.0, 1_240, "usa"),
            ("TEST", "2026-03-10", 101.3, 101.6, 100.6, 101.0, 950, "usa"),
            ("TEST", "2026-03-11", 101.2, 101.7, 100.8, 101.1, 940, "usa"),
            ("TEST", "2026-03-12", 101.0, 101.5, 100.7, 101.0, 930, "usa"),
            ("TEST", "2026-03-13", 100.8, 101.0, 98.0, 98.4, 1_500, "usa"),
        ],
    )

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=[
            "Bullish Flag",
            "Bearish Flag",
            "Bull Rectangle",
            "Bear Rectangle",
        ],
        start_date="2026-03-01",
        end_date="2026-03-13",
        progress_callback=None,
        downtrend_filter=False,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    detected_patterns = {
        finding["pattern"]
        for findings in results.values()
        for finding in findings
    }
    assert "Bullish Flag" in detected_patterns
    assert "Bear Rectangle" in detected_patterns


def test_analysis_engine_detects_new_bearish_patterns(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "stock.db"
    engine = AnalysisEngine(str(analysis_db), str(stock_db))
    stock_data = [
        {
            "date": "2026-04-01",
            "open": 100.0,
            "high": 105.0,
            "low": 99.0,
            "close": 104.0,
            "volume": 1000,
        },
        {
            "date": "2026-04-02",
            "open": 105.0,
            "high": 106.0,
            "low": 98.0,
            "close": 99.0,
            "volume": 1200,
        },
        {
            "date": "2026-04-03",
            "open": 100.2,
            "high": 108.0,
            "low": 99.95,
            "close": 100.0,
            "volume": 1100,
        },
        {
            "date": "2026-04-04",
            "open": 100.0,
            "high": 111.0,
            "low": 99.0,
            "close": 110.0,
            "volume": 1000,
        },
        {
            "date": "2026-04-05",
            "open": 111.0,
            "high": 112.0,
            "low": 103.0,
            "close": 104.0,
            "volume": 1000,
        },
        {
            "date": "2026-04-06",
            "open": 100.0,
            "high": 111.0,
            "low": 99.0,
            "close": 110.0,
            "volume": 1000,
        },
        {
            "date": "2026-04-07",
            "open": 111.0,
            "high": 113.0,
            "low": 110.0,
            "close": 112.0,
            "volume": 1000,
        },
        {
            "date": "2026-04-08",
            "open": 111.0,
            "high": 112.0,
            "low": 103.0,
            "close": 104.0,
            "volume": 1000,
        },
        {
            "date": "2026-04-09",
            "open": 106.2,
            "high": 106.3,
            "low": 100.0,
            "close": 106.0,
            "volume": 1000,
        },
    ]

    patterns = {entry["pattern"] for entry in engine._detect_patterns("TEST", stock_data)}
    assert "bearish_engulfing" in patterns
    assert "shooting_star" in patterns
    assert "dark_cloud_cover" in patterns
    assert "evening_star" in patterns
    assert "hanging_man" in patterns


def test_bearish_pattern_ids_are_registered():
    assert ResultsGenerator.PATTERN_MAPPING["Bearish Engulfing"] == 9
    assert ResultsGenerator.PATTERN_MAPPING["Shooting Star"] == 10
    assert ResultsGenerator.PATTERN_MAPPING["Dark Cloud Cover"] == 11
    assert ResultsGenerator.PATTERN_MAPPING["Evening Star"] == 12
    assert ResultsGenerator.PATTERN_MAPPING["Hanging Man"] == 13
    assert ResultsGenerator.PATTERN_MAPPING["Hidden Bullish Divergence"] == 14
    assert ResultsGenerator.PATTERN_MAPPING["Hidden Bearish Divergence"] == 15
    assert ResultsGenerator.PATTERN_MAPPING["Bullish Abandoned Baby"] == 16
    assert ResultsGenerator.PATTERN_MAPPING["Falling Three Methods"] == 17
    assert ResultsGenerator.PATTERN_MAPPING["Bullish Flag"] == 18
    assert ResultsGenerator.PATTERN_MAPPING["Bull Rectangle"] == 19
    assert ResultsGenerator.PATTERN_MAPPING["Bearish Flag"] == 20
    assert ResultsGenerator.PATTERN_MAPPING["Bear Rectangle"] == 21
    assert ResultsGenerator.PATTERN_MAPPING["Ascending Triangle"] == 22
    assert ResultsGenerator.PATTERN_MAPPING["Bullish Pennant"] == 23
    assert ResultsGenerator.PATTERN_MAPPING["Descending Triangle"] == 24
    assert ResultsGenerator.PATTERN_MAPPING["Bearish Pennant"] == 25
    assert ResultsGenerator.PATTERN_MAPPING["Cup and Handle"] == 26

    assert ExcelExporter.PATTERN_NAMES[9] == "Bearish Engulfing"
    assert ExcelExporter.PATTERN_NAMES[10] == "Shooting Star"
    assert ExcelExporter.PATTERN_NAMES[11] == "Dark Cloud Cover"
    assert ExcelExporter.PATTERN_NAMES[12] == "Evening Star"
    assert ExcelExporter.PATTERN_NAMES[13] == "Hanging Man"
    assert ExcelExporter.PATTERN_NAMES[14] == "Hidden Bullish Divergence"
    assert ExcelExporter.PATTERN_NAMES[15] == "Hidden Bearish Divergence"
    assert ExcelExporter.PATTERN_NAMES[16] == "Bullish Abandoned Baby"
    assert ExcelExporter.PATTERN_NAMES[17] == "Falling Three Methods"
    assert ExcelExporter.PATTERN_NAMES[18] == "Bullish Flag"
    assert ExcelExporter.PATTERN_NAMES[19] == "Bull Rectangle"
    assert ExcelExporter.PATTERN_NAMES[20] == "Bearish Flag"
    assert ExcelExporter.PATTERN_NAMES[21] == "Bear Rectangle"
    assert ExcelExporter.PATTERN_NAMES[22] == "Ascending Triangle"
    assert ExcelExporter.PATTERN_NAMES[23] == "Bullish Pennant"
    assert ExcelExporter.PATTERN_NAMES[24] == "Descending Triangle"
    assert ExcelExporter.PATTERN_NAMES[25] == "Bearish Pennant"
    assert ExcelExporter.PATTERN_NAMES[26] == "Cup and Handle"
