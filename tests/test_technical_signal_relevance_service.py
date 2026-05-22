import json
import sqlite3
from datetime import date, timedelta

import pytest

from rawcandle.technical_signal_relevance_persistence import (
    apply_technical_signal_relevance_migration,
    read_relevance_records_for_run,
    read_relevance_run,
)
from rawcandle.technical_signal_relevance_service import (
    run_technical_signal_relevance_for_tickers,
)


def _connect():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_technical_signal_relevance_migration(conn)
    return conn


def _create_analysis_findings(conn: sqlite3.Connection) -> None:
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


def _create_divergence_data(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE divergence_data (
            ticker TEXT,
            date TEXT,
            bullish_strength REAL DEFAULT 0,
            bearish_strength REAL DEFAULT 0,
            hidden_bullish_strength REAL DEFAULT 0,
            hidden_bearish_strength REAL DEFAULT 0,
            rsi REAL,
            is_hidden_bullish_divergence_r3 INTEGER DEFAULT 0,
            is_hidden_bearish_divergence_r3 INTEGER DEFAULT 0
        )
        """
    )


def _create_dow_events(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            event_date TEXT NOT NULL,
            confirmed_as_of_date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            trend_state TEXT,
            active_bos_high_price REAL,
            active_bos_low_price REAL,
            structure_epoch_id INTEGER
        )
        """
    )


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


def _insert_osakedata_range(
    conn: sqlite3.Connection,
    ticker: str,
    start_date: str,
    days: int,
) -> None:
    first_day = date.fromisoformat(start_date)
    rows = []
    for offset in range(days):
        bar_date = (first_day + timedelta(days=offset)).isoformat()
        rows.append((ticker, bar_date, 10.0, 11.0, 9.0, 10.0, 1000.0, "usa"))
    conn.executemany(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def test_service_reads_one_candlestick_observation_and_writes_one_relevance_row():
    conn = _connect()
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    conn.execute(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", "Hammer", 0.8, 50.0),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-09", "2024-01-10", "PIVOT_LOW", "UP", 1),
    )

    summary = run_technical_signal_relevance_for_tickers(
        conn, ["AAA"], "1d", "2024-01-01", "2024-01-31", "RUN_SERVICE_001", "2026-05-21T13:00:00Z"
    )

    assert summary.records_written == 1
    records = read_relevance_records_for_run(conn, "RUN_SERVICE_001")
    assert records[0]["signal_name"] == "Hammer"


def test_service_reads_one_bullish_divergence_observation_and_writes_one_relevance_row():
    conn = _connect()
    _create_divergence_data(conn)
    _create_dow_events(conn)
    conn.execute(
        "INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", 1.0, 0.0, 30.0),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-09", "2024-01-10", "BOS_UP", "UP", 1),
    )

    summary = run_technical_signal_relevance_for_tickers(
        conn, ["AAA"], "1d", "2024-01-01", "2024-01-31", "RUN_SERVICE_002", "2026-05-21T13:00:01Z"
    )

    assert summary.records_written == 1
    records = read_relevance_records_for_run(conn, "RUN_SERVICE_002")
    assert records[0]["signal_name"] == "Bullish Divergence"


def test_service_combines_candlestick_and_divergence_observations_for_one_ticker():
    conn = _connect()
    _create_analysis_findings(conn)
    _create_divergence_data(conn)
    _create_dow_events(conn)
    conn.execute(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", "Hammer", 0.8, 50.0),
    )
    conn.execute(
        "INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", 1.0, 0.0, 30.0),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-09", "2024-01-10", "PIVOT_LOW", "UP", 1),
    )

    summary = run_technical_signal_relevance_for_tickers(
        conn, ["AAA"], "1d", "2024-01-01", "2024-01-31", "RUN_SERVICE_003", "2026-05-21T13:00:02Z"
    )

    assert summary.observations_seen == 2
    assert summary.records_written == 2


def test_service_handles_multiple_tickers_deterministically():
    conn = _connect()
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    conn.executemany(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        [
            ("ZZZ", "2024-01-11", "Hammer", 0.7, 45.0),
            ("AAA", "2024-01-10", "Hammer", 0.8, 40.0),
        ],
    )
    conn.executemany(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("ZZZ", "2024-01-10", "2024-01-11", "PIVOT_LOW", "UP", 1),
            ("AAA", "2024-01-09", "2024-01-10", "PIVOT_LOW", "UP", 1),
        ],
    )

    run_technical_signal_relevance_for_tickers(
        conn, ["ZZZ", "AAA", "AAA"], "1d", "2024-01-01", "2024-01-31", "RUN_SERVICE_004", "2026-05-21T13:00:03Z"
    )
    records = read_relevance_records_for_run(conn, "RUN_SERVICE_004")

    assert [row["ticker"] for row in records] == ["AAA", "ZZZ"]


def test_service_uses_observation_specific_as_of_date_for_dow_context():
    conn = _connect()
    _create_divergence_data(conn)
    _create_dow_events(conn)
    conn.execute(
        "INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", 0.0, 1.0, 65.0),
    )
    conn.executemany(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("AAA", "2024-01-09", "2024-01-10", "PIVOT_HIGH", "UP", 1),
            ("AAA", "2024-01-11", "2024-01-11", "BOS_DOWN", "UP", 1),
        ],
    )

    run_technical_signal_relevance_for_tickers(
        conn, ["AAA"], "1d", "2024-01-01", "2024-01-31", "RUN_SERVICE_005", "2026-05-21T13:00:04Z"
    )
    record = read_relevance_records_for_run(conn, "RUN_SERVICE_005")[0]

    assert record["relevance_reason"] == "UP_TREND_BEARISH_CONTINUATION_WITHOUT_BEARISH_STRUCTURE" or record["relevance_reason"] == "UP_TREND_COUNTER_BEARISH_REVERSAL_STRONG_WITHOUT_BOS" or record["relevance_reason"] == "UP_TREND_COUNTER_BEARISH_REVERSAL_MEDIUM_WITHOUT_BOS" or record["relevance_reason"] == "UP_TREND_REGULAR_BEARISH_DIVERGENCE_WEAK"
    assert record["latest_bos_direction"] is None


def test_service_handles_missing_dow_context_by_writing_weak_context():
    conn = _connect()
    _create_analysis_findings(conn)
    conn.execute(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", "Hammer", 0.8, 50.0),
    )

    summary = run_technical_signal_relevance_for_tickers(
        conn, ["AAA"], "1d", "2024-01-01", "2024-01-31", "RUN_SERVICE_006", "2026-05-21T13:00:05Z"
    )
    record = read_relevance_records_for_run(conn, "RUN_SERVICE_006")[0]

    assert summary.missing_dow_context_count == 1
    assert record["relevance_reason"] == "NO_DOW_CONTEXT_AVAILABLE"


def test_service_inserts_run_row_even_when_no_observations_are_found():
    conn = _connect()
    _create_analysis_findings(conn)

    summary = run_technical_signal_relevance_for_tickers(
        conn, ["AAA"], "1d", "2024-01-01", "2024-01-31", "RUN_SERVICE_007", "2026-05-21T13:00:06Z"
    )

    run_row = read_relevance_run(conn, "RUN_SERVICE_007")
    assert run_row is not None
    assert summary.observations_seen == 0


def test_service_writes_zero_relevance_rows_when_no_observations_are_found():
    conn = _connect()
    _create_analysis_findings(conn)

    summary = run_technical_signal_relevance_for_tickers(
        conn, ["AAA"], "1d", "2024-01-01", "2024-01-31", "RUN_SERVICE_008", "2026-05-21T13:00:07Z"
    )

    assert summary.records_written == 0
    assert read_relevance_records_for_run(conn, "RUN_SERVICE_008") == []


def test_duplicate_run_id_fails():
    conn = _connect()
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    conn.execute(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", "Hammer", 0.8, 50.0),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-09", "2024-01-10", "PIVOT_LOW", "UP", 1),
    )
    args = (conn, ["AAA"], "1d", "2024-01-01", "2024-01-31", "RUN_SERVICE_009", "2026-05-21T13:00:08Z")
    run_technical_signal_relevance_for_tickers(*args)
    with pytest.raises(sqlite3.IntegrityError):
        run_technical_signal_relevance_for_tickers(*args)


def test_duplicate_relevance_primary_key_fails_if_source_observations_duplicate_identity():
    conn = _connect()
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    conn.executemany(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        [
            ("AAA", "2024-01-10", "Hammer", 0.8, 50.0),
            ("AAA", "2024-01-10", "Hammer", 0.8, 50.0),
        ],
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-09", "2024-01-10", "PIVOT_LOW", "UP", 1),
    )

    with pytest.raises(sqlite3.IntegrityError):
        run_technical_signal_relevance_for_tickers(
            conn, ["AAA"], "1d", "2024-01-01", "2024-01-31", "RUN_SERVICE_010", "2026-05-21T13:00:09Z"
        )


def test_summary_counts_match_written_records():
    conn = _connect()
    _create_analysis_findings(conn)
    _create_divergence_data(conn)
    _create_dow_events(conn)
    conn.executemany(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        [
            ("AAA", "2024-01-10", "Hammer", 0.8, 50.0),
            ("BBB", "2024-01-10", "Bearish Flag", 0.8, 50.0),
        ],
    )
    conn.execute(
        "INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi) VALUES (?, ?, ?, ?, ?)",
        ("CCC", "2024-01-10", 1.0, 0.0, 30.0),
    )
    conn.executemany(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("AAA", "2024-01-09", "2024-01-10", "PIVOT_LOW", "UP", 1),
            ("BBB", "2024-01-09", "2024-01-10", "BOS_UP", "UP", 1),
            ("CCC", "2024-01-09", "2024-01-10", "BOS_UP", "UP", 1),
        ],
    )

    summary = run_technical_signal_relevance_for_tickers(
        conn, ["CCC", "BBB", "AAA"], "1d", "2024-01-01", "2024-01-31", "RUN_SERVICE_011", "2026-05-21T13:00:10Z"
    )
    records = read_relevance_records_for_run(conn, "RUN_SERVICE_011")

    assert summary.records_written == len(records)
    assert summary.relevant_count + summary.weak_context_count + summary.noise_count == len(records)


def test_service_with_ohlcv_bars_fills_bars_since_latest_bos_for_recent_bos():
    conn = _connect()
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    _create_osakedata(conn)
    conn.execute(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", "Evening Star", 0.8, 50.0),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-09", "2024-01-09", "BOS_DOWN", "UP", 1),
    )
    conn.executemany(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("AAA", "2024-01-08", 10.0, 11.0, 9.0, 10.0, 1000.0, "usa"),
            ("AAA", "2024-01-09", 10.0, 11.0, 9.0, 10.0, 1000.0, "usa"),
            ("AAA", "2024-01-10", 10.0, 11.0, 9.0, 10.0, 1000.0, "usa"),
        ],
    )

    summary = run_technical_signal_relevance_for_tickers(
        conn, ["AAA"], "1d", "2024-01-01", "2024-01-31", "RUN_SERVICE_012", "2026-05-21T13:00:11Z"
    )
    record = read_relevance_records_for_run(conn, "RUN_SERVICE_012")[0]

    assert summary.missing_bar_index_count == 0
    assert record["latest_bos_direction"] == "BOS_DOWN"
    assert record["bars_since_latest_bos"] == 1


def test_service_with_ohlcv_bars_allows_recent_bos_down_to_upgrade_bearish_reversal():
    conn = _connect()
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    _create_osakedata(conn)
    conn.execute(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", "Evening Star", 0.8, 50.0),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-09", "2024-01-09", "BOS_DOWN", "UP", 1),
    )
    conn.executemany(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("AAA", "2024-01-08", 10.0, 11.0, 9.0, 10.0, 1000.0, "usa"),
            ("AAA", "2024-01-09", 10.0, 11.0, 9.0, 10.0, 1000.0, "usa"),
            ("AAA", "2024-01-10", 10.0, 11.0, 9.0, 10.0, 1000.0, "usa"),
        ],
    )

    run_technical_signal_relevance_for_tickers(
        conn, ["AAA"], "1d", "2024-01-01", "2024-01-31", "RUN_SERVICE_013", "2026-05-21T13:00:12Z"
    )
    record = read_relevance_records_for_run(conn, "RUN_SERVICE_013")[0]

    assert record["relevance_class"] == "RELEVANT"
    assert record["relevance_reason"] == "UP_TREND_BEARISH_REVERSAL_AFTER_BOS_DOWN"


def test_service_with_ohlcv_bars_fills_near_latest_pivot_and_upgrades_bullish_reversal():
    conn = _connect()
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    _create_osakedata(conn)
    conn.execute(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", "Hammer", 0.8, 50.0),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-09", "2024-01-09", "PIVOT_LOW", "UP", 1),
    )
    conn.executemany(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("AAA", "2024-01-08", 10.0, 11.0, 9.0, 10.0, 1000.0, "usa"),
            ("AAA", "2024-01-09", 10.0, 11.0, 9.0, 10.0, 1000.0, "usa"),
            ("AAA", "2024-01-10", 10.0, 11.0, 9.0, 10.0, 1000.0, "usa"),
        ],
    )

    run_technical_signal_relevance_for_tickers(
        conn, ["AAA"], "1d", "2024-01-01", "2024-01-31", "RUN_SERVICE_014", "2026-05-21T13:00:13Z"
    )
    record = read_relevance_records_for_run(conn, "RUN_SERVICE_014")[0]

    assert record["near_latest_pivot"] == 1
    assert record["relevance_class"] == "RELEVANT"
    assert record["relevance_reason"] == "UP_TREND_BULLISH_DIP_REVERSAL_NEAR_PIVOT_LOW"


def test_service_does_not_use_calendar_day_fallback_when_ohlcv_rows_are_missing():
    conn = _connect()
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    _create_osakedata(conn)
    conn.execute(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", "Evening Star", 0.8, 50.0),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-09", "2024-01-09", "BOS_DOWN", "UP", 1),
    )
    conn.executemany(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("AAA", "2024-01-08", 10.0, 11.0, 9.0, 10.0, 1000.0, "usa"),
            ("AAA", "2024-01-10", 10.0, 11.0, 9.0, 10.0, 1000.0, "usa"),
        ],
    )

    summary = run_technical_signal_relevance_for_tickers(
        conn, ["AAA"], "1d", "2024-01-01", "2024-01-31", "RUN_SERVICE_015", "2026-05-21T13:00:14Z"
    )
    record = read_relevance_records_for_run(conn, "RUN_SERVICE_015")[0]

    assert summary.missing_bar_index_count == 1
    assert record["bars_since_latest_bos"] is None


def test_service_builds_bar_index_wide_enough_for_older_reset_within_max_lookback():
    conn = _connect()
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    _create_osakedata(conn)
    conn.execute(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-02-20", "Hammer", 0.8, 50.0),
    )
    conn.executemany(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("AAA", "2024-01-10", "2024-01-10", "RESET", "UP", 1),
            ("AAA", "2024-02-20", "2024-02-20", "PIVOT_LOW", "UP", 1),
        ],
    )
    _insert_osakedata_range(conn, "AAA", "2024-01-01", 80)

    summary = run_technical_signal_relevance_for_tickers(
        conn, ["AAA"], "1d", "2024-02-01", "2024-02-29", "RUN_SERVICE_016", "2026-05-22T09:00:00Z"
    )
    record = read_relevance_records_for_run(conn, "RUN_SERVICE_016")[0]

    assert summary.missing_bar_index_count == 0
    assert record["bars_since_latest_reset"] == 41
    assert "recent_reset=false" in record["rule_trace"]
    assert "missing_bar_index=false" in record["rule_trace"]


def test_service_builds_bar_index_wide_enough_for_older_bos_within_max_lookback():
    conn = _connect()
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    _create_osakedata(conn)
    conn.execute(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-02-20", "Evening Star", 0.8, 50.0),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-10", "2024-01-10", "BOS_DOWN", "UP", 1),
    )
    _insert_osakedata_range(conn, "AAA", "2024-01-01", 80)

    summary = run_technical_signal_relevance_for_tickers(
        conn, ["AAA"], "1d", "2024-02-01", "2024-02-29", "RUN_SERVICE_017", "2026-05-22T09:00:01Z"
    )
    record = read_relevance_records_for_run(conn, "RUN_SERVICE_017")[0]

    assert summary.missing_bar_index_count == 0
    assert record["latest_bos_direction"] == "BOS_DOWN"
    assert record["bars_since_latest_bos"] == 41
    assert record["relevance_class"] == "WEAK_CONTEXT"
    assert record["relevance_reason"] == "UP_TREND_COUNTER_BEARISH_REVERSAL_STRONG_WITHOUT_BOS"
    assert "recent_bos=false" in record["rule_trace"]
    assert "missing_bar_index=false" in record["rule_trace"]


def test_service_builds_bar_index_wide_enough_for_older_pivot_within_max_lookback():
    conn = _connect()
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    _create_osakedata(conn)
    conn.execute(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-02-20", "Hammer", 0.8, 50.0),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-10", "2024-01-10", "PIVOT_LOW", "UP", 1),
    )
    _insert_osakedata_range(conn, "AAA", "2024-01-01", 80)

    summary = run_technical_signal_relevance_for_tickers(
        conn, ["AAA"], "1d", "2024-02-01", "2024-02-29", "RUN_SERVICE_018", "2026-05-22T09:00:02Z"
    )
    record = read_relevance_records_for_run(conn, "RUN_SERVICE_018")[0]

    assert summary.missing_bar_index_count == 0
    assert record["near_latest_pivot"] == 0
    assert record["relevance_class"] == "WEAK_CONTEXT"
    assert record["relevance_reason"] == "UP_TREND_BULLISH_REVERSAL_WITHOUT_PIVOT_CONTEXT"
    assert "missing_bar_index=false" in record["rule_trace"]


def test_service_leaves_bar_distance_missing_when_event_is_older_than_max_lookback_cap():
    conn = _connect()
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    _create_osakedata(conn)
    conn.execute(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2025-02-20", "Evening Star", 0.8, 50.0),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-10", "2024-01-10", "BOS_DOWN", "UP", 1),
    )
    _insert_osakedata_range(conn, "AAA", "2024-01-01", 500)

    summary = run_technical_signal_relevance_for_tickers(
        conn, ["AAA"], "1d", "2025-02-01", "2025-02-28", "RUN_SERVICE_019", "2026-05-22T09:00:03Z"
    )
    record = read_relevance_records_for_run(conn, "RUN_SERVICE_019")[0]

    assert summary.missing_bar_index_count == 1
    assert record["bars_since_latest_bos"] is None
    assert "recent_bos=false" in record["rule_trace"]
    assert "missing_bar_index=true" in record["rule_trace"]
