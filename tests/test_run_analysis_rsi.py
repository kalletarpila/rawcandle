import sqlite3

import pandas as pd
import pytest

from analysis.candlestick_patterns import (
    calculate_rsi,
    is_bearish_divergence,
    is_bullish_divergence,
)
from analysis.divergence_v1 import compute_rsi_wilder
from analysis.run_analysis import run_candlestick_analysis


def test_run_candlestick_analysis_prefers_divergence_rsi(tmp_path):
    osake_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"

    # Luo minimikanta kahdella päivädatalla (bearish -> bullish engulfing)
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
            [
                ("TEST", "2026-01-01", 10.0, 11.0, 9.0, 9.0, 1_000, "usa"),
                ("TEST", "2026-01-02", 8.5, 11.0, 8.0, 10.5, 1_200, "usa"),
            ],
        )

    # Lisää RSI divergence_data-tauluun, jotta analyysi voi käyttää sitä lyhyessä ikkunassa
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
        conn.execute(
            "INSERT INTO divergence_data (ticker, date, rsi, pivot2_date_r3, is_bullish_divergence_r3) VALUES (?, ?, ?, ?, ?)",
            ("TEST", "2026-01-02", 55.5, None, 0),
        )

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=["Bullish Engulfing"],
        start_date="2026-01-01",
        end_date="2026-01-02",
        progress_callback=None,
        downtrend_filter=False,  # pieni datasetti -> ohita laskutrendi-ehto
        min_decline_percent=3.0,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    key = "TEST|2026-01-02"
    assert results and key in results
    assert results[key][0]["rsi14"] == pytest.approx(55.5)


def test_bullish_divergence_no_lookahead_uses_only_past_window():
    idx = 40
    close = [160.0 - i for i in range(60)]
    close[30:42] = [120.0, 119.0, 118.0, 117.0, 116.0, 115.0, 114.0, 113.0, 112.0, 111.0, 110.0, 109.0]
    rsi = [45.0 for _ in range(60)]
    rsi[37] = 20.0
    rsi[40] = 30.0

    df = pd.DataFrame(
        {
            "pvm": pd.date_range("2025-01-01", periods=60, freq="D"),
            "Close": close,
            "RSI": rsi,
        }
    )

    result = is_bullish_divergence(df, idx=idx, close_col="Close")
    assert result is not None
    assert result["found"] is True


def test_bearish_divergence_no_lookahead_uses_only_past_window():
    idx = 40
    close = [80.0 + i for i in range(60)]
    close[30:42] = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0, 110.0, 111.0]
    rsi = [55.0 for _ in range(60)]
    rsi[37] = 70.0
    rsi[40] = 60.0

    df = pd.DataFrame(
        {
            "pvm": pd.date_range("2025-01-01", periods=60, freq="D"),
            "Close": close,
            "RSI": rsi,
        }
    )

    result = is_bearish_divergence(df, idx=idx, close_col="Close")
    assert result is not None
    assert result["found"] is True


def _create_candles_test_dbs(tmp_path):
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
            [
                ("TEST", "2026-02-01", 10.0, 11.0, 9.0, 9.0, 1_000, "usa"),
                ("TEST", "2026-02-02", 8.5, 11.0, 8.0, 10.5, 1_200, "usa"),
            ],
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


def test_run_candlestick_analysis_uses_db_backed_bullish_divergence(tmp_path):
    osake_db, analysis_db = _create_candles_test_dbs(tmp_path)

    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi, pivot2_date_r3, is_bullish_divergence_r3)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("TEST", "2026-02-02", 0.62, 0.0, 55.5, None, 1),
        )

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=["Bullish Divergence"],
        start_date="2026-02-01",
        end_date="2026-02-02",
        progress_callback=None,
        downtrend_filter=False,
        min_decline_percent=3.0,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    key = "TEST|2026-02-02"
    assert results and key in results
    assert results[key][0]["pattern"] == "Bullish Divergence"
    assert results[key][0]["strength"] == pytest.approx(0.62)
    assert results[key][0]["rsi14"] == pytest.approx(55.5)


def test_run_candlestick_analysis_skips_missing_db_bullish_divergence(tmp_path):
    osake_db, analysis_db = _create_candles_test_dbs(tmp_path)

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=["Bullish Divergence"],
        start_date="2026-02-01",
        end_date="2026-02-02",
        progress_callback=None,
        downtrend_filter=False,
        min_decline_percent=3.0,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    assert results == {}


def test_run_candlestick_analysis_requires_r3_event_for_bullish_divergence(tmp_path):
    osake_db, analysis_db = _create_candles_test_dbs(tmp_path)

    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi, pivot2_date_r3, is_bullish_divergence_r3)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("TEST", "2026-02-02", 0.62, 0.0, 55.5, None, 0),
        )

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=["Bullish Divergence"],
        start_date="2026-02-01",
        end_date="2026-02-02",
        progress_callback=None,
        downtrend_filter=False,
        min_decline_percent=3.0,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    assert results == {}


def test_run_candlestick_analysis_uses_db_backed_hidden_divergences(tmp_path):
    osake_db, analysis_db = _create_candles_test_dbs(tmp_path)

    with sqlite3.connect(analysis_db) as conn:
        conn.execute("ALTER TABLE divergence_data ADD COLUMN hidden_bullish_strength REAL DEFAULT 0")
        conn.execute("ALTER TABLE divergence_data ADD COLUMN hidden_bearish_strength REAL DEFAULT 0")
        conn.execute(
            "ALTER TABLE divergence_data ADD COLUMN is_hidden_bullish_divergence_r3 INTEGER DEFAULT 0"
        )
        conn.execute(
            "ALTER TABLE divergence_data ADD COLUMN is_hidden_bearish_divergence_r3 INTEGER DEFAULT 0"
        )
        conn.execute(
            """
            INSERT INTO divergence_data (
                ticker,
                date,
                bullish_strength,
                bearish_strength,
                hidden_bullish_strength,
                hidden_bearish_strength,
                rsi,
                pivot2_date_r3,
                is_bullish_divergence_r3,
                is_hidden_bullish_divergence_r3,
                is_hidden_bearish_divergence_r3
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("TEST", "2026-02-02", 0.0, 0.0, 0.71, 0.48, 55.5, None, 0, 1, 1),
        )

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=["Hidden Bullish Divergence", "Hidden Bearish Divergence"],
        start_date="2026-02-01",
        end_date="2026-02-02",
        progress_callback=None,
        downtrend_filter=False,
        min_decline_percent=3.0,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    key = "TEST|2026-02-02"
    assert results and key in results
    patterns = {entry["pattern"]: entry for entry in results[key]}
    assert patterns["Hidden Bullish Divergence"]["strength"] == pytest.approx(0.71)
    assert patterns["Hidden Bearish Divergence"]["strength"] == pytest.approx(0.48)
    assert patterns["Hidden Bullish Divergence"]["rsi14"] == pytest.approx(55.5)


def test_run_candlestick_analysis_checks_bulldiv_downtrend_at_pivot2_date_r3(tmp_path):
    osake_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"

    closes = [120.0, 119.0, 118.0, 117.0, 116.0, 110.0, 109.0, 108.0, 105.0, 104.0, 100.0, 108.0, 112.0]
    dates = [f"2026-03-{day:02d}" for day in range(2, 15)]
    pivot2_date = dates[10]
    event_date = dates[12]

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
            [
                ("TEST", date_value, close_value, close_value, close_value, close_value, 1_000, "usa")
                for date_value, close_value in zip(dates, closes)
            ],
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
        conn.execute(
            """
            INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi, pivot2_date_r3, is_bullish_divergence_r3)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("TEST", event_date, 0.62, 0.0, 55.5, pivot2_date, 1),
        )

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=["Bullish Divergence"],
        start_date=dates[0],
        end_date=dates[-1],
        progress_callback=None,
        downtrend_filter=True,
        min_decline_percent=3.0,
        use_ma_filter=True,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    key = f"TEST|{event_date}"
    assert results and key in results
    assert results[key][0]["pattern"] == "Bullish Divergence"


def test_run_candlestick_analysis_forms_combo_from_db_divergence(tmp_path):
    osake_db, analysis_db = _create_candles_test_dbs(tmp_path)

    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi, pivot2_date_r3, is_bullish_divergence_r3)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("TEST", "2026-02-02", 0.62, 0.0, 55.5, None, 1),
        )

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=["Bullish Engulfing", "Bullish Divergence"],
        start_date="2026-02-01",
        end_date="2026-02-02",
        progress_callback=None,
        downtrend_filter=False,
        min_decline_percent=3.0,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    key = "TEST|2026-02-02"
    assert results and key in results
    assert len(results[key]) == 3
    assert any(item["pattern"] == "Bullish Engulfing" for item in results[key])
    assert any(item["pattern"] == "BullDiv & Bullish Engulfing" for item in results[key])
    assert any(item["pattern"] == "Bullish Divergence" for item in results[key])


def test_run_candlestick_analysis_forms_all_eligible_combos_for_same_day(tmp_path):
    osake_db, analysis_db = _create_candles_test_dbs(tmp_path)

    with sqlite3.connect(osake_db) as conn:
        conn.execute("DELETE FROM osakedata WHERE osake = ?", ("TEST",))
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("TEST", "2026-02-01", 10.0, 10.0, 9.0, 9.0, 1_000, "usa"),
                ("TEST", "2026-02-02", 10.00, 10.08, 9.00, 10.05, 1_200, "usa"),
            ],
        )

    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi, pivot2_date_r3, is_bullish_divergence_r3)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("TEST", "2026-02-02", 0.62, 0.0, 55.5, None, 1),
        )

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=["Hammer", "Dragonfly Doji", "Bullish Divergence"],
        start_date="2026-02-01",
        end_date="2026-02-02",
        progress_callback=None,
        downtrend_filter=False,
        min_decline_percent=3.0,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    key = "TEST|2026-02-02"
    assert results and key in results
    patterns = [item["pattern"] for item in results[key]]
    assert "Hammer" in patterns
    assert "Dragonfly Doji" in patterns
    assert "Bullish Divergence" in patterns
    assert "BullDiv & Hammer" in patterns
    assert "BullDiv & Dragonfly Doji" in patterns


def test_run_candlestick_analysis_forms_combo_within_pivot2_window(tmp_path):
    osake_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"

    rows = [
        ("TEST", "2026-02-01", 10.0, 10.0, 10.0, 10.0, 1_000, "usa"),
        ("TEST", "2026-02-02", 9.8, 9.8, 9.8, 9.8, 1_000, "usa"),
        ("TEST", "2026-02-03", 9.6, 9.6, 9.6, 9.6, 1_000, "usa"),
        ("TEST", "2026-02-04", 10.0, 10.0, 9.0, 9.0, 1_000, "usa"),
        ("TEST", "2026-02-05", 8.5, 11.0, 8.0, 10.5, 1_200, "usa"),
        ("TEST", "2026-02-06", 10.5, 10.6, 10.4, 10.5, 1_000, "usa"),
        ("TEST", "2026-02-07", 10.5, 10.6, 10.4, 10.5, 1_000, "usa"),
        ("TEST", "2026-02-08", 10.5, 10.6, 10.4, 10.5, 1_000, "usa"),
    ]

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
        conn.execute(
            """
            INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi, pivot2_date_r3, is_bullish_divergence_r3)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("TEST", "2026-02-08", 0.62, 0.0, 55.5, "2026-02-06", 1),
        )

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=["Bullish Engulfing", "Bullish Divergence"],
        start_date="2026-02-01",
        end_date="2026-02-08",
        progress_callback=None,
        downtrend_filter=False,
        min_decline_percent=3.0,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    key = "TEST|2026-02-05"
    assert results and key in results
    assert any(item["pattern"] == "Bullish Engulfing" for item in results[key])
    assert any(item["pattern"] == "BullDiv & Bullish Engulfing" for item in results[key])
    assert not any(item["pattern"] == "Bullish Divergence" for item in results[key])


def test_run_candlestick_analysis_does_not_use_legacy_bullish_divergence(tmp_path, monkeypatch):
    osake_db, analysis_db = _create_candles_test_dbs(tmp_path)

    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi, pivot2_date_r3, is_bullish_divergence_r3)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("TEST", "2026-02-02", 0.62, 0.0, 55.5, None, 1),
        )

    monkeypatch.setattr(
        "analysis.run_analysis.is_bullish_divergence",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy divergence should not be called")),
    )

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=["Bullish Divergence"],
        start_date="2026-02-01",
        end_date="2026-02-02",
        progress_callback=None,
        downtrend_filter=False,
        min_decline_percent=3.0,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    key = "TEST|2026-02-02"
    assert results and key in results
    assert results[key][0]["pattern"] == "Bullish Divergence"


def test_run_candlestick_analysis_candle_only_behavior_unchanged(tmp_path, monkeypatch):
    osake_db, analysis_db = _create_candles_test_dbs(tmp_path)

    monkeypatch.setattr(
        "analysis.run_analysis.is_bullish_divergence",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("legacy divergence should not be called")),
    )

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=["Bullish Engulfing"],
        start_date="2026-02-01",
        end_date="2026-02-02",
        progress_callback=None,
        downtrend_filter=False,
        min_decline_percent=3.0,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    key = "TEST|2026-02-02"
    assert results and key in results
    assert len(results[key]) == 1
    assert results[key][0]["pattern"] == "Bullish Engulfing"
    assert not any(item["pattern"].startswith("BullDiv & ") for item in results[key])


def test_run_candlestick_analysis_duplicate_combo_protection(tmp_path, monkeypatch):
    osake_db, analysis_db = _create_candles_test_dbs(tmp_path)

    with sqlite3.connect(osake_db) as conn:
        conn.execute("DELETE FROM osakedata WHERE osake = ?", ("TEST",))
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("TEST", "2026-02-01", 10.0, 10.0, 9.0, 9.0, 1_000, "usa"),
                ("TEST", "2026-02-02", 10.00, 10.08, 9.00, 10.05, 1_200, "usa"),
            ],
        )

    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi, pivot2_date_r3, is_bullish_divergence_r3)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("TEST", "2026-02-02", 0.62, 0.0, 55.5, None, 1),
        )

    monkeypatch.setitem(
        __import__("analysis.run_analysis", fromlist=["COMBO_PATTERN_MAP"]).COMBO_PATTERN_MAP,
        "Dragonfly Doji",
        "BullDiv & Hammer",
    )

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=["Hammer", "Dragonfly Doji", "Bullish Divergence"],
        start_date="2026-02-01",
        end_date="2026-02-02",
        progress_callback=None,
        downtrend_filter=False,
        min_decline_percent=3.0,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    key = "TEST|2026-02-02"
    assert results and key in results
    combo_patterns = [item["pattern"] for item in results[key] if item["pattern"].startswith("BullDiv & ")]
    assert combo_patterns.count("BullDiv & Hammer") == 1


def test_run_candlestick_analysis_uses_wilder_rsi_fallback(tmp_path):
    osake_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"

    closes = [100]
    for delta in ([1] * 12 + [-12] + [1] * 2):
        closes.append(closes[-1] + delta)

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
        rows = []
        for idx, close in enumerate(closes, start=1):
            date = f"2026-03-{idx:02d}"
            if idx == len(closes):
                rows.append(("TEST", date, close, close + 0.1, close - 6.0, close + 1.0, 1_000, "usa"))
            else:
                rows.append(("TEST", date, close, close, close, close, 1_000, "usa"))
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

    results = run_candlestick_analysis(
        str(osake_db),
        "TEST",
        patterns=["Hammer"],
        start_date="2026-03-01",
        end_date="2026-03-16",
        progress_callback=None,
        downtrend_filter=False,
        min_decline_percent=3.0,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=str(analysis_db),
    )

    key = "TEST|2026-03-16"
    assert results and key in results

    actual_closes = closes[:-1] + [closes[-1] + 1.0]
    closes_df = pd.DataFrame({"Close": actual_closes})
    rolling_rsi = float(calculate_rsi(closes_df, period=14, close_col="Close")["RSI"].iloc[-1])
    wilder_rsi = compute_rsi_wilder([float(value) for value in actual_closes], period=14)[-1]

    assert wilder_rsi is not None
    assert rolling_rsi != pytest.approx(wilder_rsi)
    assert results[key][0]["rsi14"] == pytest.approx(wilder_rsi)
