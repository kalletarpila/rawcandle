import sqlite3
from datetime import date, timedelta

import pytest

from analysis.database_manager import DatabaseManager
from analysis.divergence_recompute import recompute_divergence_for_ticker


def _create_osakedata_db(path: str, ticker: str, days: int = 100) -> list[str]:
    conn = sqlite3.connect(path)
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
    start = date(2024, 1, 1)
    dates: list[str] = []
    rows = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        date_str = day.isoformat()
        dates.append(date_str)
        close = 100.0 + offset
        rows.append((ticker, date_str, close, close + 1, close - 1, close, 1000, "usa"))
    conn.executemany(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()
    return dates


def _seed_divergence_rows(path: str, ticker: str, dates: list[str]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi)
            VALUES (?, ?, 0, 0, -1)
            """,
            [(ticker, d) for d in dates],
        )
        conn.commit()


@pytest.fixture
def divergence_dbs(tmp_path):
    ticker = "TEST"
    osakedata_path = tmp_path / "osakedata.db"
    analysis_path = tmp_path / "analysis.db"
    all_dates = _create_osakedata_db(str(osakedata_path), ticker=ticker, days=100)
    DatabaseManager(str(analysis_path)).close()
    return {
        "ticker": ticker,
        "osakedata_path": str(osakedata_path),
        "analysis_path": str(analysis_path),
        "dates": all_dates,
    }


def test_recompute_divergence_only_missing_writes_only_missing_tail(
    divergence_dbs, monkeypatch
):
    ticker = divergence_dbs["ticker"]
    dates = divergence_dbs["dates"]
    _seed_divergence_rows(divergence_dbs["analysis_path"], ticker, dates[:90])

    def fake_calculate_rsi(df, period=14, close_col="close"):
        work = df.copy()
        work["RSI"] = [float(i + 1) for i in range(len(work))]
        return work

    monkeypatch.setattr(
        "analysis.divergence_recompute.calculate_rsi",
        fake_calculate_rsi,
    )
    monkeypatch.setattr(
        "analysis.divergence_recompute.is_bullish_divergence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "analysis.divergence_recompute.is_bearish_divergence",
        lambda *args, **kwargs: None,
    )

    success, rows_written, err = recompute_divergence_for_ticker(
        ticker,
        osakedata_path=divergence_dbs["osakedata_path"],
        analysis_path=divergence_dbs["analysis_path"],
        only_missing=True,
    )

    assert success is True
    assert err == ""
    assert rows_written == 10

    with sqlite3.connect(divergence_dbs["analysis_path"]) as conn:
        rows = conn.execute(
            """
            SELECT date, rsi
            FROM divergence_data
            WHERE ticker = ?
            ORDER BY date
            """,
            (ticker,),
        ).fetchall()

    assert len(rows) == 100
    assert [row[1] for row in rows[:90]] == [-1.0] * 90
    assert all(row[1] != -1.0 for row in rows[90:])


def test_recompute_divergence_only_missing_is_noop_when_nothing_missing(
    divergence_dbs, monkeypatch
):
    ticker = divergence_dbs["ticker"]
    dates = divergence_dbs["dates"]
    _seed_divergence_rows(divergence_dbs["analysis_path"], ticker, dates)

    monkeypatch.setattr(
        "analysis.divergence_recompute.calculate_rsi",
        lambda df, period=14, close_col="close": df.assign(RSI=1.0),
    )

    success, rows_written, err = recompute_divergence_for_ticker(
        ticker,
        osakedata_path=divergence_dbs["osakedata_path"],
        analysis_path=divergence_dbs["analysis_path"],
        only_missing=True,
    )

    assert success is True
    assert err == ""
    assert rows_written == 0

    with sqlite3.connect(divergence_dbs["analysis_path"]) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM divergence_data WHERE ticker = ?",
            (ticker,),
        ).fetchone()[0]
    assert count == 100


def test_recompute_divergence_full_recompute_rewrites_entire_history(
    divergence_dbs, monkeypatch
):
    ticker = divergence_dbs["ticker"]
    dates = divergence_dbs["dates"]
    _seed_divergence_rows(divergence_dbs["analysis_path"], ticker, dates[:90])

    def fake_calculate_rsi(df, period=14, close_col="close"):
        work = df.copy()
        work["RSI"] = [float(1000 + i) for i in range(len(work))]
        return work

    monkeypatch.setattr(
        "analysis.divergence_recompute.calculate_rsi",
        fake_calculate_rsi,
    )
    monkeypatch.setattr(
        "analysis.divergence_recompute.is_bullish_divergence",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "analysis.divergence_recompute.is_bearish_divergence",
        lambda *args, **kwargs: None,
    )

    success, rows_written, err = recompute_divergence_for_ticker(
        ticker,
        osakedata_path=divergence_dbs["osakedata_path"],
        analysis_path=divergence_dbs["analysis_path"],
        only_missing=False,
    )

    assert success is True
    assert err == ""
    assert rows_written == 100

    with sqlite3.connect(divergence_dbs["analysis_path"]) as conn:
        rows = conn.execute(
            """
            SELECT date, rsi
            FROM divergence_data
            WHERE ticker = ?
            ORDER BY date
            """,
            (ticker,),
        ).fetchall()

    assert len(rows) == 100
    assert rows[0][1] == 1000.0
    assert rows[-1][1] == 1099.0
    assert all(row[1] != -1.0 for row in rows)
