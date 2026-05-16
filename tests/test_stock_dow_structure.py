from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from analysis.run_stock_dow_structure import parse_args, parse_recalc_from_date
from analysis.stock_dow_structure import (
    DEFAULT_BOUNDED_INITIAL_FROM_DATE,
    DEFAULT_PIVOT_RADIUS,
    DEFAULT_RECALC_TAIL_TRADING_DAYS,
    calculate_ticker_events,
    calculate_missing_or_outdated_stock_dow_structures,
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS osakedata (
                osake TEXT NOT NULL,
                pvm TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                market TEXT
            )
            """)
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
        conn.commit()


def _insert_osakedata_rows(
    path: Path,
    rows: list[tuple[str, str, float, float, float, float, int, str]],
) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def _insert_close_series_for_dates(
    path: Path,
    dates: list[str],
    closes: list[float],
    *,
    ticker: str = "TEST",
    market: str = "usa",
) -> None:
    rows = []
    for idx, (current_date, close_value) in enumerate(zip(dates, closes, strict=True)):
        rows.append(
            (
                ticker,
                current_date,
                close_value - 0.25,
                close_value + 1.0,
                close_value - 1.0,
                close_value,
                1000 + idx,
                market,
            )
        )
    _insert_osakedata_rows(path, rows)


def _load_event_rows(db_path: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("""
            SELECT *
            FROM stock_dow_structure_events
            ORDER BY confirmed_as_of_date ASC, event_date ASC, id ASC
            """).fetchall()


def _load_bars(db_path: Path, ticker: str = "TEST"):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return fetch_price_bars(conn, ticker)


def _load_table_columns(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return {
            str(row["name"])
            for row in conn.execute(
                "PRAGMA table_info(stock_dow_structure_events)"
            ).fetchall()
        }


def _load_status_row(db_path: Path, ticker: str) -> sqlite3.Row | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT *
            FROM stock_dow_structure_status
            WHERE ticker = ?
              AND price_source = 'close'
              AND pivot_radius = 3
            """,
            (ticker,),
        ).fetchone()


def _event_run_ids_by_boundary(
    db_path: Path,
    boundary_date: str,
) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    rows = _load_event_rows(db_path)
    return (
        [row for row in rows if row["confirmed_as_of_date"] < boundary_date],
        [row for row in rows if row["confirmed_as_of_date"] >= boundary_date],
    )


def test_pivot_confirmation_uses_event_date_and_confirmed_as_of_date(tmp_path):
    def test_pivot_high_detected_from_high_not_close(tmp_path):
        osakedata_db = tmp_path / "osakedata.db"
        # High forms a local max at idx=3, but close does not
        closes = [10, 11, 12, 13, 12, 11, 10]
        highs = [10, 11, 12, 20, 12, 11, 10]  # Only idx=3 is a unique high
        lows = [9, 10, 11, 12, 11, 10, 9]
        with sqlite3.connect(osakedata_db) as conn:
            conn.execute("""
                CREATE TABLE osakedata (
                    osake TEXT, pvm TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER, market TEXT
                )""")
            for i in range(7):
                conn.execute(
                    "INSERT INTO osakedata VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "TEST",
                        f"2026-01-0{i+1}",
                        0,
                        highs[i],
                        lows[i],
                        closes[i],
                        1000 + i,
                        "test",
                    ),
                )
            conn.commit()
        bars = fetch_price_bars(sqlite3.connect(osakedata_db), "TEST")
        events = calculate_ticker_events(
            bars,
            pivot_radius=3,
            start_confirmed_as_of_date=bars[0].date,
            initial_state=None,
            run_id="run-high-test",
            created_at_utc="2026-01-01T00:00:00+00:00",
        )
        assert any(
            e["event_type"] == "PIVOT_HIGH" and e["pivot_high_price"] == 20
            for e in events
        )
        # Confirm that close at idx=3 is not a local max, so old logic would not have triggered

    def test_pivot_low_detected_from_low_not_close(tmp_path):
        osakedata_db = tmp_path / "osakedata.db"
        closes = [10, 11, 12, 13, 12, 11, 10]
        highs = [10, 11, 12, 13, 12, 11, 10]
        lows = [9, 10, 11, 1, 11, 10, 9]  # Only idx=3 is a unique low
        with sqlite3.connect(osakedata_db) as conn:
            conn.execute("""
                CREATE TABLE osakedata (
                    osake TEXT, pvm TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER, market TEXT
                )""")
            for i in range(7):
                conn.execute(
                    "INSERT INTO osakedata VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "TEST",
                        f"2026-01-0{i+1}",
                        0,
                        highs[i],
                        lows[i],
                        closes[i],
                        1000 + i,
                        "test",
                    ),
                )
            conn.commit()
        bars = fetch_price_bars(sqlite3.connect(osakedata_db), "TEST")
        events = calculate_ticker_events(
            bars,
            pivot_radius=3,
            start_confirmed_as_of_date=bars[0].date,
            initial_state=None,
            run_id="run-low-test",
            created_at_utc="2026-01-01T00:00:00+00:00",
        )
        assert any(
            e["event_type"] == "PIVOT_LOW" and e["pivot_low_price"] == 1 for e in events
        )

    def test_bos_up_triggered_by_high_not_close(tmp_path):
        osakedata_db = tmp_path / "osakedata.db"
        # Setup: active_bos_high_price = 15, high breaks it but close does not
        closes = [10, 12, 14, 15, 13, 11, 10, 16]
        highs = [10, 12, 14, 15, 13, 11, 10, 20]  # high=20 at idx=7 breaks BOS
        lows = [9, 10, 11, 12, 11, 10, 9, 8]
        with sqlite3.connect(osakedata_db) as conn:
            conn.execute("""
                CREATE TABLE osakedata (
                    osake TEXT, pvm TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER, market TEXT
                )""")
            for i in range(8):
                conn.execute(
                    "INSERT INTO osakedata VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "TEST",
                        f"2026-01-0{i+1}",
                        0,
                        highs[i],
                        lows[i],
                        closes[i],
                        1000 + i,
                        "test",
                    ),
                )
            conn.commit()
        bars = fetch_price_bars(sqlite3.connect(osakedata_db), "TEST")
        events = calculate_ticker_events(
            bars,
            pivot_radius=3,
            start_confirmed_as_of_date=bars[0].date,
            initial_state=None,
            run_id="run-bosup-test",
            created_at_utc="2026-01-01T00:00:00+00:00",
        )
        assert any(
            e["event_type"] == "BOS_UP"
            and e["break_level_price"] == 15
            and e["bar"].high == 20
            for e in events
            if "bar" in e or True
        )

    def test_bos_down_triggered_by_low_not_close(tmp_path):
        osakedata_db = tmp_path / "osakedata.db"
        closes = [10, 12, 14, 15, 13, 11, 10, 9]
        highs = [10, 12, 14, 15, 13, 11, 10, 9]
        lows = [9, 10, 11, 12, 11, 10, 9, 1]  # low=1 at idx=7 breaks BOS
        with sqlite3.connect(osakedata_db) as conn:
            conn.execute("""
                CREATE TABLE osakedata (
                    osake TEXT, pvm TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER, market TEXT
                )""")
            for i in range(8):
                conn.execute(
                    "INSERT INTO osakedata VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "TEST",
                        f"2026-01-0{i+1}",
                        0,
                        highs[i],
                        lows[i],
                        closes[i],
                        1000 + i,
                        "test",
                    ),
                )
            conn.commit()
        bars = fetch_price_bars(sqlite3.connect(osakedata_db), "TEST")
        events = calculate_ticker_events(
            bars,
            pivot_radius=3,
            start_confirmed_as_of_date=bars[0].date,
            initial_state=None,
            run_id="run-bosdown-test",
            created_at_utc="2026-01-01T00:00:00+00:00",
        )
        assert any(
            e["event_type"] == "BOS_DOWN"
            and e["break_level_price"] == 9
            and e["bar"].low == 1
            for e in events
            if "bar" in e or True
        )

    def test_close_only_change_does_not_trigger_pivot_or_bos(tmp_path):
        osakedata_db = tmp_path / "osakedata.db"
        # high/low are flat, but close spikes
        closes = [10, 10, 10, 50, 10, 10, 10]
        highs = [10, 10, 10, 10, 10, 10, 10]
        lows = [10, 10, 10, 10, 10, 10, 10]
        with sqlite3.connect(osakedata_db) as conn:
            conn.execute("""
                CREATE TABLE osakedata (
                    osake TEXT, pvm TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER, market TEXT
                )""")
            for i in range(7):
                conn.execute(
                    "INSERT INTO osakedata VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "TEST",
                        f"2026-01-0{i+1}",
                        0,
                        highs[i],
                        lows[i],
                        closes[i],
                        1000 + i,
                        "test",
                    ),
                )
            conn.commit()
        bars = fetch_price_bars(sqlite3.connect(osakedata_db), "TEST")
        events = calculate_ticker_events(
            bars,
            pivot_radius=3,
            start_confirmed_as_of_date=bars[0].date,
            initial_state=None,
            run_id="run-closeonly-test",
            created_at_utc="2026-01-01T00:00:00+00:00",
        )
        assert not any(
            e["event_type"] in ("PIVOT_HIGH", "PIVOT_LOW", "BOS_UP", "BOS_DOWN")
            for e in events
        )

    def test_event_rows_include_audit_fields(tmp_path):
        osakedata_db = tmp_path / "osakedata.db"
        closes = [10, 11, 12, 13, 12, 11, 10]
        highs = [10, 11, 12, 20, 12, 11, 10]
        lows = [9, 10, 11, 12, 11, 10, 9]
        with sqlite3.connect(osakedata_db) as conn:
            conn.execute("""
                CREATE TABLE osakedata (
                    osake TEXT, pvm TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER, market TEXT
                )""")
            for i in range(7):
                conn.execute(
                    "INSERT INTO osakedata VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        "TEST",
                        f"2026-01-0{i+1}",
                        1,
                        highs[i],
                        lows[i],
                        closes[i],
                        1000 + i,
                        "test",
                    ),
                )
            conn.commit()
        bars = fetch_price_bars(sqlite3.connect(osakedata_db), "TEST")
        events = calculate_ticker_events(
            bars,
            pivot_radius=3,
            start_confirmed_as_of_date=bars[0].date,
            initial_state=None,
            run_id="run-audit-test",
            created_at_utc="2026-01-01T00:00:00+00:00",
        )
        for e in events:
            assert "open" in e["bar"].__dict__
            assert "high" in e["bar"].__dict__
            assert "low" in e["bar"].__dict__
            assert "close" in e["bar"].__dict__

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


def test_new_schema_uses_active_bos_columns_only(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    columns = _load_table_columns(analysis_db)

    assert "active_bos_high_date" in columns
    assert "active_bos_high_price" in columns
    assert "active_bos_low_date" in columns
    assert "active_bos_low_price" in columns
    assert "structural_high_date" not in columns
    assert "structural_high_price" not in columns
    assert "structural_low_date" not in columns
    assert "structural_low_price" not in columns

    with sqlite3.connect(analysis_db) as conn:
        row = conn.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'stock_dow_structure_status'
            """).fetchone()
    assert row is not None


def test_old_schema_migrates_to_active_bos_columns_and_preserves_values(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    with sqlite3.connect(analysis_db) as conn:
        conn.execute("""
            CREATE TABLE stock_dow_structure_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                market TEXT NULL,
                event_date TEXT NOT NULL,
                confirmed_as_of_date TEXT NOT NULL,
                open REAL NULL,
                high REAL NULL,
                low REAL NULL,
                close REAL NOT NULL,
                volume INTEGER NULL,
                price_source TEXT NOT NULL DEFAULT 'close',
                structure_price REAL NOT NULL,
                pivot_radius INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                is_pivot_high INTEGER NOT NULL DEFAULT 0,
                is_pivot_low INTEGER NOT NULL DEFAULT 0,
                pivot_high_date TEXT NULL,
                pivot_high_price REAL NULL,
                pivot_low_date TEXT NULL,
                pivot_low_price REAL NULL,
                dow_label_high TEXT NULL,
                dow_label_low TEXT NULL,
                trend_state TEXT NOT NULL,
                structural_high_date TEXT NULL,
                structural_high_price REAL NULL,
                structural_low_date TEXT NULL,
                structural_low_price REAL NULL,
                last_high_label TEXT NULL,
                last_high_label_date TEXT NULL,
                last_high_label_price REAL NULL,
                last_low_label TEXT NULL,
                last_low_label_date TEXT NULL,
                last_low_label_price REAL NULL,
                bos_up_count INTEGER NOT NULL DEFAULT 0,
                bos_down_count INTEGER NOT NULL DEFAULT 0,
                break_signal TEXT NULL,
                break_level_date TEXT NULL,
                break_level_price REAL NULL,
                break_close_price REAL NULL,
                reset_marker TEXT NULL,
                reset_reason TEXT NULL,
                structure_epoch_id INTEGER NOT NULL DEFAULT 1,
                structure_epoch_start_date TEXT NULL,
                calc_version TEXT NOT NULL,
                run_id TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            )
            """)
        conn.execute("""
            INSERT INTO stock_dow_structure_events (
                ticker, market, event_date, confirmed_as_of_date, close, price_source,
                structure_price, pivot_radius, event_type, trend_state,
                structural_high_date, structural_high_price,
                structural_low_date, structural_low_price,
                calc_version, run_id, created_at_utc
            ) VALUES (
                'TEST', 'usa', '2026-01-10', '2026-01-10', 10.0, 'close',
                10.0, 3, 'RESET', 'NEUTRAL',
                '2026-01-08', 15.5,
                '2026-01-07', 9.5,
                'stock_dow_v1', 'run-old', '2026-01-10T00:00:00+00:00'
            )
            """)
        conn.commit()
        ensure_stock_dow_structure_schema(conn)

    columns = _load_table_columns(analysis_db)
    assert "active_bos_high_date" in columns
    assert "active_bos_high_price" in columns
    assert "active_bos_low_date" in columns
    assert "active_bos_low_price" in columns
    assert "structural_high_date" not in columns
    assert "structural_high_price" not in columns
    assert "structural_low_date" not in columns
    assert "structural_low_price" not in columns

    with sqlite3.connect(analysis_db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("""
            SELECT
                active_bos_high_date,
                active_bos_high_price,
                active_bos_low_date,
                active_bos_low_price
            FROM stock_dow_structure_events
            WHERE ticker = 'TEST'
            """).fetchone()

    assert row is not None
    assert row["active_bos_high_date"] == "2026-01-08"
    assert row["active_bos_high_price"] == 15.5
    assert row["active_bos_low_date"] == "2026-01-07"
    assert row["active_bos_low_price"] == 9.5


def test_parse_recalc_from_date_accepts_valid_calendar_date():
    args = parse_args(["--ticker", "TEST", "--recalc-from-date", "2025-01-31"])

    assert parse_recalc_from_date("2025-01-31") == "2025-01-31"
    assert args.recalc_from_date == "2025-01-31"


@pytest.mark.parametrize(
    "invalid_value",
    ["2025-02-30", "2025/01/01", "abc"],
)
def test_parse_recalc_from_date_rejects_invalid_values(invalid_value, capsys):
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--ticker", "TEST", "--recalc-from-date", invalid_value])

    assert exc_info.value.code != 0
    stderr = capsys.readouterr().err
    assert "Invalid --recalc-from-date:" in stderr
    assert invalid_value in stderr


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
    assert reset["active_bos_high_date"] is None
    assert reset["active_bos_low_date"] is None
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


def test_up_trend_bos_down_uses_active_bos_low(tmp_path):
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

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
    )

    rows = _load_event_rows(analysis_db)
    bos_down = next(row for row in rows if row["event_type"] == "BOS_DOWN")

    assert bos_down["active_bos_low_date"] == "2026-01-14"
    assert bos_down["active_bos_low_price"] == 8.0
    assert bos_down["active_bos_low_price"] != 9.0
    assert bos_down["break_level_date"] == bos_down["active_bos_low_date"]
    assert bos_down["break_level_price"] == bos_down["active_bos_low_price"]


def test_down_trend_bos_up_uses_active_bos_high(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    closes = [
        10,
        12,
        14,
        17,
        15,
        13,
        11,
        8,
        10,
        12,
        15,
        13,
        11,
        6,
        8,
        10,
        12,
        16,
        17,
    ]
    _create_osakedata_db(osakedata_db, closes)

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
    )

    rows = _load_event_rows(analysis_db)
    bos_up = next(row for row in rows if row["event_type"] == "BOS_UP")

    assert bos_up["active_bos_high_date"] == "2026-01-11"
    assert bos_up["active_bos_high_price"] == 16.0
    assert bos_up["active_bos_high_price"] != 15.0
    assert bos_up["break_level_date"] == bos_up["active_bos_high_date"]
    assert bos_up["break_level_price"] == bos_up["active_bos_high_price"]


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


def test_explicit_recalc_boundary_preserves_older_rows_and_rewrites_from_boundary(
    tmp_path,
):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    closes = [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14]
    _create_osakedata_db(osakedata_db, closes)

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
        run_id="run1",
    )

    summary = run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
        recalc_from_date="2026-01-17",
        recalc_tail_trading_days=30,
        run_id="run2",
    )

    old_rows, new_rows = _event_run_ids_by_boundary(analysis_db, "2026-01-17")

    assert summary["tickers_explicit_recalculated"] == 1
    assert summary["tickers_incremental_recalculated"] == 0
    assert summary["rows_deleted"] > 0
    assert old_rows
    assert new_rows
    assert all(row["run_id"] == "run1" for row in old_rows)
    assert all(row["run_id"] == "run2" for row in new_rows)


def test_explicit_recalc_does_not_shift_boundary_back_with_tail(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    closes = [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14]
    _create_osakedata_db(osakedata_db, closes)

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
        run_id="run1",
    )

    summary = run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
        recalc_from_date="2026-01-17",
        recalc_tail_trading_days=99,
        run_id="run2",
    )

    old_rows, new_rows = _event_run_ids_by_boundary(analysis_db, "2026-01-17")

    assert summary["recalc_from_date"] == "2026-01-17"
    assert old_rows
    assert new_rows
    assert all(row["confirmed_as_of_date"] < "2026-01-17" for row in old_rows)
    assert all(row["confirmed_as_of_date"] >= "2026-01-17" for row in new_rows)


def test_explicit_recalc_without_previous_event_falls_back_to_full(tmp_path):
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
        recalc_from_date="2026-01-01",
        run_id="run-explicit",
    )

    rows = _load_event_rows(analysis_db)

    assert summary["tickers_fallback_full_recalculated"] == 1
    assert summary["tickers_explicit_recalculated"] == 0
    assert rows
    assert all(row["run_id"] == "run-explicit" for row in rows)


def test_force_full_wins_over_recalc_from_date(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    closes = [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14]
    _create_osakedata_db(osakedata_db, closes)

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
        run_id="run1",
    )

    summary = run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
        recalc_from_date="2026-01-17",
        force_full=True,
        run_id="run2",
    )

    rows = _load_event_rows(analysis_db)

    assert summary["tickers_full_recalculated"] == 1
    assert summary["tickers_explicit_recalculated"] == 0
    assert summary["tickers_incremental_recalculated"] == 0
    assert all(row["run_id"] == "run2" for row in rows)


def test_explicit_recalc_dry_run_reports_changes_without_writing(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    closes = [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14]
    _create_osakedata_db(osakedata_db, closes)

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
        run_id="run1",
    )
    before_rows = _load_event_rows(analysis_db)

    summary = run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=True,
        recalc_from_date="2026-01-17",
        run_id="run2",
    )
    after_rows = _load_event_rows(analysis_db)

    assert summary["tickers_explicit_recalculated"] == 1
    assert summary["rows_deleted"] > 0
    assert summary["rows_inserted"] > 0
    assert [dict(row) for row in before_rows] == [dict(row) for row in after_rows]


def test_explicit_recalc_after_latest_ohlcv_is_noop(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    closes = [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14]
    _create_osakedata_db(osakedata_db, closes)

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
        run_id="run1",
    )

    summary = run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=True,
        recalc_from_date="2026-02-01",
        run_id="run2",
    )

    assert summary["tickers_processed"] == 1
    assert summary["tickers_explicit_recalculated"] == 1
    assert summary["tickers_full_recalculated"] == 0
    assert summary["tickers_incremental_recalculated"] == 0
    assert summary["tickers_fallback_full_recalculated"] == 0
    assert summary["rows_deleted"] == 0
    assert summary["rows_inserted"] == 0


def test_market_explicit_recalc_applies_boundary_per_ticker(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    closes = [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14]
    _create_osakedata_db(osakedata_db, closes, ticker="AAA", market="usa")
    _create_osakedata_db(osakedata_db, closes, ticker="BBB", market="usa")

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        market="usa",
        dry_run=False,
        run_id="run1",
    )

    summary = run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        market="usa",
        dry_run=True,
        recalc_from_date="2026-01-17",
        run_id="run2",
    )

    assert summary["tickers_requested"] == 2
    assert summary["tickers_processed"] == 2
    assert summary["tickers_explicit_recalculated"] == 2


def test_explicit_recalc_non_trading_boundary_uses_next_trading_date(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    _create_osakedata_db(osakedata_db, [], ticker="TEST")
    _insert_close_series_for_dates(
        osakedata_db,
        [
            "2026-01-05",
            "2026-01-06",
            "2026-01-07",
            "2026-01-08",
            "2026-01-09",
            "2026-01-12",
            "2026-01-13",
            "2026-01-14",
            "2026-01-15",
            "2026-01-16",
            "2026-01-19",
            "2026-01-20",
            "2026-01-21",
            "2026-01-22",
            "2026-01-23",
            "2026-01-26",
            "2026-01-27",
        ],
        [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14],
    )

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=False,
        run_id="run1",
    )

    summary = run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="TEST",
        dry_run=True,
        recalc_from_date="2026-01-18",
        run_id="run2",
    )

    assert summary["tickers_explicit_recalculated"] == 1
    assert summary["rows_deleted"] > 0
    assert summary["rows_inserted"] > 0


def test_missing_ticker_is_selected_for_calculation(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    _create_osakedata_db(osakedata_db, [], ticker="AAA")
    _insert_close_series_for_dates(
        osakedata_db,
        [
            "2023-12-28",
            "2023-12-29",
            "2023-12-30",
            "2023-12-31",
            "2024-01-01",
            "2024-01-02",
            "2024-01-03",
            "2024-01-04",
            "2024-01-05",
            "2024-01-06",
            "2024-01-07",
        ],
        [1, 2, 3, 4, 10, 11, 12, 15, 12, 11, 10],
        ticker="AAA",
    )

    summary = calculate_missing_or_outdated_stock_dow_structures(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        dry_run=False,
    )

    rows = _load_event_rows(analysis_db)
    status_row = _load_status_row(analysis_db, "AAA")

    assert summary["tickers_checked"] == 1
    assert summary["tickers_missing"] == 1
    assert summary["tickers_outdated"] == 0
    assert summary["tickers_up_to_date"] == 0
    assert summary["tickers_processed"] == 1
    assert summary["tickers_bounded_initial_recalculated"] == 1
    assert summary["tickers_incremental_recalculated"] == 0
    assert summary["bounded_initial_from_date"] == DEFAULT_BOUNDED_INITIAL_FROM_DATE
    assert summary["errors"] == 0
    assert rows
    assert status_row is not None
    assert status_row["calculated_from_date"] == DEFAULT_BOUNDED_INITIAL_FROM_DATE
    assert status_row["calculated_through_date"] == "2024-01-07"
    assert status_row["latest_ohlcv_date_at_run"] == "2024-01-07"
    assert status_row["last_run_mode"] == "bounded_initial"
    assert min(row["event_date"] for row in rows) >= DEFAULT_BOUNDED_INITIAL_FROM_DATE
    assert all(
        row["structure_epoch_start_date"] == DEFAULT_BOUNDED_INITIAL_FROM_DATE
        for row in rows
    )


def test_outdated_ticker_is_selected_for_incremental_calculation(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    _create_osakedata_db(
        osakedata_db,
        [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14],
        ticker="AAA",
    )

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="AAA",
        dry_run=False,
        run_id="run1",
    )

    with sqlite3.connect(osakedata_db) as conn:
        conn.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAA", "2026-01-18", 7.75, 9.0, 7.0, 8.0, 1018, "usa"),
        )
        conn.commit()

    summary = calculate_missing_or_outdated_stock_dow_structures(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        dry_run=True,
        recalc_tail_trading_days=DEFAULT_RECALC_TAIL_TRADING_DAYS,
    )

    assert summary["tickers_checked"] == 1
    assert summary["tickers_missing"] == 0
    assert summary["tickers_outdated"] == 1
    assert summary["tickers_up_to_date"] == 0
    assert summary["tickers_processed"] == 1
    assert summary["tickers_incremental_recalculated"] == 1
    assert summary["tickers_bounded_initial_recalculated"] == 0
    assert summary["errors"] == 0


def test_up_to_date_ticker_is_skipped(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    _create_osakedata_db(
        osakedata_db,
        [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14],
        ticker="AAA",
    )

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="AAA",
        dry_run=False,
        run_id="run1",
    )

    summary = calculate_missing_or_outdated_stock_dow_structures(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        dry_run=True,
    )

    assert summary["tickers_checked"] == 1
    assert summary["tickers_missing"] == 0
    assert summary["tickers_outdated"] == 0
    assert summary["tickers_up_to_date"] == 1
    assert summary["tickers_processed"] == 0
    assert summary["errors"] == 0


def test_selection_summary_counts_checked_needs_calculation_and_skipped(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    base_closes = [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14]
    _create_osakedata_db(osakedata_db, base_closes, ticker="AAA", market="usa")
    _create_osakedata_db(osakedata_db, base_closes, ticker="BBB", market="usa")
    _create_osakedata_db(osakedata_db, base_closes, ticker="CCC", market="usa")

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="BBB",
        dry_run=False,
        run_id="bbb-run1",
    )
    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="CCC",
        dry_run=False,
        run_id="ccc-run1",
    )
    with sqlite3.connect(osakedata_db) as conn:
        conn.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("CCC", "2026-01-18", 7.75, 9.0, 7.0, 8.0, 1018, "usa"),
        )
        conn.commit()

    summary = calculate_missing_or_outdated_stock_dow_structures(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        dry_run=True,
    )

    assert summary["tickers_checked"] == 3
    assert summary["tickers_missing"] == 1
    assert summary["tickers_outdated"] == 1
    assert summary["tickers_up_to_date"] == 1
    assert summary["tickers_processed"] == 2
    assert summary["tickers_bounded_initial_recalculated"] == 1
    assert summary["tickers_incremental_recalculated"] == 1
    assert summary["errors"] == 0


def test_calculate_missing_or_outdated_can_be_scoped_to_single_ticker(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    base_closes = [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14]
    _create_osakedata_db(osakedata_db, base_closes, ticker="AAA", market="usa")
    _create_osakedata_db(osakedata_db, base_closes, ticker="BBB", market="usa")

    summary = calculate_missing_or_outdated_stock_dow_structures(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="BBB",
        dry_run=False,
    )

    rows = _load_event_rows(analysis_db)
    aaa_status = _load_status_row(analysis_db, "AAA")
    bbb_status = _load_status_row(analysis_db, "BBB")

    assert summary["tickers_checked"] == 1
    assert summary["tickers_missing"] == 1
    assert summary["tickers_processed"] == 1
    assert summary["errors"] == 0
    assert rows
    assert {row["ticker"] for row in rows} == {"BBB"}
    assert aaa_status is None
    assert bbb_status is not None


def test_zero_event_processed_ticker_writes_status_row(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    _create_osakedata_db(osakedata_db, [], ticker="AAA")
    _insert_close_series_for_dates(
        osakedata_db,
        ["2024-01-01", "2024-01-02", "2024-01-03"],
        [10, 11, 12],
        ticker="AAA",
    )

    summary = calculate_missing_or_outdated_stock_dow_structures(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        dry_run=False,
    )

    rows = _load_event_rows(analysis_db)
    status_row = _load_status_row(analysis_db, "AAA")

    assert summary["rows_inserted"] == 0
    assert rows == []
    assert status_row is not None
    assert status_row["calculated_from_date"] == "2024-01-01"
    assert status_row["calculated_through_date"] == "2024-01-03"
    assert status_row["latest_event_confirmed_as_of_date"] is None
    assert status_row["last_status"] == "OK"

    summary_second = calculate_missing_or_outdated_stock_dow_structures(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        dry_run=True,
    )
    assert summary_second["tickers_up_to_date"] == 1
    assert summary_second["tickers_outdated"] == 0


def test_manual_helper_uses_status_coverage_not_latest_event_confirmed_date(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    _create_osakedata_db(
        osakedata_db,
        [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14],
        ticker="AAA",
    )

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="AAA",
        dry_run=False,
        run_id="run1",
    )
    status_row = _load_status_row(analysis_db, "AAA")
    assert status_row is not None
    assert status_row["calculated_through_date"] == "2026-01-17"

    with sqlite3.connect(analysis_db) as conn:
        conn.execute("""
            UPDATE stock_dow_structure_status
            SET latest_event_confirmed_as_of_date = '2026-01-10'
            WHERE ticker = 'AAA' AND price_source = 'close' AND pivot_radius = 3
            """)
        conn.commit()

    summary = calculate_missing_or_outdated_stock_dow_structures(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        dry_run=True,
    )
    assert summary["tickers_up_to_date"] == 1
    assert summary["tickers_outdated"] == 0


def test_outdated_by_status_coverage_is_selected(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    _create_osakedata_db(
        osakedata_db,
        [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14],
        ticker="AAA",
    )

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="AAA",
        dry_run=False,
        run_id="run1",
    )

    with sqlite3.connect(analysis_db) as conn:
        conn.execute("""
            UPDATE stock_dow_structure_status
            SET calculated_through_date = '2026-01-10'
            WHERE ticker = 'AAA' AND price_source = 'close' AND pivot_radius = 3
            """)
        conn.commit()

    summary = calculate_missing_or_outdated_stock_dow_structures(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        dry_run=True,
    )
    assert summary["tickers_outdated"] == 1
    assert summary["tickers_up_to_date"] == 0


def test_registered_without_status_uses_incremental_recovery_and_writes_status(
    tmp_path,
):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    closes = [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14]
    _create_osakedata_db(osakedata_db, closes, ticker="AAA")

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="AAA",
        dry_run=False,
        run_id="run1",
    )

    with sqlite3.connect(analysis_db) as conn:
        conn.execute("DELETE FROM stock_dow_structure_status")
        conn.commit()

    summary = calculate_missing_or_outdated_stock_dow_structures(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        dry_run=False,
    )

    status_row = _load_status_row(analysis_db, "AAA")

    assert summary["tickers_missing"] == 0
    assert summary["tickers_registered_without_status"] == 1
    assert summary["tickers_bounded_initial_recalculated"] == 0
    assert summary["tickers_incremental_recalculated"] == 1
    assert status_row is not None
    assert status_row["last_run_mode"] == "incremental"


def test_null_close_raw_tail_does_not_make_ticker_outdated(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    _create_osakedata_db(
        osakedata_db,
        [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14],
        ticker="AAA",
    )

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="AAA",
        dry_run=False,
        run_id="run1",
    )

    with sqlite3.connect(osakedata_db) as conn:
        conn.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAA", "2026-01-18", 0.0, 0.0, 0.0, None, 1018, "usa"),
        )
        conn.commit()

    status_row = _load_status_row(analysis_db, "AAA")
    assert status_row is not None
    assert status_row["calculated_through_date"] == "2026-01-17"

    summary = calculate_missing_or_outdated_stock_dow_structures(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        dry_run=True,
    )
    assert summary["tickers_up_to_date"] == 1
    assert summary["tickers_outdated"] == 0


def test_older_than_latest_valid_close_date_is_outdated(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    _create_osakedata_db(
        osakedata_db,
        [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14],
        ticker="AAA",
    )

    run_stock_dow_structure(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        ticker="AAA",
        dry_run=False,
        run_id="run1",
    )

    with sqlite3.connect(osakedata_db) as conn:
        conn.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAA", "2026-01-18", 7.75, 9.0, 7.0, 8.0, 1018, "usa"),
        )
        conn.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAA", "2026-01-19", 0.0, 0.0, 0.0, None, 1019, "usa"),
        )
        conn.commit()

    summary = calculate_missing_or_outdated_stock_dow_structures(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        dry_run=True,
    )
    assert summary["tickers_outdated"] == 1
    assert summary["tickers_up_to_date"] == 0


def test_only_null_close_rows_are_handled_without_false_ok_coverage(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    _create_osakedata_db(osakedata_db, [], ticker="AAA")
    with sqlite3.connect(osakedata_db) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("AAA", "2026-01-01", 0.0, 0.0, 0.0, None, 1000, "usa"),
                ("AAA", "2026-01-02", 0.0, 0.0, 0.0, None, 1001, "usa"),
            ],
        )
        conn.commit()

    summary = calculate_missing_or_outdated_stock_dow_structures(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        dry_run=False,
    )

    status_row = _load_status_row(analysis_db, "AAA")

    assert summary["tickers_checked"] == 1
    assert summary["tickers_no_valid_close_data"] == 1
    assert summary["tickers_processed"] == 0
    assert status_row is None


def test_tickers_no_valid_close_data_counted_separately_from_normal_tickers(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    _create_analysis_db(analysis_db)
    # AAA has valid close data
    _create_osakedata_db(
        osakedata_db,
        [10, 11, 12, 15, 13, 11, 9, 7, 9, 12, 16, 13, 11, 9, 10, 12, 14],
        ticker="AAA",
    )
    # BBB has only NULL close rows
    with sqlite3.connect(osakedata_db) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("BBB", "2026-01-01", 0.0, 0.0, 0.0, None, 500, "usa"),
                ("BBB", "2026-01-02", 0.0, 0.0, 0.0, None, 501, "usa"),
            ],
        )
        conn.commit()

    summary = calculate_missing_or_outdated_stock_dow_structures(
        analysis_db_path=analysis_db,
        osakedata_db_path=osakedata_db,
        dry_run=False,
    )

    # BBB counted in no_valid_close_data, AAA counted as missing (processed)
    assert summary["tickers_checked"] == 2
    assert summary["tickers_no_valid_close_data"] == 1
    assert summary["tickers_missing"] == 1
    assert summary["tickers_bounded_initial_recalculated"] == 1
    # BBB must not have a status row
    assert _load_status_row(analysis_db, "BBB") is None


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
        row = conn.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'stock_dow_structure_events'
            """).fetchone()
        assert row is not None
