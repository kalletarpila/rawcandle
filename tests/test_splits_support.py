from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from stock import splits as splits_mod
from stock.splits import SplitEvent, sync_splits_for_ticker
from analysis import backfill_splits_data


def _make_temp_osakedata(tmp_path: Path) -> Path:
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
        CREATE TABLE IF NOT EXISTS splits_data (
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
            ("AAA", "2024-01-02", 1, 2, 1, 2, 100, "usa"),
            ("BBB", "2024-01-02", 1, 2, 1, 2, 100, "usa"),
            ("CCC", "2024-01-02", 1, 2, 1, 2, 100, "usa"),
        ],
    )
    conn.commit()
    conn.close()
    return db_path


def test_fetch_splits_for_ticker_parses_series(monkeypatch):
    series = pd.Series([4.0], index=pd.to_datetime(["2020-08-31"]))
    monkeypatch.setattr(
        splits_mod,
        "yf",
        SimpleNamespace(Ticker=lambda ticker: SimpleNamespace(splits=series)),
    )
    events = splits_mod.fetch_splits_for_ticker("AAPL")
    assert len(events) == 1
    assert events[0].split_ratio == 4.0
    assert events[0].split_date == "2020-08-31"


def test_sync_splits_for_ticker_inserts(monkeypatch, tmp_path):
    db_path = _make_temp_osakedata(tmp_path)
    series = pd.Series([4.0, 5.0], index=pd.to_datetime(["2020-08-31", "2020-09-01"]))
    monkeypatch.setattr(
        splits_mod,
        "yf",
        SimpleNamespace(Ticker=lambda ticker: SimpleNamespace(splits=series)),
    )
    inserted = sync_splits_for_ticker(db_path, "AAPL")
    assert inserted == 2
    # idempotent
    inserted_again = sync_splits_for_ticker(db_path, "AAPL")
    assert inserted_again == 0


def test_backfill_inserts_and_is_idempotent(monkeypatch, tmp_path):
    db_path = _make_temp_osakedata(tmp_path)
    # map ticker -> events
    events_map = {
        "AAA": [
            SplitEvent(osake="AAA", split_date="2020-08-31", split_ratio=4.0),
        ],
        "BBB": [
            SplitEvent(osake="BBB", split_date="2020-08-31", split_ratio=5.0),
            SplitEvent(osake="BBB", split_date="2020-09-01", split_ratio=2.0),
        ],
        "CCC": [],
    }

    def fake_fetch(ticker: str, yf_ticker=None):
        return events_map.get(ticker, [])

    monkeypatch.setattr(backfill_splits_data, "fetch_splits_for_ticker", fake_fetch)

    processed, inserted = backfill_splits_data.backfill(db_path)
    assert processed == 3
    assert inserted == 3

    # idempotent
    processed2, inserted2 = backfill_splits_data.backfill(db_path)
    assert processed2 == 3
    assert inserted2 == 0


def test_backfill_dry_run_does_not_write(monkeypatch, tmp_path):
    db_path = _make_temp_osakedata(tmp_path)
    events_map = {
        "AAA": [SplitEvent(osake="AAA", split_date="2020-08-31", split_ratio=4.0)],
    }

    def fake_fetch(ticker: str, yf_ticker=None):
        return events_map.get(ticker, [])

    monkeypatch.setattr(backfill_splits_data, "fetch_splits_for_ticker", fake_fetch)

    processed, inserted = backfill_splits_data.backfill(db_path, dry_run=True)
    assert processed == 3
    assert inserted == 0

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM splits_data").fetchone()[0]
    conn.close()
    assert count == 0
