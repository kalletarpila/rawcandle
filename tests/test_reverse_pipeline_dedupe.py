from __future__ import annotations

import sqlite3

import pandas as pd

from reverse.analysis import run_reverse_pipeline, select_topN


def test_select_topN_dedupe_option():
    df = pd.DataFrame(
        {
            "ticker": ["A", "A", "B"],
            "date": ["2025-01-01", "2025-01-01", "2025-01-02"],
            "candle_pattern": [1, 7, 1],
            "t10": [150.0, 130.0, 140.0],
        }
    )
    top_no = select_topN(df, 10, 3, dedupe_ticker_date=False)
    assert len(top_no) == 3

    top_yes = select_topN(df, 10, 3, dedupe_ticker_date=True)
    assert len(top_yes) == 2
    assert (top_yes["ticker"] == "A").sum() == 1
    assert float(top_yes[top_yes["ticker"] == "A"]["t10"].iloc[0]) == 150.0


def test_run_reverse_pipeline_respects_dedupe():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE results_data (
            ticker TEXT,
            date TEXT,
            candle_pattern INTEGER,
            signal_strength REAL,
            t10 REAL,
            feat REAL
        )
        """
    )
    rows = [
        ("A", "2025-01-01", 1, 0.5, 150.0, 1.0),
        ("A", "2025-01-01", 7, 0.6, 130.0, 2.0),
        ("B", "2025-01-02", 1, 0.4, 140.0, 3.0),
    ]
    conn.executemany(
        "INSERT INTO results_data (ticker, date, candle_pattern, signal_strength, t10, feat) VALUES (?,?,?,?,?,?)",
        rows,
    )
    conn.commit()

    params = {"horizon": 10, "top_n": 5, "dedupe_topN_by_ticker_date": True}
    results = run_reverse_pipeline(conn, params, feature_cols=["feat"])
    top = results["top"]
    assert len(top) == 2  # deduped A rows
    assert results.get("dedupe_topN_by_ticker_date") is True

    conn.close()
