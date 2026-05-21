import sqlite3

from rawcandle.technical_signal_relevance import CANDLE, RSI
from rawcandle.technical_signal_relevance_sources import (
    normalize_candlestick_observation_row,
    normalize_signal_name,
    read_divergence_observations,
    read_dow_events,
    read_dow_pivots,
    read_dow_snapshot,
)


def _connect():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def test_divergence_adapter_emits_bullish_divergence_for_positive_bullish_strength():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE divergence_data (
            ticker TEXT,
            date TEXT,
            bullish_strength REAL,
            bearish_strength REAL,
            rsi REAL
        )
        """
    )
    conn.execute(
        "INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", 1.2, 0.0, 55.0),
    )

    observations = read_divergence_observations(conn, "AAA", "1d", "2024-01-01", "2024-01-31")

    assert len(observations) == 1
    assert observations[0].signal_name == "Bullish Divergence"
    assert observations[0].signal_source_id == RSI


def test_divergence_adapter_emits_bearish_divergence_for_positive_bearish_strength():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE divergence_data (
            ticker TEXT,
            date TEXT,
            bullish_strength REAL,
            bearish_strength REAL,
            rsi REAL
        )
        """
    )
    conn.execute(
        "INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", 0.0, 1.1, 40.0),
    )

    observations = read_divergence_observations(conn, "AAA", "1d", "2024-01-01", "2024-01-31")

    assert len(observations) == 1
    assert observations[0].signal_name == "Bearish Divergence"


def test_divergence_adapter_emits_no_observation_for_zero_strengths():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE divergence_data (
            ticker TEXT,
            date TEXT,
            bullish_strength REAL,
            bearish_strength REAL,
            rsi REAL
        )
        """
    )
    conn.execute(
        "INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", 0.0, 0.0, 50.0),
    )

    observations = read_divergence_observations(conn, "AAA", "1d", "2024-01-01", "2024-01-31")
    assert observations == []


def test_divergence_adapter_does_not_read_rows_outside_range():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE divergence_data (
            ticker TEXT,
            date TEXT,
            bullish_strength REAL,
            bearish_strength REAL,
            rsi REAL
        )
        """
    )
    conn.executemany(
        "INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi) VALUES (?, ?, ?, ?, ?)",
        [
            ("AAA", "2024-01-01", 1.0, 0.0, 50.0),
            ("AAA", "2024-02-01", 1.0, 0.0, 50.0),
        ],
    )

    observations = read_divergence_observations(conn, "AAA", "1d", "2024-01-10", "2024-01-31")
    assert observations == []


def test_hidden_divergence_is_emitted_only_when_explicit_hidden_fields_exist_and_are_active():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE divergence_data (
            ticker TEXT,
            date TEXT,
            bullish_strength REAL,
            bearish_strength REAL,
            hidden_bullish_strength REAL,
            hidden_bearish_strength REAL,
            is_hidden_bullish_divergence_r3 INTEGER,
            is_hidden_bearish_divergence_r3 INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO divergence_data (
            ticker, date, bullish_strength, bearish_strength,
            hidden_bullish_strength, hidden_bearish_strength,
            is_hidden_bullish_divergence_r3, is_hidden_bearish_divergence_r3
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-10", 0.0, 0.0, 0.5, 0.0, 1, 0),
    )

    observations = read_divergence_observations(conn, "AAA", "1d", "2024-01-01", "2024-01-31")
    assert [item.signal_name for item in observations] == ["Hidden Bullish Divergence"]


def test_normalize_signal_name_maps_known_names():
    assert normalize_signal_name("Hammer") == "Hammer"
    assert normalize_signal_name("hammer") == "Hammer"
    assert normalize_signal_name("bullish_engulfing") == "Bullish Engulfing"
    assert normalize_signal_name("hidden_bullish_divergence") == "Hidden Bullish Divergence"


def test_normalize_signal_name_returns_none_for_unknown_names():
    assert normalize_signal_name("Doji") is None
    assert normalize_signal_name("not_real") is None


def test_candlestick_row_normalization_helper_emits_observation():
    observation = normalize_candlestick_observation_row(
        {
            "ticker": "AAA",
            "signal_date": "2024-01-10",
            "signal_name": "hammer",
            "signal_close_price": 101.5,
        },
        "1d",
    )

    assert observation.ticker == "AAA"
    assert observation.timeframe == "1d"
    assert observation.signal_name == "Hammer"
    assert observation.signal_confirmed_as_of_date == "2024-01-10"
    assert observation.signal_source_id == CANDLE


def test_dow_events_adapter_filters_by_confirmed_as_of_date():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
            id INTEGER PRIMARY KEY,
            ticker TEXT,
            event_date TEXT,
            confirmed_as_of_date TEXT,
            event_type TEXT,
            trend_state TEXT,
            structure_epoch_id INTEGER
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO stock_dow_structure_events (
            id, ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "AAA", "2024-01-09", "2024-01-10", "BOS_UP", "UP", 1),
            (2, "AAA", "2024-01-10", "2024-01-11", "RESET", "NEUTRAL", 1),
        ],
    )

    events = read_dow_events(conn, "AAA", "1d", "2024-01-10")
    assert len(events) == 1
    assert events[0].event_type == "BOS_UP"


def test_dow_pivots_adapter_filters_by_confirmed_as_of_date():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
            id INTEGER PRIMARY KEY,
            ticker TEXT,
            event_date TEXT,
            confirmed_as_of_date TEXT,
            event_type TEXT,
            trend_state TEXT,
            structure_epoch_id INTEGER
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO stock_dow_structure_events (
            id, ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "AAA", "2024-01-09", "2024-01-10", "PIVOT_LOW", "UP", 1),
            (2, "AAA", "2024-01-10", "2024-01-11", "PIVOT_HIGH", "UP", 1),
        ],
    )

    pivots = read_dow_pivots(conn, "AAA", "1d", "2024-01-10")
    assert len(pivots) == 1
    assert pivots[0].event_type == "PIVOT_LOW"


def test_dow_snapshot_adapter_returns_trend_state_and_active_bos_fields():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
            id INTEGER PRIMARY KEY,
            ticker TEXT,
            event_date TEXT,
            confirmed_as_of_date TEXT,
            event_type TEXT,
            trend_state TEXT,
            active_bos_high_price REAL,
            active_bos_low_price REAL,
            structure_epoch_id INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            id, ticker, event_date, confirmed_as_of_date, event_type, trend_state,
            active_bos_high_price, active_bos_low_price, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (1, "AAA", "2024-01-09", "2024-01-10", "BOS_UP", "UP", 110.0, 95.0, 4),
    )

    snapshot = read_dow_snapshot(conn, "AAA", "1d", "2024-01-10")
    assert snapshot is not None
    assert snapshot.trend_state == "UP"
    assert snapshot.active_bos_high_price == 110.0
    assert snapshot.active_bos_low_price == 95.0
    assert snapshot.structure_epoch_id == 4


def test_dow_snapshot_adapter_does_not_recompute_missing_active_bos_fields():
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
            id INTEGER PRIMARY KEY,
            ticker TEXT,
            event_date TEXT,
            confirmed_as_of_date TEXT,
            event_type TEXT,
            trend_state TEXT,
            structure_epoch_id INTEGER
        )
        """
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            id, ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (1, "AAA", "2024-01-09", "2024-01-10", "BOS_UP", "UP", 4),
    )

    snapshot = read_dow_snapshot(conn, "AAA", "1d", "2024-01-10")
    assert snapshot is not None
    assert snapshot.active_bos_high_price is None
    assert snapshot.active_bos_low_price is None
