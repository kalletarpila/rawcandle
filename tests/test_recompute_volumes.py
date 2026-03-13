from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from analysis import recompute_volumes


def _build_stock_db(tmp_path: Path, ticker: str = "AAA") -> Path:
    db_path = tmp_path / "osakedata.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT,
                pvm TEXT,
                volume REAL
            )
            """
        )
        start = date(2024, 1, 1)
        rows = []
        for i in range(0, 150):
            rows.append((ticker, (start + timedelta(days=i)).isoformat(), 1000 + i))
        conn.executemany("INSERT INTO osakedata (osake, pvm, volume) VALUES (?, ?, ?)", rows)
    return db_path


def _build_results_db(tmp_path: Path, ticker: str = "AAA") -> Path:
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE results_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                date TEXT,
                t_2_volyymi REAL,
                t_5_volyymi REAL,
                t_10_volyymi REAL,
                t_15_volyymi REAL,
                t_20_volyymi REAL,
                t0_volyymi REAL,
                t2_volyymi REAL,
                t5_volyymi REAL,
                t10_volyymi REAL,
                t20_volyymi REAL
            )
            """
        )
        conn.executemany(
            "INSERT INTO results_data (ticker, date) VALUES (?, ?)",
            [
                (ticker, "2024-05-10"),  # t0 index 130 (0-based)
                (ticker, "2024-05-11"),
            ],
        )
    return db_path


def test_compute_volume_ratio_matches_manual():
    volumes = [100 + i for i in range(1, 151)]  # monotonic increasing
    # Choose t0 index 130, end offset -1, window 5:
    # period = idx-5+1 .. idx-1 => 125..129
    period_vals = volumes[125:130]
    baseline_vals = volumes[25:125]  # 100 days before period start
    expected = (sum(period_vals) / len(period_vals)) / (sum(baseline_vals) / len(baseline_vals)) * 100
    got = recompute_volumes.compute_volume_ratio(volumes, 130, 5, -1)
    assert pytest.approx(expected, rel=1e-9) == got


def test_recompute_for_ticker_updates_all_fields(tmp_path: Path):
    stock_db = _build_stock_db(tmp_path)
    results_db = _build_results_db(tmp_path)

    stock_df = pd.read_sql_query(
        "SELECT pvm, volume FROM osakedata WHERE osake = ? ORDER BY pvm",
        sqlite3.connect(stock_db),
        params=["AAA"],
    )
    with sqlite3.connect(results_db) as conn:
        grouped = recompute_volumes.fetch_results_grouped(conn)
        updates = recompute_volumes.recompute_for_ticker(stock_df, grouped["AAA"])
        assert len(updates) == 2
        first = updates[0].values
        # spot-check fields are filled
        for key in ["t_5_volyymi", "t0_volyymi", "t5_volyymi"]:
            assert first[key] is not None


def test_apply_updates_writes_to_db(tmp_path: Path):
    stock_db = _build_stock_db(tmp_path)
    results_db = _build_results_db(tmp_path)

    stock_df = pd.read_sql_query(
        "SELECT pvm, volume FROM osakedata WHERE osake = ? ORDER BY pvm",
        sqlite3.connect(stock_db),
        params=["AAA"],
    )
    with sqlite3.connect(results_db) as conn:
        grouped = recompute_volumes.fetch_results_grouped(conn)
        updates = recompute_volumes.recompute_for_ticker(stock_df, grouped["AAA"])
        recompute_volumes.apply_updates(conn, updates)
        rows = conn.execute(
            "SELECT t_5_volyymi, t0_volyymi, t5_volyymi FROM results_data WHERE ticker='AAA'"
        ).fetchall()
        assert all(row[0] is not None and row[1] is not None and row[2] is not None for row in rows)
