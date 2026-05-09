from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from analysis import splits_price_backfill as spb


def _make_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "osakedata.db"
    conn = sqlite3.connect(db_path)
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
            market TEXT NOT NULL DEFAULT 'usa',
            PRIMARY KEY (osake, pvm)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE splits_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            osake TEXT NOT NULL,
            split_date TEXT NOT NULL,
            split_ratio REAL NOT NULL,
            is_price_data_corrected INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(osake, split_date)
        )
        """
    )
    conn.executemany(
        "INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("AAA", "2019-01-02", 1, 2, 1, 2, 100, "usa"),
            ("AAA", "2020-01-02", 2, 3, 2, 3, 200, "usa"),
        ],
    )
    conn.executemany(
        "INSERT OR IGNORE INTO splits_data (osake, split_date, split_ratio, is_price_data_corrected) VALUES (?, ?, ?, ?)",
        [
            ("AAA", "2020-08-31", 4.0, 0),
            ("BBB", "2021-01-01", 2.0, 0),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


def test_get_tickers_with_uncorrected_splits(tmp_path):
    db_path = _make_db(tmp_path)
    conn = sqlite3.connect(db_path)
    tickers = spb.get_tickers_with_uncorrected_splits(conn)
    conn.close()
    assert tickers == ["AAA", "BBB"]


def test_refetch_and_mark(monkeypatch, tmp_path):
    db_path = _make_db(tmp_path)

    df = pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [12.0, 13.0],
            "Low": [9.0, 10.5],
            "Close": [11.0, 12.0],
            "Volume": [1000, 1100],
        },
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )
    history_calls = []
    monkeypatch.setattr(
        spb,
        "yf",
        SimpleNamespace(
            Ticker=lambda ticker: SimpleNamespace(
                history=lambda start, end: history_calls.append((start, end)) or df
            )
        ),
    )

    conn = sqlite3.connect(db_path)
    deleted = spb.delete_prices_from_2018(conn, "AAA")
    assert deleted == 2

    added = spb.refetch_prices_from_yahoo(
        conn, "AAA", start_date="2024-01-02", end_date="2024-01-03"
    )
    assert added == 2
    assert history_calls == [("2024-01-02", "2024-01-04")]

    updated = spb.mark_splits_corrected(conn, "AAA")
    assert updated == 1

    flag = conn.execute(
        "SELECT is_price_data_corrected FROM splits_data WHERE osake='AAA'"
    ).fetchone()[0]
    assert flag == 1
    max_date = conn.execute(
        "SELECT MAX(pvm) FROM osakedata WHERE osake='AAA'"
    ).fetchone()[0]
    assert max_date == "2024-01-03"
    conn.close()


def test_backfill_dry_run_writes_report(monkeypatch, tmp_path):
    db_path = _make_db(tmp_path)
    monkeypatch.setattr(spb, "logger", SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None))
    df = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [11.0],
            "Low": [9.5],
            "Close": [10.5],
            "Volume": [1000],
        },
        index=pd.to_datetime(["2024-01-02"]),
    )
    monkeypatch.setattr(
        spb,
        "yf",
        SimpleNamespace(Ticker=lambda ticker: SimpleNamespace(history=lambda start, end: df)),
    )

    processed = spb.backfill_uncorrected(db_path, dry_run=True, limit=1)
    assert processed
    report = spb._write_report(processed)
    assert report is not None
    content = Path(report).read_text().strip()
    assert content  # should contain ticker list
