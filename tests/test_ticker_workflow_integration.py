"""Integraatiotesti ticker-listan lataamiselle ja käsittelylle."""

import os
import sqlite3
import pytest
from pathlib import Path


@pytest.fixture
def setup_test_environment(tmp_path):
    """Luo täydellinen testiympäristö: kannnat ja tickers.txt."""

    # Luo osakedata.db
    osake_db = tmp_path / "osakedata.db"
    conn = sqlite3.connect(str(osake_db))
    cursor = conn.cursor()

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

    # Lisää dataa: 3 oikeaa tickeriä + 2 puuttuvaa
    valid_tickers = ["AAPL", "MSFT", "GOOGL"]
    for ticker in valid_tickers:
        for day in range(15):
            date = f"2024-01-{day+1:02d}"
            # Luo downtrend-dataa
            close_price = 110.0 - (day * 0.8)
            cursor.execute(
                """
                INSERT INTO osakedata (osake, pvm, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker,
                    date,
                    close_price + 0.5,
                    close_price + 1.0,
                    close_price - 0.5,
                    close_price,
                    2000000,
                ),
            )

    conn.commit()
    conn.close()

    # Luo analysis.db
    analysis_db = tmp_path / "analysis.db"
    conn = sqlite3.connect(str(analysis_db))
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE analysis_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            pattern TEXT,
            signal_strength REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ticker, date, pattern)
        )
    """
    )

    # Lisää testidata analysis-kantaan vain valid tickereille
    for ticker in valid_tickers:
        cursor.execute(
            "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength) VALUES (?, ?, ?, ?)",
            (ticker, "2024-01-10", "Hammer", 0.85),
        )

    conn.commit()
    conn.close()

    # Luo tickers.txt (sisältää sekä validit että invalidit)
    tickers_file = tmp_path / "tickers.txt"
    content = """ AAPL  
 MSFT  
 GOOGL  
TSLA
NVDA
"""
    tickers_file.write_text(content)

    return {
        "osake_db": str(osake_db),
        "analysis_db": str(analysis_db),
        "tickers_file": str(tickers_file),
        "tmp_path": tmp_path,
        "valid_tickers": valid_tickers,
        "all_tickers": ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"],
    }


def test_full_workflow_candles_analysis(setup_test_environment):
    """Integraatiotesti: Koko workflow candles-sivulle."""
    from analysis.run_analysis import run_candlestick_analysis

    env = setup_test_environment

    # 1. Lataa tickerit tiedostosta (simuloi load_tickers_from_csv)
    with open(env["tickers_file"], "r", encoding="utf-8") as f:
        content = f.read().strip()

    tickers = [line.strip() for line in content.split("\n") if line.strip()]
    assert len(tickers) == 5

    # 2. Muodosta pilkulla eroteltu merkkijono (UI:ssa)
    tickers_str = ",".join(tickers)
    assert tickers_str == "AAPL,MSFT,GOOGL,TSLA,NVDA"

    # 3. Parsitaan takaisin listaksi (start_candles_analysis)
    if "," in tickers_str:
        ticker_list = [t.strip() for t in tickers_str.split(",") if t.strip()]
    else:
        ticker_list = None

    assert ticker_list is not None
    assert len(ticker_list) == 5

    # 4. Aja analyysi jokaiselle tickerille
    results = {}
    empty_tickers = []
    processed_tickers = []

    for ticker in ticker_list:
        res = run_candlestick_analysis(
            env["osake_db"],
            ticker,
            ["Hammer"],
            start_date=None,
            end_date=None,
        )

        processed_tickers.append(ticker)

        if not res:
            empty_tickers.append(ticker)

        for k, v in res.items():
            results[k] = results.get(k, []) + v

    # 5. Varmista että puuttuvat tickerit havaittiin
    # Huom: TSLA ja NVDA puuttuvat osakedata.db:stä, joten niille ei tuloksia
    # AAPL, MSFT, GOOGL on kannassa, mutta Hammer-kuvioita ei välttämättä löydy
    assert "TSLA" in empty_tickers
    assert "NVDA" in empty_tickers

    # 6. Varmista että kaikki tickerit käsiteltiin
    assert len(processed_tickers) == 5

    print(f"\n✓ Analysoi {len(ticker_list)} tickeriä")
    print(f"✓ Käsiteltyjä tickereitä: {len(processed_tickers)}")
    print(f"✓ Tyhjät tulokset: {len(empty_tickers)}")
    print(
        f"✓ Tickerit joilla ei dataa: {[t for t in empty_tickers if t in ['TSLA', 'NVDA']]}"
    )


def test_full_workflow_results_generation(setup_test_environment):
    """Integraatiotesti: Koko workflow results-sivulle."""

    env = setup_test_environment

    # 1. Lataa tickerit tiedostosta
    with open(env["tickers_file"], "r", encoding="utf-8") as f:
        content = f.read().strip()

    tickers = [line.strip() for line in content.split("\n") if line.strip()]

    # 2. Muodosta pilkulla eroteltu merkkijono
    tickers_str = ",".join(tickers)

    # 3. Parsitaan takaisin listaksi
    if "," in tickers_str:
        ticker_list = [t.strip() for t in tickers_str.split(",") if t.strip()]
    else:
        ticker_list = None

    # 4. Tarkista tickerit analysis.db:stä (simuloi results/view.py logiikka)
    missing_tickers = []

    with sqlite3.connect(env["analysis_db"]) as conn:
        for ticker in ticker_list:
            res = conn.execute(
                "SELECT 1 FROM analysis_findings WHERE UPPER(ticker) = ? LIMIT 1",
                (ticker.upper(),),
            ).fetchone()

            if res is None:
                missing_tickers.append(ticker)

    # 5. Varmista että puuttuvat tickerit havaittiin
    assert len(missing_tickers) == 2
    assert "TSLA" in missing_tickers
    assert "NVDA" in missing_tickers

    # 6. Simuloi ticker_filter käsittely (results/generate_results.py)
    ticker_filter = ticker_list
    ticker_filter_set = None

    if ticker_filter:
        if isinstance(ticker_filter, list):
            ticker_filter_set = {t.upper() for t in ticker_filter if t}
        else:
            ticker_filter_set = {ticker_filter.upper()}

    assert ticker_filter_set is not None
    assert len(ticker_filter_set) == 5

    # 7. Testaa suodatusta
    valid_count = 0
    for ticker in env["valid_tickers"]:
        if ticker.upper() in ticker_filter_set:
            valid_count += 1

    assert valid_count == 3  # AAPL, MSFT, GOOGL

    print(f"\n✓ Ladattu {len(ticker_list)} tickeriä")
    print(f"✓ Puuttuvia analysis.db:stä: {len(missing_tickers)}")
    print(f"✓ Ticker-filtteri set: {len(ticker_filter_set)} tickeriä")
    print(f"✓ Validit tickerit suodatuksessa: {valid_count}")


def test_edge_case_empty_tickers_file(tmp_path):
    """Testi: Tyhjä tickers.txt tiedosto."""

    tickers_file = tmp_path / "empty_tickers.txt"
    tickers_file.write_text("")

    with open(tickers_file, "r", encoding="utf-8") as f:
        content = f.read().strip()

    # Tyhjä tiedosto
    assert content == ""

    tickers = [line.strip() for line in content.split("\n") if line.strip()]
    assert len(tickers) == 0

    print("✓ Tyhjä tiedosto käsitelty oikein")


def test_edge_case_whitespace_only_lines(tmp_path):
    """Testi: Tiedosto jossa vain välilyöntejä."""

    tickers_file = tmp_path / "whitespace_tickers.txt"
    content = """   
    
  
 AAPL 
    
 MSFT 
  
"""
    tickers_file.write_text(content)

    with open(tickers_file, "r", encoding="utf-8") as f:
        content = f.read().strip()

    tickers = [line.strip() for line in content.split("\n") if line.strip()]

    assert len(tickers) == 2
    assert tickers == ["AAPL", "MSFT"]

    print("✓ Välilyönnit käsitelty oikein")


def test_edge_case_single_ticker(tmp_path):
    """Testi: Vain yksi ticker tiedostossa."""

    tickers_file = tmp_path / "single_ticker.txt"
    tickers_file.write_text("AAPL")

    with open(tickers_file, "r", encoding="utf-8") as f:
        content = f.read().strip()

    tickers = [line.strip() for line in content.split("\n") if line.strip()]

    assert len(tickers) == 1
    assert tickers == ["AAPL"]

    # Muodosta pilkulla eroteltu (ei pilkkuja yhdellä tickerillä)
    tickers_str = ",".join(tickers)
    assert tickers_str == "AAPL"

    print("✓ Yksittäinen ticker käsitelty oikein")
