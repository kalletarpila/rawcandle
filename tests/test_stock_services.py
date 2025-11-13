import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from stock import services


def _create_price_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "prices.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
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
    base_date = dt.date(2024, 1, 1)
    for i in range(1, 7):
        date_value = (base_date + dt.timedelta(days=i)).isoformat()
        price = 100 + i
        cursor.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "TEST",
                date_value,
                price - 0.5,
                price + 1.0,
                price - 1.2,
                price,
                1_000 + i * 10,
                "usa",
            ),
        )
    conn.commit()
    conn.close()
    return db_path


def _create_analysis_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "analysis.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE analysis_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            pattern TEXT,
            signal_strength REAL,
            rsi14 REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    for i in range(3):
        cursor.execute(
            """
            INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "TEST",
                f"2024-01-0{i+1}",
                "Hammer",
                0.5 + i * 0.1,
                55 + i,
            ),
        )
    conn.commit()
    conn.close()
    return db_path


def test_fetch_price_rows_returns_rsi_and_sma(tmp_path):
    price_db = _create_price_db(tmp_path)
    rows, total = services.fetch_price_rows(
        "test",
        limit=5,
        rsi_period=3,
        price_db=price_db,
    )
    assert total == 6
    assert len(rows) == 5
    assert rows[-1]["rsi"] is not None
    assert "sma20" in rows[-1] and "sma50" in rows[-1]


def test_fetch_price_rows_missing_db(tmp_path):
    missing_db = tmp_path / "missing.db"
    with pytest.raises(services.StockDataError):
        services.fetch_price_rows("MSFT", price_db=missing_db)


def test_fetch_analysis_records_pagination(tmp_path):
    analysis_db = _create_analysis_db(tmp_path)
    rows, total = services.fetch_analysis_records(
        "test",
        page=0,
        page_size=2,
        analysis_db=analysis_db,
    )
    assert total == 3
    assert len(rows) == 2
    assert rows[0]["date"] >= rows[1]["date"]

    rows_page_2, _ = services.fetch_analysis_records(
        "test",
        page=1,
        page_size=2,
        analysis_db=analysis_db,
    )
    assert len(rows_page_2) == 1
