from __future__ import annotations

import sqlite3

from analysis.datacenter_indices import (
    read_candlestick_enrichment,
    read_divergence_enrichment,
    read_dow_structure_enrichment,
    read_ticker_analysis_enrichment,
)
from analysis.datacenter_indices.swing_analysis_readers import (
    read_batch_candlestick_enrichment,
    read_batch_divergence_enrichment,
    read_batch_dow_structure_enrichment,
)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_dow_reader_enforces_confirmed_as_of_date_and_ignores_future_confirmed_rows():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
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
        INSERT INTO stock_dow_structure_events (
            ticker, market, event_date, confirmed_as_of_date, event_type,
            dow_label_high, dow_label_low, trend_state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "usa", "2024-01-10", "2024-01-10", "PIVOT_HIGH", "HH", None, "UP"),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, market, event_date, confirmed_as_of_date, event_type,
            dow_label_high, dow_label_low, trend_state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "usa", "2024-01-12", "2024-01-15", "PIVOT_LOW", None, "HL", "UP"),
    )

    snapshot = read_dow_structure_enrichment(conn, "AAA", "usa", "2024-01-12")

    assert snapshot.source_status == "OK"
    assert snapshot.latest_structure_label == "HH"
    assert snapshot.latest_structure_confirmed_as_of_date == "2024-01-10"
    assert snapshot.latest_event_date == "2024-01-10"
    assert snapshot.trend_state == "UP"
    assert snapshot.latest_bos_event_type is None
    assert snapshot.latest_reset_event_date is None


def test_dow_reader_returns_latest_available_label_deterministically():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
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
        INSERT INTO stock_dow_structure_events (
            ticker, market, event_date, confirmed_as_of_date, event_type,
            dow_label_high, dow_label_low, trend_state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "usa", "2024-01-09", "2024-01-10", "PIVOT_LOW", None, "HL", "UP"),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, market, event_date, confirmed_as_of_date, event_type,
            dow_label_high, dow_label_low, trend_state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "usa", "2024-01-10", "2024-01-10", "PIVOT_HIGH", "HH", None, "UP"),
    )

    snapshot = read_dow_structure_enrichment(conn, "AAA", "usa", "2024-01-10")

    assert snapshot.latest_structure_label == "HH"
    assert snapshot.latest_event_date == "2024-01-10"


def test_dow_reader_returns_no_dow_event_when_no_eligible_row_exists():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
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

    snapshot = read_dow_structure_enrichment(conn, "AAA", "usa", "2024-01-10")

    assert snapshot.source_status == "NO_DOW_EVENT"
    assert snapshot.latest_structure_label is None


def test_dow_reader_ignores_raw_h_and_falls_back_to_latest_valid_structure_label():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
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
        INSERT INTO stock_dow_structure_events (
            ticker, market, event_date, confirmed_as_of_date, event_type,
            dow_label_high, dow_label_low, trend_state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "usa", "2024-01-09", "2024-01-10", "PIVOT_HIGH", "HH", None, "UP"),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, market, event_date, confirmed_as_of_date, event_type,
            dow_label_high, dow_label_low, trend_state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "usa", "2024-01-11", "2024-01-12", "PIVOT_HIGH", "H", None, "UP"),
    )

    snapshot = read_dow_structure_enrichment(conn, "AAA", "usa", "2024-01-12")

    assert snapshot.source_status == "OK"
    assert snapshot.latest_structure_label == "HH"
    assert snapshot.latest_structure_confirmed_as_of_date == "2024-01-10"
    assert snapshot.latest_event_date == "2024-01-09"


def test_dow_reader_ignores_raw_l_and_returns_none_when_only_first_pivot_labels_exist():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
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
        INSERT INTO stock_dow_structure_events (
            ticker, market, event_date, confirmed_as_of_date, event_type,
            dow_label_high, dow_label_low, trend_state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "usa", "2024-01-11", "2024-01-12", "PIVOT_LOW", None, "L", "NEUTRAL"),
    )

    snapshot = read_dow_structure_enrichment(conn, "AAA", "usa", "2024-01-12")

    assert snapshot.source_status == "NO_DOW_EVENT"
    assert snapshot.latest_structure_label is None
    assert snapshot.latest_structure_confirmed_as_of_date is None
    assert snapshot.latest_event_date is None


def test_dow_reader_reads_latest_bos_and_reset_context_no_lookahead_safely():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            market TEXT NULL,
            event_date TEXT NOT NULL,
            confirmed_as_of_date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            dow_label_high TEXT NULL,
            dow_label_low TEXT NULL,
            trend_state TEXT NULL,
            reset_reason TEXT NULL,
            structure_epoch_id INTEGER NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, market, event_date, confirmed_as_of_date, event_type,
            dow_label_high, dow_label_low, trend_state, reset_reason, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "usa", "2024-01-09", "2024-01-10", "PIVOT_HIGH", "HH", None, "UP", None, 1),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, market, event_date, confirmed_as_of_date, event_type,
            dow_label_high, dow_label_low, trend_state, reset_reason, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "usa", "2024-01-11", "2024-01-12", "BOS_DOWN", None, None, "UP", None, 1),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, market, event_date, confirmed_as_of_date, event_type,
            dow_label_high, dow_label_low, trend_state, reset_reason, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "usa", "2024-01-13", "2024-01-14", "RESET", None, None, "NEUTRAL", "DOUBLE_BOS_DOWN", 2),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, market, event_date, confirmed_as_of_date, event_type,
            dow_label_high, dow_label_low, trend_state, reset_reason, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "usa", "2024-01-15", "2024-01-16", "BOS_UP", None, None, "DOWN", None, 3),
    )

    snapshot = read_dow_structure_enrichment(conn, "AAA", "usa", "2024-01-14")

    assert snapshot.trend_state == "NEUTRAL"
    assert snapshot.structure_epoch_id == 2
    assert snapshot.latest_bos_event_type == "BOS_DOWN"
    assert snapshot.latest_bos_event_date == "2024-01-11"
    assert snapshot.latest_bos_confirmed_as_of_date == "2024-01-12"
    assert snapshot.latest_reset_event_date == "2024-01-13"
    assert snapshot.latest_reset_confirmed_as_of_date == "2024-01-14"
    assert snapshot.latest_reset_reason == "DOUBLE_BOS_DOWN"


def test_divergence_reader_reads_latest_row_up_to_as_of_date_and_ignores_future_rows():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE divergence_data (
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
        INSERT INTO divergence_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-10", 1.2, 0.0, 0.0, 0.0, 55.0, 1, 0, 0, 0),
    )
    conn.execute(
        """
        INSERT INTO divergence_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-15", 0.0, 1.0, 0.0, 0.0, 45.0, 0, 1, 0, 0),
    )

    snapshot = read_divergence_enrichment(conn, "AAA", "2024-01-12")

    assert snapshot.source_status == "OK"
    assert snapshot.source_date == "2024-01-10"
    assert snapshot.bullish_divergence_signal == 1
    assert snapshot.bearish_divergence_signal == 0
    assert snapshot.bullish_strength == 1.2
    assert snapshot.rsi == 55.0


def test_divergence_reader_returns_no_divergence_row_when_no_eligible_row_exists():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE divergence_data (
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

    snapshot = read_divergence_enrichment(conn, "AAA", "2024-01-10")

    assert snapshot.source_status == "NO_DIVERGENCE_ROW"
    assert snapshot.source_date is None


def test_candlestick_reader_reads_only_as_of_date_and_classifies_bullish_and_bearish_patterns():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE analysis_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            pattern TEXT,
            signal_strength REAL,
            rsi14 REAL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-10", "Hammer", 0.9, 30.0),
    )
    conn.execute(
        """
        INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-10", "Shooting Star", 0.8, 70.0),
    )
    conn.execute(
        """
        INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-11", "Morning Star", 0.6, 35.0),
    )

    snapshot = read_candlestick_enrichment(conn, "AAA", "2024-01-10")

    assert snapshot.source_status == "OK"
    assert snapshot.source_date == "2024-01-10"
    assert snapshot.bullish_candle_signal == 1
    assert snapshot.bearish_candle_signal == 1
    assert snapshot.bullish_patterns == ("Hammer",)
    assert snapshot.bearish_patterns == ("Shooting Star",)


def test_candlestick_reader_returns_no_candle_finding_when_no_matching_row_exists():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE analysis_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            pattern TEXT,
            signal_strength REAL,
            rsi14 REAL
        )
        """
    )

    snapshot = read_candlestick_enrichment(conn, "AAA", "2024-01-10")

    assert snapshot.source_status == "NO_CANDLE_FINDING"
    assert snapshot.bullish_patterns == ()
    assert snapshot.bearish_patterns == ()


def test_missing_table_returns_missing_table_instead_of_crashing():
    conn = _connect()

    snapshot = read_dow_structure_enrichment(conn, "AAA", "usa", "2024-01-10")

    assert snapshot.source_status == "MISSING_TABLE"


def test_combined_helper_composes_all_readers():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
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
        CREATE TABLE divergence_data (
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
        CREATE TABLE analysis_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            pattern TEXT,
            signal_strength REAL,
            rsi14 REAL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, market, event_date, confirmed_as_of_date, event_type,
            dow_label_high, dow_label_low, trend_state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "usa", "2024-01-10", "2024-01-10", "PIVOT_HIGH", "HH", None, "UP"),
    )
    conn.execute(
        """
        INSERT INTO divergence_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-10", 1.0, 0.0, 0.0, 0.0, 50.0, 1, 0, 0, 0),
    )
    conn.execute(
        """
        INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-10", "Hammer", 0.9, 30.0),
    )

    snapshot = read_ticker_analysis_enrichment(conn, "AAA", "usa", "2024-01-10")

    assert snapshot.dow.latest_structure_label == "HH"
    assert snapshot.divergence.bullish_divergence_signal == 1
    assert snapshot.candlestick.bullish_patterns == ("Hammer",)


def test_batch_enrichment_helpers_match_single_ticker_readers():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
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
        CREATE TABLE divergence_data (
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
        CREATE TABLE analysis_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            pattern TEXT,
            signal_strength REAL,
            rsi14 REAL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, market, event_date, confirmed_as_of_date, event_type,
            dow_label_high, dow_label_low, trend_state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "usa", "2024-01-10", "2024-01-10", "PIVOT_HIGH", "HH", None, "UP"),
    )
    conn.execute(
        """
        INSERT INTO divergence_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-10", 1.0, 0.0, 0.0, 0.0, 55.0, 1, 0, 0, 0),
    )
    conn.execute(
        """
        INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-10", "Hammer", 0.9, 30.0),
    )

    batch_dow = read_batch_dow_structure_enrichment(conn, ["AAA", "BBB"], "usa", "2024-01-10")
    batch_div = read_batch_divergence_enrichment(conn, ["AAA", "BBB"], "2024-01-10")
    batch_candle = read_batch_candlestick_enrichment(conn, ["AAA", "BBB"], "2024-01-10")

    assert batch_dow["AAA"] == read_dow_structure_enrichment(conn, "AAA", "usa", "2024-01-10")
    assert batch_div["AAA"] == read_divergence_enrichment(conn, "AAA", "2024-01-10")
    assert batch_candle["AAA"] == read_candlestick_enrichment(conn, "AAA", "2024-01-10")
    assert batch_dow["BBB"].source_status == "NO_DOW_EVENT"
    assert batch_div["BBB"].source_status == "NO_DIVERGENCE_ROW"
    assert batch_candle["BBB"].source_status == "NO_CANDLE_FINDING"
