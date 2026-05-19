from __future__ import annotations

import inspect

import main


class _FakeLoadingText:
    def __init__(self):
        self.value = ""
        self.color = None


class _FakeButton:
    def __init__(self):
        self.disabled = False


class _FakePage:
    def __init__(self):
        self.update_calls = 0

    def update(self):
        self.update_calls += 1


class _FakeField:
    def __init__(self, value=""):
        self.value = value


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
        "maybe_update_quarter_state": object(),
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
        "maybe_update_quarter_state": adapters["maybe_update_quarter_state"],
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
        "maybe_update_quarter_state": object(),
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
        "maybe_update_quarter_state": object(),
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


def test_format_stock_update_service_result_for_ui_basic_ok_result():
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    result = main.StockUpdateResult(
        market="omxh",
        tickers_checked=10,
        tickers_updated=3,
        tickers_skipped=7,
        tickers_failed=0,
        ohlcv_rows_inserted=12,
        status="OK",
    )

    formatted = app._format_stock_update_service_result_for_ui(result)

    assert "Markkina: omxh" in formatted
    assert "Tarkistetut tickerit: 10" in formatted
    assert "Päivitetyt tickerit: 3" in formatted
    assert "Ohitetut tickerit: 7" in formatted
    assert "Virheelliset tickerit: 0" in formatted
    assert "Lisätyt OHLCV-rivit: 12" in formatted
    assert "Status: OK" in formatted


def test_format_stock_update_service_result_for_ui_includes_warnings_and_errors():
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    result = main.StockUpdateResult(
        market="omxh",
        warnings=["varoitus 1", "varoitus 2"],
        errors=["virhe 1", "virhe 2"],
        status="OK_WITH_WARNINGS",
    )

    formatted = app._format_stock_update_service_result_for_ui(result)

    assert "Varoitukset:" in formatted
    assert "- varoitus 1" in formatted
    assert "- varoitus 2" in formatted
    assert "Virheet:" in formatted
    assert "- virhe 1" in formatted
    assert "- virhe 2" in formatted
    assert formatted.index("- varoitus 1") < formatted.index("- varoitus 2")
    assert formatted.index("- virhe 1") < formatted.index("- virhe 2")


def test_format_stock_update_service_result_for_ui_includes_dow_structures_updated():
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    result = main.StockUpdateResult(
        market="omxh",
        dow_structures_updated=5,
    )

    formatted = app._format_stock_update_service_result_for_ui(result)

    assert "Dow-rakenteet päivitetty: 5" in formatted


def test_format_stock_update_service_result_for_ui_includes_multiline_dow_summary():
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    result = main.StockUpdateResult(
        market="omxh",
        dow_summary={"updated": 3, "processed": 10},
    )

    formatted = app._format_stock_update_service_result_for_ui(result)

    assert "Dow-yhteenveto:" in formatted
    assert "Dow-yhteenveto:\nprocessed=10\nupdated=3" in formatted
    assert "processed=10" in formatted
    assert "updated=3" in formatted
    assert formatted.index("processed=10") < formatted.index("updated=3")


def test_format_stock_update_service_result_for_ui_does_not_require_ui_fields():
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    result = main.StockUpdateResult(market="omxh", status="OK")

    formatted = app._format_stock_update_service_result_for_ui(result)

    assert "Markkina: omxh" in formatted


def test_update_stock_data_via_service_ui_flow_success(monkeypatch):
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.loading_text = _FakeLoadingText()
    app.update_stock_button = _FakeButton()
    app.page = _FakePage()
    app.update_market_dropdown = _FakeField("usa")
    app.update_start_input = _FakeField("")
    app._stock_update_in_progress = False

    called = {}

    def fake_run_stock_update_via_service(**kwargs):
        called.update(kwargs)
        return main.StockUpdateResult(market="usa", status="OK")

    monkeypatch.setattr(
        app,
        "_run_stock_update_via_service",
        fake_run_stock_update_via_service,
    )
    monkeypatch.setattr(
        app,
        "_format_stock_update_service_result_for_ui",
        lambda result: "FORMATTED RESULT",
    )

    app._update_stock_data_via_service_ui_flow()

    assert called["market"] == "usa"
    assert called["start_override"] is None
    assert "today" in called
    assert "fetch_until_exclusive" in called
    assert app.loading_text.value == "FORMATTED RESULT"
    assert app.update_stock_button.disabled is False
    assert app._stock_update_in_progress is False
    assert app.page.update_calls >= 1


def test_update_stock_data_via_service_ui_flow_invalid_start_override_does_not_call_service(
    monkeypatch,
):
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.loading_text = _FakeLoadingText()
    app.update_stock_button = _FakeButton()
    app.page = _FakePage()
    app.update_market_dropdown = _FakeField("usa")
    app.update_start_input = _FakeField("bad-date")
    app._stock_update_in_progress = False

    monkeypatch.setattr(
        app,
        "_run_stock_update_via_service",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("service should not run")),
    )

    app._update_stock_data_via_service_ui_flow()

    assert "Aloituspäivä virheellinen" in app.loading_text.value
    assert app.update_stock_button.disabled is False
    assert app._stock_update_in_progress is False


def test_update_stock_data_via_service_ui_flow_catches_service_exception():
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.loading_text = _FakeLoadingText()
    app.update_stock_button = _FakeButton()
    app.page = _FakePage()
    app.update_market_dropdown = _FakeField("usa")
    app.update_start_input = _FakeField("")
    app._stock_update_in_progress = False
    app._run_stock_update_via_service = lambda **kwargs: (_ for _ in ()).throw(
        RuntimeError("service failed")
    )

    app._update_stock_data_via_service_ui_flow()

    assert "service failed" in app.loading_text.value
    assert app.update_stock_button.disabled is False
    assert app._stock_update_in_progress is False


def test_update_stock_data_via_service_ui_flow_returns_early_when_already_running():
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.loading_text = _FakeLoadingText()
    app.update_stock_button = _FakeButton()
    app.page = _FakePage()
    app.update_market_dropdown = _FakeField("usa")
    app.update_start_input = _FakeField("")
    app._stock_update_in_progress = True
    app._run_stock_update_via_service = lambda **kwargs: (_ for _ in ()).throw(
        AssertionError("service should not run")
    )

    app._update_stock_data_via_service_ui_flow()

    assert app.page.update_calls == 0


def test_update_stock_data_via_service_ui_flow_does_not_call_old_update_stock_data():
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.loading_text = _FakeLoadingText()
    app.update_stock_button = _FakeButton()
    app.page = _FakePage()
    app.update_market_dropdown = _FakeField("usa")
    app.update_start_input = _FakeField("")
    app._stock_update_in_progress = False
    app._run_stock_update_via_service = lambda **kwargs: main.StockUpdateResult(
        market="usa",
        status="OK",
    )
    app._format_stock_update_service_result_for_ui = lambda result: "FORMATTED RESULT"
    app.update_stock_data = lambda e=None: (_ for _ in ()).throw(
        AssertionError("old update_stock_data should not be called")
    )

    app._update_stock_data_via_service_ui_flow()

    assert app.loading_text.value == "FORMATTED RESULT"


def test_update_stock_data_opt_in_true_delegates_to_service_ui_flow():
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app._use_stock_update_service = True
    called = []

    def fake_service_ui_flow(event):
        called.append(event)

    app._update_stock_data_via_service_ui_flow = fake_service_ui_flow

    app.update_stock_data("EVENT")

    assert called == ["EVENT"]


def test_update_stock_data_source_uses_missing_opt_in_flag_default_false():
    source = inspect.getsource(main.RawCandleApp.update_stock_data)

    assert 'getattr(self, "_use_stock_update_service", False)' in source
    assert "return self._update_stock_data_via_service_ui_flow(e)" in source


def test_update_stock_data_source_guards_service_branch_with_explicit_flag():
    source = inspect.getsource(main.RawCandleApp.update_stock_data)

    assert 'if getattr(self, "_use_stock_update_service", False):' in source


def test_update_stock_button_on_click_handler_is_still_update_stock_data():
    source = inspect.getsource(main.RawCandleApp.__init__)

    assert "on_click=self.update_stock_data" in source


def test_raw_candle_app_still_has_service_ui_flow_method():
    assert hasattr(main.RawCandleApp, "_update_stock_data_via_service_ui_flow")
