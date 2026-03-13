from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from analysis import backfill_bulldiv_metrics as bbm


def _create_analysis_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        # results_data
        conn.execute(
            """
            CREATE TABLE results_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                date TEXT,
                RSI14_t0 REAL,
                BullDiv_strength REAL,
                BullDiv_recent_strength REAL,
                BullDiv_recent_offset INTEGER,
                Has_BullDiv_recent INTEGER
            )
            """
        )
        conn.executemany(
            "INSERT INTO results_data (ticker, date, RSI14_t0) VALUES (?, ?, ?)",
            [
                ("AAA", "2024-01-10", 50.0),
                ("BBB", "2024-02-10", 55.0),
                ("CCC", "2024-03-01", 60.0),
            ],
        )

        # analysis_findings
        conn.execute(
            """
            CREATE TABLE analysis_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                date TEXT,
                pattern TEXT,
                signal_strength REAL,
                rsi14 REAL
            )
            """
        )
        # AAA: t0 bullish=2.0, t-2 bullish=1.0
        conn.executemany(
            """
            INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("AAA", "2024-01-10", "Bullish Divergence", 2.0, 52.0),
                ("AAA", "2024-01-08", "Bullish Divergence", 1.0, 51.0),
            ],
        )

        # divergence_data (fallback)
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
        # BBB: t-3 bullish=1.5
        d = date(2024, 2, 10) + timedelta(days=-3)
        conn.execute(
            "INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi) VALUES (?, ?, ?, ?, ?)",
            ("BBB", d.isoformat(), 1.5, 0.0, 54.0),
        )
    return db_path


def test_build_updates_uses_findings_and_fallback(tmp_path: Path):
    db_path = _create_analysis_db(tmp_path)
    conn = sqlite3.connect(db_path)
    rows_by_ticker = bbm._fetch_results_rows(conn)
    updates = bbm.build_updates(rows_by_ticker, conn)

    by_id = {u.row_id: u.values for u in updates}
    # AAA from analysis_findings
    aaa = by_id[1]
    assert pytest.approx(aaa["BullDiv_strength"]) == 2.0
    assert pytest.approx(aaa["BullDiv_recent_strength"]) == 2.0
    assert aaa["BullDiv_recent_offset"] == 0
    assert aaa["Has_BullDiv_recent"] == 1

    # BBB from divergence_data fallback
    bbb = by_id[2]
    assert pytest.approx(bbb["BullDiv_strength"]) == 0.0
    assert pytest.approx(bbb["BullDiv_recent_strength"]) == 1.5
    assert bbb["BullDiv_recent_offset"] == 3
    assert bbb["Has_BullDiv_recent"] == 1

    # CCC no divergence
    ccc = by_id[3]
    assert ccc["BullDiv_strength"] == 0.0
    assert ccc["BullDiv_recent_strength"] == 0.0
    assert ccc["BullDiv_recent_offset"] == -1
    assert ccc["Has_BullDiv_recent"] == 0


def test_apply_updates_writes_to_db(tmp_path: Path):
    db_path = _create_analysis_db(tmp_path)
    conn = sqlite3.connect(db_path)
    rows_by_ticker = bbm._fetch_results_rows(conn)
    updates = bbm.build_updates(rows_by_ticker, conn)
    applied = bbm.apply_updates(conn, updates)
    assert applied == 3

    rows = conn.execute(
        "SELECT BullDiv_strength, BullDiv_recent_strength, BullDiv_recent_offset, Has_BullDiv_recent FROM results_data ORDER BY id"
    ).fetchall()
    assert rows[0] == (2.0, 2.0, 0, 1)
    assert rows[1] == (0.0, 1.5, 3, 1)
    assert rows[2] == (0.0, 0.0, -1, 0)
