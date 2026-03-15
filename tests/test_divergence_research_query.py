import sqlite3

from analysis.divergence_research_query import fetch_divergence_events


def _create_analysis_db(path: str) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE divergence_data (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                bullish_strength REAL DEFAULT 0,
                bearish_strength REAL DEFAULT 0,
                rsi REAL,
                is_bullish_divergence INTEGER DEFAULT 0,
                is_bearish_divergence INTEGER DEFAULT 0,
                is_bullish_divergence_r2 INTEGER DEFAULT 0,
                is_bearish_divergence_r2 INTEGER DEFAULT 0,
                is_bullish_divergence_r3 INTEGER DEFAULT 0,
                is_bearish_divergence_r3 INTEGER DEFAULT 0,
                pivot_gap INTEGER,
                pivot_drop_pct REAL,
                pivot_gap_r2 INTEGER,
                pivot_drop_pct_r2 REAL,
                pivot_gap_r3 INTEGER,
                pivot_drop_pct_r3 REAL,
                PRIMARY KEY (ticker, date)
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO divergence_data (
                ticker, date, bullish_strength, bearish_strength, rsi,
                is_bullish_divergence, is_bearish_divergence,
                is_bullish_divergence_r2, is_bearish_divergence_r2,
                is_bullish_divergence_r3, is_bearish_divergence_r3,
                pivot_gap, pivot_drop_pct,
                pivot_gap_r2, pivot_drop_pct_r2,
                pivot_gap_r3, pivot_drop_pct_r3
            )
            VALUES (?, ?, 0, 0, ?, 0, 0, ?, 0, ?, 0, NULL, NULL, ?, ?, ?, ?)
            """,
            [
                ("AAA", "2025-01-02", 31.0, 1, 0, 6, 2.5, None, None),
                ("BBB", "2025-01-02", 28.0, 0, 1, None, None, 9, 7.5),
                ("CCC", "2025-01-02", 35.0, 1, 1, 7, 3.0, 10, 8.0),
                ("DDD", "2025-01-02", 40.0, 0, 0, None, None, None, None),
            ],
        )
        conn.commit()


def _create_stock_db(path: str) -> None:
    with sqlite3.connect(path) as conn:
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
        rows = []
        for ticker, closes in {
            "AAA": [100, 101, 102, 103, 104, 105, 106],
            "BBB": [50, 51, 52, 53, 54, 55, 56],
            "CCC": [200, 202, 204, 206, 208, 210, 212],
            "DDD": [10, 10, 10, 10, 10, 10, 10],
        }.items():
            for idx, close in enumerate(closes):
                date_value = ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09", "2025-01-10"][idx]
                rows.append((ticker, date_value, close, close, close, close, 1000, "usa"))
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def test_fetch_divergence_events_returns_only_bullish_rows(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    rows = fetch_divergence_events(str(analysis_db), stock_db_path=str(stock_db), limit=20)

    tickers = {row["ticker"] for row in rows}
    assert tickers == {"AAA", "BBB", "CCC"}


def test_fetch_divergence_events_classifies_event_rows_correctly(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    rows = fetch_divergence_events(str(analysis_db), stock_db_path=str(stock_db), limit=20, sort_by="ticker", sort_desc=False)
    by_ticker = {row["ticker"]: row["event_class"] for row in rows}

    assert by_ticker["AAA"] == "R2_ONLY"
    assert by_ticker["BBB"] == "R3_ONLY"
    assert by_ticker["CCC"] == "R2_AND_R3"


def test_fetch_divergence_events_uses_trading_day_offsets_for_returns(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R2_ONLY",
        radius="R2",
        limit=20,
    )

    row = rows[0]
    assert row["ticker"] == "AAA"
    assert round(row["ret_5d"], 6) == 5.0


def test_fetch_divergence_events_filters_by_radius_specific_gap_and_drop(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    rows_r2 = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        radius="R2",
        min_gap=7,
        max_gap=8,
        min_drop=2.8,
        max_drop=3.2,
        limit=20,
    )
    rows_r3 = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        radius="R3",
        min_gap=9,
        max_gap=10,
        min_drop=7.0,
        max_drop=8.1,
        limit=20,
    )

    assert [row["ticker"] for row in rows_r2] == ["CCC"]
    assert {row["ticker"] for row in rows_r3} == {"BBB", "CCC"}
