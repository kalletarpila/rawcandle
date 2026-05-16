from __future__ import annotations

import sqlite3

import pytest

from services.stock_update_service import (
    StockUpdateBatchExecutionResult,
    StockUpdateDateRange,
    StockUpdateTickerCandidate,
    StockUpdateTickerPlan,
    execute_stock_update_batch,
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


def test_execute_stock_update_batch_preserves_order_and_checked_count(tmp_path) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    history_aaa = pd.DataFrame(
        {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
        index=pd.to_datetime(["2026-01-02"]),
    )
    history_bbb = pd.DataFrame(
        {"Open": [20.0], "High": [21.0], "Low": [19.5], "Close": [20.8], "Volume": [2]},
        index=pd.to_datetime(["2026-01-03"]),
    )

    stocks = {
        "AAA": _GuardStock(results=[history_aaa]),
        "BBB": _GuardStock(results=[history_bbb]),
    }
    factory_calls = []

    def stock_factory(ticker: str):
        factory_calls.append(ticker)
        return stocks[ticker]

    plans = [
        StockUpdateTickerPlan(
            candidate=StockUpdateTickerCandidate("SKIP", "2026-01-01", "2026-05-10", "omxh"),
            needs_update=False,
            date_ranges=[StockUpdateDateRange("2026-01-01", "2026-01-02")],
            skip_reason="already_current",
        ),
        StockUpdateTickerPlan(
            candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
            needs_update=True,
            update_start_date="2026-01-02",
            fetch_until_exclusive="2026-01-10",
            date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
        ),
        StockUpdateTickerPlan(
            candidate=StockUpdateTickerCandidate("BBB", "2026-01-01", "2026-01-01", "omxh"),
            needs_update=True,
            update_start_date="2026-01-03",
            fetch_until_exclusive="2026-01-10",
            date_ranges=[StockUpdateDateRange("2026-01-03", "2026-01-10")],
        ),
    ]

    result = execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=plans,
        stock_factory=stock_factory,
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
    )

    assert result.tickers_checked == 3
    assert [ticker_result.ticker for ticker_result in result.ticker_results] == [
        "SKIP",
        "AAA",
        "BBB",
    ]
    assert factory_calls == ["AAA", "BBB"]


def test_execute_stock_update_batch_skipped_plan_avoids_stock_factory(tmp_path) -> None:
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("SKIP", "2026-01-01", "2026-05-10", "omxh"),
        needs_update=False,
        date_ranges=[StockUpdateDateRange("2026-01-01", "2026-01-02")],
        skip_reason="already_current",
    )

    result = execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=[plan],
        stock_factory=lambda ticker: (_ for _ in ()).throw(
            AssertionError("stock_factory should not be called")
        ),
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
    )

    assert result.tickers_skipped == 1
    assert result.tickers_failed == 0
    assert result.ticker_results[0].skipped is True


def test_execute_stock_update_batch_successful_update_increments_updated(tmp_path) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    history = pd.DataFrame(
        {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
        index=pd.to_datetime(["2026-01-02"]),
    )
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    result = execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=[plan],
        stock_factory=lambda ticker: _GuardStock(results=[history]),
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
    )

    assert result.tickers_checked == 1
    assert result.tickers_updated == 1
    assert result.tickers_skipped == 0
    assert result.tickers_failed == 0
    assert result.ohlcv_rows_inserted == 1
    assert result.ticker_results[0].skipped is False


def test_execute_stock_update_batch_empty_history_counts_as_skipped(tmp_path) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    empty_history = pd.DataFrame(
        {"Open": [], "High": [], "Low": [], "Close": [], "Volume": []},
        index=[],
    )
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    result = execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=[plan],
        stock_factory=lambda ticker: _GuardStock(results=[empty_history]),
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
    )

    assert result.tickers_checked == 1
    assert result.tickers_skipped == 1
    assert result.tickers_updated == 0
    assert result.tickers_failed == 0
    assert result.ticker_results[0].skip_reason == "no_history_data"


def test_execute_stock_update_batch_zero_insert_still_counts_updated(tmp_path) -> None:
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
        {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
        index=pd.to_datetime(["2026-01-02"]),
    )
    calls = []
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    result = execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=[plan],
        stock_factory=lambda ticker: _GuardStock(results=[history]),
        sync_splits=lambda ticker, stock: calls.append("split_sync") or 0,
        maybe_backfill_splits=lambda ticker: calls.append("backfill") or False,
        calculate_divergences=lambda ticker, only_missing: calls.append("divergence")
        or (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: calls.append(
            "candlestick"
        )
        or (0, None),
    )

    assert result.tickers_updated == 1
    assert result.tickers_skipped == 0
    assert result.ohlcv_rows_inserted == 0
    assert calls == ["split_sync", "backfill", "divergence"]
    assert result.ticker_results[0].downstream_result.candlestick_attempted is False


def test_execute_stock_update_batch_factory_exception_increments_failed_and_continues(
    tmp_path,
) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    history = pd.DataFrame(
        {"Open": [20.0], "High": [21.0], "Low": [19.5], "Close": [20.8], "Volume": [2]},
        index=pd.to_datetime(["2026-01-03"]),
    )
    plan_fail = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("FAIL", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )
    plan_ok = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("OK", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-03",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-03", "2026-01-10")],
    )

    def stock_factory(ticker: str):
        if ticker == "FAIL":
            raise RuntimeError("factory failed")
        return _GuardStock(results=[history])

    result = execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=[plan_fail, plan_ok],
        stock_factory=stock_factory,
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
    )

    assert result.tickers_checked == 2
    assert result.tickers_failed == 1
    assert any("FAIL" in error and "factory failed" in error for error in result.errors)
    assert [ticker_result.ticker for ticker_result in result.ticker_results] == ["OK"]


def test_execute_stock_update_batch_ticker_flow_exception_increments_failed_and_continues(
    tmp_path,
) -> None:
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path, with_unique=False)

    class _BadHistory:
        empty = False

        def iterrows(self):
            yield "2026-01-02", {"Open": "", "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1}

    plan_fail = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("FAIL", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )
    plan_skip = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("SKIP", "2026-01-01", "2026-05-10", "omxh"),
        needs_update=False,
        date_ranges=[StockUpdateDateRange("2026-01-01", "2026-01-02")],
        skip_reason="already_current",
    )

    result = execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=[plan_fail, plan_skip],
        stock_factory=lambda ticker: _GuardStock(results=[_BadHistory()]),
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
    )

    assert result.tickers_failed == 1
    assert any("FAIL" in error for error in result.errors)
    assert [ticker_result.ticker for ticker_result in result.ticker_results] == ["SKIP"]


def test_execute_stock_update_batch_aggregates_split_warning(tmp_path) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    history = pd.DataFrame(
        {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
        index=pd.to_datetime(["2026-01-02"]),
    )
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    result = execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=[plan],
        stock_factory=lambda ticker: _GuardStock(results=[history]),
        sync_splits=lambda ticker, stock: (_ for _ in ()).throw(RuntimeError("split failed")),
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
    )

    assert any("split failed" in warning for warning in result.warnings)


def test_execute_stock_update_batch_backfill_exception_fails_ticker_but_continues(
    tmp_path,
) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    history_a = pd.DataFrame(
        {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
        index=pd.to_datetime(["2026-01-02"]),
    )
    history_b = pd.DataFrame(
        {"Open": [20.0], "High": [21.0], "Low": [19.5], "Close": [20.8], "Volume": [2]},
        index=pd.to_datetime(["2026-01-03"]),
    )
    plans = [
        StockUpdateTickerPlan(
            candidate=StockUpdateTickerCandidate("FAIL", "2026-01-01", "2026-01-01", "omxh"),
            needs_update=True,
            update_start_date="2026-01-02",
            fetch_until_exclusive="2026-01-10",
            date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
        ),
        StockUpdateTickerPlan(
            candidate=StockUpdateTickerCandidate("OK", "2026-01-01", "2026-01-01", "omxh"),
            needs_update=True,
            update_start_date="2026-01-03",
            fetch_until_exclusive="2026-01-10",
            date_ranges=[StockUpdateDateRange("2026-01-03", "2026-01-10")],
        ),
    ]

    def stock_factory(ticker: str):
        return _GuardStock(results=[history_a if ticker == "FAIL" else history_b])

    def maybe_backfill_splits(ticker: str):
        if ticker == "FAIL":
            raise RuntimeError("backfill failed")
        return False

    result = execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=plans,
        stock_factory=stock_factory,
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=maybe_backfill_splits,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
    )

    assert result.tickers_failed == 1
    assert any("FAIL" in error and "backfill failed" in error for error in result.errors)
    assert [ticker_result.ticker for ticker_result in result.ticker_results] == ["OK"]


def test_stock_update_batch_execution_result_has_no_dow_fields() -> None:
    result = StockUpdateBatchExecutionResult(market="usa")

    assert not hasattr(result, "dow_summary")
    assert not hasattr(result, "dow_structures_updated")

