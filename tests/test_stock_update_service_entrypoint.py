from __future__ import annotations

import inspect
import sqlite3

import pytest

from services import stock_update_service as sus

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


def _insert_osakedata_row(db_path, ticker, pvm, market):
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ticker, pvm, 1.0, 2.0, 0.5, 1.5, 100, market),
        )
        conn.commit()


def test_run_stock_data_update_resolves_default_market_and_runs_flow(tmp_path):
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    _insert_osakedata_row(db_path, "AAA", "2026-01-01", "omxh")
    history = pd.DataFrame(
        {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
        index=pd.to_datetime(["2026-01-02"]),
    )

    result = sus.run_stock_data_update(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market=None,
        start_override=None,
        today="2026-05-10",
        fetch_until_exclusive="2026-05-17",
        stock_factory=lambda ticker: _GuardStock(results=[history]),
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        calculate_dow_structures=lambda **kwargs: {"status": "OK"},
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert result.market == "omxh"
    assert result.tickers_checked == 1
    assert result.tickers_updated == 1
    assert result.tickers_failed == 0
    assert result.ohlcv_rows_inserted > 0
    assert result.status == sus.STATUS_OK


def test_run_stock_data_update_filters_selected_market(tmp_path):
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    _insert_osakedata_row(db_path, "AAA", "2026-01-01", "omxh")
    _insert_osakedata_row(db_path, "BBB", "2026-01-01", "usa")
    history = pd.DataFrame(
        {"Open": [20.0], "High": [21.0], "Low": [19.5], "Close": [20.8], "Volume": [2]},
        index=pd.to_datetime(["2026-01-02"]),
    )
    factory_calls = []

    def stock_factory(ticker: str):
        factory_calls.append(ticker)
        return _GuardStock(results=[history])

    result = sus.run_stock_data_update(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="USA",
        start_override=None,
        today="2026-05-10",
        fetch_until_exclusive="2026-05-17",
        stock_factory=stock_factory,
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        calculate_dow_structures=lambda **kwargs: {"status": "OK"},
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert result.market == "usa"
    assert result.tickers_checked == 1
    assert factory_calls == ["BBB"]


def test_run_stock_data_update_empty_market_still_runs_dow(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    dow_calls = []

    result = sus.run_stock_data_update(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="usa",
        start_override=None,
        today="2026-05-10",
        fetch_until_exclusive="2026-05-17",
        stock_factory=lambda ticker: None,
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        calculate_dow_structures=lambda **kwargs: dow_calls.append(kwargs) or {"status": "OK"},
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert result.tickers_checked == 0
    assert dow_calls
    assert result.status == sus.STATUS_OK


def test_run_stock_data_update_ticker_failure_maps_to_ok_with_warnings(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    _insert_osakedata_row(db_path, "AAA", "2026-01-01", "omxh")

    result = sus.run_stock_data_update(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="omxh",
        start_override=None,
        today="2026-05-10",
        fetch_until_exclusive="2026-05-17",
        stock_factory=lambda ticker: (_ for _ in ()).throw(RuntimeError("factory failed")),
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        calculate_dow_structures=lambda **kwargs: {"status": "OK"},
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert result.tickers_failed == 1
    assert any("AAA" in error and "factory failed" in error for error in result.errors)
    assert result.status == sus.STATUS_OK_WITH_WARNINGS


def test_run_stock_data_update_dow_failure_maps_to_ok_with_warnings(tmp_path):
    if pd is None:
        pytest.skip("pandas not available")

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    _insert_osakedata_row(db_path, "AAA", "2026-01-01", "omxh")
    history = pd.DataFrame(
        {"Open": [10.0], "High": [11.0], "Low": [9.5], "Close": [10.8], "Volume": [1]},
        index=pd.to_datetime(["2026-01-02"]),
    )

    result = sus.run_stock_data_update(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="omxh",
        start_override=None,
        today="2026-05-10",
        fetch_until_exclusive="2026-05-17",
        stock_factory=lambda ticker: _GuardStock(results=[history]),
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        calculate_dow_structures=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("dow failed")),
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert result.status == sus.STATUS_OK_WITH_WARNINGS
    assert any("dow failed" in warning for warning in result.warnings)
    assert not any("dow failed" in error for error in result.errors)


def test_run_stock_data_update_invalid_start_override_propagates(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    _insert_osakedata_row(db_path, "AAA", "2026-01-01", "omxh")

    with pytest.raises(ValueError):
        sus.run_stock_data_update(
            osakedata_db_path=str(db_path),
            analysis_db_path="analysis.db",
            market="omxh",
            start_override="bad-date",
            today="2026-05-10",
            fetch_until_exclusive="2026-05-17",
            stock_factory=lambda ticker: None,
            sync_splits=lambda ticker, stock: 0,
            maybe_backfill_splits=lambda ticker: False,
            calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
            run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
            calculate_dow_structures=lambda **kwargs: {"status": "OK"},
            pivot_radius=7,
            bounded_initial_from_date="2020-01-01",
            recalc_tail_trading_days=50,
        )


def test_run_stock_data_update_accepts_progress_callback_but_does_not_call_it(tmp_path):
    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    events = []

    result = sus.run_stock_data_update(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="usa",
        start_override=None,
        today="2026-05-10",
        fetch_until_exclusive="2026-05-17",
        stock_factory=lambda ticker: None,
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        calculate_dow_structures=lambda **kwargs: {"status": "OK"},
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
        progress_callback=lambda event: events.append(event),
    )

    assert result.tickers_checked == 0
    assert events == []


def test_run_stock_data_update_result_lists_are_new_objects(tmp_path, monkeypatch):
    warnings = ["w1"]
    errors = ["e1"]

    def fake_orchestration(**kwargs):
        return sus.StockUpdateOrchestrationResult(
            batch_result=sus.StockUpdateBatchExecutionResult(
                market="omxh",
                warnings=warnings,
                errors=errors,
            ),
            dow_result=sus.StockUpdateDowResult(
                attempted=True,
                success=False,
                dow_summary=None,
                warning="w2",
            ),
            warnings=[*warnings, "w2"],
            errors=list(errors),
        )

    monkeypatch.setattr(sus, "execute_stock_update_orchestration", fake_orchestration)

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    result = sus.run_stock_data_update(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="omxh",
        start_override=None,
        today="2026-05-10",
        fetch_until_exclusive="2026-05-17",
        stock_factory=lambda ticker: None,
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        calculate_dow_structures=lambda **kwargs: {"status": "OK"},
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert result.warnings == ["w1", "w2"]
    assert result.errors == ["e1"]
    assert result.warnings is not warnings
    assert result.errors is not errors


@pytest.mark.parametrize(
    ("dow_summary", "expected"),
    [
        ({"updated": 7, "inserted": 5, "rows_inserted": 3}, 7),
        ({"inserted": 5, "rows_inserted": 3}, 5),
        ({"rows_inserted": 621, "rows_deleted": 603}, 621),
        ({"rows_deleted": 603}, None),
        ({"processed": 10}, None),
    ],
)
def test_run_stock_data_update_dow_structures_updated_mapping(
    tmp_path, monkeypatch, dow_summary, expected
):
    def fake_orchestration(**kwargs):
        return sus.StockUpdateOrchestrationResult(
            batch_result=sus.StockUpdateBatchExecutionResult(market="omxh"),
            dow_result=sus.StockUpdateDowResult(
                attempted=True,
                success=True,
                dow_summary=dow_summary,
                warning=None,
            ),
            warnings=[],
            errors=[],
        )

    monkeypatch.setattr(sus, "execute_stock_update_orchestration", fake_orchestration)

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    result = sus.run_stock_data_update(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="omxh",
        start_override=None,
        today="2026-05-10",
        fetch_until_exclusive="2026-05-17",
        stock_factory=lambda ticker: None,
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        calculate_dow_structures=lambda **kwargs: {"status": "OK"},
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert result.dow_structures_updated == expected


def test_run_stock_data_update_summary_lines_reflect_rows_inserted_dow_mapping(
    tmp_path, monkeypatch
):
    def fake_orchestration(**kwargs):
        return sus.StockUpdateOrchestrationResult(
            batch_result=sus.StockUpdateBatchExecutionResult(market="omxh"),
            dow_result=sus.StockUpdateDowResult(
                attempted=True,
                success=True,
                dow_summary={"rows_inserted": 621, "rows_deleted": 603},
                warning=None,
            ),
            warnings=[],
            errors=[],
        )

    monkeypatch.setattr(sus, "execute_stock_update_orchestration", fake_orchestration)

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    result = sus.run_stock_data_update(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="omxh",
        start_override=None,
        today="2026-05-10",
        fetch_until_exclusive="2026-05-17",
        stock_factory=lambda ticker: None,
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        calculate_dow_structures=lambda **kwargs: {"status": "OK"},
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert "SUMMARY dow_structures_updated=621" in sus.format_stock_update_summary_lines(
        result
    )


def test_run_stock_data_update_conservative_aggregate_fields_remain_zero(tmp_path, monkeypatch):
    def fake_orchestration(**kwargs):
        return sus.StockUpdateOrchestrationResult(
            batch_result=sus.StockUpdateBatchExecutionResult(market="omxh"),
            dow_result=sus.StockUpdateDowResult(
                attempted=True,
                success=True,
                dow_summary={"updated": 1},
                warning=None,
            ),
            warnings=[],
            errors=[],
        )

    monkeypatch.setattr(sus, "execute_stock_update_orchestration", fake_orchestration)

    db_path = tmp_path / "osakedata.db"
    _create_osakedata_table(db_path)
    result = sus.run_stock_data_update(
        osakedata_db_path=str(db_path),
        analysis_db_path="analysis.db",
        market="omxh",
        start_override=None,
        today="2026-05-10",
        fetch_until_exclusive="2026-05-17",
        stock_factory=lambda ticker: None,
        sync_splits=lambda ticker, stock: 0,
        maybe_backfill_splits=lambda ticker: False,
        calculate_divergences=lambda ticker, only_missing: (True, 1, ""),
        run_candlestick_analysis=lambda ticker, analysis_start, analysis_end: (0, None),
        calculate_dow_structures=lambda **kwargs: {"status": "OK"},
        pivot_radius=7,
        bounded_initial_from_date="2020-01-01",
        recalc_tail_trading_days=50,
    )

    assert result.splits_synced == 0
    assert result.divergences_updated == 0
    assert result.candlesticks_updated == 0


def test_no_forbidden_imports_in_stock_update_service_module():
    source = inspect.getsource(sus)

    assert "import yfinance" not in source
    assert "import pandas" not in source
    assert "import numpy" not in source
    assert "import flet" not in source.lower()
    assert "import stock.splits" not in source
    assert "analysis.stock_dow_structure" not in source
