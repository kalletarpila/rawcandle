from __future__ import annotations

import sqlite3

import pytest

from services.stock_update_service import (
    execute_stock_update_orchestration,
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


def _make_plan(ticker: str, last_date: str = "2026-01-01", skip: bool = False):
    from services.stock_update_service import (
        StockUpdateDateRange,
        StockUpdateTickerCandidate,
        StockUpdateTickerPlan,
    )

    if skip:
        return StockUpdateTickerPlan(
            candidate=StockUpdateTickerCandidate(ticker, "2026-01-01", "2026-05-10", "omxh"),
            needs_update=False,
            date_ranges=[StockUpdateDateRange("2026-01-01", "2026-01-02")],
            skip_reason="already_current",
        )
    start = "2026-01-02" if last_date == "2026-01-01" else "2026-01-03"
    return StockUpdateTickerPlan(
        candidate=StockUpdateTickerCandidate(ticker, "2026-01-01", last_date, "omxh"),
        needs_update=True,
        update_start_date=start,
        fetch_until_exclusive="2026-01-10",
        date_ranges=[StockUpdateDateRange(start, "2026-01-10")],
    )


def test_execute_stock_update_orchestration_runs_batch_then_dow(tmp_path) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    order = []
    history = pd.DataFrame(
        {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
        index=pd.to_datetime(["2026-01-02"]),
    )

    def stock_factory(ticker: str):
        order.append("stock_factory")
        return _GuardStock(results=[history])

    def sync_splits(ticker: str, stock) -> int:
        order.append("split_sync")
        return 0

    def maybe_backfill_splits(ticker: str) -> bool:
        order.append("backfill")
        return False

    def calculate_divergences(ticker: str, only_missing: bool):
        order.append("divergence")
        return (True, 1, "")

    def run_candlestick_analysis(ticker: str, analysis_start: str, analysis_end: str):
        order.append("candlestick")
        return (0, None)

    def calculate_dow_structures(**kwargs):
        order.append("dow")
        return {"status": "OK"}

    result = execute_stock_update_orchestration(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="usa",
        plans=[_make_plan("AAA")],
        stock_factory=stock_factory,
        sync_splits=sync_splits,
        maybe_backfill_splits=maybe_backfill_splits,
        calculate_divergences=calculate_divergences,
        run_candlestick_analysis=run_candlestick_analysis,
        maybe_update_quarter_state=lambda ticker, market, stock: None,
        calculate_dow_structures=calculate_dow_structures,
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert order == ["stock_factory", "split_sync", "backfill", "divergence", "candlestick", "dow"]
    assert result.batch_result is not None
    assert result.dow_result is not None
    assert result.dow_result.success is True


def test_execute_stock_update_orchestration_calls_dow_even_when_ticker_failed(tmp_path) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    dow_calls = []
    history = pd.DataFrame(
        {"Open": [20.0], "High": [21.0], "Low": [19.5], "Close": [20.8], "Volume": [2]},
        index=pd.to_datetime(["2026-01-03"]),
    )

    def stock_factory(ticker: str):
        if ticker == "FAIL":
            raise RuntimeError("factory failed")
        return _GuardStock(results=[history])

    def calculate_dow_structures(**kwargs):
        dow_calls.append(kwargs)
        return {"status": "OK"}

    result = execute_stock_update_orchestration(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="usa",
        plans=[_make_plan("FAIL"), _make_plan("OK", last_date="2026-01-02")],
        stock_factory=stock_factory,
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        maybe_update_quarter_state=lambda ticker, market, stock: None,
        calculate_dow_structures=calculate_dow_structures,
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert result.batch_result.tickers_failed == 1
    assert dow_calls
    assert result.dow_result.attempted is True


def test_execute_stock_update_orchestration_aggregates_dow_warning_not_error(tmp_path) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    history = pd.DataFrame(
        {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
        index=pd.to_datetime(["2026-01-02"]),
    )

    result = execute_stock_update_orchestration(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="usa",
        plans=[_make_plan("AAA")],
        stock_factory=lambda ticker: _GuardStock(results=[history]),
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        maybe_update_quarter_state=lambda ticker, market, stock: None,
        calculate_dow_structures=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("dow failed")),
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert result.dow_result.success is False
    assert "dow failed" in result.dow_result.warning
    assert result.dow_result.warning in result.warnings
    assert result.dow_result.warning not in result.errors


def test_execute_stock_update_orchestration_batch_warnings_precede_dow_warning(tmp_path) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    history = pd.DataFrame(
        {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
        index=pd.to_datetime(["2026-01-02"]),
    )

    result = execute_stock_update_orchestration(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="usa",
        plans=[_make_plan("AAA")],
        stock_factory=lambda ticker: _GuardStock(results=[history]),
        sync_splits=lambda ticker, stock: (_ for _ in ()).throw(RuntimeError("split failed")),
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        maybe_update_quarter_state=lambda ticker, market, stock: None,
        calculate_dow_structures=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("dow failed")),
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert "split failed" in result.warnings[0]
    assert "dow failed" in result.warnings[-1]


def test_execute_stock_update_orchestration_preserves_batch_errors(tmp_path) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    history = pd.DataFrame(
        {"Open": [20.0], "High": [21.0], "Low": [19.5], "Close": [20.8], "Volume": [2]},
        index=pd.to_datetime(["2026-01-03"]),
    )

    def stock_factory(ticker: str):
        if ticker == "FAIL":
            raise RuntimeError("factory failed")
        return _GuardStock(results=[history])

    result = execute_stock_update_orchestration(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="usa",
        plans=[_make_plan("FAIL"), _make_plan("OK", last_date="2026-01-02")],
        stock_factory=stock_factory,
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        maybe_update_quarter_state=lambda ticker, market, stock: None,
        calculate_dow_structures=lambda **kwargs: {"status": "OK"},
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert result.errors == result.batch_result.errors
    assert result.dow_result.success is True


def test_execute_stock_update_orchestration_forwards_dow_kwargs(tmp_path) -> None:
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    history = pd.DataFrame(
        {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
        index=pd.to_datetime(["2026-01-02"]),
    )
    calls = {}

    def calculate_dow_structures(**kwargs):
        calls.update(kwargs)
        return {"status": "OK"}

    execute_stock_update_orchestration(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="usa",
        plans=[_make_plan("AAA")],
        stock_factory=lambda ticker: _GuardStock(results=[history]),
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        maybe_update_quarter_state=lambda ticker, market, stock: None,
        calculate_dow_structures=calculate_dow_structures,
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
        dow_dry_run=True,
        dow_run_id="RUN1",
        dow_created_at_utc="2026-05-16T00:00:00Z",
    )

    assert calls == {
        "analysis_db_path": "analysis.db",
        "osakedata_db_path": str(db_path),
        "market": "usa",
        "pivot_radius": 7,
        "bounded_initial_from_date": "2020-01-01",
        "recalc_tail_trading_days": 50,
        "dry_run": True,
        "run_id": "RUN1",
        "created_at_utc": "2026-05-16T00:00:00Z",
    }


def test_execute_stock_update_orchestration_unexpected_batch_exception_propagates(
    tmp_path, monkeypatch
) -> None:
    from services import stock_update_service

    def boom(**kwargs):
        raise RuntimeError("batch failed")

    monkeypatch.setattr(stock_update_service, "execute_stock_update_batch", boom)

    called = []

    def calculate_dow_structures(**kwargs):
        called.append(True)
        return {"status": "OK"}

    with pytest.raises(RuntimeError, match="batch failed"):
        execute_stock_update_orchestration(
            osakedata_db_path=str(tmp_path / "osakedata.db"),
            analysis_db_path="analysis.db",
            market="usa",
            plans=[],
            stock_factory=lambda ticker: None,
            sync_splits=lambda ticker, stock: 0,
            maybe_backfill_splits=lambda ticker: False,
            calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
            run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
            maybe_update_quarter_state=lambda ticker, market, stock: None,
            calculate_dow_structures=calculate_dow_structures,
            pivot_radius=7,
            bounded_initial_from_date="2020-01-01",
            recalc_tail_trading_days=50,
        )

    assert called == []


def test_execute_stock_update_orchestration_dow_runs_when_plans_empty(tmp_path) -> None:
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    called = []

    def calculate_dow_structures(**kwargs):
        called.append(kwargs)
        return {"status": "OK"}

    result = execute_stock_update_orchestration(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="usa",
        plans=[],
        stock_factory=lambda ticker: None,
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        maybe_update_quarter_state=lambda ticker, market, stock: None,
        calculate_dow_structures=calculate_dow_structures,
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert result.batch_result.tickers_checked == 0
    assert called
    assert result.dow_result.attempted is True


def test_execute_stock_update_orchestration_warning_and_error_lists_are_new_objects(
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

    def stock_factory(ticker: str):
        if ticker == "FAIL":
            raise RuntimeError("factory failed")
        return _GuardStock(results=[history])

    result = execute_stock_update_orchestration(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="usa",
        plans=[_make_plan("FAIL"), _make_plan("OK", last_date="2026-01-02")],
        stock_factory=stock_factory,
        sync_splits=lambda ticker, stock: (_ for _ in ()).throw(RuntimeError("split failed")),
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        maybe_update_quarter_state=lambda ticker, market, stock: None,
        calculate_dow_structures=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("dow failed")),
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert result.warnings == [
        *result.batch_result.warnings,
        result.dow_result.warning,
    ]
    assert result.errors == result.batch_result.errors
    assert result.warnings is not result.batch_result.warnings
    assert result.errors is not result.batch_result.errors
