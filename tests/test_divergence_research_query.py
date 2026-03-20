import csv
import sqlite3
from datetime import date, timedelta

import ui.pages.divergence_page as divergence_page_module
from analysis.divergence_research_query import (
    EXPORT_COLUMNS,
    export_divergence_events_csv,
    fetch_divergence_events,
    fetch_divergence_heatmap,
    summarize_divergence_events,
)
from ui.pages.divergence_page import DivergencePage


def _build_trading_dates(start_iso: str, count: int) -> list[str]:
    current = date.fromisoformat(start_iso)
    result: list[str] = []
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def _create_analysis_db(path: str) -> None:
    aaa_event_date = _build_trading_dates("2025-01-02", 50)[15]
    bbb_event_date = _build_trading_dates("2025-06-02", 50)[15]
    ccc_event_date = _build_trading_dates("2025-12-02", 50)[15]
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
                pivot2_date_r2 TEXT,
                pivot_gap_r3 INTEGER,
                pivot_drop_pct_r3 REAL,
                pivot2_date_r3 TEXT,
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
                pivot2_date_r2,
                pivot_gap_r3, pivot_drop_pct_r3,
                pivot2_date_r3
            )
            VALUES (?, ?, 0, 0, ?, 0, 0, ?, 0, ?, 0, NULL, NULL, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("AAA", aaa_event_date, 31.0, 1, 0, 6, 2.5, "2025-01-17", None, None, None),
                ("BBB", bbb_event_date, 28.0, 0, 1, None, None, None, 9, 7.5, "2025-06-17"),
                ("CCC", ccc_event_date, 35.0, 1, 1, 7, 3.0, "2025-12-17", 10, 8.0, "2025-12-16"),
                ("DDD", "2025-01-02", 40.0, 0, 0, None, None, None, None, None, None),
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
        conn.execute(
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
        conn.executemany(
            """
            INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("BBB", bbb_event_date, "BullDiv & Hammer", 0.7, 28.0),
                ("BBB", bbb_event_date, "BullDiv & Piercing Pattern", 0.8, 28.0),
                ("CCC", ccc_event_date, "BullDiv & Bullish Engulfing", 0.9, 35.0),
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
        price_map = {
            "AAA": [120 - idx for idx in range(16)] + [106 + idx for idx in range(34)],
            "BBB": [50 + idx for idx in range(50)],
            "CCC": [220 - (2 * idx) for idx in range(16)] + [192 + (2 * idx) for idx in range(34)],
            "DDD": [10 for _ in range(50)],
        }
        for ticker, closes in price_map.items():
            if ticker == "AAA":
                dates = _build_trading_dates("2025-01-02", len(closes))
            elif ticker == "BBB":
                dates = _build_trading_dates("2025-06-02", len(closes))
            elif ticker == "CCC":
                dates = _build_trading_dates("2025-12-02", len(closes))
            else:
                dates = _build_trading_dates("2025-01-02", len(closes))
            for idx, close in enumerate(closes):
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


def _insert_divergence_row(
    analysis_db: str,
    *,
    ticker: str,
    event_date: str,
    rsi: float = 30.0,
    is_r2: int = 0,
    is_r3: int = 1,
    pivot_gap_r2: int | None = None,
    pivot_drop_pct_r2: float | None = None,
    pivot2_date_r2: str | None = None,
    pivot_gap_r3: int | None = 19,
    pivot_drop_pct_r3: float | None = 8.0,
    pivot2_date_r3: str | None = None,
) -> None:
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO divergence_data (
                ticker, date, bullish_strength, bearish_strength, rsi,
                is_bullish_divergence, is_bearish_divergence,
                is_bullish_divergence_r2, is_bearish_divergence_r2,
                is_bullish_divergence_r3, is_bearish_divergence_r3,
                pivot_gap, pivot_drop_pct,
                pivot_gap_r2, pivot_drop_pct_r2, pivot2_date_r2,
                pivot_gap_r3, pivot_drop_pct_r3, pivot2_date_r3
            )
            VALUES (?, ?, 0, 0, ?, 0, 0, ?, 0, ?, 0, NULL, NULL, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker,
                event_date,
                rsi,
                is_r2,
                is_r3,
                pivot_gap_r2,
                pivot_drop_pct_r2,
                pivot2_date_r2,
                pivot_gap_r3,
                pivot_drop_pct_r3,
                pivot2_date_r3,
            ),
        )
        conn.commit()


def _insert_combo_finding(
    analysis_db: str,
    *,
    ticker: str,
    event_date: str,
    pattern: str,
) -> None:
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14)
            VALUES (?, ?, ?, 1.0, 30.0)
            """,
            (ticker, event_date, pattern),
        )
        conn.commit()


def _insert_stock_series(
    stock_db: str,
    *,
    ticker: str,
    start_iso: str,
    count: int = 60,
    market: str = "usa",
) -> None:
    dates = _build_trading_dates(start_iso, count)
    rows = [
        (ticker, day, 100 + idx, 100 + idx, 100 + idx, 100 + idx, 1000, market)
        for idx, day in enumerate(dates)
    ]
    with sqlite3.connect(stock_db) as conn:
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
    assert round(row["ret_5d"], 6) == round(((110.0 / 105.0) - 1.0) * 100.0, 6)


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


def test_fetch_divergence_events_trend_filter_all_matches_current_behavior(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    base_rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )
    trend_rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        trend_filter="all",
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )

    assert base_rows == trend_rows


def test_fetch_divergence_events_trend_filter_downtrend_only_keeps_and_removes_rows(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        trend_filter="downtrend_only",
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )

    assert [row["ticker"] for row in rows] == ["AAA", "CCC"]


def test_fetch_divergence_events_trend_filter_matches_candles_rule_conditions(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        trend_filter="downtrend_only",
        event_class="R2",
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )

    assert [row["ticker"] for row in rows] == ["AAA", "CCC"]


def test_fetch_divergence_events_trend_filter_insufficient_history_is_false(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    event_date = _build_trading_dates("2025-03-03", 8)[5]
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
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
            ("EEE", event_date, 30.0, 0, 1, 6, 4.0, None, None),
        )
        conn.commit()
    with sqlite3.connect(stock_db) as conn:
        dates = _build_trading_dates("2025-03-03", 8)
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [("EEE", day, 20 + idx, 20 + idx, 20 + idx, 20 + idx, 1000, "usa") for idx, day in enumerate(dates)],
        )
        conn.commit()

    rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R2_ONLY",
        trend_filter="downtrend_only",
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )

    assert [row["ticker"] for row in rows] == ["AAA"]


def test_summary_heatmap_and_export_respect_downtrend_filter(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    export_path = tmp_path / "downtrend.csv"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    summary = summarize_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        trend_filter="downtrend_only",
    )
    heatmap = fetch_divergence_heatmap(
        str(analysis_db),
        stock_db_path=str(stock_db),
        trend_filter="downtrend_only",
    )
    saved_path = export_divergence_events_csv(
        str(analysis_db),
        stock_db_path=str(stock_db),
        trend_filter="downtrend_only",
        export_path=str(export_path),
    )

    assert summary["n"] == 2
    assert {(row["gap"], row["drop"]) for row in heatmap} == {(6, 2), (7, 3), (10, 8)}
    with open(saved_path, "r", encoding="utf-8", newline="") as csv_file:
        exported_rows = list(csv.DictReader(csv_file))
    assert {row["ticker"] for row in exported_rows} == {"AAA", "CCC"}


def test_fetch_divergence_events_excludes_rows_with_null_selected_pivot2_date(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO divergence_data (
                ticker, date, bullish_strength, bearish_strength, rsi,
                is_bullish_divergence, is_bearish_divergence,
                is_bullish_divergence_r2, is_bearish_divergence_r2,
                is_bullish_divergence_r3, is_bearish_divergence_r3,
                pivot_gap, pivot_drop_pct,
                pivot_gap_r2, pivot_drop_pct_r2, pivot2_date_r2,
                pivot_gap_r3, pivot_drop_pct_r3, pivot2_date_r3
            )
            VALUES ('EEE', '2025-02-03', 0, 0, 30.0, 0, 0, 1, 0, 0, 0, NULL, NULL, 6, 3.0, NULL, NULL, NULL, NULL)
            """
        )
        conn.commit()
    with sqlite3.connect(stock_db) as conn:
        dates = _build_trading_dates("2025-02-03", 40)
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [("EEE", day, 30 + idx, 30 + idx, 30 + idx, 30 + idx, 1000, "usa") for idx, day in enumerate(dates)],
        )
        conn.commit()

    rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R2",
        anchor="pivot2",
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )

    assert [row["ticker"] for row in rows] == ["AAA", "CCC"]


def test_fetch_divergence_events_switches_returns_when_anchor_changes(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    event_rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R2_ONLY",
        anchor="event",
        limit=20,
    )
    pivot_rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R2_ONLY",
        anchor="pivot2",
        limit=20,
    )

    assert event_rows[0]["ticker"] == "AAA"
    assert pivot_rows[0]["ticker"] == "AAA"
    assert event_rows[0]["ret_5d"] != pivot_rows[0]["ret_5d"]
    assert event_rows[0]["anchor_type"] == "event"
    assert event_rows[0]["anchor_date"] == event_rows[0]["date"]
    assert pivot_rows[0]["anchor_type"] == "pivot2"
    assert pivot_rows[0]["anchor_date"] == "2025-01-17"


def test_fetch_divergence_events_date_filter_depends_on_anchor(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    event_rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R2_ONLY",
        anchor="event",
        start_date="2025-01-20",
        end_date="2025-01-24",
        limit=20,
    )
    pivot_rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R2_ONLY",
        anchor="pivot2",
        start_date="2025-01-16",
        end_date="2025-01-18",
        limit=20,
    )

    assert [row["ticker"] for row in event_rows] == ["AAA"]
    assert [row["ticker"] for row in pivot_rows] == ["AAA"]


def test_fetch_divergence_events_uses_radius_specific_pivot2_dates(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    rows_r2 = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R2",
        anchor="pivot2",
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )
    rows_r3 = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R3",
        anchor="pivot2",
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )

    aaa_r2 = next(row for row in rows_r2 if row["ticker"] == "AAA")
    bbb_r3 = next(row for row in rows_r3 if row["ticker"] == "BBB")
    ccc_r2 = next(row for row in rows_r2 if row["ticker"] == "CCC")
    ccc_r3 = next(row for row in rows_r3 if row["ticker"] == "CCC")

    assert aaa_r2["anchor_date"] == "2025-01-17"
    assert bbb_r3["anchor_date"] == "2025-06-17"
    assert ccc_r2["anchor_date"] == "2025-12-17"
    assert ccc_r3["anchor_date"] == "2025-12-16"


def test_summary_and_heatmap_change_with_anchor_switch(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    event_summary = summarize_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R2",
        anchor="event",
    )
    pivot_summary = summarize_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R2",
        anchor="pivot2",
    )
    event_heatmap = fetch_divergence_heatmap(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R2",
        anchor="event",
    )
    pivot_heatmap = fetch_divergence_heatmap(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R2",
        anchor="pivot2",
    )

    assert event_summary["mean_ret_30d"] != pivot_summary["mean_ret_30d"]
    assert event_heatmap != pivot_heatmap


def test_export_divergence_events_csv_includes_anchor_fields_and_uses_selected_anchor(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    export_path = tmp_path / "pivot2.csv"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    saved_path = export_divergence_events_csv(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R2_ONLY",
        anchor="pivot2",
        export_path=str(export_path),
    )

    with open(saved_path, "r", encoding="utf-8", newline="") as csv_file:
        rows = list(csv.DictReader(csv_file))

    assert rows[0]["pivot2_date_r2"] == "2025-01-17"
    assert rows[0]["pivot2_date_r3"] == ""
    assert rows[0]["anchor_type"] == "pivot2"
    assert rows[0]["anchor_date"] == "2025-01-17"
    assert float(rows[0]["ret_5d"]) != round(((110.0 / 105.0) - 1.0) * 100.0, 6)


def test_fetch_divergence_events_combines_trend_filter_with_event_class_and_date_range(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R3",
        start_date="2025-06-01",
        end_date="2025-06-30",
        trend_filter="downtrend_only",
        limit=20,
    )

    assert rows == []


def test_fetch_divergence_events_computes_combo_offset_correctly(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    eee_dates = _build_trading_dates("2025-07-01", 30)
    _insert_divergence_row(
        str(analysis_db),
        ticker="EEE",
        event_date=eee_dates[12],
        pivot_gap_r3=19,
        pivot_drop_pct_r3=8.0,
        pivot2_date_r3=eee_dates[10],
    )
    _insert_combo_finding(
        str(analysis_db),
        ticker="EEE",
        event_date=eee_dates[12],
        pattern="BullDiv & Hammer",
    )
    _insert_stock_series(str(stock_db), ticker="EEE", start_iso="2025-07-01")

    rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R3_ONLY",
        combo_pattern="BullDiv & Hammer",
        start_date=eee_dates[12],
        end_date=eee_dates[12],
        limit=20,
    )

    assert len(rows) == 1
    assert rows[0]["ticker"] == "EEE"
    assert rows[0]["pivot2_date_r3"] == eee_dates[10]
    assert rows[0]["combo_pattern"] == "BullDiv & Hammer"
    assert rows[0]["combo_offset"] == 2


def test_fetch_divergence_events_filters_combo_offset_range_minus1_plus1(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    fff_dates = _build_trading_dates("2025-08-01", 30)
    ggg_dates = _build_trading_dates("2025-09-01", 30)
    hhh_dates = _build_trading_dates("2025-10-01", 30)
    iii_dates = _build_trading_dates("2025-11-03", 30)
    for ticker, dates, event_idx, pivot_idx in [
        ("FFF", fff_dates, 9, 10),
        ("GGG", ggg_dates, 10, 10),
        ("HHH", hhh_dates, 11, 10),
        ("III", iii_dates, 12, 10),
    ]:
        _insert_divergence_row(
            str(analysis_db),
            ticker=ticker,
            event_date=dates[event_idx],
            pivot_gap_r3=19,
            pivot_drop_pct_r3=8.0,
            pivot2_date_r3=dates[pivot_idx],
        )
        _insert_combo_finding(
            str(analysis_db),
            ticker=ticker,
            event_date=dates[event_idx],
            pattern="BullDiv & Hammer",
        )
        _insert_stock_series(str(stock_db), ticker=ticker, start_iso=dates[0])

    rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R3_ONLY",
        combo_pattern="BullDiv & Hammer",
        combo_offset_min=-1,
        combo_offset_max=1,
        limit=50,
        sort_by="ticker",
        sort_desc=False,
    )

    assert [row["ticker"] for row in rows] == ["FFF", "GGG", "HHH"]
    assert [row["combo_offset"] for row in rows] == [-1, 0, 1]


def test_fetch_divergence_events_filters_combo_offset_range_0_plus1(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    jjj_dates = _build_trading_dates("2025-07-15", 30)
    kkk_dates = _build_trading_dates("2025-08-15", 30)
    lll_dates = _build_trading_dates("2025-09-15", 30)
    for ticker, dates, event_idx, pivot_idx in [
        ("JJJ", jjj_dates, 9, 10),
        ("KKK", kkk_dates, 10, 10),
        ("LLL", lll_dates, 11, 10),
    ]:
        _insert_divergence_row(
            str(analysis_db),
            ticker=ticker,
            event_date=dates[event_idx],
            pivot_gap_r3=19,
            pivot_drop_pct_r3=8.0,
            pivot2_date_r3=dates[pivot_idx],
        )
        _insert_combo_finding(
            str(analysis_db),
            ticker=ticker,
            event_date=dates[event_idx],
            pattern="BullDiv & Hammer",
        )
        _insert_stock_series(str(stock_db), ticker=ticker, start_iso=dates[0])

    rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R3_ONLY",
        combo_pattern="BullDiv & Hammer",
        combo_offset_min=0,
        combo_offset_max=1,
        limit=50,
        sort_by="ticker",
        sort_desc=False,
    )

    assert [row["ticker"] for row in rows] == ["KKK", "LLL"]
    assert [row["combo_offset"] for row in rows] == [0, 1]


def test_fetch_divergence_events_filters_combo_pattern_exact_match(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    mmm_dates = _build_trading_dates("2025-07-21", 30)
    nnn_dates = _build_trading_dates("2025-08-21", 30)
    for ticker, pattern, dates in [
        ("MMM", "BullDiv & Bullish Engulfing", mmm_dates),
        ("NNN", "BullDiv & Piercing Pattern", nnn_dates),
    ]:
        _insert_divergence_row(
            str(analysis_db),
            ticker=ticker,
            event_date=dates[11],
            pivot_gap_r3=19,
            pivot_drop_pct_r3=8.0,
            pivot2_date_r3=dates[10],
        )
        _insert_combo_finding(
            str(analysis_db),
            ticker=ticker,
            event_date=dates[11],
            pattern=pattern,
        )
        _insert_stock_series(str(stock_db), ticker=ticker, start_iso=dates[0])

    engulfing_rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R3_ONLY",
        combo_pattern="BullDiv & Bullish Engulfing",
        limit=50,
        sort_by="ticker",
        sort_desc=False,
    )
    piercing_rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R3_ONLY",
        combo_pattern="BullDiv & Piercing Pattern",
        limit=50,
        sort_by="ticker",
        sort_desc=False,
    )

    assert [row["ticker"] for row in engulfing_rows] == ["MMM"]
    assert [row["ticker"] for row in piercing_rows] == ["NNN"]


def test_fetch_divergence_events_combined_combo_filters_keep_only_intended_rows(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    ooo_dates = _build_trading_dates("2025-10-15", 30)
    ppp_dates = _build_trading_dates("2025-11-15", 30)
    qqq_dates = _build_trading_dates("2025-12-15", 30)
    for ticker, dates, gap_value, drop_value, pattern, event_idx in [
        ("OOO", ooo_dates, 20, 6.0, "BullDiv & Bullish Engulfing", 11),
        ("PPP", ppp_dates, 18, 6.0, "BullDiv & Bullish Engulfing", 11),
        ("QQQ", qqq_dates, 20, 21.0, "BullDiv & Bullish Engulfing", 11),
    ]:
        _insert_divergence_row(
            str(analysis_db),
            ticker=ticker,
            event_date=dates[event_idx],
            pivot_gap_r3=gap_value,
            pivot_drop_pct_r3=drop_value,
            pivot2_date_r3=dates[10],
        )
        _insert_combo_finding(
            str(analysis_db),
            ticker=ticker,
            event_date=dates[event_idx],
            pattern=pattern,
        )
        _insert_stock_series(str(stock_db), ticker=ticker, start_iso=dates[0])

    rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R3_ONLY",
        combo_pattern="BullDiv & Bullish Engulfing",
        combo_offset_min=0,
        combo_offset_max=1,
        min_gap=19,
        max_gap=24,
        min_drop=5.0,
        max_drop=20.0,
        limit=50,
        sort_by="ticker",
        sort_desc=False,
    )

    assert [row["ticker"] for row in rows] == ["OOO"]
    assert rows[0]["combo_pattern"] == "BullDiv & Bullish Engulfing"
    assert rows[0]["combo_offset"] == 1


def test_fetch_divergence_events_collapses_duplicate_same_day_combo_deterministically(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R3_ONLY",
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )

    bbb_row = next(row for row in rows if row["ticker"] == "BBB")
    assert bbb_row["combo_pattern"] == "BullDiv & Hammer"


def test_fetch_divergence_events_without_combo_filters_keeps_legacy_rows(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    stock_db = tmp_path / "osakedata.db"
    _create_analysis_db(str(analysis_db))
    _create_stock_db(str(stock_db))

    base_rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R3_ONLY",
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )
    all_rows = fetch_divergence_events(
        str(analysis_db),
        stock_db_path=str(stock_db),
        event_class="R3_ONLY",
        combo_pattern="ALL",
        limit=20,
        sort_by="ticker",
        sort_desc=False,
    )

    assert [row["ticker"] for row in base_rows] == ["BBB"]
    assert [row["ticker"] for row in all_rows] == ["BBB"]
    assert base_rows[0]["combo_pattern"] == "BullDiv & Hammer"
    assert all_rows[0]["combo_pattern"] == "BullDiv & Hammer"


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


class _FakePage:
    def update(self) -> None:
        pass

    def run_task(self, *args, **kwargs) -> None:
        pass

    def open(self, *args, **kwargs) -> None:
        pass

    def close(self, *args, **kwargs) -> None:
        pass


def _build_divergence_page(monkeypatch) -> DivergencePage:
    monkeypatch.setattr(
        divergence_page_module,
        "list_markets",
        lambda _path: [{"abbreviation": "usa"}],
    )
    page = DivergencePage(_FakePage(), lambda: None)
    page.create_view()
    return page


def test_divergence_page_presets_define_required_entries():
    required_presets = {
        "Default / All Bullish",
        "R3_ONLY Event",
        "R3_ONLY Pivot2",
        "R3 Long Swing",
        "R3 Long Swing Pivot2",
        "R2_ONLY Event",
        "R2_AND_R3 Event",
        "R3 Strong Combo (0,+1)",
    }
    assert required_presets.issubset(DivergencePage.PRESETS.keys())
    for preset_name in required_presets:
        preset = DivergencePage.PRESETS[preset_name]
        assert preset is not None
        assert set(
            [
                "event_class",
                "anchor",
                "trend_filter",
                "market",
                "combo_pattern",
                "combo_offset_min",
                "combo_offset_max",
                "min_gap",
                "max_gap",
                "min_drop",
                "max_drop",
                "min_rsi",
                "max_rsi",
                "start_date",
                "end_date",
            ]
        ) == set(preset.keys())
        assert "radius" not in preset


def test_divergence_page_apply_preset_populates_controls_and_triggers_refresh(monkeypatch):
    page = _build_divergence_page(monkeypatch)
    refresh_calls: list[dict[str, object]] = []

    def fake_refresh(_e=None) -> None:
        refresh_calls.append(page._get_filters())

    page._refresh = fake_refresh
    page.preset_dropdown.value = "R3 Long Swing Pivot2"

    page._apply_preset()

    assert page.event_class_dropdown.value == "R3_ONLY"
    assert page.anchor_dropdown.value == "Pivot2"
    assert page.combo_pattern_dropdown.value == "All"
    assert page.min_gap_slider.value == 19
    assert page.max_gap_slider.value == 24
    assert page.min_drop_slider.value == 5
    assert page.max_drop_slider.value == 20
    assert page.combo_offset_min_slider.value == -3
    assert page.combo_offset_max_slider.value == 3
    assert page.start_date_field.value == ""
    assert page.end_date_field.value == ""
    assert page.filter_error_text.value == ""
    assert refresh_calls == [
        {
            "event_class": "R3_ONLY",
            "anchor": "pivot2",
            "trend_filter": "all",
            "market": None,
            "combo_pattern": "ALL",
            "combo_offset_min": -3,
            "combo_offset_max": 3,
            "min_gap": 19,
            "max_gap": 24,
            "min_drop": 5.0,
            "max_drop": 20.0,
            "min_rsi": 1.0,
            "max_rsi": 100.0,
            "start_date": None,
            "end_date": None,
        }
    ]


def test_divergence_page_apply_preset_supports_date_range(monkeypatch):
    page = _build_divergence_page(monkeypatch)
    page._refresh = lambda _e=None: None
    page.preset_dropdown.value = "2025 R3 Long Swing"

    page._apply_preset()

    assert page.event_class_dropdown.value == "R3_ONLY"
    assert page.anchor_dropdown.value == "Event"
    assert page.start_date_field.value == "2025-01-01"
    assert page.end_date_field.value == "2025-12-31"
    assert page._get_filters()["start_date"] == "2025-01-01"
    assert page._get_filters()["end_date"] == "2025-12-31"


def test_divergence_page_get_filters_maps_combo_controls(monkeypatch):
    page = _build_divergence_page(monkeypatch)

    page.combo_pattern_dropdown.value = "Piercing"
    page.combo_offset_min_slider.value = 0
    page.combo_offset_max_slider.value = 1

    filters = page._get_filters()

    assert filters["combo_pattern"] == "BullDiv & Piercing Pattern"
    assert filters["combo_offset_min"] == 0
    assert filters["combo_offset_max"] == 1


def test_divergence_page_strong_combo_preset_sets_locked_values(monkeypatch):
    page = _build_divergence_page(monkeypatch)
    page._refresh = lambda _e=None: None
    page.preset_dropdown.value = "R3 Strong Combo (0,+1)"

    page._apply_preset()

    filters = page._get_filters()
    assert filters["event_class"] == "R3_ONLY"
    assert filters["anchor"] == "pivot2"
    assert filters["min_gap"] == 19
    assert filters["min_drop"] == 5.0
    assert filters["max_drop"] == 20.0
    assert filters["combo_offset_min"] == 0
    assert filters["combo_offset_max"] == 1
    assert filters["combo_pattern"] == "ALL"


def test_divergence_page_refresh_and_export_use_same_combo_filters(monkeypatch):
    page = _build_divergence_page(monkeypatch)
    page.combo_pattern_dropdown.value = "Hammer"
    page.combo_offset_min_slider.value = 0
    page.combo_offset_max_slider.value = 1

    captured: dict[str, list[dict[str, object]]] = {"refresh": [], "export": []}

    def fake_start_refresh_worker(filters):
        captured["refresh"].append(filters)

    def fake_export(*args, **kwargs):
        captured["export"].append(kwargs)
        return "/tmp/out.csv"

    page._start_refresh_worker = fake_start_refresh_worker
    monkeypatch.setattr(divergence_page_module, "export_divergence_events_csv", fake_export)

    page._refresh()
    page._export_csv(None)

    assert captured["refresh"][0]["combo_pattern"] == "BullDiv & Hammer"
    assert captured["refresh"][0]["combo_offset_min"] == 0
    assert captured["refresh"][0]["combo_offset_max"] == 1
    assert captured["export"][0]["combo_pattern"] == "BullDiv & Hammer"
    assert captured["export"][0]["combo_offset_min"] == 0
    assert captured["export"][0]["combo_offset_max"] == 1


def test_divergence_page_manual_filter_change_keeps_manual_behavior(monkeypatch):
    page = _build_divergence_page(monkeypatch)
    page._refresh = lambda _e=None: None
    page.preset_dropdown.value = "R2_ONLY Event"
    page._apply_preset()

    page.min_gap_slider.value = 8
    page._on_filter_change(None)

    assert page.preset_dropdown.value == "Custom"
    assert page._get_filters()["min_gap"] == 8


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
