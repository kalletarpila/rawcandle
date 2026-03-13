import sqlite3

import pytest

from sector_update import refresh_single_ticker_metadata, update_sector_metadata
import sector_update


class _FakeTicker:
    def __init__(self, ticker, mapping):
        self.info = mapping.get(ticker, {})


@pytest.fixture
def fake_yfinance(monkeypatch):
    mapping = {}

    def fake_factory(ticker):
        return _FakeTicker(ticker, mapping)

    monkeypatch.setattr(sector_update.yf, "Ticker", fake_factory)
    return mapping


def test_update_sector_metadata_adds_columns_and_updates_values(tmp_path, fake_yfinance):
    db_path = tmp_path / "osakedata.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE osakedata (osake TEXT, market TEXT)")
        conn.executemany(
            "INSERT INTO osakedata (osake, market) VALUES (?, ?)",
            [("AAA", "usa"), ("BBB", "fin")],
        )

    fake_yfinance.update(
        {
            "AAA": {"sector": "Technology", "industry": "Software"},
            "BBB": {},
        }
    )

    logs = []
    summary = update_sector_metadata(
        str(db_path),
        market_filter=None,
        logger=logs.append,
        sleep_fn=lambda _: None,
        ticker_pause=0,
        batch_pause=0,
    )

    with sqlite3.connect(db_path) as conn:
        rows = {
            ticker: (market, sector, industry)
            for ticker, market, sector, industry in conn.execute(
                "SELECT ticker, market, sector, industry FROM ticker_meta ORDER BY ticker"
            ).fetchall()
        }
    assert rows["AAA"] == ("usa", "Technology", "Software")
    # Missing sector/industry are stored as "NULL"
    assert rows["BBB"] == ("fin", "NULL", "NULL")
    assert summary["updated"] == 2
    assert summary["missing"] == 1
    assert summary["tickers"] == 2
    assert summary["skipped"] == 0
    assert "AAA | Technology | Software" in logs
    assert "BBB | ei löydetty" in logs


def test_market_filter_limits_updated_tickers(tmp_path, fake_yfinance):
    db_path = tmp_path / "osakedata.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE osakedata (osake TEXT, market TEXT)")
        conn.executemany(
            "INSERT INTO osakedata (osake, market) VALUES (?, ?)",
            [("AAA", "usa"), ("BBB", "fin")],
        )

    fake_yfinance.update(
        {
            "AAA": {"sector": "Tech", "industry": "Hardware"},
            "BBB": {"sector": "Finance", "industry": "Banks"},
        }
    )

    update_sector_metadata(
        str(db_path),
        market_filter="usa",
        logger=lambda *_: None,
        sleep_fn=lambda *_: None,
        ticker_pause=0,
        batch_pause=0,
    )

    with sqlite3.connect(db_path) as conn:
        rows = {
            ticker: (market, sector, industry)
            for ticker, market, sector, industry in conn.execute(
                "SELECT ticker, market, sector, industry FROM ticker_meta ORDER BY ticker"
            ).fetchall()
        }
    assert rows["AAA"] == ("usa", "Tech", "Hardware")
    # BBB not updated because of market filter; stays absent/None
    assert rows.get("BBB") is None


def test_complete_metadata_skips_fetch_and_updates_summary(tmp_path, monkeypatch):
    db_path = tmp_path / "osakedata.db"
    fetched = []

    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE osakedata (osake TEXT, market TEXT)")
        conn.executemany(
            "INSERT INTO osakedata (osake, market) VALUES (?, ?)",
            [("AAA", "usa"), ("BBB", "usa"), ("CCC", "usa")],
        )
        conn.execute(
            """
            CREATE TABLE ticker_meta (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                sector TEXT,
                industry TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO ticker_meta (ticker, market, sector, industry) VALUES (?, ?, ?, ?)",
            [
                ("AAA", "usa", "Technology", "Software"),
                ("BBB", "usa", "", "Banks"),
            ],
        )

    monkeypatch.setattr(
        sector_update,
        "_fetch_sector_data",
        lambda ticker: fetched.append(ticker) or ("Finance", "Banks"),
    )

    summary = update_sector_metadata(
        str(db_path),
        market_filter="usa",
        logger=lambda *_: None,
        sleep_fn=lambda *_: None,
        ticker_pause=0,
        batch_pause=0,
    )

    assert fetched == ["BBB", "CCC"]
    assert summary["tickers"] == 3
    assert summary["updated"] == 2
    assert summary["missing"] == 0
    assert summary["errors"] == 0
    assert summary["skipped"] == 1


@pytest.mark.parametrize("sector_value", [None, "", "NULL", " null "])
def test_missing_sector_variants_trigger_fetch(tmp_path, monkeypatch, sector_value):
    db_path = tmp_path / "osakedata.db"
    fetched = []

    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE osakedata (osake TEXT, market TEXT)")
        conn.execute("INSERT INTO osakedata (osake, market) VALUES (?, ?)", ("AAA", "usa"))
        conn.execute(
            """
            CREATE TABLE ticker_meta (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                sector TEXT,
                industry TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO ticker_meta (ticker, market, sector, industry) VALUES (?, ?, ?, ?)",
            ("AAA", "usa", sector_value, "Software"),
        )

    monkeypatch.setattr(
        sector_update,
        "_fetch_sector_data",
        lambda ticker: fetched.append(ticker) or ("Technology", "Software"),
    )

    update_sector_metadata(
        str(db_path),
        market_filter="usa",
        logger=lambda *_: None,
        sleep_fn=lambda *_: None,
        ticker_pause=0,
        batch_pause=0,
    )

    assert fetched == ["AAA"]


@pytest.mark.parametrize("industry_value", [None, "", "NULL", " null "])
def test_missing_industry_variants_trigger_fetch(tmp_path, monkeypatch, industry_value):
    db_path = tmp_path / "osakedata.db"
    fetched = []

    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE osakedata (osake TEXT, market TEXT)")
        conn.execute("INSERT INTO osakedata (osake, market) VALUES (?, ?)", ("AAA", "usa"))
        conn.execute(
            """
            CREATE TABLE ticker_meta (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                sector TEXT,
                industry TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO ticker_meta (ticker, market, sector, industry) VALUES (?, ?, ?, ?)",
            ("AAA", "usa", "Technology", industry_value),
        )

    monkeypatch.setattr(
        sector_update,
        "_fetch_sector_data",
        lambda ticker: fetched.append(ticker) or ("Technology", "Software"),
    )

    update_sector_metadata(
        str(db_path),
        market_filter="usa",
        logger=lambda *_: None,
        sleep_fn=lambda *_: None,
        ticker_pause=0,
        batch_pause=0,
    )

    assert fetched == ["AAA"]


def test_missing_ticker_meta_row_triggers_fetch(tmp_path, monkeypatch):
    db_path = tmp_path / "osakedata.db"
    fetched = []

    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE osakedata (osake TEXT, market TEXT)")
        conn.execute("INSERT INTO osakedata (osake, market) VALUES (?, ?)", ("AAA", "usa"))

    monkeypatch.setattr(
        sector_update,
        "_fetch_sector_data",
        lambda ticker: fetched.append(ticker) or ("Technology", "Software"),
    )

    update_sector_metadata(
        str(db_path),
        market_filter="usa",
        logger=lambda *_: None,
        sleep_fn=lambda *_: None,
        ticker_pause=0,
        batch_pause=0,
    )

    assert fetched == ["AAA"]


def test_refresh_single_ticker_metadata_inserts_missing_row(tmp_path, monkeypatch):
    db_path = tmp_path / "osakedata.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE osakedata (osake TEXT, market TEXT)")

    monkeypatch.setattr(
        sector_update,
        "_fetch_sector_data",
        lambda ticker: ("Technology", "Software"),
    )

    changed = refresh_single_ticker_metadata(str(db_path), "AAA", market="usa")

    assert changed is True
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT ticker, market, sector, industry FROM ticker_meta WHERE ticker = ?",
            ("AAA",),
        ).fetchone()
    assert row == ("AAA", "usa", "Technology", "Software")


def test_refresh_single_ticker_metadata_updates_missing_sector(tmp_path, monkeypatch):
    db_path = tmp_path / "osakedata.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE osakedata (osake TEXT, market TEXT)")
        conn.execute(
            """
            CREATE TABLE ticker_meta (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                sector TEXT,
                industry TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO ticker_meta (ticker, market, sector, industry) VALUES (?, ?, ?, ?)",
            ("AAA", "usa", "", "Software"),
        )

    monkeypatch.setattr(
        sector_update,
        "_fetch_sector_data",
        lambda ticker: ("Technology", "Software"),
    )

    changed = refresh_single_ticker_metadata(str(db_path), "AAA", market="usa")

    assert changed is True
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT sector, industry FROM ticker_meta WHERE ticker = ?",
            ("AAA",),
        ).fetchone()
    assert row == ("Technology", "Software")


def test_refresh_single_ticker_metadata_updates_missing_industry(tmp_path, monkeypatch):
    db_path = tmp_path / "osakedata.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE osakedata (osake TEXT, market TEXT)")
        conn.execute(
            """
            CREATE TABLE ticker_meta (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                sector TEXT,
                industry TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO ticker_meta (ticker, market, sector, industry) VALUES (?, ?, ?, ?)",
            ("AAA", "usa", "Technology", "NULL"),
        )

    monkeypatch.setattr(
        sector_update,
        "_fetch_sector_data",
        lambda ticker: ("Technology", "Software"),
    )

    changed = refresh_single_ticker_metadata(str(db_path), "AAA", market="usa")

    assert changed is True
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT sector, industry FROM ticker_meta WHERE ticker = ?",
            ("AAA",),
        ).fetchone()
    assert row == ("Technology", "Software")


def test_refresh_single_ticker_metadata_updates_changed_values(tmp_path, monkeypatch):
    db_path = tmp_path / "osakedata.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE osakedata (osake TEXT, market TEXT)")
        conn.execute(
            """
            CREATE TABLE ticker_meta (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                sector TEXT,
                industry TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO ticker_meta (ticker, market, sector, industry) VALUES (?, ?, ?, ?)",
            ("AAA", "usa", "Technology", "Software"),
        )

    monkeypatch.setattr(
        sector_update,
        "_fetch_sector_data",
        lambda ticker: ("Financial Services", "Banks"),
    )

    changed = refresh_single_ticker_metadata(str(db_path), "AAA", market="usa")

    assert changed is True
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT sector, industry FROM ticker_meta WHERE ticker = ?",
            ("AAA",),
        ).fetchone()
    assert row == ("Financial Services", "Banks")


def test_refresh_single_ticker_metadata_skips_same_normalized_values(tmp_path, monkeypatch):
    db_path = tmp_path / "osakedata.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE osakedata (osake TEXT, market TEXT)")
        conn.execute(
            """
            CREATE TABLE ticker_meta (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                sector TEXT,
                industry TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO ticker_meta (ticker, market, sector, industry) VALUES (?, ?, ?, ?)",
            ("AAA", "usa", "Technology", "Software"),
        )

    monkeypatch.setattr(
        sector_update,
        "_fetch_sector_data",
        lambda ticker: ("  Technology  ", "Software"),
    )

    changed = refresh_single_ticker_metadata(str(db_path), "AAA", market="usa")

    assert changed is False
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT sector, industry FROM ticker_meta WHERE ticker = ?",
            ("AAA",),
        ).fetchone()
    assert row == ("Technology", "Software")


def test_refresh_single_ticker_metadata_no_useful_yahoo_data_keeps_existing_row(tmp_path, monkeypatch):
    db_path = tmp_path / "osakedata.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE osakedata (osake TEXT, market TEXT)")
        conn.execute(
            """
            CREATE TABLE ticker_meta (
                ticker TEXT PRIMARY KEY,
                market TEXT,
                sector TEXT,
                industry TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO ticker_meta (ticker, market, sector, industry) VALUES (?, ?, ?, ?)",
            ("AAA", "usa", "Technology", "Software"),
        )

    monkeypatch.setattr(sector_update, "_fetch_sector_data", lambda ticker: None)

    changed = refresh_single_ticker_metadata(str(db_path), "AAA", market="usa")

    assert changed is False
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT sector, industry FROM ticker_meta WHERE ticker = ?",
            ("AAA",),
        ).fetchone()
    assert row == ("Technology", "Software")


def test_refresh_single_ticker_metadata_no_useful_yahoo_data_does_not_create_row(tmp_path, monkeypatch):
    db_path = tmp_path / "osakedata.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE osakedata (osake TEXT, market TEXT)")

    monkeypatch.setattr(sector_update, "_fetch_sector_data", lambda ticker: None)

    changed = refresh_single_ticker_metadata(str(db_path), "AAA", market="usa")

    assert changed is False
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT ticker FROM ticker_meta WHERE ticker = ?",
            ("AAA",),
        ).fetchone()
    assert row is None


def test_throttling_calls_sleep_with_batch_pause(tmp_path, fake_yfinance):
    db_path = tmp_path / "osakedata.db"
    tickers = [("T1", "usa"), ("T2", "usa"), ("T3", "usa")]
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE osakedata (osake TEXT, market TEXT)")
        conn.executemany("INSERT INTO osakedata (osake, market) VALUES (?, ?)", tickers)

    fake_yfinance.update({t[0]: {"sector": "S", "industry": "I"} for t in tickers})

    sleeps = []

    update_sector_metadata(
        str(db_path),
        market_filter=None,
        logger=lambda *_: None,
        sleep_fn=lambda duration: sleeps.append(duration),
        ticker_pause=0.0,
        batch_pause=99.0,
        batch_size=2,
    )

    # Expect one per ticker + one batch pause after 2nd ticker
    assert sleeps == [0.0, 0.0, 99.0, 0.0]
