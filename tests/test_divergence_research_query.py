import csv
import sqlite3
from datetime import date, timedelta

from analysis.divergence_research_query import (
    EXPORT_COLUMNS,
    export_divergence_events_csv,
    fetch_divergence_events,
    fetch_divergence_heatmap,
    summarize_divergence_events,
)
from ui.pages.divergence_page import DivergencePage


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
                ("BBB", "2025-06-02", 28.0, 0, 1, None, None, 9, 7.5),
                ("CCC", "2025-12-02", 35.0, 1, 1, 7, 3.0, 10, 8.0),
                ("DDD", "2025-01-02", 40.0, 0, 0, None, None, None, None),
            ],
        )
        conn.execute(
            """
            CREATE TABLE excluded_tickers (
                ticker TEXT PRIMARY KEY,
                reason TEXT,
                category TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _create_stock_db(path: str) -> None:
    def build_trading_dates(start_iso: str, count: int) -> list[str]:
        current = date.fromisoformat(start_iso)
        result: list[str] = []
        while len(result) < count:
            if current.weekday() < 5:
                result.append(current.isoformat())
            current += timedelta(days=1)
        return result

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
        conn.execute(
            """
            CREATE TABLE markets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                abbreviation TEXT NOT NULL UNIQUE,
                yahoo_suffix TEXT NOT NULL DEFAULT '',
                min_volume INTEGER NOT NULL DEFAULT 100000
            )
            """
        )
        conn.executemany(
            """
            INSERT INTO markets (name, abbreviation, yahoo_suffix, min_volume)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("United States", "usa", "", 100000),
                ("Finland", "suomi", ".HE", 25000),
            ],
        )
        rows = []
        for ticker, closes in {
            "AAA": [100 + idx for idx in range(40)],
            "BBB": [50 + idx for idx in range(40)],
            "CCC": [200 + 2 * idx for idx in range(40)],
            "DDD": [10 for _ in range(40)],
        }.items():
            for idx, close in enumerate(closes):
                if ticker == "AAA":
                    dates = build_trading_dates("2025-01-02", len(closes))
                elif ticker == "BBB":
                    dates = build_trading_dates("2025-06-02", len(closes))
                elif ticker == "CCC":
                    dates = build_trading_dates("2025-12-02", len(closes))
                else:
                    dates = build_trading_dates("2025-01-02", len(closes))
                date_value = dates[idx]
                market = "suomi" if ticker == "CCC" else "usa"
                rows.append((ticker, date_value, close, close, close, close, 1000, market))
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


def test_fetch_divergence_events_supports_r2_and_r3_event_class_filters(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    rows_r2 = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R2",
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )
    rows_r3 = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R3",
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )

    assert [row["ticker"] for row in rows_r2] == ["AAA", "CCC"]
    assert [row["ticker"] for row in rows_r3] == ["BBB", "CCC"]


def test_fetch_divergence_events_uses_trading_day_offsets_for_returns(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R2_ONLY",
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
        event_class="R2",
        min_gap=7,
        max_gap=8,
        min_drop=2.8,
        max_drop=3.2,
        limit=20,
    )
    rows_r3 = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R3",
        min_gap=9,
        max_gap=10,
        min_drop=7.0,
        max_drop=8.1,
        limit=20,
    )

    assert [row["ticker"] for row in rows_r2] == ["CCC"]
    assert {row["ticker"] for row in rows_r3} == {"BBB", "CCC"}


def test_fetch_divergence_events_filters_by_rsi_range(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        min_rsi=30.0,
        max_rsi=32.0,
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )

    assert [row["ticker"] for row in rows] == ["AAA"]


def test_fetch_divergence_events_filters_by_market(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    usa_rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        market="usa",
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )
    suomi_rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        market="suomi",
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )

    assert [row["ticker"] for row in usa_rows] == ["AAA", "BBB"]
    assert [row["ticker"] for row in suomi_rows] == ["CCC"]


def test_fetch_divergence_events_excludes_active_excluded_tickers(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO excluded_tickers (ticker, reason, category, active)
            VALUES ('BBB', 'ETF', 'test', 1)
            """
        )
        conn.commit()

    rows = fetch_divergence_events(str(analysis_db), stock_db_path=str(stock_db), limit=20)

    tickers = {row["ticker"] for row in rows}
    assert tickers == {"AAA", "CCC"}


def test_fetch_divergence_events_filters_by_date_range(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    rows_from_start = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        start_date="2025-06-01",
        limit=20,
    )
    rows_to_end = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        end_date="2025-06-30",
        limit=20,
    )
    rows_between = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        start_date="2025-06-01",
        end_date="2025-11-30",
        limit=20,
    )

    assert {row["ticker"] for row in rows_from_start} == {"BBB", "CCC"}
    assert {row["ticker"] for row in rows_to_end} == {"AAA", "BBB"}
    assert {row["ticker"] for row in rows_between} == {"BBB"}


def test_summary_and_heatmap_respect_date_filtering(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    full_summary = summarize_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
    )
    filtered_summary = summarize_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        start_date="2025-06-01",
        end_date="2025-11-30",
    )
    filtered_heatmap = fetch_divergence_heatmap(
        str(analysis_db),
        stock_db_path=str(stock_db),
        start_date="2025-06-01",
        end_date="2025-11-30",
    )

    assert full_summary["n"] == 3
    assert filtered_summary["n"] == 1
    assert len(filtered_heatmap) == 1
    assert filtered_heatmap[0]["gap"] == 9
    assert filtered_heatmap[0]["drop"] == 7
    assert "winsor_ret_30d" in filtered_heatmap[0]


def test_summary_and_heatmap_respect_market_filtering(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    usa_summary = summarize_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        market="usa",
    )
    suomi_heatmap = fetch_divergence_heatmap(
        str(analysis_db),
        stock_db_path=str(stock_db),
        market="suomi",
    )

    assert usa_summary["n"] == 2
    assert len(suomi_heatmap) == 2
    assert {(row["gap"], row["drop"]) for row in suomi_heatmap} == {(7, 3), (10, 8)}


def test_divergence_page_validates_date_range():
    assert DivergencePage.validate_date_range("", "") is None
    assert DivergencePage.validate_date_range("2025-01-01", "") is None
    assert DivergencePage.validate_date_range("", "2025-12-31") is None
    assert (
        DivergencePage.validate_date_range("2025/01/01", "") ==
        "Start date must use YYYY-MM-DD format."
    )
    assert (
        DivergencePage.validate_date_range("", "2025/12/31") ==
        "End date must use YYYY-MM-DD format."
    )
    assert (
        DivergencePage.validate_date_range("2025-12-31", "2025-01-01") ==
        "Start date cannot be after end date."
    )


def test_export_divergence_events_csv_writes_expected_columns_and_path(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    export_dir = tmp_path / "exports"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    saved_path = export_divergence_events_csv(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R3_ONLY",
        min_gap=9,
        max_gap=10,
        min_drop=7.0,
        max_drop=8.1,
        start_date="2025-06-01",
        end_date="2025-06-30",
        export_path=str(export_dir),
    )

    assert saved_path.endswith(".csv")
    with open(saved_path, "r", encoding="utf-8", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))

    assert rows[0]["ticker"] == "BBB"
    assert list(rows[0].keys()) == EXPORT_COLUMNS


def test_export_divergence_events_csv_zero_rows_still_writes_header_only(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    export_path = tmp_path / "empty.csv"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    saved_path = export_divergence_events_csv(
        str(analysis_db),
        stock_db_path=str(stock_db),
        start_date="2026-01-01",
        export_path=str(export_path),
    )

    assert saved_path == str(export_path)
    with open(saved_path, "r", encoding="utf-8", newline="") as csv_file:
        rows = list(csv.reader(csv_file))

    assert rows == [EXPORT_COLUMNS]
