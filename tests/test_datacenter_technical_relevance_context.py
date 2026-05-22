from __future__ import annotations

import sqlite3

from analysis.datacenter_indices.technical_relevance_context import (
    load_technical_relevance_context,
    select_latest_relevance_companion_rows,
)
from rawcandle.technical_signal_relevance import TechnicalSignalRelevanceConfig
from rawcandle.technical_signal_relevance_persistence import (
    TechnicalSignalRelevanceStoredRow,
    apply_technical_signal_relevance_migration,
    build_relevance_run_row,
    insert_relevance_records,
    insert_relevance_run,
)


def _connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    apply_technical_signal_relevance_migration(conn)
    return conn


def _insert_run(conn: sqlite3.Connection, run_id: str) -> None:
    insert_relevance_run(
        conn,
        build_relevance_run_row(
            run_id=run_id,
            config=TechnicalSignalRelevanceConfig(),
            created_at_utc="2026-05-22T00:00:00Z",
        ),
    )


def _insert_record(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    ticker: str,
    signal_date: str,
    signal_name: str,
    relevance_class: str,
    relevance_reason: str,
    timeframe: str = "1d",
) -> None:
    insert_relevance_records(
        conn,
        [
            TechnicalSignalRelevanceStoredRow(
                ticker=ticker,
                timeframe=timeframe,
                signal_date=signal_date,
                signal_confirmed_as_of_date=signal_date,
                signal_name=signal_name,
                signal_close_price=100.0,
                signal_direction="BULLISH",
                signal_family="REVERSAL_MEDIUM",
                signal_source_type="CANDLE",
                signal_source_id="CANDLE",
                dow_trend_state="UP",
                dow_context_state="NORMAL",
                latest_bos_direction="BOS_UP",
                bars_since_latest_bos=3,
                latest_reset_reason="RESET",
                bars_since_latest_reset=8,
                near_latest_pivot=1,
                near_active_bos_level=0,
                is_trend_aligned=1,
                is_counter_trend=0,
                relevance_class=relevance_class,
                relevance_reason=relevance_reason,
                relevance_rule_version="TECH_SIGNAL_RELEVANCE_V1",
                mapping_version="TECH_SIGNAL_MAPPING_V1",
                reason_version="TECH_SIGNAL_RELEVANCE_REASON_V1",
                rule_trace='["missing_bar_index=false"]',
                created_at_utc="2026-05-22T00:00:00Z",
                run_id=run_id,
            )
        ],
    )


def test_load_technical_relevance_context_filters_by_run_id(tmp_path):
    db_path = tmp_path / "analysis.db"
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_run(conn, "RUN_B")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2024-01-10", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="A")
    _insert_record(conn, run_id="RUN_B", ticker="AAA", signal_date="2024-01-10", signal_name="Hammer", relevance_class="WEAK_CONTEXT", relevance_reason="B")
    conn.commit()

    rows = load_technical_relevance_context(
        conn,
        technical_relevance_run_id="RUN_B",
        tickers=["AAA"],
        timeframe="1d",
        start_date="2024-01-10",
        end_date="2024-01-10",
    )

    assert [row.relevance_reason for row in rows] == ["B"]


def test_load_technical_relevance_context_filters_by_ticker_timeframe_and_date_range(tmp_path):
    db_path = tmp_path / "analysis.db"
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2024-01-10", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="A")
    _insert_record(conn, run_id="RUN_A", ticker="BBB", signal_date="2024-01-10", signal_name="Hammer", relevance_class="WEAK_CONTEXT", relevance_reason="B")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2024-01-11", signal_name="Morning Star", relevance_class="NOISE", relevance_reason="C", timeframe="1wk")
    conn.commit()

    rows = load_technical_relevance_context(
        conn,
        technical_relevance_run_id="RUN_A",
        tickers=["AAA", "CCC"],
        timeframe="1d",
        start_date="2024-01-10",
        end_date="2024-01-10",
    )

    assert [(row.ticker, row.timeframe, row.signal_date) for row in rows] == [
        ("AAA", "1d", "2024-01-10")
    ]


def test_load_technical_relevance_context_returns_deterministic_order_and_all_classes_by_default(tmp_path):
    db_path = tmp_path / "analysis.db"
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(conn, run_id="RUN_A", ticker="BBB", signal_date="2024-01-10", signal_name="Hammer", relevance_class="WEAK_CONTEXT", relevance_reason="B")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2024-01-10", signal_name="Morning Star", relevance_class="NOISE", relevance_reason="C")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2024-01-10", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="A")
    conn.commit()

    rows = load_technical_relevance_context(
        conn,
        technical_relevance_run_id="RUN_A",
        tickers=["BBB", "AAA"],
        timeframe="1d",
        start_date="2024-01-10",
        end_date="2024-01-10",
    )

    assert [(row.ticker, row.signal_name, row.relevance_class, row.relevance_reason) for row in rows] == [
        ("AAA", "Hammer", "RELEVANT", "A"),
        ("AAA", "Morning Star", "NOISE", "C"),
        ("BBB", "Hammer", "WEAK_CONTEXT", "B"),
    ]


def test_load_technical_relevance_context_can_filter_relevance_classes(tmp_path):
    db_path = tmp_path / "analysis.db"
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2024-01-10", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="A")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2024-01-10", signal_name="Morning Star", relevance_class="NOISE", relevance_reason="B")
    conn.commit()

    rows = load_technical_relevance_context(
        conn,
        technical_relevance_run_id="RUN_A",
        tickers=["AAA"],
        timeframe="1d",
        start_date="2024-01-10",
        end_date="2024-01-10",
        relevance_classes=["RELEVANT"],
    )

    assert [(row.signal_name, row.relevance_class) for row in rows] == [("Hammer", "RELEVANT")]


def test_select_latest_relevance_companion_rows_separates_bullish_and_bearish_and_ignores_noise(tmp_path):
    db_path = tmp_path / "analysis.db"
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2024-01-09", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="BULL")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2024-01-10", signal_name="Bearish Divergence", relevance_class="WEAK_CONTEXT", relevance_reason="BEAR")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2024-01-10", signal_name="Morning Star", relevance_class="NOISE", relevance_reason="NOISE_BULL")
    conn.commit()

    rows = load_technical_relevance_context(
        conn,
        technical_relevance_run_id="RUN_A",
        tickers=["AAA"],
        timeframe="1d",
        start_date="2024-01-09",
        end_date="2024-01-10",
    )

    companion = select_latest_relevance_companion_rows(
        rows,
        ticker="AAA",
        timeframe="1d",
        signal_date="2024-01-10",
    )

    assert companion.latest_bullish_relevance_signal_name == "Hammer"
    assert companion.latest_bullish_relevance_class == "RELEVANT"
    assert companion.latest_bullish_relevance_reason == "BULL"
    assert companion.latest_bearish_relevance_signal_name == "Bearish Divergence"
    assert companion.latest_bearish_relevance_class == "WEAK_CONTEXT"
    assert companion.latest_bearish_relevance_reason == "BEAR"


def test_select_latest_relevance_companion_rows_prefers_relevant_over_weaker_newer_signal(tmp_path):
    db_path = tmp_path / "analysis.db"
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2024-01-09", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="OLDER_RELEVANT")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2024-01-10", signal_name="Morning Star", relevance_class="WEAK_CONTEXT", relevance_reason="NEWER_WEAK")
    conn.commit()

    rows = load_technical_relevance_context(
        conn,
        technical_relevance_run_id="RUN_A",
        tickers=["AAA"],
        timeframe="1d",
        start_date="2024-01-09",
        end_date="2024-01-10",
    )

    companion = select_latest_relevance_companion_rows(
        rows,
        ticker="AAA",
        timeframe="1d",
        signal_date="2024-01-10",
    )

    assert companion.latest_bullish_relevance_signal_name == "Hammer"
    assert companion.latest_bullish_relevance_class == "RELEVANT"
    assert companion.latest_bullish_relevance_reason == "OLDER_RELEVANT"


def test_select_latest_relevance_companion_rows_uses_latest_date_and_deterministic_ties(tmp_path):
    db_path = tmp_path / "analysis.db"
    conn = _connect(db_path)
    _insert_run(conn, "RUN_A")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2024-01-09", signal_name="Hammer", relevance_class="RELEVANT", relevance_reason="OLDER")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2024-01-10", signal_name="Morning Star", relevance_class="RELEVANT", relevance_reason="B_REASON")
    _insert_record(conn, run_id="RUN_A", ticker="AAA", signal_date="2024-01-10", signal_name="Piercing Pattern", relevance_class="RELEVANT", relevance_reason="A_REASON")
    conn.commit()

    rows = load_technical_relevance_context(
        conn,
        technical_relevance_run_id="RUN_A",
        tickers=["AAA"],
        timeframe="1d",
        start_date="2024-01-09",
        end_date="2024-01-10",
    )

    companion = select_latest_relevance_companion_rows(
        rows,
        ticker="AAA",
        timeframe="1d",
        signal_date="2024-01-10",
    )

    assert companion.latest_bullish_relevance_signal_date == "2024-01-10"
    assert companion.latest_bullish_relevance_signal_name == "Morning Star"
    assert companion.latest_bullish_relevance_reason == "B_REASON"
