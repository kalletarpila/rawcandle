import datetime
import sqlite3
from pathlib import Path

import pytest

from analysis.downtrend_generator import DowntrendGenerator


def _build_stock_db(tmp_path: Path) -> str:
    db_path = tmp_path / "osakedata.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE osakedata (
            osake TEXT,
            pvm TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            market TEXT NOT NULL DEFAULT 'usa'
        )
        """
    )

    start = datetime.date(2024, 1, 1)
    price = 50.0
    for i in range(25):
        date = start + datetime.timedelta(days=i)
        # tee tasaisesti laskeva kurssi -> varmistaa downtrend-kriteerit
        close = price - (i * 0.7)
        cursor.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "AAA",
                date.isoformat(),
                close + 0.5,
                close + 1.0,
                close - 1.0,
                close,
                1_000_000 + (i * 1000),
            ),
        )
    conn.commit()
    conn.close()
    return str(db_path)


def _build_analysis_db(tmp_path: Path) -> str:
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
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.mark.parametrize("events_per_ticker", [1, 2])
def test_downtrend_generator_creates_events(tmp_path, monkeypatch, events_per_ticker):
    stock_db = _build_stock_db(Path(tmp_path))
    analysis_db = _build_analysis_db(Path(tmp_path))

    generator = DowntrendGenerator(stock_db_path=stock_db, analysis_db_path=analysis_db)

    # tee deterministiseksi: valitaan aina sama ticker ja käytetään ensimmäistä päivää
    monkeypatch.setattr(
        "analysis.downtrend_generator.random.choice", lambda seq: seq[0]
    )
    monkeypatch.setattr(
        generator, "_select_random_tickers", lambda conn, n: ["AAA"]
    )

    saved, errors = generator.generate_random_findings(
        num_tickers=1,
        events_per_ticker=events_per_ticker,
    )

    assert not errors
    assert saved >= 1

    conn = sqlite3.connect(analysis_db)
    cursor = conn.cursor()
    cursor.execute("SELECT ticker, pattern, rsi14 FROM analysis_findings")
    rows = cursor.fetchall()
    conn.close()

    assert rows, "expected downtrend rows written"
    for ticker, pattern, rsi14 in rows:
        assert ticker == "AAA"
        assert pattern == "downtrend"
        assert rsi14 is None or isinstance(rsi14, float)
