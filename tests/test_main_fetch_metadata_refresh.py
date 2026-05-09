from types import SimpleNamespace
import sqlite3
from datetime import datetime, timedelta

import pandas as pd

import main


class _FakePage:
    def __init__(self):
        self.overlay = []

    def update(self):
        return None


class _FakeTicker:
    def __init__(self):
        self.history_calls = []

    def history(self, start=None, end=None):
        self.history_calls.append((start, end))
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
    dow_calls = []
    div_calls = []
    candle_calls = []
    expected_end = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
    fake_ticker = _FakeTicker()

    monkeypatch.setattr(main.yf, "Ticker", lambda ticker: fake_ticker)
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

    import analysis.stock_dow_structure

    monkeypatch.setattr(
        analysis.stock_dow_structure,
        "calculate_missing_or_outdated_stock_dow_structures",
        lambda **kwargs: dow_calls.append(kwargs) or {"rows_inserted": 0},
    )

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
    app._calculate_and_save_divergences = (
        lambda ticker, only_missing=True: div_calls.append((ticker, only_missing))
        or (True, 0, "")
    )
    app._run_incremental_candlestick_analysis = (
        lambda ticker, analysis_start, analysis_end: candle_calls.append(
            (ticker, analysis_start, analysis_end)
        )
        or (0, None)
    )

    app.fetch_stock_data(None)

    assert called == [(app.osakedata_db_path, "AAA", "usa")]
    assert div_calls == [("AAA", True)]
    assert candle_calls == [("AAA", "2018-01-02", expected_end)]
    assert dow_calls == [
        {
            "analysis_db_path": app.analysis_db_path,
            "osakedata_db_path": app.osakedata_db_path,
            "ticker": "AAA",
            "pivot_radius": analysis.stock_dow_structure.DEFAULT_PIVOT_RADIUS,
            "bounded_initial_from_date": analysis.stock_dow_structure.DEFAULT_BOUNDED_INITIAL_FROM_DATE,
            "recalc_tail_trading_days": analysis.stock_dow_structure.DEFAULT_RECALC_TAIL_TRADING_DAYS,
            "dry_run": False,
        }
    ]


class _FakeUpdateTicker:
    def __init__(self, hist):
        self.hist = hist
        self.history_calls = []

    def history(self, start=None, end=None):
        self.history_calls.append((start, end))
        return self.hist.copy()


def test_update_stock_data_includes_latest_available_day(tmp_path, monkeypatch):
    today = datetime.now().date()
    yesterday = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    two_days_ago = (today - timedelta(days=2)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    expected_end = (today + timedelta(days=1)).strftime("%Y-%m-%d")

    db_path = tmp_path / "osakedata.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT NOT NULL,
                pvm TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                market TEXT NOT NULL DEFAULT 'usa',
                PRIMARY KEY (osake, pvm)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAA", two_days_ago, 10.0, 11.0, 9.5, 10.5, 100000, "usa"),
        )
        conn.commit()

    fake_hist = pd.DataFrame(
        {
            "Open": [10.5, 11.0],
            "High": [11.5, 12.0],
            "Low": [10.0, 10.5],
            "Close": [11.0, 11.5],
            "Volume": [210000, 230000],
        },
        index=pd.to_datetime([yesterday, today_str]),
    )
    fake_ticker = _FakeUpdateTicker(fake_hist)
    split_sync_calls = []
    split_backfill_calls = []
    div_calls = []
    candle_calls = []

    monkeypatch.setattr(main.yf, "Ticker", lambda ticker: fake_ticker)
    monkeypatch.setattr(main, "validate_market", lambda market, db_path=None: True)
    monkeypatch.setattr(main.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        main,
        "sync_splits_for_ticker",
        lambda db_path_arg, ticker, yf_ticker=None: split_sync_calls.append(
            (db_path_arg, ticker, yf_ticker)
        )
        or 0,
    )

    import analysis.stock_dow_structure

    monkeypatch.setattr(
        analysis.stock_dow_structure,
        "calculate_missing_or_outdated_stock_dow_structures",
        lambda **kwargs: {
            "tickers_checked": 0,
            "tickers_bounded_initial_recalculated": 0,
            "tickers_registered_without_status": 0,
            "tickers_incremental_recalculated": 0,
            "tickers_up_to_date": 0,
            "tickers_no_valid_close_data": 0,
            "rows_inserted": 0,
            "rows_deleted": 0,
        },
    )

    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.osakedata_db_path = str(db_path)
    app.analysis_db_path = str(tmp_path / "analysis.db")
    app.data_dir = str(tmp_path)
    app.loading_text = SimpleNamespace(value="", color=None)
    app.page = _FakePage()
    app.update_start_input = SimpleNamespace(value="")
    app.update_market_dropdown = SimpleNamespace(value="")
    app._quarter_detection_run_id = lambda: "run-1"
    app._update_quarter_state_from_yahoo_detection = lambda **kwargs: {}
    app._extract_yahoo_latest_quarter_period_end_date = lambda stock: None
    app._quarter_state_timestamp_utc = lambda: "2026-01-01T00:00:00Z"
    app._quarter_state_db_path_for_market = lambda market: str(tmp_path / "fundamentals.db")
    app._calculate_and_save_divergences = (
        lambda ticker, only_missing=True: div_calls.append((ticker, only_missing))
        or (True, 0, "")
    )
    app._maybe_backfill_splits_for_ticker = lambda ticker: split_backfill_calls.append(ticker) or False
    app._run_incremental_candlestick_analysis = (
        lambda ticker, analysis_start, analysis_end: candle_calls.append(
            (ticker, analysis_start, analysis_end)
        )
        or (0, None)
    )

    app.update_stock_data(None)

    assert fake_ticker.history_calls == [(yesterday, expected_end)]
    assert split_sync_calls == [(app.osakedata_db_path, "AAA", fake_ticker)]
    assert split_backfill_calls == ["AAA"]
    assert div_calls == [("AAA", True)]
    assert candle_calls == [("AAA", yesterday, expected_end)]
    with sqlite3.connect(db_path) as conn:
        max_date = conn.execute(
            "SELECT MAX(pvm) FROM osakedata WHERE osake = ?", ("AAA",)
        ).fetchone()[0]
    assert max_date == today_str


def test_incremental_candlestick_helper_includes_new_patterns_and_no_downtrend_filter(
    tmp_path, monkeypatch
):
    captured = {}

    def _fake_run_candlestick_analysis(
        db_path,
        ticker,
        patterns,
        start_date,
        end_date,
        progress_callback=None,
        downtrend_filter=False,
        min_decline_percent=0.0,
        use_ma_filter=False,
        use_volume_filter=False,
        analysis_db_path=None,
    ):
        captured["patterns"] = list(patterns)
        captured["downtrend_filter"] = downtrend_filter
        captured["db_path"] = db_path
        captured["ticker"] = ticker
        captured["start_date"] = start_date
        captured["end_date"] = end_date
        captured["analysis_db_path"] = analysis_db_path
        return {}

    import analysis.run_analysis

    monkeypatch.setattr(
        analysis.run_analysis,
        "run_candlestick_analysis",
        _fake_run_candlestick_analysis,
    )

    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.osakedata_db_path = str(tmp_path / "osakedata.db")
    app.analysis_db_path = str(tmp_path / "analysis.db")

    analysis_total, analysis_error = app._run_incremental_candlestick_analysis(
        "AAA",
        "2026-01-01",
        "2026-01-31",
    )

    assert analysis_total == 0
    assert analysis_error is None
    assert "Bullish Abandoned Baby" in captured["patterns"]
    assert "Bullish Flag" in captured["patterns"]
    assert "Bull Rectangle" in captured["patterns"]
    assert "Ascending Triangle" in captured["patterns"]
    assert "Bullish Pennant" in captured["patterns"]
    assert "Falling Three Methods" in captured["patterns"]
    assert "Bearish Flag" in captured["patterns"]
    assert "Bear Rectangle" in captured["patterns"]
    assert "Descending Triangle" in captured["patterns"]
    assert "Bearish Pennant" in captured["patterns"]
    assert captured["downtrend_filter"] is False
