from __future__ import annotations

import main


def test_build_stock_update_service_adapters_returns_expected_keys(monkeypatch):
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.osakedata_db_path = "/tmp/osakedata.db"
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

    assert set(adapters) >= {
        "stock_factory",
        "sync_splits",
        "maybe_backfill_splits",
        "calculate_divergences",
        "run_candlestick_analysis",
        "maybe_update_quarter_state",
        "calculate_dow_structures",
        "pivot_radius",
        "bounded_initial_from_date",
        "recalc_tail_trading_days",
    }


def test_build_stock_update_service_adapters_stock_factory_uses_yf_ticker(monkeypatch):
    called = []
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.osakedata_db_path = "/tmp/osakedata.db"
    app._maybe_backfill_splits_for_ticker = lambda ticker: False
    app._calculate_and_save_divergences = lambda ticker, only_missing=True: (
        True,
        0,
        "",
    )
    app._run_incremental_candlestick_analysis = (
        lambda ticker, analysis_start, analysis_end: (0, None)
    )

    monkeypatch.setattr(main.yf, "Ticker", lambda ticker: called.append(ticker) or {"ticker": ticker})

    adapters = app._build_stock_update_service_adapters()
    result = adapters["stock_factory"]("AAA")

    assert called == ["AAA"]
    assert result == {"ticker": "AAA"}


def test_build_stock_update_service_adapters_sync_splits_binds_db_path_and_stock(monkeypatch):
    called = []
    fake_stock = object()
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.osakedata_db_path = "/tmp/osakedata.db"
    app._maybe_backfill_splits_for_ticker = lambda ticker: False
    app._calculate_and_save_divergences = lambda ticker, only_missing=True: (
        True,
        0,
        "",
    )
    app._run_incremental_candlestick_analysis = (
        lambda ticker, analysis_start, analysis_end: (0, None)
    )

    monkeypatch.setattr(
        main,
        "sync_splits_for_ticker",
        lambda db_path, ticker, yf_ticker=None: called.append((db_path, ticker, yf_ticker))
        or 3,
    )

    adapters = app._build_stock_update_service_adapters()
    result = adapters["sync_splits"]("AAA", fake_stock)

    assert result == 3
    assert called == [(app.osakedata_db_path, "AAA", fake_stock)]


def test_build_stock_update_service_adapters_backfill_calls_app_method():
    called = []
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.osakedata_db_path = "/tmp/osakedata.db"
    app._maybe_backfill_splits_for_ticker = lambda ticker: called.append(ticker) or 1
    app._calculate_and_save_divergences = lambda ticker, only_missing=True: (
        True,
        0,
        "",
    )
    app._run_incremental_candlestick_analysis = (
        lambda ticker, analysis_start, analysis_end: (0, None)
    )

    adapters = app._build_stock_update_service_adapters()
    result = adapters["maybe_backfill_splits"]("AAA")

    assert result is True
    assert called == ["AAA"]


def test_build_stock_update_service_adapters_divergence_calls_app_method():
    called = []
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.osakedata_db_path = "/tmp/osakedata.db"
    app._maybe_backfill_splits_for_ticker = lambda ticker: False
    app._calculate_and_save_divergences = (
        lambda ticker, only_missing=True: called.append((ticker, only_missing))
        or (True, 7, "")
    )
    app._run_incremental_candlestick_analysis = (
        lambda ticker, analysis_start, analysis_end: (0, None)
    )

    adapters = app._build_stock_update_service_adapters()
    result = adapters["calculate_divergences"]("AAA", True)

    assert result == (True, 7, "")
    assert called == [("AAA", True)]


def test_build_stock_update_service_adapters_candlestick_calls_app_method():
    called = []
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.osakedata_db_path = "/tmp/osakedata.db"
    app._maybe_backfill_splits_for_ticker = lambda ticker: False
    app._calculate_and_save_divergences = lambda ticker, only_missing=True: (
        True,
        0,
        "",
    )
    app._run_incremental_candlestick_analysis = (
        lambda ticker, analysis_start, analysis_end: called.append(
            (ticker, analysis_start, analysis_end)
        )
        or (4, None)
    )

    adapters = app._build_stock_update_service_adapters()
    result = adapters["run_candlestick_analysis"]("AAA", "2026-01-01", "2026-01-10")

    assert result == (4, None)
    assert called == [("AAA", "2026-01-01", "2026-01-10")]


def test_build_stock_update_service_adapters_quarter_detection_calls_app_methods():
    fake_stock = object()
    extract_calls = []
    update_calls = []
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.osakedata_db_path = "/tmp/osakedata.db"
    app._maybe_backfill_splits_for_ticker = lambda ticker: False
    app._calculate_and_save_divergences = lambda ticker, only_missing=True: (
        True,
        0,
        "",
    )
    app._run_incremental_candlestick_analysis = (
        lambda ticker, analysis_start, analysis_end: (0, None)
    )
    app._extract_yahoo_latest_quarter_period_end_date = (
        lambda stock: extract_calls.append(stock) or "2026-03-31"
    )
    app._quarter_detection_run_id = lambda: "run-1"
    app._quarter_state_timestamp_utc = lambda: "2026-05-19T10:00:00Z"
    app._update_quarter_state_from_yahoo_detection = lambda **kwargs: update_calls.append(
        kwargs
    ) or {"checked": True}

    adapters = app._build_stock_update_service_adapters()
    result = adapters["maybe_update_quarter_state"]("AAA", "usa", fake_stock)

    assert result == {"checked": True}
    assert extract_calls == [fake_stock]
    assert update_calls == [
        {
            "ticker": "AAA",
            "market": "usa",
            "yahoo_latest_period_end_date": "2026-03-31",
            "run_id": "run-1",
            "checked_at_utc": "2026-05-19T10:00:00Z",
        }
    ]


def test_build_stock_update_service_adapters_dow_forwards_kwargs_exactly(monkeypatch):
    import analysis.stock_dow_structure as dow_module

    called = []
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.osakedata_db_path = "/tmp/osakedata.db"
    app._maybe_backfill_splits_for_ticker = lambda ticker: False
    app._calculate_and_save_divergences = lambda ticker, only_missing=True: (
        True,
        0,
        "",
    )
    app._run_incremental_candlestick_analysis = (
        lambda ticker, analysis_start, analysis_end: (0, None)
    )

    monkeypatch.setattr(
        dow_module,
        "calculate_missing_or_outdated_stock_dow_structures",
        lambda **kwargs: called.append(kwargs) or {"status": "OK"},
    )

    adapters = app._build_stock_update_service_adapters()
    payload = {
        "analysis_db_path": "analysis.db",
        "osakedata_db_path": "osakedata.db",
        "market": "usa",
        "pivot_radius": 7,
        "bounded_initial_from_date": "2020-01-01",
        "recalc_tail_trading_days": 50,
        "dry_run": False,
        "run_id": "RUN1",
        "created_at_utc": "2026-05-16T00:00:00Z",
    }
    result = adapters["calculate_dow_structures"](**payload)

    assert result == {"status": "OK"}
    assert called == [payload]


def test_build_stock_update_service_adapters_does_not_call_adapters_during_construction(monkeypatch):
    calls = []
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.osakedata_db_path = "/tmp/osakedata.db"
    app._maybe_backfill_splits_for_ticker = lambda ticker: calls.append("backfill")
    app._calculate_and_save_divergences = (
        lambda ticker, only_missing=True: calls.append("divergence")
    )
    app._run_incremental_candlestick_analysis = (
        lambda ticker, analysis_start, analysis_end: calls.append("candlestick")
    )

    monkeypatch.setattr(main.yf, "Ticker", lambda ticker: calls.append("stock_factory"))
    monkeypatch.setattr(
        main,
        "sync_splits_for_ticker",
        lambda db_path, ticker, yf_ticker=None: calls.append("split_sync"),
    )

    app._build_stock_update_service_adapters()

    assert calls == []


def test_raw_candle_app_still_has_update_stock_data():
    assert hasattr(main.RawCandleApp, "update_stock_data")
