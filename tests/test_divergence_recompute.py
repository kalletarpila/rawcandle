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
                "hidden_bullish_strength": 0.0,
                "hidden_bearish_strength": 0.0,
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
    assert rows_written == 30

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
    assert [row[1] for row in rows[:70]] == [-1.0] * 70
    assert all(row[1] != -1.0 for row in rows[70:])


def test_recompute_divergence_only_missing_rewrites_recent_buffer_for_v2_updates(
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
                "hidden_bullish_strength": 0.0,
                "hidden_bearish_strength": 0.0,
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
    assert rows_written == 70

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
    for date_value in dates[:30]:
        assert rsi_by_date[date_value] == -1.0
    for date_value in dates[30:60]:
        assert rsi_by_date[date_value] != -1.0
    for date_value in dates[60:]:
        assert rsi_by_date[date_value] != -1.0


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
                "hidden_bullish_strength": 0.0,
                "hidden_bearish_strength": 0.0,
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
        pd.DataFrame(
            {
                "pvm": custom_dates,
                "low": [value - 1.0 for value in custom_closes],
                "high": [value + 1.0 for value in custom_closes],
                "close": custom_closes,
            }
        )
    )
    expected_last = expected_rows[-1]

    with sqlite3.connect(analysis_path) as conn:
        stored_rows = conn.execute(
            """
            SELECT date, bullish_strength, bearish_strength,
                   hidden_bullish_strength, hidden_bearish_strength, rsi,
                   is_bullish_divergence, is_bearish_divergence,
                   is_hidden_bullish_divergence, is_hidden_bearish_divergence,
                   is_bullish_divergence_r2, is_bearish_divergence_r2,
                   is_hidden_bullish_divergence_r2, is_hidden_bearish_divergence_r2,
                   is_bullish_divergence_r3, is_bearish_divergence_r3,
                   is_hidden_bullish_divergence_r3, is_hidden_bearish_divergence_r3,
                   pivot_gap, pivot_drop_pct,
                   pivot_gap_r2, pivot_drop_pct_r2, pivot2_date_r2,
                   pivot_gap_r3, pivot_drop_pct_r3, pivot2_date_r3
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
    assert stored_last[3] == expected_last["hidden_bullish_strength"]
    assert stored_last[4] == expected_last["hidden_bearish_strength"]
    assert stored_last[5] == expected_last["rsi"]
    assert stored_last[6] == expected_last["is_bullish_divergence"]
    assert stored_last[7] == expected_last["is_bearish_divergence"]
    assert stored_last[8] == expected_last["is_hidden_bullish_divergence"]
    assert stored_last[9] == expected_last["is_hidden_bearish_divergence"]
    assert stored_last[10] == expected_last["is_bullish_divergence_r2"]
    assert stored_last[11] == expected_last["is_bearish_divergence_r2"]
    assert stored_last[12] == expected_last["is_hidden_bullish_divergence_r2"]
    assert stored_last[13] == expected_last["is_hidden_bearish_divergence_r2"]
    assert stored_last[14] == expected_last["is_bullish_divergence_r3"]
    assert stored_last[15] == expected_last["is_bearish_divergence_r3"]
    assert stored_last[16] == expected_last["is_hidden_bullish_divergence_r3"]
    assert stored_last[17] == expected_last["is_hidden_bearish_divergence_r3"]
    assert stored_last[18] == expected_last["pivot_gap"]
    assert stored_last[19] == expected_last["pivot_drop_pct"]
    assert stored_last[20] == expected_last["pivot_gap_r2"]
    assert stored_last[21] == expected_last["pivot_drop_pct_r2"]
    assert stored_last[22] == expected_last["pivot2_date_r2"]
    assert stored_last[23] == expected_last["pivot_gap_r3"]
    assert stored_last[24] == expected_last["pivot_drop_pct_r3"]
    assert stored_last[25] == expected_last["pivot2_date_r3"]


def test_recompute_divergence_only_missing_updates_v2_flags_for_recent_existing_rows(
    tmp_path, monkeypatch
):
    ticker = "TEST"
    osakedata_path = tmp_path / "osakedata.db"
    analysis_path = tmp_path / "analysis.db"

    with sqlite3.connect(osakedata_path) as conn:
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
        initial_rows = [
            ("2024-06-01", 10.0, 20.0, 100.0),
            ("2024-06-02", 9.0, 20.0, 100.0),
            ("2024-06-03", 8.0, 20.0, 100.0),
            ("2024-06-04", 9.0, 20.0, 100.0),
            ("2024-06-05", 10.0, 20.0, 100.0),
            ("2024-06-06", 9.0, 20.0, 100.0),
            ("2024-06-07", 7.0, 20.0, 100.0),
            ("2024-06-08", 6.0, 20.0, 100.0),
            ("2024-06-09", 7.0, 20.0, 100.0),
        ]
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(ticker, d, c, h, l, c, 1000, "usa") for d, l, h, c in initial_rows],
        )
        conn.commit()

    DatabaseManager(str(analysis_path)).close()

    from analysis import divergence_engine as divergence_engine_module

    original_compute_rsi_wilder = divergence_engine_module.compute_rsi_wilder

    def fake_compute_rsi_wilder(closes, period=14):
        if len(closes) == 9:
            return [40.0, 35.0, 20.0, 36.0, 37.0, 35.0, 32.0, 30.0, 33.0]
        if len(closes) == 11:
            return [40.0, 35.0, 20.0, 36.0, 37.0, 35.0, 32.0, 30.0, 33.0, 36.0, 38.0]
        return original_compute_rsi_wilder(closes, period=period)

    monkeypatch.setattr("analysis.divergence_engine.compute_rsi_wilder", fake_compute_rsi_wilder)

    success, rows_written, err = recompute_divergence_for_ticker(
        ticker,
        osakedata_path=str(osakedata_path),
        analysis_path=str(analysis_path),
        only_missing=False,
    )

    assert success is True
    assert err == ""
    assert rows_written == 9

    with sqlite3.connect(osakedata_path) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (ticker, "2024-06-10", 8.0, 20.0, 8.0, 100.0, 1000, "usa"),
                (ticker, "2024-06-11", 9.0, 20.0, 9.0, 100.0, 1000, "usa"),
            ],
        )
        conn.commit()

    success, rows_written, err = recompute_divergence_for_ticker(
        ticker,
        osakedata_path=str(osakedata_path),
        analysis_path=str(analysis_path),
        only_missing=True,
    )

    assert success is True
    assert err == ""
    assert rows_written == 11

    with sqlite3.connect(analysis_path) as conn:
        row = conn.execute(
            """
            SELECT is_bullish_divergence,
                   is_bullish_divergence_r2,
                   is_bullish_divergence_r3,
                   pivot_gap,
                   pivot_drop_pct,
                   pivot_gap_r2,
                   pivot_drop_pct_r2,
                   pivot2_date_r2,
                   pivot_gap_r3,
                   pivot_drop_pct_r3,
                   pivot2_date_r3
            FROM divergence_data
            WHERE ticker = ? AND date = ?
            """,
            (ticker, "2024-06-10"),
        ).fetchone()

    assert row is not None
    assert row[0] == 1
    assert row[1] == 1
    assert row[2] == 0
    assert row[3] == 5
    assert row[4] == 25.0
    assert row[5] == 5
    assert row[6] == 25.0
    assert row[7] == "2024-06-08"
    assert row[8] is None
    assert row[9] is None


def test_recompute_divergence_persists_geometry_fields(tmp_path):
    ticker = "TEST"
    osakedata_path = tmp_path / "osakedata.db"
    analysis_path = tmp_path / "analysis.db"

    with sqlite3.connect(osakedata_path) as conn:
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
        rows = [
            ("2024-06-01", 10.0, 20.0, 100.0),
            ("2024-06-02", 9.0, 20.0, 100.0),
            ("2024-06-03", 8.0, 20.0, 100.0),
            ("2024-06-04", 9.0, 20.0, 100.0),
            ("2024-06-05", 10.0, 20.0, 100.0),
            ("2024-06-06", 9.0, 20.0, 100.0),
            ("2024-06-07", 7.0, 20.0, 100.0),
            ("2024-06-08", 6.0, 20.0, 100.0),
            ("2024-06-09", 7.0, 20.0, 100.0),
            ("2024-06-10", 8.0, 20.0, 100.0),
            ("2024-06-11", 9.0, 20.0, 100.0),
        ]
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(ticker, d, c, h, l, c, 1000, "usa") for d, l, h, c in rows],
        )
        conn.commit()

    DatabaseManager(str(analysis_path)).close()

    from analysis import divergence_engine as divergence_engine_module

    original_compute_rsi_wilder = divergence_engine_module.compute_rsi_wilder

    def fake_compute_rsi_wilder(closes, period=14):
        if len(closes) == 11:
            return [40.0, 35.0, 20.0, 36.0, 37.0, 35.0, 32.0, 30.0, 33.0, 36.0, 38.0]
        return original_compute_rsi_wilder(closes, period=period)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("analysis.divergence_engine.compute_rsi_wilder", fake_compute_rsi_wilder)
        success, rows_written, err = recompute_divergence_for_ticker(
            ticker,
            osakedata_path=str(osakedata_path),
            analysis_path=str(analysis_path),
            only_missing=False,
        )

    assert success is True
    assert err == ""
    assert rows_written == 11

    with sqlite3.connect(analysis_path) as conn:
        event_row = conn.execute(
            """
            SELECT pivot_gap, pivot_drop_pct,
                   pivot_gap_r2, pivot_drop_pct_r2, pivot2_date_r2,
                   pivot_gap_r3, pivot_drop_pct_r3, pivot2_date_r3
            FROM divergence_data
            WHERE ticker = ? AND date = ?
            """,
            (ticker, "2024-06-10"),
        ).fetchone()
        non_event_row = conn.execute(
            """
            SELECT pivot_gap, pivot_drop_pct,
                   pivot_gap_r2, pivot_drop_pct_r2, pivot2_date_r2,
                   pivot_gap_r3, pivot_drop_pct_r3, pivot2_date_r3
            FROM divergence_data
            WHERE ticker = ? AND date = ?
            """,
            (ticker, "2024-06-09"),
        ).fetchone()

    assert event_row == (5, 25.0, 5, 25.0, "2024-06-08", None, None, None)
    assert non_event_row == (None, None, None, None, None, None, None, None)


def test_recompute_divergence_persists_radius_specific_pivot2_dates_independently(tmp_path, monkeypatch):
    ticker = "TEST"
    osakedata_path = tmp_path / "osakedata.db"
    analysis_path = tmp_path / "analysis.db"

    _create_osakedata_db(str(osakedata_path), ticker=ticker, days=20)
    DatabaseManager(str(analysis_path)).close()

    monkeypatch.setattr(
        "analysis.divergence_recompute.compute_divergence_series",
        lambda df, start_date=None: [
            {
                "date": str(row["pvm"]),
                "bullish_strength": 0.0,
                "bearish_strength": 0.0,
                "rsi": float(idx),
                "is_bullish_divergence": 1 if str(row["pvm"]) == "2024-01-15" else 0,
                "is_bearish_divergence": 0,
                "is_bullish_divergence_r2": 1 if str(row["pvm"]) == "2024-01-15" else 0,
                "is_bearish_divergence_r2": 0,
                "is_bullish_divergence_r3": 1 if str(row["pvm"]) == "2024-01-15" else 0,
                "is_bearish_divergence_r3": 0,
                "pivot_gap": 5 if str(row["pvm"]) == "2024-01-15" else None,
                "pivot_drop_pct": 10.0 if str(row["pvm"]) == "2024-01-15" else None,
                "pivot_gap_r2": 5 if str(row["pvm"]) == "2024-01-15" else None,
                "pivot_drop_pct_r2": 10.0 if str(row["pvm"]) == "2024-01-15" else None,
                "pivot2_date_r2": "2024-01-13" if str(row["pvm"]) == "2024-01-15" else None,
                "pivot_gap_r3": 8 if str(row["pvm"]) == "2024-01-15" else None,
                "pivot_drop_pct_r3": 12.0 if str(row["pvm"]) == "2024-01-15" else None,
                "pivot2_date_r3": "2024-01-12" if str(row["pvm"]) == "2024-01-15" else None,
            }
            for idx, row in enumerate(df.to_dict("records"))
            if start_date is None or str(row["pvm"]) >= start_date
        ],
    )

    success, rows_written, err = recompute_divergence_for_ticker(
        ticker,
        osakedata_path=str(osakedata_path),
        analysis_path=str(analysis_path),
        only_missing=False,
    )

    assert success is True
    assert err == ""
    assert rows_written == 20

    with sqlite3.connect(analysis_path) as conn:
        row = conn.execute(
            """
            SELECT pivot2_date_r2, pivot2_date_r3
            FROM divergence_data
            WHERE ticker = ? AND date = ?
            """,
            (ticker, "2024-01-15"),
        ).fetchone()

    assert row == ("2024-01-13", "2024-01-12")


def test_recompute_persists_hidden_fields(divergence_dbs, monkeypatch):
    ticker = divergence_dbs["ticker"]

    monkeypatch.setattr(
        "analysis.divergence_recompute.compute_divergence_series",
        lambda df, start_date=None: [
            {
                "date": str(row["pvm"]),
                "bullish_strength": 0.1,
                "bearish_strength": 0.2,
                "hidden_bullish_strength": 0.3,
                "hidden_bearish_strength": 0.4,
                "rsi": float(idx),
                "is_bullish_divergence": 1,
                "is_bearish_divergence": 0,
                "is_hidden_bullish_divergence": 1,
                "is_hidden_bearish_divergence": 0,
                "is_bullish_divergence_r2": 1,
                "is_bearish_divergence_r2": 0,
                "is_hidden_bullish_divergence_r2": 1,
                "is_hidden_bearish_divergence_r2": 0,
                "is_bullish_divergence_r3": 0,
                "is_bearish_divergence_r3": 1,
                "is_hidden_bullish_divergence_r3": 0,
                "is_hidden_bearish_divergence_r3": 1,
                "pivot_gap": None,
                "pivot_drop_pct": None,
                "pivot_gap_r2": None,
                "pivot_drop_pct_r2": None,
                "pivot2_date_r2": None,
                "pivot_gap_r3": None,
                "pivot_drop_pct_r3": None,
                "pivot2_date_r3": None,
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
    assert rows_written == len(divergence_dbs["dates"])

    with sqlite3.connect(divergence_dbs["analysis_path"]) as conn:
        row = conn.execute(
            """
            SELECT hidden_bullish_strength,
                   hidden_bearish_strength,
                   is_hidden_bullish_divergence,
                   is_hidden_bearish_divergence,
                   is_hidden_bullish_divergence_r2,
                   is_hidden_bearish_divergence_r2,
                   is_hidden_bullish_divergence_r3,
                   is_hidden_bearish_divergence_r3
            FROM divergence_data
            WHERE ticker = ?
            ORDER BY date DESC
            LIMIT 1
            """,
            (ticker,),
        ).fetchone()

    assert row == (0.3, 0.4, 1, 0, 1, 0, 0, 1)
