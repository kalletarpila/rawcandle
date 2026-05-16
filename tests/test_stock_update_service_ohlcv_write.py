import sqlite3

import pytest

from services.stock_update_service import (
    StockOhlcvRow,
    insert_missing_ohlcv_rows,
    load_existing_ohlcv_dates_for_ticker,
    run_stock_data_update,
)


def _create_osakedata_table(db_path, with_unique=True):
    unique_clause = ", UNIQUE(osake, pvm)" if with_unique else ""
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            f"""
            CREATE TABLE osakedata (
                osake TEXT,
                pvm TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                market TEXT
                {unique_clause}
            )
            """
        )
        conn.commit()


def test_load_existing_ohlcv_dates_for_ticker_returns_only_selected_ticker_dates(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    assert load_existing_ohlcv_dates_for_ticker(
        osakedata_db_path=str(db_path),
        ticker="AAA",
    ) == set()

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("AAA", "2026-01-02", 1.0, 2.0, 0.5, 1.5, 100, "usa"),
                ("AAA", "2026-01-05", 1.1, 2.1, 0.6, 1.6, 110, "usa"),
                ("BBB", "2026-01-03", 3.0, 4.0, 2.5, 3.5, 200, "omxh"),
            ],
        )
        conn.commit()

    assert load_existing_ohlcv_dates_for_ticker(
        osakedata_db_path=str(db_path),
        ticker="AAA",
    ) == {"2026-01-02", "2026-01-05"}


def test_insert_missing_ohlcv_rows_inserts_new_rows(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    rows = [
        StockOhlcvRow("AAA", "2026-01-02", 1.0, 2.0, 0.5, 1.5, 100, "usa"),
        StockOhlcvRow("AAA", "2026-01-03", 1.1, 2.1, 0.6, 1.6, 110, "usa"),
    ]

    result = insert_missing_ohlcv_rows(
        osakedata_db_path=str(db_path),
        ticker="AAA",
        rows=rows,
    )

    assert result.rows_seen == 2
    assert result.rows_inserted == 2
    assert result.rows_skipped_existing == 0

    with sqlite3.connect(db_path) as conn:
        inserted_rows = conn.execute(
            """
            SELECT osake, pvm, open, high, low, close, volume, market
            FROM osakedata
            ORDER BY pvm
            """
        ).fetchall()

    assert inserted_rows == [
        ("AAA", "2026-01-02", 1.0, 2.0, 0.5, 1.5, 100, "usa"),
        ("AAA", "2026-01-03", 1.1, 2.1, 0.6, 1.6, 110, "usa"),
    ]


def test_insert_missing_ohlcv_rows_skips_existing_db_dates(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAA", "2026-01-02", 1.0, 2.0, 0.5, 1.5, 100, "usa"),
        )
        conn.commit()

    rows = [
        StockOhlcvRow("AAA", "2026-01-02", 9.0, 9.0, 9.0, 9.0, 999, "usa"),
        StockOhlcvRow("AAA", "2026-01-03", 1.1, 2.1, 0.6, 1.6, 110, "usa"),
    ]

    result = insert_missing_ohlcv_rows(
        osakedata_db_path=str(db_path),
        ticker="AAA",
        rows=rows,
    )

    assert result.rows_seen == 2
    assert result.rows_inserted == 1
    assert result.rows_skipped_existing == 1

    with sqlite3.connect(db_path) as conn:
        inserted_rows = conn.execute(
            """
            SELECT osake, pvm, open, high, low, close, volume, market
            FROM osakedata
            ORDER BY pvm
            """
        ).fetchall()

    assert inserted_rows == [
        ("AAA", "2026-01-02", 1.0, 2.0, 0.5, 1.5, 100, "usa"),
        ("AAA", "2026-01-03", 1.1, 2.1, 0.6, 1.6, 110, "usa"),
    ]


def test_insert_missing_ohlcv_rows_skips_duplicate_dates_inside_input_batch(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    rows = [
        StockOhlcvRow("AAA", "2026-01-02", 1.0, 2.0, 0.5, 1.5, 100, "usa"),
        StockOhlcvRow("AAA", "2026-01-02", 9.0, 9.0, 9.0, 9.0, 999, "usa"),
    ]

    result = insert_missing_ohlcv_rows(
        osakedata_db_path=str(db_path),
        ticker="AAA",
        rows=rows,
    )

    assert result.rows_seen == 2
    assert result.rows_inserted == 1
    assert result.rows_skipped_existing == 1

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT osake, pvm, open, high, low, close, volume, market
            FROM osakedata
            """
        ).fetchone()

    assert row == ("AAA", "2026-01-02", 1.0, 2.0, 0.5, 1.5, 100, "usa")


def test_insert_missing_ohlcv_rows_preserves_input_order_for_inserts(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    rows = [
        StockOhlcvRow("AAA", "2026-01-02", 1.0, 2.0, 0.5, 1.5, 100, "usa"),
        StockOhlcvRow("AAA", "2026-01-03", 1.1, 2.1, 0.6, 1.6, 110, "usa"),
        StockOhlcvRow("AAA", "2026-01-04", 1.2, 2.2, 0.7, 1.7, 120, "usa"),
    ]

    insert_missing_ohlcv_rows(
        osakedata_db_path=str(db_path),
        ticker="AAA",
        rows=rows,
    )

    with sqlite3.connect(db_path) as conn:
        dates = [
            row[0]
            for row in conn.execute(
                "SELECT pvm FROM osakedata WHERE osake = ? ORDER BY pvm",
                ("AAA",),
            ).fetchall()
        ]

    assert dates == ["2026-01-02", "2026-01-03", "2026-01-04"]


def test_insert_missing_ohlcv_rows_propagates_sqlite_errors(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE osakedata")
        conn.commit()

    with pytest.raises(sqlite3.Error):
        insert_missing_ohlcv_rows(
            osakedata_db_path=str(db_path),
            ticker="AAA",
            rows=[StockOhlcvRow("AAA", "2026-01-02", 1.0, 2.0, 0.5, 1.5, 100, "usa")],
        )


def test_run_stock_data_update_still_raises_not_implemented():
    with pytest.raises(
        NotImplementedError,
        match="run_stock_data_update is not implemented yet",
    ):
        run_stock_data_update(
            osakedata_db_path="data/osakedata.db",
            analysis_db_path="data/analysis.db",
        )
