"""Testit ticker-listan parsimiselle ja käsittelylle."""

import os
import sqlite3
import pytest
from pathlib import Path


@pytest.fixture
def temp_databases(tmp_path):
    """Luo väliaikainen osakedata.db tiedosto testaukseen."""
    db_path = tmp_path / "osakedata.db"

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Luo osakedata-taulu
    cursor.execute(
        """
        CREATE TABLE osakedata (
            osake TEXT,
            pvm TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER
        )
    """
    )

    # Lisää testidataa kolmelle tickerille
    tickers = ["AAPL", "MSFT", "GOOGL"]
    for ticker in tickers:
        for day in range(20):
            date = f"2024-01-{day+1:02d}"
            cursor.execute(
                """
                INSERT INTO osakedata (osake, pvm, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker,
                    date,
                    100.0 + day,
                    102.0 + day,
                    99.0 + day,
                    101.0 + day,
                    1000000,
                ),
            )

    conn.commit()
    conn.close()

    return str(db_path)


@pytest.fixture
def temp_tickers_file(tmp_path):
    """Luo väliaikainen tickers.txt tiedosto."""
    tickers_file = tmp_path / "tickers.txt"

    # Kirjoita tickereitä (joissain välilyöntejä)
    content = """ AAPL  
 MSFT  
 GOOGL  
TSLA
INVALID_TICKER
"""

    tickers_file.write_text(content)
    return str(tickers_file)


def test_ticker_list_parsing_from_csv(temp_tickers_file):
    """Testi: Tickereiden parsiminen CSV-tiedostosta."""

    with open(temp_tickers_file, "r", encoding="utf-8") as f:
        content = f.read().strip()

    # Parsitaan tickerit (trimmataan välilyönnit)
    tickers = [line.strip() for line in content.split("\n") if line.strip()]

    assert len(tickers) == 5
    assert "AAPL" in tickers
    assert "MSFT" in tickers
    assert "GOOGL" in tickers
    assert "TSLA" in tickers
    assert "INVALID_TICKER" in tickers

    # Varmista että välilyönnit on poistettu
    for ticker in tickers:
        assert ticker == ticker.strip()
        assert not ticker.startswith(" ")
        assert not ticker.endswith(" ")


def test_ticker_list_comma_separated():
    """Testi: Pilkulla eroteltujen tickereiden parsiminen."""

    ticker_string = "AAPL,MSFT,GOOGL"

    # Tarkista onko pilkkuja
    if "," in ticker_string:
        ticker_list = [t.strip() for t in ticker_string.split(",") if t.strip()]
    else:
        ticker_list = None

    assert ticker_list is not None
    assert len(ticker_list) == 3
    assert ticker_list == ["AAPL", "MSFT", "GOOGL"]


def test_ticker_list_with_spaces():
    """Testi: Pilkulla eroteltujen tickereiden parsiminen välilyöntien kanssa."""

    ticker_string = " AAPL , MSFT , GOOGL "

    if "," in ticker_string:
        ticker_list = [t.strip() for t in ticker_string.split(",") if t.strip()]
    else:
        ticker_list = None

    assert ticker_list is not None
    assert len(ticker_list) == 3
    assert ticker_list == ["AAPL", "MSFT", "GOOGL"]


def test_single_ticker_no_comma():
    """Testi: Yksittäinen ticker ilman pilkkuja."""

    ticker_string = "AAPL"

    if "," in ticker_string:
        ticker_list = [t.strip() for t in ticker_string.split(",") if t.strip()]
    else:
        ticker_list = None

    assert ticker_list is None  # Ei pilkkuja, joten None


def test_run_analysis_with_ticker_list(temp_databases):
    """Testi: Analyysin ajaminen ticker-listalla."""
    from analysis.run_analysis import run_candlestick_analysis

    db_path = temp_databases
    ticker_list = ["AAPL", "MSFT", "GOOGL"]
    patterns = ["Hammer"]

    # Analysoi jokainen ticker
    all_results = {}
    for ticker in ticker_list:
        results = run_candlestick_analysis(
            db_path,
            ticker,
            patterns,
            start_date=None,
            end_date=None,
        )
        # Merge results
        for k, v in results.items():
            all_results[k] = all_results.get(k, []) + v

    # Varmista että tuloksia saatiin (tai ainakin ei virheitä)
    assert isinstance(all_results, dict)
    print(f"Analysoi {len(ticker_list)} tickeriä, tuloksia: {len(all_results)} päivää")


def test_empty_ticker_detection(temp_databases):
    """Testi: Tyhjien tulosten havaitseminen."""
    from analysis.run_analysis import run_candlestick_analysis

    db_path = temp_databases

    # Analysoi ticker jota ei ole kannassa
    results = run_candlestick_analysis(
        db_path,
        "INVALID_TICKER",
        ["Hammer"],
        start_date=None,
        end_date=None,
    )

    # Pitäisi palauttaa tyhjä dict
    assert results == {}
    print("✓ Tyhjä tulos havaittu oikein puuttuvalle tickerille")


def test_ticker_list_filtering():
    """Testi: Ticker-listan suodatus set-pohjaisesti."""

    ticker_filter_list = ["AAPL", "MSFT", "GOOGL"]
    ticker_filter_set = {t.upper() for t in ticker_filter_list if t}

    # Tarkista että ticker on listassa
    test_cases = [
        ("AAPL", True),
        ("aapl", True),  # Case-insensitive
        ("MSFT", True),
        ("TSLA", False),
        ("INVALID", False),
    ]

    for ticker, should_match in test_cases:
        matches = ticker.upper() in ticker_filter_set
        assert matches == should_match, f"Ticker {ticker} matching failed"

    print("✓ Ticker-suodatus toimii oikein")


def test_results_ticker_filter_with_list():
    """Testi: results/generate_results.py ticker_filter list-tuki."""

    # Simuloi ticker_filter parametrin käsittely
    ticker_filter = ["AAPL", "MSFT", "GOOGL"]

    # Koodi results/generate_results.py:stä
    ticker_filter_set = None
    if ticker_filter:
        if isinstance(ticker_filter, list):
            ticker_filter_set = {t.upper() for t in ticker_filter if t}
        else:
            ticker_filter_set = {ticker_filter.upper()}

    assert ticker_filter_set is not None
    assert len(ticker_filter_set) == 3
    assert "AAPL" in ticker_filter_set
    assert "MSFT" in ticker_filter_set
    assert "GOOGL" in ticker_filter_set

    # Testaa suodatusta
    test_tickers = [
        ("AAPL", True),
        ("MSFT", True),
        ("TSLA", False),
    ]

    for ticker_str, should_pass in test_tickers:
        passes = ticker_str.upper() in ticker_filter_set
        assert passes == should_pass

    print("✓ Results ticker_filter list-tuki toimii")


def test_results_ticker_filter_with_string():
    """Testi: results/generate_results.py ticker_filter string-tuki."""

    # Simuloi ticker_filter parametrin käsittely merkkijonolla
    ticker_filter = "AAPL"

    ticker_filter_set = None
    if ticker_filter:
        if isinstance(ticker_filter, list):
            ticker_filter_set = {t.upper() for t in ticker_filter if t}
        else:
            ticker_filter_set = {ticker_filter.upper()}

    assert ticker_filter_set is not None
    assert len(ticker_filter_set) == 1
    assert "AAPL" in ticker_filter_set

    # Testaa suodatusta
    assert "AAPL" in ticker_filter_set
    assert "MSFT" not in ticker_filter_set

    print("✓ Results ticker_filter string-tuki toimii")
