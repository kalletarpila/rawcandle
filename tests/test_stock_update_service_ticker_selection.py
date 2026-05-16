import sqlite3

from services.stock_update_service import (
    StockUpdateTickerCandidate,
    filter_stock_update_candidates_by_market,
    load_grouped_stock_update_candidates,
    load_stock_update_candidates_for_market,
    resolve_stock_update_market,
)


def _create_osakedata_table(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT,
                pvm TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                market TEXT
            )
            """
        )
        conn.commit()


def test_resolve_stock_update_market_defaults_and_normalizes():
    assert resolve_stock_update_market(None) == "omxh"
    assert resolve_stock_update_market("") == "omxh"
    assert resolve_stock_update_market("   ") == "omxh"
    assert resolve_stock_update_market("USA") == "usa"
    assert resolve_stock_update_market(" omxh ") == "omxh"


def test_load_grouped_stock_update_candidates_returns_grouped_sql_rows(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("AAA", "2026-01-02", 1, 1, 1, 1, 10, "usa"),
                ("AAA", "2026-01-05", 1, 1, 1, 1, 10, "usa"),
                ("BBB", "2026-01-03", 1, 1, 1, 1, 10, "omxh"),
                ("CCC", "2026-01-01", 1, 1, 1, 1, 10, "usa"),
                ("CCC", "2026-01-07", 1, 1, 1, 1, 10, "usa"),
            ],
        )
        conn.commit()

    candidates = load_grouped_stock_update_candidates(str(db_path))

    assert [candidate.ticker for candidate in candidates] == ["AAA", "BBB", "CCC"]
    assert candidates[0].first_date == "2026-01-02"
    assert candidates[0].last_date == "2026-01-05"
    assert candidates[0].market == "usa"
    assert candidates[1].first_date == "2026-01-03"
    assert candidates[1].last_date == "2026-01-03"
    assert candidates[1].market == "omxh"
    assert candidates[2].first_date == "2026-01-01"
    assert candidates[2].last_date == "2026-01-07"
    assert candidates[2].market == "usa"


def test_filter_stock_update_candidates_by_market_matches_normalized_market_and_preserves_order():
    candidates = [
        StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-02", "usa"),
        StockUpdateTickerCandidate("BBB", "2026-01-01", "2026-01-02", " USA "),
        StockUpdateTickerCandidate("CCC", "2026-01-01", "2026-01-02", "UsA"),
        StockUpdateTickerCandidate("DDD", "2026-01-01", "2026-01-02", "omxh"),
    ]

    usa_candidates = filter_stock_update_candidates_by_market(candidates, "usa")
    omxh_candidates = filter_stock_update_candidates_by_market(candidates, "omxh")

    assert [candidate.ticker for candidate in usa_candidates] == ["AAA", "BBB", "CCC"]
    assert [candidate.ticker for candidate in omxh_candidates] == ["DDD"]
    assert candidates[1].market == " USA "
    assert candidates[2].market == "UsA"


def test_load_stock_update_candidates_for_market_uses_resolved_market(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("AAA", "2026-01-02", 1, 1, 1, 1, 10, "usa"),
                ("BBB", "2026-01-03", 1, 1, 1, 1, 10, "omxh"),
                ("CCC", "2026-01-04", 1, 1, 1, 1, 10, "usa"),
            ],
        )
        conn.commit()

    omxh_candidates = load_stock_update_candidates_for_market(str(db_path), None)
    usa_candidates = load_stock_update_candidates_for_market(str(db_path), "USA")

    assert [candidate.ticker for candidate in omxh_candidates] == ["BBB"]
    assert [candidate.ticker for candidate in usa_candidates] == ["AAA", "CCC"]
