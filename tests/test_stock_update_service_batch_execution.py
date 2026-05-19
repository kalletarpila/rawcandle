from __future__ import annotations

import sqlite3

import pytest
import main

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


class _QuarterStock(_GuardStock):
    def __init__(self, *, quarterly_income_stmt, exc=None, results=None):
        super().__init__(exc=exc, results=results)
        self.quarterly_income_stmt = quarterly_income_stmt


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


def _create_quarter_state_db(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE rc_fundamental_quarter_state (
                ticker TEXT NOT NULL,
                market TEXT NOT NULL,
                primary_source TEXT,
                latest_db_period_end_date TEXT,
                detected_source_period_end_date TEXT,
                new_quarter_available INTEGER NOT NULL DEFAULT 0,
                last_checked_at_utc TEXT,
                last_updated_at_utc TEXT,
                last_detection_run_id TEXT,
                last_ingest_run_id TEXT,
                PRIMARY KEY (ticker)
            )
            """
        )
        conn.commit()


def _fetch_quarter_state_row(db_path, ticker):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            """
            SELECT ticker,
                   market,
                   primary_source,
                   latest_db_period_end_date,
                   detected_source_period_end_date,
                   new_quarter_available
            FROM rc_fundamental_quarter_state
            WHERE ticker = ?
            """,
            (ticker,),
        ).fetchone()


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


def test_execute_stock_update_batch_skipped_plan_uses_short_terminal_sleep(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    sleep_calls = []

    monkeypatch.setattr(
        "services.stock_update_service.time.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("SKIP", "2026-01-01", "2026-05-10", "omxh"),
        needs_update=False,
        date_ranges=[StockUpdateDateRange("2026-01-01", "2026-01-02")],
        skip_reason="already_current",
    )

    execute_stock_update_batch(
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

    assert sleep_calls == [0.5]


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


def test_execute_stock_update_batch_successful_large_insert_uses_1s_terminal_sleep(
    tmp_path, monkeypatch
) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    sleep_calls = []

    monkeypatch.setattr(
        "services.stock_update_service.time.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

    history = pd.DataFrame(
        {
            "Open": [10.0] * 50,
            "High": [11.0] * 50,
            "Low": [9.5] * 50,
            "Close": [10.8] * 50,
            "Volume": [1] * 50,
        },
        index=pd.date_range("2026-01-01", periods=50, freq="D"),
    )
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2025-12-31", "2025-12-31", "omxh"),
        needs_update=True,
        update_start_date="2026-01-01",
        fetch_until_exclusive="2026-03-01",
        date_ranges=[StockUpdateDateRange("2026-01-01", "2026-03-01")],
    )

    execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=[plan],
        stock_factory=lambda ticker: _GuardStock(results=[history]),
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
    )

    assert sleep_calls == [0.5, 1.0]


def test_execute_stock_update_batch_successful_small_insert_uses_1_5s_terminal_sleep(
    tmp_path, monkeypatch
) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    sleep_calls = []

    monkeypatch.setattr(
        "services.stock_update_service.time.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

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

    execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=[plan],
        stock_factory=lambda ticker: _GuardStock(results=[history]),
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
    )

    assert sleep_calls == [0.5, 1.5]


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


def test_execute_stock_update_batch_empty_history_uses_short_terminal_sleep(
    tmp_path, monkeypatch
) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    sleep_calls = []

    monkeypatch.setattr(
        "services.stock_update_service.time.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

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

    execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=[plan],
        stock_factory=lambda ticker: _GuardStock(results=[empty_history]),
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
    )

    assert sleep_calls == [0.5, 0.5]


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


def test_execute_stock_update_batch_exception_uses_short_terminal_sleep(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    sleep_calls = []

    monkeypatch.setattr(
        "services.stock_update_service.time.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("FAIL", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    result = execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=[plan],
        stock_factory=lambda ticker: (_ for _ in ()).throw(RuntimeError("factory failed")),
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
    )

    assert result.tickers_failed == 1
    assert any("factory failed" in error for error in result.errors)
    assert sleep_calls == [0.5]


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


def test_execute_stock_update_batch_sleeps_30s_after_500_processed_tickers(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    sleep_calls = []

    monkeypatch.setattr(
        "services.stock_update_service.time.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

    plans = [
        StockUpdateTickerPlan(
            candidate=StockUpdateTickerCandidate(f"SKIP{i}", "2026-01-01", "2026-05-10", "omxh"),
            needs_update=False,
            date_ranges=[StockUpdateDateRange("2026-01-01", "2026-01-02")],
            skip_reason="already_current",
        )
        for i in range(500)
    ]

    result = execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=plans,
        stock_factory=lambda ticker: (_ for _ in ()).throw(
            AssertionError("stock_factory should not be called")
        ),
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
    )

    assert result.tickers_checked == 500
    assert len(sleep_calls) == 501
    assert sleep_calls.count(0.5) == 500
    assert sleep_calls[-1] == 30.0


def test_fetch_history_for_date_ranges_sleeps_after_each_range_call(
    tmp_path, monkeypatch
) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    sleep_calls = []

    monkeypatch.setattr(
        "services.stock_update_service.time.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )

    history_a = pd.DataFrame(
        {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
        index=pd.to_datetime(["2026-01-02"]),
    )
    history_b = pd.DataFrame(
        {"Open": [20.0], "High": [21.0], "Low": [19.5], "Close": [20.8], "Volume": [2]},
        index=pd.to_datetime(["2026-01-03"]),
    )
    stock = _GuardStock(results=[history_a, history_b])
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[
            StockUpdateDateRange("2026-01-02", "2026-01-03"),
            StockUpdateDateRange("2026-01-03", "2026-01-10"),
        ],
    )

    execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=[plan],
        stock_factory=lambda ticker: stock,
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
    )

    assert stock.calls == [("2026-01-02", "2026-01-03"), ("2026-01-03", "2026-01-10")]
    assert sleep_calls == [0.5, 0.5, 1.5]


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


def test_execute_stock_update_batch_sets_new_quarter_available_when_yahoo_is_newer(
    tmp_path,
) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    quarter_db = tmp_path / "fundamentals_usa.db"
    _create_osakedata_table(db_path)
    _create_quarter_state_db(quarter_db)
    with sqlite3.connect(quarter_db) as conn:
        conn.execute(
            """
            INSERT INTO rc_fundamental_quarter_state (
                ticker, market, primary_source, latest_db_period_end_date,
                detected_source_period_end_date, new_quarter_available
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("AAA", "usa", "sec_edgar", "2025-12-31", None, 0),
        )
        conn.commit()

    history = pd.DataFrame(
        {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
        index=pd.to_datetime(["2026-01-02"]),
    )
    quarterly_income_stmt = pd.DataFrame(
        [[1.0]],
        columns=pd.to_datetime(["2026-03-31"]),
    )
    stock = _QuarterStock(quarterly_income_stmt=quarterly_income_stmt, results=[history])
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.fundamentals_usa_db_path = str(quarter_db)
    app._maybe_backfill_splits_for_ticker = lambda ticker: False
    app._calculate_and_save_divergences = lambda ticker, only_missing=True: (True, 0, "")
    app._run_incremental_candlestick_analysis = (
        lambda ticker, analysis_start, analysis_end: (0, None)
    )
    adapters = app._build_stock_update_service_adapters()
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "usa"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="usa",
        plans=[plan],
        stock_factory=lambda ticker: stock,
        sync_splits=adapters["sync_splits"],
        maybe_backfill_splits=adapters["maybe_backfill_splits"],
        calculate_divergences=adapters["calculate_divergences"],
        run_candlestick_analysis=adapters["run_candlestick_analysis"],
        maybe_update_quarter_state=adapters["maybe_update_quarter_state"],
    )

    row = _fetch_quarter_state_row(quarter_db, "AAA")
    assert row[3] == "2025-12-31"
    assert row[4] == "2026-03-31"
    assert row[5] == 1


def test_execute_stock_update_batch_does_not_raise_quarter_flag_when_yahoo_same_or_older(
    tmp_path,
) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    quarter_db = tmp_path / "fundamentals_usa.db"
    _create_osakedata_table(db_path)
    _create_quarter_state_db(quarter_db)

    def run_case(ticker, latest_db_period_end_date, yahoo_period_end_date):
        with sqlite3.connect(quarter_db) as conn:
            conn.execute("DELETE FROM rc_fundamental_quarter_state")
            conn.execute(
                """
                INSERT INTO rc_fundamental_quarter_state (
                    ticker, market, primary_source, latest_db_period_end_date,
                    detected_source_period_end_date, new_quarter_available
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ticker, "usa", "sec_edgar", latest_db_period_end_date, None, 0),
            )
            conn.commit()

        history = pd.DataFrame(
            {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
            index=pd.to_datetime(["2026-01-02"]),
        )
        quarterly_income_stmt = pd.DataFrame(
            [[1.0]],
            columns=pd.to_datetime([yahoo_period_end_date]),
        )
        stock = _QuarterStock(quarterly_income_stmt=quarterly_income_stmt, results=[history])
        app = main.RawCandleApp.__new__(main.RawCandleApp)
        app.fundamentals_usa_db_path = str(quarter_db)
        app._maybe_backfill_splits_for_ticker = lambda ticker: False
        app._calculate_and_save_divergences = lambda ticker, only_missing=True: (
            True,
            0,
            "",
        )
        app._run_incremental_candlestick_analysis = (
            lambda ticker, analysis_start, analysis_end: (0, None)
        )
        adapters = app._build_stock_update_service_adapters()
        plan = StockUpdateTickerPlan(
            candidate=StockUpdateTickerCandidate(ticker, "2026-01-01", "2026-01-01", "usa"),
            needs_update=True,
            update_start_date="2026-01-02",
            fetch_until_exclusive="2026-01-10",
            date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
        )

        execute_stock_update_batch(
            osakedata_db_path=str(db_path),
            market="usa",
            plans=[plan],
            stock_factory=lambda _: stock,
            sync_splits=adapters["sync_splits"],
            maybe_backfill_splits=adapters["maybe_backfill_splits"],
            calculate_divergences=adapters["calculate_divergences"],
            run_candlestick_analysis=adapters["run_candlestick_analysis"],
            maybe_update_quarter_state=adapters["maybe_update_quarter_state"],
        )

        return _fetch_quarter_state_row(quarter_db, ticker)

    same_row = run_case("SAME", "2026-03-31", "2026-03-31")
    older_row = run_case("OLDER", "2026-06-30", "2026-03-31")

    assert same_row[4] is None
    assert same_row[5] == 0
    assert older_row[4] is None
    assert older_row[5] == 0


def test_execute_stock_update_batch_quarter_detection_empty_or_error_does_not_crash(
    tmp_path,
) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    quarter_db = tmp_path / "fundamentals_usa.db"
    _create_osakedata_table(db_path)
    _create_quarter_state_db(quarter_db)

    def run_case(ticker, stock):
        with sqlite3.connect(quarter_db) as conn:
            conn.execute("DELETE FROM rc_fundamental_quarter_state")
            conn.execute(
                """
                INSERT INTO rc_fundamental_quarter_state (
                    ticker, market, primary_source, latest_db_period_end_date,
                    detected_source_period_end_date, new_quarter_available
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ticker, "usa", "sec_edgar", "2025-12-31", None, 0),
            )
            conn.commit()

        app = main.RawCandleApp.__new__(main.RawCandleApp)
        app.fundamentals_usa_db_path = str(quarter_db)
        app._maybe_backfill_splits_for_ticker = lambda ticker: False
        app._calculate_and_save_divergences = lambda ticker, only_missing=True: (
            True,
            0,
            "",
        )
        app._run_incremental_candlestick_analysis = (
            lambda ticker, analysis_start, analysis_end: (0, None)
        )
        adapters = app._build_stock_update_service_adapters()
        plan = StockUpdateTickerPlan(
            candidate=StockUpdateTickerCandidate(ticker, "2026-01-01", "2026-01-01", "usa"),
            needs_update=True,
            update_start_date="2026-01-02",
            fetch_until_exclusive="2026-01-10",
            date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
        )

        result = execute_stock_update_batch(
            osakedata_db_path=str(db_path),
            market="usa",
            plans=[plan],
            stock_factory=lambda _: stock,
            sync_splits=adapters["sync_splits"],
            maybe_backfill_splits=adapters["maybe_backfill_splits"],
            calculate_divergences=adapters["calculate_divergences"],
            run_candlestick_analysis=adapters["run_candlestick_analysis"],
            maybe_update_quarter_state=adapters["maybe_update_quarter_state"],
        )
        return result, _fetch_quarter_state_row(quarter_db, ticker)

    good_history = pd.DataFrame(
        {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
        index=pd.to_datetime(["2026-01-02"]),
    )
    empty_stock = _QuarterStock(quarterly_income_stmt=pd.DataFrame(), results=[good_history])

    class _QuarterlyRaiseStock(_GuardStock):
        @property
        def quarterly_income_stmt(self):
            raise RuntimeError("quarter lookup failed")

    error_stock = _QuarterlyRaiseStock(results=[good_history])

    empty_result, empty_row = run_case("EMPTY", empty_stock)
    error_result, error_row = run_case("ERROR", error_stock)

    assert empty_result.tickers_updated == 1
    assert empty_row[4] is None
    assert empty_row[5] == 0
    assert error_result.tickers_updated == 1
    assert error_row[4] is None
    assert error_row[5] == 0


def test_execute_stock_update_batch_quarter_detection_skips_cleanly_when_db_unavailable(
    tmp_path,
) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    history = pd.DataFrame(
        {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
        index=pd.to_datetime(["2026-01-02"]),
    )
    quarterly_income_stmt = pd.DataFrame(
        [[1.0]],
        columns=pd.to_datetime(["2026-03-31"]),
    )
    stock = _QuarterStock(quarterly_income_stmt=quarterly_income_stmt, results=[history])
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app._maybe_backfill_splits_for_ticker = lambda ticker: False
    app._calculate_and_save_divergences = lambda ticker, only_missing=True: (True, 0, "")
    app._run_incremental_candlestick_analysis = (
        lambda ticker, analysis_start, analysis_end: (0, None)
    )
    adapters = app._build_stock_update_service_adapters()
    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxs"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    result = execute_stock_update_batch(
        osakedata_db_path=str(db_path),
        market="omxs",
        plans=[plan],
        stock_factory=lambda ticker: stock,
        sync_splits=adapters["sync_splits"],
        maybe_backfill_splits=adapters["maybe_backfill_splits"],
        calculate_divergences=adapters["calculate_divergences"],
        run_candlestick_analysis=adapters["run_candlestick_analysis"],
        maybe_update_quarter_state=adapters["maybe_update_quarter_state"],
    )

    assert result.tickers_updated == 1
    assert result.tickers_failed == 0


def test_stock_update_batch_execution_result_has_no_dow_fields() -> None:
    result = StockUpdateBatchExecutionResult(market="usa")

    assert not hasattr(result, "dow_summary")
    assert not hasattr(result, "dow_structures_updated")
