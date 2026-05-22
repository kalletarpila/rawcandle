import sqlite3

from rawcandle.technical_signal_relevance import CANDLE, RSI
from rawcandle.technical_signal_relevance_sources import (
    build_bar_index,
    build_context_aware_bar_index,
    normalize_candlestick_observation_row,
    normalize_signal_name,
    read_bar_dates,
    read_candlestick_observations,
    read_divergence_observations,
    read_dow_events,
    read_dow_pivots,
    read_dow_snapshot,
)


def _connect():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


def _create_osakedata(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE osakedata (
            osake TEXT,
            pvm TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            market TEXT DEFAULT 'usa'
        )
        """
    )


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


def test_read_candlestick_observations_emits_hammer_from_analysis_findings():
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
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", "Hammer", 0.8, 55.0),
    )

    observations = read_candlestick_observations(conn, "AAA", "1d", "2024-01-01", "2024-01-31")

    assert len(observations) == 1
    assert observations[0].signal_name == "Hammer"
    assert observations[0].signal_date == "2024-01-10"
    assert observations[0].signal_confirmed_as_of_date == "2024-01-10"
    assert observations[0].signal_source_id == CANDLE


def test_read_candlestick_observations_emits_bearish_candle_from_analysis_findings():
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
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", "Bearish Engulfing", 0.8, 45.0),
    )

    observations = read_candlestick_observations(conn, "AAA", "1d", "2024-01-01", "2024-01-31")

    assert len(observations) == 1
    assert observations[0].signal_name == "Bearish Engulfing"


def test_read_candlestick_observations_maps_snake_case_names_explicitly():
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
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", "bullish_engulfing", 0.8, 55.0),
    )

    observations = read_candlestick_observations(conn, "AAA", "1d", "2024-01-01", "2024-01-31")

    assert len(observations) == 1
    assert observations[0].signal_name == "Bullish Engulfing"


def test_read_candlestick_observations_ignores_non_candlestick_rows():
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
    conn.executemany(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        [
            ("AAA", "2024-01-10", "Bullish Divergence", 1.0, 30.0),
            ("AAA", "2024-01-10", "Hammer", 0.7, 45.0),
        ],
    )

    observations = read_candlestick_observations(conn, "AAA", "1d", "2024-01-01", "2024-01-31")

    assert [item.signal_name for item in observations] == ["Hammer"]


def test_read_candlestick_observations_ignores_unknown_names_without_fuzzy_matching():
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
    conn.executemany(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        [
            ("AAA", "2024-01-10", "Doji", 0.6, 50.0),
            ("AAA", "2024-01-10", "Hammer", 0.7, 50.0),
        ],
    )

    observations = read_candlestick_observations(conn, "AAA", "1d", "2024-01-01", "2024-01-31")

    assert [item.signal_name for item in observations] == ["Hammer"]


def test_read_candlestick_observations_date_range_filtering_works():
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
    conn.executemany(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        [
            ("AAA", "2024-01-01", "Hammer", 0.7, 50.0),
            ("AAA", "2024-01-15", "Hammer", 0.8, 50.0),
            ("AAA", "2024-02-01", "Hammer", 0.9, 50.0),
        ],
    )

    observations = read_candlestick_observations(conn, "AAA", "1d", "2024-01-10", "2024-01-31")

    assert len(observations) == 1
    assert observations[0].signal_date == "2024-01-15"


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


def test_bar_distance_helper_counts_actual_bars_not_calendar_days():
    conn = _connect()
    _create_osakedata(conn)
    conn.executemany(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("AAA", "2026-05-01", 1.0, 1.0, 1.0, 1.0, 1.0, "usa"),
            ("AAA", "2026-05-05", 1.0, 1.0, 1.0, 1.0, 1.0, "usa"),
            ("AAA", "2026-05-06", 1.0, 1.0, 1.0, 1.0, 1.0, "usa"),
        ],
    )

    bar_dates = read_bar_dates(conn, "AAA", "1d", "2026-05-05", "2026-05-06", 10)
    bar_index = build_bar_index(conn, "AAA", "1d", "2026-05-05", "2026-05-06", 10)

    assert bar_dates == ["2026-05-01", "2026-05-05", "2026-05-06"]
    assert bar_index is not None
    assert bar_index.bars_since("2026-05-01", "2026-05-06") == 2


def test_bar_distance_helper_same_bar_distance_is_zero():
    conn = _connect()
    _create_osakedata(conn)
    conn.execute(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2026-05-06", 1.0, 1.0, 1.0, 1.0, 1.0, "usa"),
    )

    bar_index = build_bar_index(conn, "AAA", "1d", "2026-05-06", "2026-05-06", 10)

    assert bar_index is not None
    assert bar_index.bars_since("2026-05-06", "2026-05-06") == 0


def test_bar_distance_helper_returns_none_when_confirmed_date_missing_from_index():
    conn = _connect()
    _create_osakedata(conn)
    conn.executemany(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("AAA", "2026-05-01", 1.0, 1.0, 1.0, 1.0, 1.0, "usa"),
            ("AAA", "2026-05-06", 1.0, 1.0, 1.0, 1.0, 1.0, "usa"),
        ],
    )

    bar_index = build_bar_index(conn, "AAA", "1d", "2026-05-06", "2026-05-06", 10)

    assert bar_index is not None
    assert bar_index.bars_since("2026-05-05", "2026-05-06") is None


def test_context_aware_bar_index_includes_older_required_context_within_cap():
    conn = _connect()
    _create_osakedata(conn)
    rows = [
        ("AAA", f"2026-01-{day:02d}", 1.0, 1.0, 1.0, 1.0, 1.0, "usa")
        for day in range(1, 32)
    ]
    rows.extend(
        [
            ("AAA", f"2026-02-{day:02d}", 1.0, 1.0, 1.0, 1.0, 1.0, "usa")
            for day in range(1, 29)
        ]
    )
    conn.executemany(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )

    bar_index = build_context_aware_bar_index(
        conn,
        "AAA",
        "1d",
        ["2026-02-20"],
        ["2026-01-10", "2026-02-20"],
        max_lookback_bars=260,
    )

    assert bar_index is not None
    assert bar_index.bars_since("2026-01-10", "2026-02-20") == 41


def test_context_aware_bar_index_respects_lookback_cap_for_older_context():
    conn = _connect()
    _create_osakedata(conn)
    rows = []
    for month in range(1, 13):
        for day in range(1, 29):
            rows.append(
                ("AAA", f"2026-{month:02d}-{day:02d}", 1.0, 1.0, 1.0, 1.0, 1.0, "usa")
            )
    conn.executemany(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )

    bar_index = build_context_aware_bar_index(
        conn,
        "AAA",
        "1d",
        ["2026-12-20"],
        ["2026-01-10", "2026-12-20"],
        max_lookback_bars=260,
    )

    assert bar_index is not None
    assert bar_index.bars_since("2026-01-10", "2026-12-20") is None
