from types import SimpleNamespace

import pandas as pd

import main


class _FakePage:
    def __init__(self):
        self.overlay = []

    def update(self):
        return None


class _FakeTicker:
    def history(self, start=None, end=None):
        index = pd.to_datetime(["2026-01-02", "2026-01-05"])
        return pd.DataFrame(
            {
                "Open": [10.0, 10.5],
                "High": [11.0, 11.5],
                "Low": [9.5, 10.0],
                "Close": [10.8, 11.2],
                "Volume": [200000, 220000],
            },
            index=index,
        )


def test_fetch_stock_data_calls_single_ticker_metadata_refresh(tmp_path, monkeypatch):
    called = []

    monkeypatch.setattr(main.yf, "Ticker", lambda ticker: _FakeTicker())
    monkeypatch.setattr(main, "validate_market", lambda market, db_path=None: True)
    monkeypatch.setattr(main, "sync_splits_for_ticker", lambda *args, **kwargs: 0)
    monkeypatch.setattr(
        main,
        "refresh_single_ticker_metadata",
        lambda db_path, ticker, market=None, logger=None: called.append(
            (db_path, ticker, market)
        )
        or True,
    )

    import analysis.run_analysis

    monkeypatch.setattr(analysis.run_analysis, "run_candlestick_analysis", lambda *args, **kwargs: {})

    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.data_dir = str(tmp_path)
    app.osakedata_db_path = str(tmp_path / "osakedata.db")
    app.analysis_db_path = str(tmp_path / "analysis.db")
    app.loading_text = SimpleNamespace(value="", color=None)
    app.page = _FakePage()
    app.ticker_field = SimpleNamespace(value="AAA")
    app.stock_data = None
    app.markets = []
    app._default_market_code = lambda: "usa"
    app._infer_market_from_ticker = lambda ticker: None
    app._get_market_min_volume_requirement = lambda market: 0
    app._maybe_backfill_splits_for_ticker = lambda ticker: False
    app._calculate_and_save_divergences = lambda ticker, only_missing=True: (True, 0, "")

    app.fetch_stock_data(None)

    assert called == [(app.osakedata_db_path, "AAA", "usa")]

