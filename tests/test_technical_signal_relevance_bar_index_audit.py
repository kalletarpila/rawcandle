import json
import sqlite3

from rawcandle.technical_signal_relevance import TechnicalSignalRelevanceConfig
from rawcandle.technical_signal_relevance_bar_index_audit import (
    EVENT_OR_PIVOT_ID_NOT_AVAILABLE_FOR_AUDIT,
    MISSING_OHLCV_SOURCE,
    NO_LATEST_BOS_OR_RESET_OR_PIVOT_CONTEXT,
    NO_OHLCV_ROWS_FOR_TICKER,
    NO_RELEVANCE_ROWS_FOR_RUN,
    OBSERVATION_DATE_NOT_IN_BAR_INDEX,
    audit_missing_bar_index_for_run,
)
from rawcandle.technical_signal_relevance_persistence import (
    apply_technical_signal_relevance_migration,
    build_relevance_run_row,
    insert_relevance_run,
)


def _analysis_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    apply_technical_signal_relevance_migration(conn)
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            event_date TEXT NOT NULL,
            confirmed_as_of_date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            trend_state TEXT,
            structure_epoch_id INTEGER
        )
        """
    )
    return conn


def _osakedata_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
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
    return conn


def _insert_run(conn: sqlite3.Connection, run_id: str) -> None:
    insert_relevance_run(
        conn,
        build_relevance_run_row(
            run_id=run_id,
            config=TechnicalSignalRelevanceConfig(),
            created_at_utc="2026-05-21T00:00:00Z",
        ),
    )


def _insert_relevance_row(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str = "AAA",
    signal_date: str = "2026-05-06",
    signal_name: str = "Hammer",
    rule_trace_entries: list[str],
) -> None:
    conn.execute(
        """
        INSERT INTO technical_signal_relevance (
            ticker,
            timeframe,
            signal_date,
            signal_confirmed_as_of_date,
            signal_name,
            signal_close_price,
            signal_direction,
            signal_family,
            signal_source_type,
            signal_source_id,
            dow_trend_state,
            dow_context_state,
            latest_bos_direction,
            bars_since_latest_bos,
            latest_reset_reason,
            bars_since_latest_reset,
            near_latest_pivot,
            near_active_bos_level,
            is_trend_aligned,
            is_counter_trend,
            relevance_class,
            relevance_reason,
            relevance_rule_version,
            mapping_version,
            reason_version,
            rule_trace,
            created_at_utc,
            run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticker,
            "1d",
            signal_date,
            signal_date,
            signal_name,
            100.0,
            "BULLISH",
            "REVERSAL_MEDIUM",
            "CANDLE",
            "CANDLE",
            "UP",
            "NORMAL",
            None,
            None,
            None,
            None,
            0,
            0,
            1,
            0,
            "WEAK_CONTEXT",
            "UP_TREND_BULLISH_REVERSAL_WITHOUT_PIVOT_CONTEXT",
            "TECH_SIGNAL_RELEVANCE_V1",
            "TECH_SIGNAL_MAPPING_V1",
            "TECH_SIGNAL_RELEVANCE_REASON_V1",
            json.dumps(rule_trace_entries, ensure_ascii=True, separators=(",", ":")),
            "2026-05-21T00:00:00Z",
            run_id,
        ),
    )


def test_audit_returns_no_relevance_rows_for_missing_run_id():
    conn = _analysis_conn()

    summary = audit_missing_bar_index_for_run(conn, "MISSING_RUN")

    assert summary.rows_total == 0
    assert summary.rows_missing_bar_index == 0
    assert summary.category_counts[NO_RELEVANCE_ROWS_FOR_RUN] == 1


def test_audit_counts_rows_missing_bar_index_correctly():
    conn = _analysis_conn()
    osake_conn = _osakedata_conn()
    _insert_run(conn, "RUN_AUDIT_001")
    osake_conn.execute(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2026-05-06", 1.0, 1.0, 1.0, 1.0, 1.0, "usa"),
    )
    _insert_relevance_row(
        conn,
        run_id="RUN_AUDIT_001",
        rule_trace_entries=[
            "missing_bar_index=true",
            "latest_bos_event_id=null",
            "latest_reset_event_id=null",
            "latest_pivot_event_id=null",
        ],
    )
    _insert_relevance_row(
        conn,
        run_id="RUN_AUDIT_001",
        ticker="BBB",
        signal_name="Bullish Flag",
        rule_trace_entries=["missing_bar_index=false"],
    )

    summary = audit_missing_bar_index_for_run(conn, "RUN_AUDIT_001", osakedata_conn=osake_conn)

    assert summary.rows_total == 2
    assert summary.rows_missing_bar_index == 1
    assert summary.rows_with_bar_index_available == 1


def test_audit_categorizes_missing_ohlcv_source():
    conn = _analysis_conn()
    _insert_run(conn, "RUN_AUDIT_002")
    _insert_relevance_row(
        conn,
        run_id="RUN_AUDIT_002",
        rule_trace_entries=[
            "missing_bar_index=true",
            "latest_bos_event_id=null",
            "latest_reset_event_id=null",
            "latest_pivot_event_id=null",
        ],
    )

    summary = audit_missing_bar_index_for_run(conn, "RUN_AUDIT_002")

    assert summary.category_counts[MISSING_OHLCV_SOURCE] == 1


def test_audit_categorizes_no_ohlcv_rows_for_ticker():
    conn = _analysis_conn()
    osake_conn = _osakedata_conn()
    _insert_run(conn, "RUN_AUDIT_003")
    _insert_relevance_row(
        conn,
        run_id="RUN_AUDIT_003",
        rule_trace_entries=[
            "missing_bar_index=true",
            "latest_bos_event_id=null",
            "latest_reset_event_id=null",
            "latest_pivot_event_id=null",
        ],
    )

    summary = audit_missing_bar_index_for_run(conn, "RUN_AUDIT_003", osakedata_conn=osake_conn)

    assert summary.category_counts[NO_OHLCV_ROWS_FOR_TICKER] == 1


def test_audit_categorizes_observation_date_not_in_bar_index():
    conn = _analysis_conn()
    osake_conn = _osakedata_conn()
    _insert_run(conn, "RUN_AUDIT_004")
    osake_conn.execute(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2026-05-05", 1.0, 1.0, 1.0, 1.0, 1.0, "usa"),
    )
    _insert_relevance_row(
        conn,
        run_id="RUN_AUDIT_004",
        rule_trace_entries=[
            "missing_bar_index=true",
            "latest_bos_event_id=null",
            "latest_reset_event_id=null",
            "latest_pivot_event_id=null",
        ],
    )

    summary = audit_missing_bar_index_for_run(conn, "RUN_AUDIT_004", osakedata_conn=osake_conn)

    assert summary.category_counts[OBSERVATION_DATE_NOT_IN_BAR_INDEX] == 1


def test_audit_categorizes_no_latest_bos_or_reset_or_pivot_context():
    conn = _analysis_conn()
    osake_conn = _osakedata_conn()
    _insert_run(conn, "RUN_AUDIT_005")
    osake_conn.execute(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2026-05-06", 1.0, 1.0, 1.0, 1.0, 1.0, "usa"),
    )
    _insert_relevance_row(
        conn,
        run_id="RUN_AUDIT_005",
        rule_trace_entries=[
            "missing_bar_index=true",
            "latest_bos_event_id=null",
            "latest_reset_event_id=null",
            "latest_pivot_event_id=null",
        ],
    )

    summary = audit_missing_bar_index_for_run(conn, "RUN_AUDIT_005", osakedata_conn=osake_conn)

    assert summary.category_counts[NO_LATEST_BOS_OR_RESET_OR_PIVOT_CONTEXT] == 1


def test_audit_categorizes_event_or_pivot_id_not_available_for_audit():
    conn = _analysis_conn()
    osake_conn = _osakedata_conn()
    _insert_run(conn, "RUN_AUDIT_006")
    osake_conn.execute(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2026-05-06", 1.0, 1.0, 1.0, 1.0, 1.0, "usa"),
    )
    _insert_relevance_row(
        conn,
        run_id="RUN_AUDIT_006",
        rule_trace_entries=[
            "missing_bar_index=true",
            "some_other_trace_key=value",
        ],
    )

    summary = audit_missing_bar_index_for_run(conn, "RUN_AUDIT_006", osakedata_conn=osake_conn)

    assert summary.category_counts[EVENT_OR_PIVOT_ID_NOT_AVAILABLE_FOR_AUDIT] == 1


def test_audit_sample_rows_are_deterministic():
    conn = _analysis_conn()
    osake_conn = _osakedata_conn()
    _insert_run(conn, "RUN_AUDIT_007")
    osake_conn.executemany(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("AAA", "2026-05-06", 1.0, 1.0, 1.0, 1.0, 1.0, "usa"),
            ("BBB", "2026-05-06", 1.0, 1.0, 1.0, 1.0, 1.0, "usa"),
        ],
    )
    _insert_relevance_row(
        conn,
        run_id="RUN_AUDIT_007",
        ticker="BBB",
        signal_name="Hammer",
        rule_trace_entries=["missing_bar_index=true", "some_key=value"],
    )
    _insert_relevance_row(
        conn,
        run_id="RUN_AUDIT_007",
        ticker="AAA",
        signal_name="Hammer",
        rule_trace_entries=["missing_bar_index=true", "some_key=value"],
    )

    summary = audit_missing_bar_index_for_run(
        conn,
        "RUN_AUDIT_007",
        osakedata_conn=osake_conn,
        limit_samples=10,
    )

    samples = summary.sample_rows_by_category[EVENT_OR_PIVOT_ID_NOT_AVAILABLE_FOR_AUDIT]
    assert [sample.ticker for sample in samples] == ["AAA", "BBB"]


def test_audit_uses_full_ticker_date_span_for_bar_index_lookup():
    conn = _analysis_conn()
    osake_conn = _osakedata_conn()
    _insert_run(conn, "RUN_AUDIT_008")
    osake_conn.executemany(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("AAA", "2026-05-01", 1.0, 1.0, 1.0, 1.0, 1.0, "usa"),
            ("AAA", "2026-05-02", 1.0, 1.0, 1.0, 1.0, 1.0, "usa"),
            ("AAA", "2026-05-03", 1.0, 1.0, 1.0, 1.0, 1.0, "usa"),
        ],
    )
    _insert_relevance_row(
        conn,
        run_id="RUN_AUDIT_008",
        signal_date="2026-05-01",
        signal_name="Hammer",
        rule_trace_entries=[
            "missing_bar_index=true",
            "latest_bos_event_id=null",
            "latest_reset_event_id=null",
            "latest_pivot_event_id=null",
        ],
    )
    _insert_relevance_row(
        conn,
        run_id="RUN_AUDIT_008",
        signal_date="2026-05-03",
        signal_name="Morning Star",
        rule_trace_entries=[
            "missing_bar_index=true",
            "latest_bos_event_id=null",
            "latest_reset_event_id=null",
            "latest_pivot_event_id=null",
        ],
    )

    summary = audit_missing_bar_index_for_run(conn, "RUN_AUDIT_008", osakedata_conn=osake_conn)

    assert summary.category_counts[OBSERVATION_DATE_NOT_IN_BAR_INDEX] == 0
    assert summary.category_counts[NO_LATEST_BOS_OR_RESET_OR_PIVOT_CONTEXT] == 2
