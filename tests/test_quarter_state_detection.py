import sqlite3
from types import SimpleNamespace

import pandas as pd

import main


def _create_quarter_state_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
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
    conn.close()


def _fetch_state_row(db_path, ticker, market):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT ticker,
               market,
               primary_source,
               latest_db_period_end_date,
               detected_source_period_end_date,
               new_quarter_available,
               last_checked_at_utc,
               last_updated_at_utc,
               last_detection_run_id,
               last_ingest_run_id
        FROM rc_fundamental_quarter_state
        WHERE ticker = ? AND market = ?
        """,
        (ticker, market),
    )
    row = cursor.fetchone()
    conn.close()
    return row


def _build_app(tmp_path):
    app = main.RawCandleApp.__new__(main.RawCandleApp)
    app.fundamentals_fin_db_path = str(tmp_path / "fundamentals_fin.db")
    app.fundamentals_usa_db_path = str(tmp_path / "fundamentals_usa.db")
    _create_quarter_state_db(app.fundamentals_fin_db_path)
    _create_quarter_state_db(app.fundamentals_usa_db_path)
    return app


def test_quarter_state_usa_new_quarter_sets_flag(tmp_path):
    app = _build_app(tmp_path)
    conn = sqlite3.connect(app.fundamentals_usa_db_path)
    conn.execute(
        """
        INSERT INTO rc_fundamental_quarter_state (
            ticker, market, primary_source, latest_db_period_end_date,
            detected_source_period_end_date, new_quarter_available
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("LRCX", "usa", "sec_edgar", "2025-12-28", None, 0),
    )
    conn.commit()
    conn.close()

    result = app._update_quarter_state_from_yahoo_detection(
        ticker="LRCX",
        market="usa",
        yahoo_latest_period_end_date="2026-03-31",
        run_id="run-1",
        checked_at_utc="2026-05-06T10:00:00Z",
    )

    row = _fetch_state_row(app.fundamentals_usa_db_path, "LRCX", "usa")
    assert result["checked"] is True
    assert result["new_detected"] is True
    assert row[3] == "2025-12-28"
    assert row[4] == "2026-03-31"
    assert row[5] == 1
    assert row[8] == "run-1"
    assert row[2] == "sec_edgar"


def test_quarter_state_omxh_routes_only_to_fin_db(tmp_path):
    app = _build_app(tmp_path)
    conn = sqlite3.connect(app.fundamentals_fin_db_path)
    conn.execute(
        """
        INSERT INTO rc_fundamental_quarter_state (
            ticker, market, primary_source, latest_db_period_end_date,
            detected_source_period_end_date, new_quarter_available
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("NOKIA.HE", "omxh", "yahoo", "2025-12-31", None, 0),
    )
    conn.commit()
    conn.close()

    app._update_quarter_state_from_yahoo_detection(
        ticker="NOKIA.HE",
        market="omxh",
        yahoo_latest_period_end_date="2026-03-31",
        run_id="run-2",
        checked_at_utc="2026-05-06T10:00:00Z",
    )

    fin_row = _fetch_state_row(app.fundamentals_fin_db_path, "NOKIA.HE", "omxh")
    usa_row = _fetch_state_row(app.fundamentals_usa_db_path, "NOKIA.HE", "omxh")
    assert fin_row[4] == "2026-03-31"
    assert fin_row[5] == 1
    assert fin_row[2] == "yahoo"
    assert usa_row is None


def test_quarter_state_no_new_quarter_does_not_clear_existing_flag(tmp_path):
    app = _build_app(tmp_path)
    conn = sqlite3.connect(app.fundamentals_usa_db_path)
    conn.execute(
        """
        INSERT INTO rc_fundamental_quarter_state (
            ticker, market, primary_source, latest_db_period_end_date,
            detected_source_period_end_date, new_quarter_available,
            last_updated_at_utc, last_detection_run_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "MSFT",
            "usa",
            "sec_edgar",
            "2026-03-31",
            "2026-03-31",
            1,
            "2026-04-01T00:00:00Z",
            "old-run",
        ),
    )
    conn.commit()
    conn.close()

    result = app._update_quarter_state_from_yahoo_detection(
        ticker="MSFT",
        market="usa",
        yahoo_latest_period_end_date="2026-03-31",
        run_id="run-3",
        checked_at_utc="2026-05-06T10:00:00Z",
    )

    row = _fetch_state_row(app.fundamentals_usa_db_path, "MSFT", "usa")
    assert result["new_detected"] is False
    assert result["existing_flag_preserved"] is True
    assert row[3] == "2026-03-31"
    assert row[4] == "2026-03-31"
    assert row[5] == 1
    assert row[7] == "2026-04-01T00:00:00Z"
    assert row[8] == "old-run"


def test_quarter_state_existing_flag_preserved_when_yahoo_same(tmp_path):
    app = _build_app(tmp_path)
    conn = sqlite3.connect(app.fundamentals_usa_db_path)
    conn.execute(
        """
        INSERT INTO rc_fundamental_quarter_state (
            ticker, market, primary_source, latest_db_period_end_date,
            detected_source_period_end_date, new_quarter_available
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("NVDA", "usa", "sec_edgar", "2025-12-28", "2026-03-31", 1),
    )
    conn.commit()
    conn.close()

    result = app._update_quarter_state_from_yahoo_detection(
        ticker="NVDA",
        market="usa",
        yahoo_latest_period_end_date="2026-03-31",
        run_id="run-4",
        checked_at_utc="2026-05-06T10:00:00Z",
    )

    row = _fetch_state_row(app.fundamentals_usa_db_path, "NVDA", "usa")
    assert result["existing_flag_preserved"] is True
    assert row[4] == "2026-03-31"
    assert row[5] == 1


def test_quarter_state_newer_detection_supersedes_older_detected_date(tmp_path):
    app = _build_app(tmp_path)
    conn = sqlite3.connect(app.fundamentals_usa_db_path)
    conn.execute(
        """
        INSERT INTO rc_fundamental_quarter_state (
            ticker, market, primary_source, latest_db_period_end_date,
            detected_source_period_end_date, new_quarter_available
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AMAT", "usa", "sec_edgar", "2025-12-28", "2026-03-31", 1),
    )
    conn.commit()
    conn.close()

    result = app._update_quarter_state_from_yahoo_detection(
        ticker="AMAT",
        market="usa",
        yahoo_latest_period_end_date="2026-06-30",
        run_id="run-5",
        checked_at_utc="2026-05-06T10:00:00Z",
    )

    row = _fetch_state_row(app.fundamentals_usa_db_path, "AMAT", "usa")
    assert result["new_detected"] is True
    assert row[4] == "2026-06-30"
    assert row[5] == 1


def test_quarter_state_missing_row_is_inserted_with_null_latest_db_date(tmp_path):
    app = _build_app(tmp_path)

    result = app._update_quarter_state_from_yahoo_detection(
        ticker="QCOM",
        market="usa",
        yahoo_latest_period_end_date="2026-03-31",
        run_id="run-6",
        checked_at_utc="2026-05-06T10:00:00Z",
    )

    row = _fetch_state_row(app.fundamentals_usa_db_path, "QCOM", "usa")
    assert result["row_inserted"] is True
    assert row[3] is None
    assert row[4] == "2026-03-31"
    assert row[5] == 1


def test_quarter_state_preserves_newer_stored_detected_date(tmp_path):
    app = _build_app(tmp_path)
    conn = sqlite3.connect(app.fundamentals_usa_db_path)
    conn.execute(
        """
        INSERT INTO rc_fundamental_quarter_state (
            ticker, market, primary_source, latest_db_period_end_date,
            detected_source_period_end_date, new_quarter_available
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("INTC", "usa", "sec_edgar", "2025-12-28", "2026-06-30", 1),
    )
    conn.commit()
    conn.close()

    result = app._update_quarter_state_from_yahoo_detection(
        ticker="INTC",
        market="usa",
        yahoo_latest_period_end_date="2026-03-31",
        run_id="run-7",
        checked_at_utc="2026-05-06T10:00:00Z",
    )

    row = _fetch_state_row(app.fundamentals_usa_db_path, "INTC", "usa")
    assert result["new_detected"] is False
    assert result["existing_flag_preserved"] is True
    assert row[4] == "2026-06-30"
    assert row[5] == 1


class _FakePage:
    def __init__(self):
        self.overlay = []

    def update(self):
        return None


class _QuarterlessTicker:
    def __init__(self):
        self.quarterly_income_stmt = pd.DataFrame()
        self.history_calls = []

    def history(self, start=None, end=None):
        self.history_calls.append((start, end))
        index = pd.to_datetime(["2026-05-05"])
        return pd.DataFrame(
            {
                "Open": [10.0],
                "High": [11.0],
                "Low": [9.5],
                "Close": [10.5],
                "Volume": [100000],
            },
            index=index,
        )


def test_update_stock_data_counts_missing_quarter_detection(tmp_path, monkeypatch, capsys):
    price_db = tmp_path / "osakedata.db"
    conn = sqlite3.connect(price_db)
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
        ("AAA", "2026-05-01", 10.0, 11.0, 9.0, 10.5, 100000, "usa"),
    )
    conn.commit()
    conn.close()

    app = _build_app(tmp_path)
    app.osakedata_db_path = str(price_db)
    app.analysis_db_path = str(tmp_path / "analysis.db")
    app.loading_text = SimpleNamespace(value="", color=None)
    app.page = _FakePage()
    app.update_start_input = SimpleNamespace(value="")
    app.update_market_dropdown = SimpleNamespace(value="")
    app._calculate_and_save_divergences = lambda ticker, only_missing=True: (True, 0, "")

    monkeypatch.setattr(main.yf, "Ticker", lambda ticker: _QuarterlessTicker())
    monkeypatch.setattr(main, "validate_market", lambda market, db_path=None: True)
    monkeypatch.setattr(main.time, "sleep", lambda *args, **kwargs: None)

    import analysis.run_analysis

    monkeypatch.setattr(analysis.run_analysis, "run_candlestick_analysis", lambda *args, **kwargs: {})

    app.update_stock_data(None)

    output = capsys.readouterr().out
    row = _fetch_state_row(app.fundamentals_usa_db_path, "AAA", "usa")
    assert "SUMMARY quarter_state_checked=1" in output
    assert "SUMMARY quarter_state_detection_missing=1" in output
    assert row is not None
    assert row[4] is None
    assert row[5] == 0


def test_update_stock_data_fetches_only_forward_from_latest_db_day(tmp_path, monkeypatch):
    price_db = tmp_path / "osakedata.db"
    conn = sqlite3.connect(price_db)
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
    conn.executemany(
        """
        INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("AAA", "2026-04-15", 10.0, 11.0, 9.0, 10.5, 100000, "usa"),
            ("AAA", "2026-05-01", 10.2, 11.2, 9.2, 10.7, 120000, "usa"),
        ],
    )
    conn.commit()
    conn.close()

    app = _build_app(tmp_path)
    app.osakedata_db_path = str(price_db)
    app.analysis_db_path = str(tmp_path / "analysis.db")
    app.loading_text = SimpleNamespace(value="", color=None)
    app.page = _FakePage()
    app.update_start_input = SimpleNamespace(value="")
    app.update_market_dropdown = SimpleNamespace(value="")
    app._calculate_and_save_divergences = lambda ticker, only_missing=True: (True, 0, "")

    fake_ticker = _QuarterlessTicker()
    monkeypatch.setattr(main.yf, "Ticker", lambda ticker: fake_ticker)
    monkeypatch.setattr(main, "validate_market", lambda market, db_path=None: True)
    monkeypatch.setattr(main.time, "sleep", lambda *args, **kwargs: None)

    import analysis.run_analysis

    monkeypatch.setattr(analysis.run_analysis, "run_candlestick_analysis", lambda *args, **kwargs: {})

    app.update_stock_data(None)

    assert fake_ticker.history_calls
    assert fake_ticker.history_calls[0][0] == "2026-05-02"
