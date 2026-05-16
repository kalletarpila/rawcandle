from __future__ import annotations

import main


def test_run_stock_update_via_service_calls_service_with_adapter_values(monkeypatch):
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.osakedata_db_path = "/tmp/osakedata.db"
    app.analysis_db_path = "/tmp/analysis.db"

    adapters = {
        "stock_factory": object(),
        "sync_splits": object(),
        "maybe_backfill_splits": object(),
        "calculate_divergences": object(),
        "run_candlestick_analysis": object(),
        "calculate_dow_structures": object(),
        "pivot_radius": 7,
        "bounded_initial_from_date": "2020-01-01",
        "recalc_tail_trading_days": 50,
    }
    app._build_stock_update_service_adapters = lambda: adapters

    fake_result = main.StockUpdateResult(market="usa")
    called = {}

    def fake_run_stock_data_update(**kwargs):
        called.update(kwargs)
        return fake_result

    monkeypatch.setattr(main, "run_stock_data_update", fake_run_stock_data_update)

    result = app._run_stock_update_via_service(
        market="usa",
        start_override="2026-01-01",
        today="2026-05-16",
        fetch_until_exclusive="2026-05-17",
    )

    assert result is fake_result
    assert called == {
        "osakedata_db_path": app.osakedata_db_path,
        "analysis_db_path": app.analysis_db_path,
        "market": "usa",
        "start_override": "2026-01-01",
        "today": "2026-05-16",
        "fetch_until_exclusive": "2026-05-17",
        "stock_factory": adapters["stock_factory"],
        "sync_splits": adapters["sync_splits"],
        "maybe_backfill_splits": adapters["maybe_backfill_splits"],
        "calculate_divergences": adapters["calculate_divergences"],
        "run_candlestick_analysis": adapters["run_candlestick_analysis"],
        "calculate_dow_structures": adapters["calculate_dow_structures"],
        "pivot_radius": adapters["pivot_radius"],
        "bounded_initial_from_date": adapters["bounded_initial_from_date"],
        "recalc_tail_trading_days": adapters["recalc_tail_trading_days"],
        "progress_callback": None,
    }


def test_run_stock_update_via_service_does_not_require_ui_fields(monkeypatch):
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.osakedata_db_path = "/tmp/osakedata.db"
    app.analysis_db_path = "/tmp/analysis.db"
    app._build_stock_update_service_adapters = lambda: {
        "stock_factory": object(),
        "sync_splits": object(),
        "maybe_backfill_splits": object(),
        "calculate_divergences": object(),
        "run_candlestick_analysis": object(),
        "calculate_dow_structures": object(),
        "pivot_radius": 7,
        "bounded_initial_from_date": "2020-01-01",
        "recalc_tail_trading_days": 50,
    }

    monkeypatch.setattr(
        main,
        "run_stock_data_update",
        lambda **kwargs: main.StockUpdateResult(market="usa"),
    )

    result = app._run_stock_update_via_service(
        market="usa",
        start_override=None,
        today="2026-05-16",
        fetch_until_exclusive="2026-05-17",
    )

    assert result.market == "usa"


def test_run_stock_update_via_service_does_not_catch_service_exceptions(monkeypatch):
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.osakedata_db_path = "/tmp/osakedata.db"
    app.analysis_db_path = "/tmp/analysis.db"
    app._build_stock_update_service_adapters = lambda: {
        "stock_factory": object(),
        "sync_splits": object(),
        "maybe_backfill_splits": object(),
        "calculate_divergences": object(),
        "run_candlestick_analysis": object(),
        "calculate_dow_structures": object(),
        "pivot_radius": 7,
        "bounded_initial_from_date": "2020-01-01",
        "recalc_tail_trading_days": 50,
    }

    monkeypatch.setattr(
        main,
        "run_stock_data_update",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("service failed")),
    )

    try:
        app._run_stock_update_via_service(
            market="usa",
            start_override=None,
            today="2026-05-16",
            fetch_until_exclusive="2026-05-17",
        )
    except RuntimeError as exc:
        assert str(exc) == "service failed"
    else:
        raise AssertionError("Expected RuntimeError to propagate")


def test_raw_candle_app_still_has_update_stock_data():
    assert hasattr(main.RawCandleApp, "update_stock_data")


def test_raw_candle_app_still_has_build_stock_update_service_adapters():
    assert hasattr(main.RawCandleApp, "_build_stock_update_service_adapters")
