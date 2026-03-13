import sqlite3
from datetime import date, timedelta

import pandas as pd
import pytest

from analysis.database_manager import DatabaseManager
from analysis.divergence_engine import compute_divergence_series
from analysis.divergence_recompute import (
    recompute_divergence_for_ticker,
    ticker_has_missing_divergence_dates,
)


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

    monkeypatch.setattr(
        "analysis.divergence_recompute.compute_divergence_series",
        lambda df, start_date=None: [
            {
                "date": row["pvm"],
                "bullish_strength": 0.0,
                "bearish_strength": 0.0,
                "rsi": float(idx + 1),
            }
            for idx, row in enumerate(df.to_dict("records"))
            if start_date is None or str(row["pvm"]) >= start_date
        ],
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


def test_recompute_divergence_only_missing_does_not_rewrite_existing_later_rows(
    divergence_dbs, monkeypatch
):
    ticker = divergence_dbs["ticker"]
    dates = divergence_dbs["dates"]
    kept_dates = dates[:50] + dates[60:]
    _seed_divergence_rows(divergence_dbs["analysis_path"], ticker, kept_dates)

    monkeypatch.setattr(
        "analysis.divergence_recompute.compute_divergence_series",
        lambda df, start_date=None: [
            {
                "date": row["pvm"],
                "bullish_strength": 0.0,
                "bearish_strength": 0.0,
                "rsi": float(5000 + idx),
            }
            for idx, row in enumerate(df.to_dict("records"))
            if start_date is None or str(row["pvm"]) >= start_date
        ],
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
    rsi_by_date = {row[0]: row[1] for row in rows}
    for date_value in dates[:50]:
        assert rsi_by_date[date_value] == -1.0
    for date_value in dates[50:60]:
        assert rsi_by_date[date_value] != -1.0
    for date_value in dates[60:]:
        assert rsi_by_date[date_value] == -1.0


def test_ticker_has_missing_divergence_dates_detects_partial_history(divergence_dbs):
    ticker = divergence_dbs["ticker"]
    dates = divergence_dbs["dates"]
    _seed_divergence_rows(divergence_dbs["analysis_path"], ticker, dates[:90])

    assert (
        ticker_has_missing_divergence_dates(
            ticker,
            osakedata_path=divergence_dbs["osakedata_path"],
            analysis_path=divergence_dbs["analysis_path"],
        )
        is True
    )


def test_ticker_has_missing_divergence_dates_false_when_history_complete(divergence_dbs):
    ticker = divergence_dbs["ticker"]
    dates = divergence_dbs["dates"]
    _seed_divergence_rows(divergence_dbs["analysis_path"], ticker, dates)

    assert (
        ticker_has_missing_divergence_dates(
            ticker,
            osakedata_path=divergence_dbs["osakedata_path"],
            analysis_path=divergence_dbs["analysis_path"],
        )
        is False
    )


def test_recompute_divergence_only_missing_is_noop_when_nothing_missing(
    divergence_dbs, monkeypatch
):
    ticker = divergence_dbs["ticker"]
    dates = divergence_dbs["dates"]
    _seed_divergence_rows(divergence_dbs["analysis_path"], ticker, dates)

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

    monkeypatch.setattr(
        "analysis.divergence_recompute.compute_divergence_series",
        lambda df, start_date=None: [
            {
                "date": row["pvm"],
                "bullish_strength": 0.0,
                "bearish_strength": 0.0,
                "rsi": float(1000 + idx),
            }
            for idx, row in enumerate(df.to_dict("records"))
            if start_date is None or str(row["pvm"]) >= start_date
        ],
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


def test_recompute_divergence_full_recompute_uses_real_v1_engine(divergence_dbs):
    ticker = divergence_dbs["ticker"]
    osakedata_path = divergence_dbs["osakedata_path"]
    analysis_path = divergence_dbs["analysis_path"]

    custom_dates = [f"2024-06-{day:02d}" for day in range(1, 41)]
    custom_closes = [120.0] * 20 + [100.0] + [119.0] * 8 + [98.0] + [118.0] * 9 + [90.0]

    with sqlite3.connect(osakedata_path) as conn:
        conn.execute("DELETE FROM osakedata WHERE osake = ?", (ticker,))
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    ticker,
                    date_value,
                    close_value,
                    close_value + 1.0,
                    close_value - 1.0,
                    close_value,
                    1000,
                    "usa",
                )
                for date_value, close_value in zip(custom_dates, custom_closes)
            ],
        )
        conn.commit()

    success, rows_written, err = recompute_divergence_for_ticker(
        ticker,
        osakedata_path=osakedata_path,
        analysis_path=analysis_path,
        only_missing=False,
    )

    assert success is True
    assert err == ""
    assert rows_written == len(custom_dates)

    expected_rows = compute_divergence_series(
        pd.DataFrame({"pvm": custom_dates, "close": custom_closes})
    )
    expected_last = expected_rows[-1]

    with sqlite3.connect(analysis_path) as conn:
        stored_rows = conn.execute(
            """
            SELECT date, bullish_strength, bearish_strength, rsi
            FROM divergence_data
            WHERE ticker = ?
            ORDER BY date
            """,
            (ticker,),
        ).fetchall()

    assert len(stored_rows) == len(custom_dates)
    stored_last = stored_rows[-1]
    assert stored_last[0] == expected_last["date"]
    assert stored_last[1] == expected_last["bullish_strength"]
    assert stored_last[2] == expected_last["bearish_strength"]
    assert stored_last[3] == expected_last["rsi"]
