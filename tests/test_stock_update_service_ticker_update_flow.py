from __future__ import annotations

import sqlite3

import pytest

from services.stock_update_service import (
    StockTickerUpdateFlowResult,
    StockUpdateDateRange,
    StockUpdateTickerCandidate,
    StockUpdateTickerPlan,
    execute_ticker_update_flow,
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


def test_execute_ticker_update_flow_skipped_plan_skips_everything(tmp_path) -> None:
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    stock = _GuardStock(exc=RuntimeError("history should not be called"))

    def _raise(*args, **kwargs):
        raise AssertionError("downstream should not be called")

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

    result = execute_ticker_update_flow(
        osakedata_db_path=str(db_path),
        stock=stock,
        plan=plan,
        market="usa",
        sync_splits=_raise,
        maybe_backfill_splits=_raise,
        calculate_divergences=_raise,
        run_candlestick_analysis=_raise,
    )

    assert result.skipped is True
    assert result.skip_reason == "already_current"
    assert result.ohlcv_result is None
    assert result.downstream_result is None
    assert stock.calls == []

    with sqlite3.connect(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM osakedata").fetchone()[0]
    assert count == 0


def test_execute_ticker_update_flow_empty_history_skips_downstream(tmp_path) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    empty_history = pd.DataFrame(
        {"Open": [], "High": [], "Low": [], "Close": [], "Volume": []},
        index=[],
    )
    stock = _GuardStock(results=[empty_history])

    def _raise(*args, **kwargs):
        raise AssertionError("downstream should not be called")

    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    result = execute_ticker_update_flow(
        osakedata_db_path=str(db_path),
        stock=stock,
        plan=plan,
        market="usa",
        sync_splits=_raise,
        maybe_backfill_splits=_raise,
        calculate_divergences=_raise,
        run_candlestick_analysis=_raise,
    )

    assert result.skipped is True
    assert result.skip_reason == "no_history_data"
    assert result.ohlcv_result is not None
    assert result.ohlcv_result.ohlcv_rows_converted == 0
    assert result.downstream_result is None


def test_execute_ticker_update_flow_runs_downstream_when_rows_inserted(tmp_path) -> None:
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
    calls = []

    def sync_splits(ticker: str, stock_obj: object) -> int:
        calls.append("split_sync")
        return 1

    def maybe_backfill_splits(ticker: str) -> bool:
        calls.append("backfill")
        return False

    def calculate_divergences(ticker: str, only_missing: bool) -> tuple:
        calls.append("divergence")
        return (True, 2, "")

    def run_candlestick_analysis(
        ticker: str,
        analysis_start: str,
        analysis_end: str,
    ) -> tuple:
        calls.append("candlestick")
        return (5, None)

    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    result = execute_ticker_update_flow(
        osakedata_db_path=str(db_path),
        stock=stock,
        plan=plan,
        market="usa",
        sync_splits=sync_splits,
        maybe_backfill_splits=maybe_backfill_splits,
        calculate_divergences=calculate_divergences,
        run_candlestick_analysis=run_candlestick_analysis,
    )

    assert result.skipped is False
    assert result.ohlcv_result is not None
    assert result.ohlcv_result.ohlcv_rows_converted > 0
    assert result.ohlcv_result.ohlcv_rows_inserted > 0
    assert result.downstream_result is not None
    assert calls == ["split_sync", "backfill", "divergence", "candlestick"]
    assert result.downstream_result.candlestick_attempted is True


def test_execute_ticker_update_flow_zero_insert_still_runs_downstream(tmp_path) -> None:
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
            "Open": [9.0],
            "High": [9.5],
            "Low": [8.5],
            "Close": [9.1],
            "Volume": [900],
        },
        index=pd.to_datetime(["2026-01-02"]),
    )
    stock = _GuardStock(results=[history])
    calls = []

    def sync_splits(ticker: str, stock_obj: object) -> int:
        calls.append("split_sync")
        return 0

    def maybe_backfill_splits(ticker: str) -> bool:
        calls.append("backfill")
        return False

    def calculate_divergences(ticker: str, only_missing: bool) -> tuple:
        calls.append("divergence")
        return (True, 1, "")

    def run_candlestick_analysis(
        ticker: str,
        analysis_start: str,
        analysis_end: str,
    ) -> tuple:
        calls.append("candlestick")
        raise AssertionError("candlestick should not be called")

    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    result = execute_ticker_update_flow(
        osakedata_db_path=str(db_path),
        stock=stock,
        plan=plan,
        market="usa",
        sync_splits=sync_splits,
        maybe_backfill_splits=maybe_backfill_splits,
        calculate_divergences=calculate_divergences,
        run_candlestick_analysis=run_candlestick_analysis,
    )

    assert result.skipped is False
    assert result.ohlcv_result is not None
    assert result.ohlcv_result.ohlcv_rows_converted > 0
    assert result.ohlcv_result.ohlcv_rows_inserted == 0
    assert result.downstream_result is not None
    assert calls == ["split_sync", "backfill", "divergence"]
    assert result.downstream_result.candlestick_attempted is False


def test_execute_ticker_update_flow_ohlcv_exception_propagates(tmp_path) -> None:
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)

    stock = _GuardStock(exc=RuntimeError("fetch failed"))
    downstream_calls = []

    def _record(*args, **kwargs):
        downstream_calls.append("called")
        return 0

    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    with pytest.raises(RuntimeError, match="fetch failed"):
        execute_ticker_update_flow(
            osakedata_db_path=str(db_path),
            stock=stock,
            plan=plan,
            market="usa",
            sync_splits=_record,
            maybe_backfill_splits=_record,
            calculate_divergences=_record,
            run_candlestick_analysis=_record,
        )

    assert downstream_calls == []


def test_execute_ticker_update_flow_downstream_backfill_exception_propagates(
    tmp_path,
) -> None:
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

    with pytest.raises(RuntimeError, match="backfill failed"):
        execute_ticker_update_flow(
            osakedata_db_path=str(db_path),
            stock=stock,
            plan=plan,
            market="usa",
            sync_splits=lambda ticker, stock_obj: 0,
            maybe_backfill_splits=lambda ticker: (_ for _ in ()).throw(
                RuntimeError("backfill failed")
            ),
            calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
            run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (
                0,
                None,
            ),
        )


def test_execute_ticker_update_flow_split_sync_warning_is_non_fatal(tmp_path) -> None:
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
    calls = []

    def sync_splits(ticker: str, stock_obj: object) -> int:
        calls.append("split_sync")
        raise RuntimeError("split failed")

    def maybe_backfill_splits(ticker: str) -> bool:
        calls.append("backfill")
        return False

    def calculate_divergences(ticker: str, only_missing: bool) -> tuple:
        calls.append("divergence")
        return (True, 1, "")

    def run_candlestick_analysis(
        ticker: str,
        analysis_start: str,
        analysis_end: str,
    ) -> tuple:
        calls.append("candlestick")
        return (2, None)

    plan = StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate("AAA", "2026-01-01", "2026-01-01", "omxh"),
        needs_update=True,
        update_start_date="2026-01-02",
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange("2026-01-02", "2026-01-10")],
    )

    result = execute_ticker_update_flow(
        osakedata_db_path=str(db_path),
        stock=stock,
        plan=plan,
        market="usa",
        sync_splits=sync_splits,
        maybe_backfill_splits=maybe_backfill_splits,
        calculate_divergences=calculate_divergences,
        run_candlestick_analysis=run_candlestick_analysis,
    )

    assert result.downstream_result is not None
    assert "split failed" in result.downstream_result.split_sync_warning
    assert result.downstream_result.warnings == [
        result.downstream_result.split_sync_warning
    ]
    assert calls == ["split_sync", "backfill", "divergence", "candlestick"]


def test_execute_ticker_update_flow_candlestick_warning_is_non_fatal(tmp_path) -> None:
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

    result = execute_ticker_update_flow(
        osakedata_db_path=str(db_path),
        stock=stock,
        plan=plan,
        market="usa",
        sync_splits=lambda ticker, stock_obj: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (
            (_ for _ in ()).throw(RuntimeError("candle failed"))
        ),
    )

    assert result.downstream_result is not None
    assert "candle failed" in result.downstream_result.candlestick_error
    assert any(
        "candle failed" in warning for warning in result.downstream_result.warnings
    )


def test_execute_ticker_update_flow_uses_market_argument_for_inserted_rows(
    tmp_path,
) -> None:
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

    execute_ticker_update_flow(
        osakedata_db_path=str(db_path),
        stock=stock,
        plan=plan,
        market="usa",
        sync_splits=lambda ticker, stock_obj: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (
            0,
            None,
        ),
    )

    with sqlite3.connect(db_path) as conn:
        market = conn.execute("SELECT market FROM osakedata").fetchone()[0]
    assert market == "usa"


def test_stock_ticker_update_flow_result_has_no_dow_fields() -> None:
    result = StockTickerUpdateFlowResult(ticker="AAA")

    assert not hasattr(result, "dow_summary")
    assert not hasattr(result, "dow_structures_updated")


def test_run_stock_data_update_raises_not_implemented_ticker_update_flow() -> None:
    with pytest.raises(NotImplementedError):
        run_stock_data_update(
            osakedata_db_path="osakedata.db",
            analysis_db_path="analysis.db",
        )
