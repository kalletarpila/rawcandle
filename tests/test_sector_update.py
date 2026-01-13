import sqlite3

import pytest

from sector_update import update_sector_metadata
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
        cols = {row[1] for row in conn.execute("PRAGMA table_info(osakedata)")}
        assert {"sector", "industry"}.issubset(cols)
        rows = {
            osake: (sector, industry)
            for osake, sector, industry in conn.execute(
                "SELECT osake, sector, industry FROM osakedata ORDER BY osake"
            ).fetchall()
        }
    assert rows["AAA"] == ("Technology", "Software")
    assert rows["BBB"] == ("ei löydetty", "ei löydetty")
    assert summary["updated"] == 2
    assert summary["missing"] == 1
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
            osake: (sector, industry)
            for osake, sector, industry in conn.execute(
                "SELECT osake, sector, industry FROM osakedata ORDER BY osake"
            ).fetchall()
        }
    assert rows["AAA"] == ("Tech", "Hardware")
    # BBB not updated because of market filter; stays NULL
    assert rows["BBB"] == (None, None)


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
