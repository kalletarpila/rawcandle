from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from analysis import recompute_history_normalization as rh


def _build_stock_db(tmp_path: Path, ticker: str = "AAA") -> Path:
    db_path = tmp_path / "osakedata.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT,
                pvm TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL
            )
            """
        )
        start = date(2024, 1, 1)
        rows = []
        for i in range(0, 60):
            close_price = 100 + i  # strictly increasing
            rows.append(
                (
                    ticker,
                    (start + timedelta(days=i)).isoformat(),
                    close_price - 1,
                    close_price + 2,
                    close_price - 2,
                    close_price,
                    1000000,
                )
            )
        conn.executemany(
            "INSERT INTO osakedata (osake, pvm, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
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
                t_1_alin REAL,
                t_1_ylin REAL,
                t_1_bodi REAL,
                t_1_bodi_colour INTEGER,
                t_2 REAL,
                t_5 REAL,
                t_10 REAL,
                t_15 REAL,
                t_20 REAL,
                t_2_hajonta REAL,
                t_5_hajonta REAL,
                t_10_hajonta REAL,
                t_15_hajonta REAL,
                t_20_hajonta REAL,
                t_2_5p_liukuva REAL,
                t_2_10p_liukuva REAL,
                t_2_20p_liukuva REAL,
                t_5_5p_liukuva REAL,
                t_5_10p_liukuva REAL,
                t_5_20p_liukuva REAL,
                t_10_5p_liukuva REAL,
                t_10_10p_liukuva REAL,
                t_10_20p_liukuva REAL,
                t_15_5p_liukuva REAL,
                t_15_10p_liukuva REAL,
                t_15_20p_liukuva REAL,
                t_20_5p_liukuva REAL,
                t_20_10p_liukuva REAL,
                t_20_20p_liukuva REAL,
                t0_20p_liukuva REAL,
                t0_50p_liukuva REAL,
                t0_200p_liukuva REAL,
                Price_slope_5 REAL,
                Price_slope_10 REAL,
                Price_acceleration_5_10 REAL,
                Volatility_ratio_10_20 REAL,
                t0_50p_slope REAL,
                t0_200p_slope REAL,
                ATR_ratio_14 REAL,
                Gap_down_strength REAL
            )
            """
        )
        # t0 = 2024-02-15 (index 45)
        conn.execute(
            "INSERT INTO results_data (ticker, date) VALUES (?, ?)",
            (ticker, "2024-02-15"),
        )
    return db_path


def test_recompute_for_ticker_calculates_expected_fields(tmp_path: Path):
    stock_db = _build_stock_db(tmp_path)
    results_db = _build_results_db(tmp_path)

    with sqlite3.connect(stock_db) as conn:
        stock_df = pd.read_sql_query(
            "SELECT pvm, open, high, low, close FROM osakedata WHERE osake = ? ORDER BY pvm",
            conn,
            params=["AAA"],
        )

    # Build updates
    updates = rh.recompute_for_ticker(stock_df, [(1, "2024-02-15")])
    assert len(updates) == 1
    vals = updates[0].values

    # t0_low = close-2 = 143 on that day (close 145 at i=45)
    expected_t0_low = 143.0
    close_t5 = 140.0  # i=40 => close 140
    assert pytest.approx(vals["t_5"]) == close_t5 / expected_t0_low * 100

    # gap_down_strength: prev_close=144, open=144, low=143 -> (144-144)/143 = 0
    assert vals["Gap_down_strength"] == 0.0

    # Price_slope_5 based on t_5
    assert pytest.approx(vals["Price_slope_5"]) == (100 - vals["t_5"]) / 5


def test_apply_updates_writes_all_columns(tmp_path: Path):
    stock_db = _build_stock_db(tmp_path)
    results_db = _build_results_db(tmp_path)

    with sqlite3.connect(stock_db) as conn:
        stock_df = pd.read_sql_query(
            "SELECT pvm, open, high, low, close FROM osakedata WHERE osake = ? ORDER BY pvm",
            conn,
            params=["AAA"],
        )

    updates = rh.recompute_for_ticker(stock_df, [(1, "2024-02-15")])
    with sqlite3.connect(results_db) as conn:
        conn.row_factory = sqlite3.Row
        rh.apply_updates(conn, updates)
        row = conn.execute(
            "SELECT " + ", ".join(rh.HISTORY_COLUMNS) + " FROM results_data WHERE id = 1"
        ).fetchone()
    assert all(col in row.keys() for col in rh.HISTORY_COLUMNS)
    # spot check a couple of values were written (not None)
    assert row["t_5"] is not None
    assert row["t_2_hajonta"] is not None
