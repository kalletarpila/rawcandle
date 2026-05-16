import sqlite3

import pytest

from services.stock_update_service import (
    StockUpdateDateRange,
    StockUpdateTickerCandidate,
    StockUpdateTickerPlan,
    execute_ticker_ohlcv_update_plan,
    run_stock_data_update,
)

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None


class _GuardStock:
    def __init__(self, exc=None, results=None):
        self.exc = exc
        self.results = list(results or [])
        self.calls = []

    def history(self, start=None, end=None):
        self.calls.append((start, end))
        if self.exc is not None:
            raise self.exc
        return self.results.pop(0)


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


def test_execute_ticker_ohlcv_update_plan_skipped_plan_does_not_call_history(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    stock = _GuardStock(exc=RuntimeError("history should not be called"))
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate(
            ticker="AAA",
            first_date="2026-01-01",
            last_date="2026-05-10",
            market="omxh",
        ),
        needs_update=False,
        date_ranges=[StockUpdateDateRange("2026-01-01", "2026-01-10")],
        skip_reason="already_current",
    )

    result = execute_ticker_ohlcv_update_plan(
        osakedata_db_path=str(db_path),
        stock=stock,
        plan=plan,
        market="usa",
    )

    assert result.skipped is True
    assert result.needs_update is False
    assert result.skip_reason == "already_current"
    assert result.ranges_requested == 0
    assert result.ranges_returned == 0
    assert result.history_objects_seen == 0
    assert result.ohlcv_rows_converted == 0
    assert result.ohlcv_rows_seen == 0
    assert result.ohlcv_rows_inserted == 0
    assert result.ohlcv_rows_skipped_existing == 0
    assert stock.calls == []

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM osakedata").fetchone()[0]
    assert count == 0


def test_execute_ticker_ohlcv_update_plan_fetches_converts_and_inserts_rows(tmp_path):
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    history = pd.DataFrame(
        {
            "Open": [10.0, 11.0],
            "High": [11.0, 12.0],
            "Low": [9.5, 10.5],
            "Close": [10.8, 11.8],
            "Volume": [200000, 210000],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )
    stock = _GuardStock(results=[history])
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    result = execute_ticker_ohlcv_update_plan(
        osakedata_db_path=str(db_path),
        stock=stock,
        plan=plan,
        market="usa",
    )

    assert result.ranges_requested == 1
    assert result.ranges_returned == 1
    assert result.history_objects_seen == 1
    assert result.ohlcv_rows_converted == 2
    assert result.ohlcv_rows_seen == 2
    assert result.ohlcv_rows_inserted == 2
    assert result.ohlcv_rows_skipped_existing == 0

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT osake, pvm, open, high, low, close, volume, market
            FROM osakedata
            ORDER BY pvm
            """
        ).fetchall()
    assert rows == [
        ("AAA", "2026-01-02", 10.0, 11.0, 9.5, 10.8, 200000, "usa"),
        ("AAA", "2026-01-03", 11.0, 12.0, 10.5, 11.8, 210000, "usa"),
    ]


def test_execute_ticker_ohlcv_update_plan_skips_existing_db_dates(tmp_path):
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAA", "2026-01-02", 1.0, 2.0, 0.5, 1.5, 100, "omxh"),
        )
        conn.commit()

    history = pd.DataFrame(
        {
            "Open": [9.0, 11.0],
            "High": [9.5, 12.0],
            "Low": [8.5, 10.5],
            "Close": [9.1, 11.8],
            "Volume": [900, 210000],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )
    stock = _GuardStock(results=[history])
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    result = execute_ticker_ohlcv_update_plan(
        osakedata_db_path=str(db_path),
        stock=stock,
        plan=plan,
        market="usa",
    )

    assert result.ohlcv_rows_converted == 2
    assert result.ohlcv_rows_seen == 2
    assert result.ohlcv_rows_inserted == 1
    assert result.ohlcv_rows_skipped_existing == 1

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT osake, pvm, open, high, low, close, volume, market
            FROM osakedata
            ORDER BY pvm
            """
        ).fetchall()
    assert rows == [
        ("AAA", "2026-01-02", 1.0, 2.0, 0.5, 1.5, 100, "omxh"),
        ("AAA", "2026-01-03", 11.0, 12.0, 10.5, 11.8, 210000, "usa"),
    ]


def test_execute_ticker_ohlcv_update_plan_empty_histories_lead_to_zero_rows(tmp_path):
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    empty_history = pd.DataFrame(
        {"Open": [], "High": [], "Low": [], "Close": [], "Volume": []},
        index=[],
    )
    stock = _GuardStock(results=[empty_history])
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    result = execute_ticker_ohlcv_update_plan(
        osakedata_db_path=str(db_path),
        stock=stock,
        plan=plan,
        market="usa",
    )

    assert result.ranges_requested == 1
    assert result.ranges_returned == 1
    assert result.history_objects_seen == 1
    assert result.ohlcv_rows_converted == 0
    assert result.ohlcv_rows_seen == 0
    assert result.ohlcv_rows_inserted == 0


def test_execute_ticker_ohlcv_update_plan_propagates_history_exception(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    stock = _GuardStock(exc=RuntimeError("boom"))
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    with pytest.raises(RuntimeError, match="boom"):
        execute_ticker_ohlcv_update_plan(
            osakedata_db_path=str(db_path),
            stock=stock,
            plan=plan,
            market="usa",
        )


def test_execute_ticker_ohlcv_update_plan_propagates_conversion_exception(tmp_path):
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    history = pd.DataFrame(
        {
            "Open": ["bad"],
            "High": [11.0],
            "Low": [9.5],
            "Close": [10.8],
            "Volume": [200000],
        },
        index=pd.to_datetime(["2026-01-02"]),
    )
    stock = _GuardStock(results=[history])
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    with pytest.raises(Exception):
        execute_ticker_ohlcv_update_plan(
            osakedata_db_path=str(db_path),
            stock=stock,
            plan=plan,
            market="usa",
        )


def test_execute_ticker_ohlcv_update_plan_propagates_sqlite_exception(tmp_path):
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE osakedata (osake TEXT)")
        conn.commit()

    history = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [11.0],
            "Low": [9.5],
            "Close": [10.8],
            "Volume": [200000],
        },
        index=pd.to_datetime(["2026-01-02"]),
    )
    stock = _GuardStock(results=[history])
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    with pytest.raises(sqlite3.Error):
        execute_ticker_ohlcv_update_plan(
            osakedata_db_path=str(db_path),
            stock=stock,
            plan=plan,
            market="usa",
        )


def test_execute_ticker_ohlcv_update_plan_passes_market_argument_through(tmp_path):
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    history = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [11.0],
            "Low": [9.5],
            "Close": [10.8],
            "Volume": [200000],
        },
        index=pd.to_datetime(["2026-01-02"]),
    )
    stock = _GuardStock(results=[history])
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    execute_ticker_ohlcv_update_plan(
        osakedata_db_path=str(db_path),
        stock=stock,
        plan=plan,
        market=" USA ",
    )

    with sqlite3.connect(db_path) as conn:
        market = conn.execute("SELECT market FROM osakedata").fetchone()[0]
    assert market == " USA "


def test_execute_ticker_ohlcv_update_plan_skipped_plan_ignores_date_ranges_and_market(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    stock = _GuardStock(exc=RuntimeError("history should not be called"))
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate(
            ticker="AAA",
            first_date="2026-01-01",
            last_date="2026-05-10",
            market="omxh",
        ),
        needs_update=False,
        date_ranges=[StockUpdateDateRange("2026-01-01", "2026-01-10")],
        skip_reason="already_current",
    )

    result = execute_ticker_ohlcv_update_plan(
        osakedata_db_path=str(db_path),
        stock=stock,
        plan=plan,
        market="usa",
    )

    assert result.skipped is True
    assert result.skip_reason == "already_current"
    assert stock.calls == []
    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM osakedata").fetchone()[0]
    assert count == 0


def test_execute_ticker_ohlcv_update_plan_uses_market_argument_not_candidate_market(tmp_path):
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    history = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [11.0],
            "Low": [9.5],
            "Close": [10.8],
            "Volume": [200000],
        },
        index=pd.to_datetime(["2026-01-02"]),
    )
    stock = _GuardStock(results=[history])
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    execute_ticker_ohlcv_update_plan(
        osakedata_db_path=str(db_path),
        stock=stock,
        plan=plan,
        market="usa",
    )

    with sqlite3.connect(db_path) as conn:
        market = conn.execute("SELECT market FROM osakedata").fetchone()[0]
    assert market == "usa"


def test_run_stock_data_update_still_raises_not_implemented():
    with pytest.raises(NotImplementedError, match="run_stock_data_update is not implemented yet"):
        run_stock_data_update(
            osakedata_db_path="data/osakedata.db",
            analysis_db_path="data/analysis.db",
        )
