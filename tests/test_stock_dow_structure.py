from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from analysis.stock_dow_structure import (
    DEFAULT_PIVOT_RADIUS,
    calculate_ticker_events,
    ensure_stock_dow_structure_schema,
    fetch_price_bars,
    format_summary_lines,
    run_stock_dow_structure,
)


def _create_analysis_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        ensure_stock_dow_structure_schema(conn)


def _create_osakedata_db(
    path: Path,
    closes: list[float],
    *,
    ticker: str = "TEST",
    market: str = "usa",
    start_date: date = date(2026, 1, 1),
) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT NOT NULL,
                pvm TEXT NOT NULL,
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
        for idx, close_value in enumerate(closes):
            current_date = start_date + timedelta(days=idx)
            rows.append(
                (
                    ticker,
                    current_date.isoformat(),
                    close_value - 0.25,
                    close_value + 1.0,
                    close_value - 1.0,
                    close_value,
                    1000 + idx,
                    market,
                )
            )
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _load_event_rows(db_path: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT *
            FROM stock_dow_structure_events
            ORDER BY confirmed_as_of_date ASC, event_date ASC, id ASC
            """
        ).fetchall()


def _load_bars(db_path: Path, ticker: str = "TEST"):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return fetch_price_bars(conn, ticker)


def test_pivot_confirmation_uses_event_date_and_confirmed_as_of_date(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    closes = [10, 11, 12, 15, 12, 11, 10]
    _create_osakedata_db(osakedata_db, closes)

    bars = _load_bars(osakedata_db)
    events = calculate_ticker_events(
        bars,
        pivot_radius=DEFAULT_PIVOT_RADIUS,
        start_confirmed_as_of_date=bars[0].date,
        initial_state=None,
        run_id="run-test",
        created_at_utc="2026-01-01T00:00:00+00:00",
    )

    pivot_high = next(row for row in events if row["event_type"] == "PIVOT_HIGH")
    assert pivot_high["event_date"] == "2026-01-04"
    assert pivot_high["confirmed_as_of_date"] == "2026-01-07"


def test_no_lookahead_skips_unconfirmed_last_three_trading_days(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    closes = [10, 11, 12, 15, 12, 11]
    _create_osakedata_db(osakedata_db, closes)

    bars = _load_bars(osakedata_db)
    events = calculate_ticker_events(
        bars,
        pivot_radius=DEFAULT_PIVOT_RADIUS,
        start_confirmed_as_of_date=bars[0].date,
        initial_state=None,
        run_id="run-test",
        created_at_utc="2026-01-01T00:00:00+00:00",
    )

    assert not [row for row in events if row["event_type"].startswith("PIVOT_")]


def test_unique_pivot_rule_rejects_tied_highs(tmp_path):
    osakedata_db = tmp_path / "osakedata.db"
    closes = [10, 12, 15, 15, 12, 11, 10]
    _create_osakedata_db(osakedata_db, closes)

    bars = _load_bars(osakedata_db)
    events = calculate_ticker_events(
        bars,
        pivot_radius=DEFAULT_PIVOT_RADIUS,
        start_confirmed_as_of_date=bars[0].date,
        initial_state=None,
        run_id="run-test",
        created_at_utc="2026-01-01T00:00:00+00:00",
    )

    assert not [row for row in events if row["event_type"] == "PIVOT_HIGH"]


def test_hh_hl_sequence_creates_up_trend(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    closes = [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14]
    _create_osakedata_db(osakedata_db, closes)

    summary = run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
    )

    rows = _load_event_rows(analysis_db)
    pivot_low = next(
        row
        for row in rows
        if row["event_type"] == "PIVOT_LOW" and row["dow_label_low"] == "HL"
    )
    trend_change = next(
        row
        for row in rows
        if row["event_type"] == "TREND_CHANGE"
        and row["trend_state"] == "UP"
        and row["confirmed_as_of_date"] == pivot_low["confirmed_as_of_date"]
    )

    assert pivot_low["event_date"] == "2026-01-14"
    assert pivot_low["confirmed_as_of_date"] == "2026-01-17"
    assert pivot_low["trend_state"] == "UP"
    assert trend_change["event_date"] == "2026-01-14"
    assert summary["trend_change_events"] == 1


def test_lh_ll_sequence_creates_down_trend(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    closes = [10, 12, 14, 17, 15, 13, 11, 8, 10, 12, 15, 13, 11, 6, 8, 10, 12]
    _create_osakedata_db(osakedata_db, closes)

    summary = run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
    )

    rows = _load_event_rows(analysis_db)
    pivot_low = next(
        row
        for row in rows
        if row["event_type"] == "PIVOT_LOW" and row["dow_label_low"] == "LL"
    )
    trend_change = next(
        row
        for row in rows
        if row["event_type"] == "TREND_CHANGE"
        and row["trend_state"] == "DOWN"
        and row["confirmed_as_of_date"] == pivot_low["confirmed_as_of_date"]
    )

    assert pivot_low["event_date"] == "2026-01-14"
    assert pivot_low["confirmed_as_of_date"] == "2026-01-17"
    assert pivot_low["trend_state"] == "DOWN"
    assert trend_change["event_date"] == "2026-01-14"
    assert summary["trend_change_events"] == 1


def test_bos_down_then_reset_increments_epoch_and_clears_structure(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    closes = [
        10,
        11,
        12,
        15,
        13,
        11,
        9,
        7,
        9,
        12,
        16,
        13,
        11,
        9,
        10,
        12,
        14,
        8,
        7,
    ]
    _create_osakedata_db(osakedata_db, closes)

    summary = run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
    )

    rows = _load_event_rows(analysis_db)
    bos = next(row for row in rows if row["event_type"] == "BOS_DOWN")
    reset = next(row for row in rows if row["event_type"] == "RESET")
    trend_change = next(
        row
        for row in rows
        if row["event_type"] == "TREND_CHANGE"
        and row["trend_state"] == "NEUTRAL"
        and row["confirmed_as_of_date"] == reset["confirmed_as_of_date"]
    )

    assert bos["bos_down_count"] == 1
    assert reset["event_date"] == "2026-01-19"
    assert reset["confirmed_as_of_date"] == "2026-01-19"
    assert reset["trend_state"] == "NEUTRAL"
    assert reset["structure_epoch_id"] == 2
    assert reset["structural_high_date"] is None
    assert reset["structural_low_date"] is None
    assert reset["last_high_label"] is None
    assert reset["last_low_label"] is None
    assert reset["bos_up_count"] == 0
    assert reset["bos_down_count"] == 0
    assert reset["reset_reason"] == "DOUBLE_BOS_DOWN"
    assert trend_change["event_date"] == reset["event_date"]
    assert summary["reset_events"] == 1


def test_bos_counter_resets_when_price_recovers_before_second_break(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    closes = [
        10,
        11,
        12,
        15,
        13,
        11,
        9,
        7,
        9,
        12,
        16,
        13,
        11,
        9,
        10,
        12,
        14,
        8,
        10,
        15,
        7,
    ]
    _create_osakedata_db(osakedata_db, closes)

    summary = run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
    )

    rows = _load_event_rows(analysis_db)
    bos_rows = [row for row in rows if row["event_type"] == "BOS_DOWN"]
    reset_rows = [row for row in rows if row["event_type"] == "RESET"]

    assert [row["event_date"] for row in bos_rows] == ["2026-01-18", "2026-01-21"]
    assert all(row["bos_down_count"] == 1 for row in bos_rows)
    assert reset_rows == []
    assert summary["bos_down_events"] == 2
    assert summary["reset_events"] == 0


def test_incremental_tail_deletes_and_rewrites_rows_from_recalc_start_date(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    initial_closes = [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14]
    _create_osakedata_db(osakedata_db, initial_closes)

    summary_first = run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
        run_id="run1",
    )
    assert summary_first["tickers_full_recalculated"] == 1

    with sqlite3.connect(osakedata_db) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("TEST", "2026-01-18", 7.75, 9.0, 7.0, 8.0, 1018, "usa"),
                ("TEST", "2026-01-19", 6.75, 8.0, 6.0, 7.0, 1019, "usa"),
            ],
        )
        conn.commit()

    summary_second = run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
        recalc_tail_trading_days=3,
        run_id="run2",
    )

    rows = _load_event_rows(analysis_db)
    old_rows = [row for row in rows if row["run_id"] == "run1"]
    new_rows = [row for row in rows if row["run_id"] == "run2"]

    assert summary_second["tickers_incremental_recalculated"] == 1
    assert summary_second["rows_deleted"] > 0
    assert old_rows
    assert new_rows
    assert all(row["confirmed_as_of_date"] < "2026-01-14" for row in old_rows)
    assert all(row["confirmed_as_of_date"] >= "2026-01-14" for row in new_rows)


def test_cli_dry_run_creates_table_and_prints_deterministic_summary(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_osakedata_db(osakedata_db, [10, 11, 12, 15, 12, 11, 10], ticker="AAA")

    summary = run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="AAA",
        dry_run=True,
        run_id="dryrun",
    )
    lines = format_summary_lines(summary)
    print("\n".join(lines))

    captured = capsys.readouterr().out.strip().splitlines()
    assert captured[0] == "SUMMARY tickers_requested=1"
    assert captured[-1] == "SUMMARY errors=0"

    with sqlite3.connect(analysis_db) as conn:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'stock_dow_structure_events'
            """
        ).fetchone()
        assert row is not None
